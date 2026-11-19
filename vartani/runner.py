"""Background runs checkpoint completed questions so cancelled runs can resume."""
from __future__ import annotations
import json
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .backends import BackendError, make_backend
from .config import DATA_DIR, WORKERS
from .credentials import write_json
from .perturb import build_conditions, count_calls
from .security import credential_values, redact_message, redact_secrets

RUNS = DATA_DIR / "runs"
_jobs: dict[str, dict] = {}
_cancel: dict[str, threading.Event] = {}
_lock = threading.RLock()
_hf_model_lock = threading.Lock()


def _dir(rid: str):
    return RUNS / rid


def _save_meta(meta: dict):
    write_json(_dir(meta["id"]) / "meta.json", redact_secrets(meta, credential_values(meta)))


def _read_meta(path) -> dict:
    """Remove embedded credentials and their echoes from old run files."""
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("Invalid run metadata")
    clean = redact_secrets(raw, credential_values(raw))
    if "id" in raw:
        clean["id"] = raw["id"]
    if clean != raw:
        try:
            write_json(path, clean)
        except OSError:
            # A read-only old profile may still be viewed without exposing its secrets.
            pass
    return clean


def _checkpoint(rid: str, *, repair: bool = False) -> list[dict]:
    path = _dir(rid) / "rows.jsonl"
    if not path.exists():
        return []
    with path.open("r+b" if repair else "rb") as f:
        data = f.read()
        # A crash mid-write can leave a partial final line. A line ending is
        # the commit marker, so ignore that tail and remove it before resuming.
        end = data.rfind(b"\n") + 1
        if repair and end != len(data):
            f.truncate(end)
    return [json.loads(line) for line in data[:end].splitlines() if line.strip()]


def load_rows(rid: str) -> list[dict]:
    with _lock:
        return [redact_secrets(row, credential_values(row)) for row in _checkpoint(rid)]


def load_items(rid: str) -> list[dict]:
    p = _dir(rid) / "items.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def migrate_run_metadata():
    with _lock:
        for path in RUNS.glob("*/meta.json"):
            try:
                _read_meta(path)
            except (OSError, ValueError, TypeError):
                # Unreadable legacy runs must not prevent Vartani from starting.
                continue


def list_runs() -> list[dict]:
    with _lock:
        out = [get_meta(path.parent.name) for path in RUNS.glob("*/meta.json")]
        return sorted((m for m in out if m), key=lambda m: m["created"], reverse=True)


def get_meta(rid: str) -> dict | None:
    with _lock:
        if rid in _jobs:
            return dict(_jobs[rid])
        p = _dir(rid) / "meta.json"
        if not p.exists():
            return None
        m = _read_meta(p)
        if m["status"] in ("running", "queued"):
            m["status"] = "interrupted"
            m["done_items"] = len({r["qid"] for r in _checkpoint(rid)})
        return m


def _start_locked(rid: str, meta: dict, model: dict) -> dict:
    _save_meta(meta)
    stop = threading.Event()
    _jobs[rid], _cancel[rid] = meta, stop
    threading.Thread(target=_execute, args=(rid, meta, model, stop), daemon=True).start()
    return dict(meta)


def create_run(name: str, items: list[dict], model: dict, cfg: dict) -> dict:
    prepared = [build_conditions(it, cfg) for it in items]
    if len({p["qid"] for p in prepared}) != len(prepared):
        raise ValueError("Question IDs must be unique.")
    rid = uuid.uuid4().hex[:10]
    secrets = credential_values(model) | credential_values(cfg)
    meta = redact_secrets({"name": name, "model": model,
            "model_label": model.get("label") or model.get("model") or model.get("hf_id"), "config": cfg}, secrets)
    meta.update(id=rid, created=time.time(), status="queued", n_items=len(items),
                total_calls=count_calls(prepared), done_calls=0, done_items=0, error=None, kind="run")
    write_json(_dir(rid) / "items.json", prepared)
    with _lock:
        return _start_locked(rid, meta, model)


def resume_run(rid: str, model: dict) -> dict:
    with _lock:
        meta = get_meta(rid)
        if not meta or meta["status"] not in ("interrupted", "failed", "cancelled"):
            raise ValueError("This run cannot be resumed.")
        meta.update(status="queued", error=None)
        meta.pop("finished", None)
        return _start_locked(rid, meta, model)


def cancel_run(rid: str):
    with _lock:
        if rid in _cancel:
            _cancel[rid].set()


def delete_run(rid: str):
    with _lock:
        if rid in _cancel:
            _cancel[rid].set()
            raise ValueError("Stop the run and wait for it to finish before deleting it.")
        _jobs.pop(rid, None)
        shutil.rmtree(_dir(rid), ignore_errors=True)


def _execute(rid: str, meta: dict, model: dict, stop: threading.Event):
    hf_locked = False
    status, error = "done", None
    try:
        with _lock:
            prepared = load_items(rid)
            done = {r["qid"] for r in _checkpoint(rid, repair=True)}
            todo = [p for p in prepared if p["qid"] not in done]
            meta.update(status="running", done_items=len(done),
                        done_calls=count_calls([p for p in prepared if p["qid"] in done]))
            _save_meta(meta)
        if model.get("kind") == "hf" and not stop.is_set() and todo:
            _hf_model_lock.acquire()
            hf_locked = True
        if stop.is_set() or not todo:
            return
        backend = make_backend(model)

        with (_dir(rid) / "rows.jsonl").open("a", encoding="utf-8", newline="\n") as out:
            def work(rec: dict):
                answers, margins = {}, {}
                canon = rec["meta"]["canon"]
                for name in rec["conditions"]:
                    if canon[name] != name:
                        continue
                    if stop.is_set():
                        return
                    a = backend.answer(rec["conditions"][name])
                    answers[name], margins[name] = a.letter, a.margin
                    with _lock:
                        meta["done_calls"] += 1
                for name, c in canon.items():
                    answers.setdefault(name, answers[c])
                    margins.setdefault(name, margins[c])
                row = {"qid": rec["qid"], "lang": rec["lang"], "gold": rec["gold"], "answers": answers,
                       "margins": margins, "meta": {k: rec["meta"][k] for k in ("identical_to_roman", "bridge_converged", "persona") if k in rec["meta"]}}
                with _lock:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    meta["done_items"] += 1

            def guarded(rec):
                try:
                    work(rec)
                except Exception:
                    stop.set()
                    raise

            workers = WORKERS if getattr(backend, "parallel", False) else 1
            with ThreadPoolExecutor(workers) as ex:
                list(ex.map(guarded, todo))
    except BackendError as e:
        status, error = "failed", redact_message(str(e), model)
    except Exception as e:  # Keep the failure visible, even if it occurs before evaluation.
        status, error = "failed", redact_message(f"{type(e).__name__}: {e}", model)
    finally:
        if hf_locked:
            _hf_model_lock.release()
        with _lock:
            if stop.is_set() and status == "done":
                status = "cancelled"
            meta.update(status=status, error=error, finished=time.time())
            try:
                _save_meta(meta)
            except OSError:
                # Retain the failure in memory if the profile cannot be written.
                meta.update(status="failed", error="Could not save run progress. Check disk space and folder permissions.")
            else:
                _jobs.pop(rid, None)
            finally:
                _cancel.pop(rid, None)
