"""Background test runs. Every finished item is appended to rows.jsonl immediately, so a crash or Ctrl+C loses
at most the item in flight and a run can be resumed (the same idea as the Colab notebook's resumable loop)."""
from __future__ import annotations
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from .backends import BackendError, make_backend
from .config import DATA_DIR, WORKERS
from .perturb import build_conditions, count_calls

RUNS = DATA_DIR / "runs"
_jobs: Dict[str, dict] = {}
_cancel: Dict[str, threading.Event] = {}
_lock = threading.Lock()
_hf_model_lock = threading.Lock()


def _dir(rid: str):
    return RUNS / rid


def _save_meta(meta: dict):
    (_dir(meta["id"]) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def load_rows(rid: str) -> List[dict]:
    p = _dir(rid) / "rows.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_items(rid: str) -> List[dict]:
    p = _dir(rid) / "items.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def list_runs() -> List[dict]:
    RUNS.mkdir(parents=True, exist_ok=True)
    out = []
    for p in RUNS.glob("*/meta.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        if m["status"] in ("running", "queued") and m["id"] not in _jobs:
            m["status"] = "interrupted"
        if m["id"] in _jobs:
            m = _jobs[m["id"]]
        out.append(m)
    return sorted(out, key=lambda m: m["created"], reverse=True)


def get_meta(rid: str) -> Optional[dict]:
    if rid in _jobs:
        return _jobs[rid]
    p = _dir(rid) / "meta.json"
    if not p.exists():
        return None
    m = json.loads(p.read_text(encoding="utf-8"))
    if m["status"] in ("running", "queued"):
        m["status"] = "interrupted"
    return m


def create_run(name: str, items: List[dict], model: dict, cfg: dict) -> dict:
    prepared = [build_conditions(it, cfg) for it in items]
    rid = uuid.uuid4().hex[:10]
    _dir(rid).mkdir(parents=True, exist_ok=True)
    (_dir(rid) / "items.json").write_text(json.dumps(prepared, ensure_ascii=False), encoding="utf-8")
    meta = {"id": rid, "name": name, "created": time.time(), "status": "queued", "model": {k: v for k, v in model.items() if k != "api_key"},
            "model_label": model.get("label") or model.get("model") or model.get("hf_id"), "config": cfg, "n_items": len(items),
            "total_calls": count_calls(prepared), "done_calls": 0, "done_items": 0, "error": None, "kind": "run"}
    _save_meta(meta)
    _jobs[rid] = meta
    # Register cancellation before starting the worker. Otherwise an immediate
    # Stop click can arrive in the tiny window before _execute creates its Event.
    _cancel[rid] = threading.Event()
    threading.Thread(target=_execute, args=(rid, model), daemon=True).start()
    return meta


def resume_run(rid: str, model: dict) -> dict:
    meta = get_meta(rid)
    if not meta or meta["status"] not in ("interrupted", "failed", "cancelled"):
        raise ValueError("this run cannot be resumed")
    meta["status"], meta["error"] = "queued", None
    _jobs[rid] = meta
    _cancel[rid] = threading.Event()
    threading.Thread(target=_execute, args=(rid, model), daemon=True).start()
    return meta


def cancel_run(rid: str):
    if rid in _cancel:
        _cancel[rid].set()


def delete_run(rid: str):
    import shutil
    cancel_run(rid)
    _jobs.pop(rid, None)
    shutil.rmtree(_dir(rid), ignore_errors=True)


def _execute(rid: str, model: dict):
    meta = _jobs[rid]
    stop = _cancel.setdefault(rid, threading.Event())
    prepared = load_items(rid)
    done = {r["qid"] for r in load_rows(rid)}
    todo = [p for p in prepared if p["qid"] not in done]
    meta.update(status="running", done_items=len(done),
                done_calls=count_calls([p for p in prepared if p["qid"] in done]))
    _save_meta(meta)
    hf_locked = False
    try:
        # A stop can arrive while the worker is still queued. Do not start a
        # potentially large model load/download after the user has stopped it.
        if stop.is_set():
            meta["status"] = "cancelled"
            return
        # Avoid loading multiple local Hugging Face checkpoints at once during a
        # multi-model comparison. Hosted HTTP models still use the normal parallel path.
        if model.get("kind") == "hf":
            _hf_model_lock.acquire()
            hf_locked = True
        backend = make_backend(model)
        out = open(_dir(rid) / "rows.jsonl", "a", encoding="utf-8")

        def work(rec: dict):
            if stop.is_set():
                return
            answers, margins, texts = {}, {}, {}
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
            for name, c in canon.items():                       # identical texts reuse the answer
                answers.setdefault(name, answers[c]); margins.setdefault(name, margins[c])
            row = {"qid": rec["qid"], "lang": rec["lang"], "gold": rec["gold"], "answers": answers,
                   "margins": margins, "meta": {k: rec["meta"][k] for k in ("identical_to_roman", "bridge_converged", "persona") if k in rec["meta"]}}
            with _lock:
                out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
                meta["done_items"] += 1

        workers = WORKERS if getattr(backend, "parallel", False) else 1
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(work, todo))
        meta["status"] = "cancelled" if stop.is_set() else "done"
    except BackendError as e:
        meta.update(status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001  - surface anything to the UI instead of dying silently
        meta.update(status="failed", error=f"{type(e).__name__}: {e}")
    finally:
        try:
            out.close()
        except Exception:
            pass
        if hf_locked:
            _hf_model_lock.release()
        meta["finished"] = time.time()
        _save_meta(meta)
