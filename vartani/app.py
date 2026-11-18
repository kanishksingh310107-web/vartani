"""HTTP API + static web UI."""
from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, datasets, evidence as ev, export, models, optional_setup, runner, suites
from .security import redact_message
from .analysis import report
from .backends import BackendError, PROBE, make_backend, torch_status
from .config import BUNDLE_DATA_DIR, DATA_DIR, WEB_DIR
from .perturb import RULES, build_conditions, count_calls, default_config
from .scripts import LANG_INFO, bridge, script_of
from .speech import SpeechError, transcribe

app = FastAPI(title="Vartani", version=__version__)
optional_setup.activate_installed()


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
            "paper_data": bool(list((BUNDLE_DATA_DIR / "paper").glob("*.jsonl")))}


@app.get("/api/setup/{component}")
def optional_status(component: str):
    if component not in optional_setup.COMPONENTS:
        raise HTTPException(404, "Unknown optional component")
    return optional_setup.status(component)


@app.post("/api/setup/{component}")
def optional_install(component: str, request: Request):
    origin = request.headers.get("origin")
    if (
        request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or not request.client
        or request.client.host not in {"127.0.0.1", "::1"}
        or request.headers.get("x-vartani-setup") != "1"
        or (origin and origin != f"{request.url.scheme}://{request.url.netloc}")
    ):
        raise HTTPException(403, "Start optional setup from your local Vartani page.")
    if component not in optional_setup.COMPONENTS:
        raise HTTPException(404, "Unknown optional component")
    return optional_setup.start(component)


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
    return {"native": bridge(body["text"], body["lang"]), "script": script_of(body["text"])}


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
    try:
        cfg = models.get_model(body["id"]) if body.get("id") else body
    except KeyError:
        raise HTTPException(404, "No such saved model")
    if body.get("id") and not cfg.get("api_key") and body.get("api_key"):
        cfg = {**cfg, "api_key": body["api_key"]}
    try:
        a = make_backend(cfg).answer(PROBE)
    except BackendError as e:
        return {"ok": False, "error": redact_message(str(e), cfg)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": redact_message(f"{type(e).__name__}: {e}", cfg)}
    return {"ok": a.letter is not None, "letter": a.letter, "correct": a.letter == "B", "ms": a.ms,
            "margin_available": a.margin is not None,
            "error": None if a.letter else redact_message(f"The model replied {a.raw!r}, which has no A–D letter.", cfg)}


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
        f = (WEB_DIR / path).resolve()
        if f.is_relative_to(WEB_DIR.resolve()) and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB_DIR / "index.html")
