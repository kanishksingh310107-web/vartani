"""HTTP API + static web UI."""
from __future__ import annotations
import json
from fractions import Fraction
import re
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, datasets, evidence as ev, export, guided, models, runner, suites
from .analysis import report
from .backends import BackendError, PROBE, make_backend, torch_status
from .config import DATA_DIR, WEB_DIR
from .perturb import RULES, build_conditions, count_calls, default_config
from .scripts import LANG_INFO, bridge, script_of
from .speech import SpeechError, transcribe

app = FastAPI(title="Vartani", version=__version__)


@app.post("/api/speech/transcribe")
def speech_transcribe(file: UploadFile = File(...), lang: str = Form(...), model_size: str = Form("base")):
    """Transcribe a short question locally; uploaded audio is always discarded."""
    import tempfile
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".mpeg", ".mpga"}:
        raise HTTPException(400, "Use WAV, MP3, M4A, MP4, WebM, OGG, or FLAC audio.")
    max_bytes = 25 * 1024 * 1024
    size = 0
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, "Audio file is too large. Keep it under 25 MB.")
                tmp.write(chunk)
        return transcribe(tmp_path, lang, model_size)
    except SpeechError as e:
        raise HTTPException(503, str(e)) from e
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        file.file.close()


@app.get("/api/health")
def health():
    return {"version": __version__, "torch": torch_status(), "langs": {k: v["name"] for k, v in LANG_INFO.items()},
            "rules": {k: v[0] for k, v in RULES.items()}, "defaults": default_config(),
            "paper_data": bool(list((DATA_DIR / "paper").glob("*.jsonl")))}


# ---- data --------------------------------------------------------------------------------------------------
@app.get("/api/samples")
def samples():
    return datasets.starter_sets()


@app.get("/api/samples/{sid}")
def sample(sid: str):
    try:
        return datasets.load_starter(sid)
    except FileNotFoundError:
        raise HTTPException(404, "no such starter set")


@app.post("/api/datasets/parse")
def parse(body: dict = Body(...)):
    try:
        return datasets.parse_dataset(body.get("text", ""), body.get("filename", ""), body.get("lang"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not read this file: {e}")


@app.post("/api/plan")
def plan(body: dict = Body(...)):
    items, cfg = body["items"], body.get("config") or {}
    prepared = [build_conditions(i, cfg) for i in items]
    return {"calls": count_calls(prepared), "items": len(items), "preview": prepared[0] if prepared else None}


@app.get("/api/suites")
def get_suites():
    return suites.list_suites()


@app.post("/api/suites")
def put_suite(body: dict = Body(...)):
    try:
        return suites.save_suite(body.get("name", ""), body.get("items", []), body.get("config") or {})
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/suites/{sid}")
def read_suite(sid: str):
    suite = suites.get_suite(sid)
    if not suite:
        raise HTTPException(404, "no such saved benchmark")
    return suite


@app.delete("/api/suites/{sid}")
def remove_suite(sid: str):
    if not suites.delete_suite(sid):
        raise HTTPException(404, "no such saved benchmark")
    return {"ok": True}


@app.post("/api/bridge")
def bridge_text(body: dict = Body(...)):
    text, lang = body.get("text"), body.get("lang")
    if not isinstance(text, str) or len(text) > 20000 or not isinstance(lang, str) or lang not in LANG_INFO:
        raise HTTPException(400, "Choose Hindi, Bengali, or Tamil and enter up to 20,000 characters.")
    return {"native": bridge(text, lang), "script": script_of(text)}


def _guided_plan(body):
    try:
        return guided.prepare(body.get("items"), body.get("limit", 20))
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        raise HTTPException(400, f"Could not prepare the comparison. {error}") from error


@app.post("/api/guided/plan")
def guided_plan(body: dict = Body(...)):
    return _guided_plan(body)[1]


@app.post("/api/guided/fix-preview")
def guided_fix_preview(body: dict = Body(...)):
    try:
        return guided.conversion_preview(body.get("items"))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/guided/start")
def guided_start(body: dict = Body(...)):
    selected, plan = _guided_plan(body)
    key = body.get("groq_key")
    if key is not None:
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 512 or "\r" in key or "\n" in key:
            raise HTTPException(400, "Enter a valid Groq API key.")
        import httpx
        try:
            response = httpx.get(guided.GROQ_URL + "/models",
                                 headers={"Authorization": "Bearer " + key.strip()}, timeout=12)
            if response.status_code in (401, 403):
                raise HTTPException(400, "Groq rejected this API key. Check it and try again.")
            response.raise_for_status()
            available = {m["id"] for m in response.json()["data"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(502, "Could not check Groq models. Check your internet connection and try again.") from error
        configs = [{"kind": "openai", "base_url": guided.GROQ_URL, "model": model,
                    "label": label, "api_key": key.strip()}
                   for model, label in guided.GROQ_MODELS.items() if model in available]
        if len(configs) < 2:
            raise HTTPException(400, "This Groq account does not have access to both starter models. Try saved models instead.")
    else:
        ids = body.get("model_ids")
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or not 2 <= len(set(ids)) == len(ids) <= 3:
            raise HTTPException(400, "Choose two or three saved models.")
        try:
            configs = [models.get_model(i) for i in ids]
        except KeyError as error:
            raise HTTPException(400, "A saved model was removed. Reload and select models again.") from error
        identities = {(m.get("kind"), m.get("base_url", "").rstrip("/"), m.get("model"), m.get("hf_id"))
                      for m in configs}
        if len(identities) != len(configs):
            raise HTTPException(400, "Choose different models. Two of the selected connections point to the same model.")
    batch = uuid.uuid4().hex
    cfg = {**guided.CONFIG, "guided_batch": batch, "guided_size": len(configs), "guided_plan": plan}
    runs = []
    try:
        for model in configs:
            label = model.get("label") or model.get("model") or model.get("hf_id")
            runs.append(runner.create_run(f"Guided comparison · {label}", selected, model, cfg))
    except (ValueError, OSError) as error:
        for run in runs:
            runner.cancel_run(run["id"])
        raise HTTPException(500, "Could not start the full comparison. Check local storage and try again.") from error
    return {"ids": [r["id"] for r in runs]}


@app.get("/api/guided/results")
def guided_results(ids: str):
    run_ids = ids.split(",")
    if not 2 <= len(set(run_ids)) == len(run_ids) <= 3 or any(
            not re.fullmatch(r"[a-f0-9]{10}", rid) for rid in run_ids):
        raise HTTPException(400, "Choose a valid guided comparison.")
    metas = [runner.get_meta(rid) for rid in run_ids]
    if any(m is None for m in metas):
        raise HTTPException(404, "A run is missing. Start a new comparison.")
    batches = {m["config"].get("guided_batch") for m in metas}
    if None in batches or len(batches) != 1 or metas[0]["config"].get("guided_size") != len(metas):
        raise HTTPException(400, "These runs are not from the same guided comparison.")
    entries = []
    for rid, meta in zip(run_ids, metas):
        status = meta["status"]
        scores = guided.evaluate(runner.load_items(rid), runner.load_rows(rid)) if status == "done" else None
        # Backend errors can contain provider response text. Keep setup keys out of this public summary.
        detail = "Open the detailed report for the connection error." if status == "failed" else None
        entries.append({"id": rid, "label": meta["model_label"], "status": status,
                        "done": meta["done_items"], "total": meta["n_items"], "scores": scores, "detail": detail})
    complete = [e for e in entries if e["scores"]]
    finished = all(e["status"] not in ("queued", "running") for e in entries)

    def leaders(metric):
        if len(complete) < 2 or not finished:
            return []
        best = max(Fraction(e["scores"][metric]) for e in complete)
        return [e["id"] for e in complete if Fraction(e["scores"][metric]) == best]

    raw_leaders = leaders("raw_rank")
    converted_leaders = leaders("converted_rank")
    conversion_beats_raw = bool(raw_leaders and
        max(Fraction(e["scores"]["converted_rank"]) for e in complete) >
        max(Fraction(e["scores"]["raw_rank"]) for e in complete))
    return {"entries": entries, "finished": finished, "plan": metas[0]["config"]["guided_plan"],
            "raw_leaders": raw_leaders, "converted_leaders": converted_leaders,
            "conversion_beats_raw": conversion_beats_raw}


# ---- models ------------------------------------------------------------------------------------------------
@app.get("/api/models")
def get_models():
    return {"saved": models.list_models(), "presets": models.PRESETS}


@app.post("/api/models")
def put_model(body: dict = Body(...)):
    m = models.save_model(body)
    return models.redact_secrets(m)


@app.delete("/api/models/{mid}")
def del_model(mid: str):
    models.delete_model(mid)
    return {"ok": True}


@app.post("/api/models/test")
def test_model(body: dict = Body(...)):
    cfg = models.get_model(body["id"]) if body.get("id") else body
    if body.get("id") and not cfg.get("api_key") and body.get("api_key"):
        cfg = {**cfg, "api_key": body["api_key"]}
    try:
        a = make_backend(cfg).answer(PROBE)
    except BackendError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": a.letter is not None, "letter": a.letter, "correct": a.letter == "B", "ms": a.ms,
            "margin_available": a.margin is not None,
            "error": None if a.letter else f"The model replied {a.raw!r}, which has no A–D letter."}


# ---- runs --------------------------------------------------------------------------------------------------
@app.post("/api/runs")
def start_run(body: dict = Body(...)):
    try:
        model = models.get_model(body["model_id"])
    except KeyError:
        raise HTTPException(400, "Choose a model first.")
    if not body.get("items"):
        raise HTTPException(400, "Add some test items first.")
    return runner.create_run(body.get("name") or "Untitled run", body["items"], model, body.get("config") or {})


@app.get("/api/runs")
def runs():
    return runner.list_runs()


@app.get("/api/runs/{rid}")
def run_status(rid: str):
    m = runner.get_meta(rid)
    if not m:
        raise HTTPException(404, "no such run")
    return m


@app.get("/api/runs/{rid}/report")
def run_report(rid: str):
    m = runner.get_meta(rid)
    if not m:
        raise HTTPException(404, "no such run")
    return {"meta": m, "report": report(runner.load_rows(rid))}


@app.get("/api/runs/{rid}/fix-preview")
def run_fix_preview(rid: str):
    if not re.fullmatch(r"[a-f0-9]{10}", rid):
        raise HTTPException(404, "Run not found.")
    meta = runner.get_meta(rid)
    if not meta or meta["status"] != "done":
        raise HTTPException(404, "Choose a completed run.")
    items = []
    for prepared in runner.load_items(rid):
        conditions = prepared["conditions"]
        items.append({"id": prepared["qid"], "lang": prepared["lang"], "gold": prepared.get("gold"),
                      "native": conditions.get("native"),
                      "roman": conditions.get("roman") if prepared["meta"].get("roman_source") == "provided" else None})
    if not items:
        raise HTTPException(400, "This report has no saved questions. Upload your original dataset to review it.")
    if any(not (item["native"] or item["roman"]) for item in items):
        raise HTTPException(400, "This run did not keep the original native input. Upload your original dataset to review it.")
    return guided_fix_preview({"items": items})


@app.get("/api/runs/{rid}/items")
def run_items(rid: str):
    rows = {r["qid"]: r for r in runner.load_rows(rid)}
    prepared = {p["qid"]: p for p in runner.load_items(rid)}
    out = []
    for qid, r in rows.items():
        p = prepared.get(qid)
        out.append({**r, "conditions": p["conditions"] if p else None, "persona": (p or {}).get("meta", {}).get("persona", {})})
    return sorted(out, key=lambda x: x["qid"])


@app.post("/api/runs/{rid}/cancel")
def run_cancel(rid: str):
    runner.cancel_run(rid)
    return {"ok": True}


@app.post("/api/runs/{rid}/resume")
def run_resume(rid: str, body: dict = Body(...)):
    meta = runner.get_meta(rid)
    if meta and meta["config"].get("guided_batch"):
        raise HTTPException(400, "Start a new comparison to keep each model's results comparable.")
    try:
        return runner.resume_run(rid, models.get_model(body["model_id"]))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.delete("/api/runs/{rid}")
def run_delete(rid: str):
    runner.delete_run(rid)
    return {"ok": True}


@app.get("/api/runs/{rid}/export.{fmt}")
def run_export(rid: str, fmt: str):
    m = runner.get_meta(rid)
    if not m:
        raise HTTPException(404, "no such run")
    rows = runner.load_rows(rid)
    if fmt == "csv":
        return PlainTextResponse(export.rows_csv(rows), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=vartani-{rid}.csv"})
    if fmt == "jsonl":
        return PlainTextResponse(export.rows_jsonl(rows), media_type="application/x-ndjson", headers={"Content-Disposition": f"attachment; filename=vartani-{rid}.jsonl"})
    if fmt == "html":
        return HTMLResponse(export.report_html(m, report(rows)), headers={"Content-Disposition": f"attachment; filename=vartani-report-{rid}.html"})
    raise HTTPException(404, "unknown format")


@app.post("/api/import")
async def import_runs(files: List[UploadFile] = File(...)):
    """Load Colab notebook result files (*.jsonl) as a viewable run (answers only; no passage text)."""
    rows = []
    for f in files:
        rows += ev.import_colab((await f.read()).decode("utf-8"))
    if not rows:
        raise HTTPException(400, "No rows found in the uploaded files.")
    rid = uuid.uuid4().hex[:10]
    d = runner.RUNS / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "rows.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    meta = {"id": rid, "name": "Imported: " + ", ".join(f.filename for f in files)[:60], "created": time.time(), "status": "done",
            "model_label": "imported results", "config": {}, "n_items": len(rows), "total_calls": 0, "done_calls": 0,
            "done_items": len(rows), "error": None, "kind": "import"}
    runner._save_meta(meta)
    return meta


# ---- evidence ----------------------------------------------------------------------------------------------
@app.get("/api/evidence")
def evidence():
    return ev.evidence()


# ---- web ---------------------------------------------------------------------------------------------------
if WEB_DIR.is_dir() and (WEB_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = WEB_DIR / path
        return FileResponse(f if path and f.is_file() else WEB_DIR / "index.html")
