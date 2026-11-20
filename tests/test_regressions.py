import importlib
import json
import threading

import pytest
from fastapi.testclient import TestClient

from vartani import models, runner
from vartani.backends import Answer, BackendError
from vartani.perturb import build_conditions, count_calls
from test_api import _wait

api_module = importlib.import_module("vartani.app")
c = TestClient(api_module.app)


@pytest.fixture(autouse=True)
def separate_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "P", tmp_path / "user" / "models.json")
    monkeypatch.setattr(runner, "RUNS", tmp_path / "runs")


def install_probe(monkeypatch, *, delay_at=None, entered=None, release=None, fail_at=None):
    calls = []

    class Probe:
        def answer(self, item):
            calls.append(item)
            if len(calls) == delay_at:
                entered.set()
                if not release.wait(5):
                    raise AssertionError("mock did not resume in time")
            if len(calls) == fail_at:
                raise BackendError("Mock connection lost")
            return Answer("B", margin=1.0)

    monkeypatch.setattr(runner, "make_backend", lambda _cfg: Probe())
    model = c.post("/api/models", json={"kind": "openai", "label": "Mock", "base_url": "http://127.0.0.1:1/v1", "model": "mock"}).json()
    return model["id"], calls


def start(model_id, items):
    return c.post("/api/runs", json={"model_id": model_id, "items": items, "config": {"scan": True}})


def demo():
    return c.get("/api/samples/hi_demo").json()["items"][:3]


@pytest.mark.parametrize("filename,text,hint", [
    ("bad.jsonl", '{"question":"First"}\nnot json\n', "line 2 is not valid JSON"),
    ("bad.json", '[{"question":', "Could not read this file"),
    ("bad.csv", 'question,option_a\n"unclosed', "unexpected end of data"),
])
def test_malformed_dataset_reports_a_400(filename, text, hint):
    response = c.post("/api/datasets/parse", json={"filename": filename, "lang": "hi", "text": text})
    assert response.status_code == 400 and hint in response.json()["detail"]


def test_dataset_keeps_unscored_questions_and_skips_invalid_rows(monkeypatch):
    model_id, _ = install_probe(monkeypatch)
    rows = [42, {"lang": "invalid"}, {"question": "Insufficient options?"},
            {"question": "Suraj kahan se ugta hai?", "options": ["poorab", "paschim", "uttar", "dakshin"]},
            {"question": "Suraj kahan se doobta hai?", "options": ["poorab", "paschim", "uttar", "dakshin"], "answer": "B"}]
    parsed = c.post("/api/datasets/parse", json={"filename": "set.json", "lang": "hi", "text": json.dumps(rows)}).json()
    assert len(parsed["items"]) == 2 and parsed["skipped"] == 3
    assert parsed["items"][0]["gold"] is None and any("no answer key" in w for w in parsed["warnings"])
    rid = start(model_id, parsed["items"]).json()["id"]
    assert _wait(rid)["status"] == "done"
    report = c.get(f"/api/runs/{rid}/report").json()["report"]
    assert report["n_items"] == 2 and report["accuracy"]["roman"]["n"] == 1
    assert report["bridge_gain"] is None


def test_duplicate_input_question_ids_are_rejected(monkeypatch):
    model_id, calls = install_probe(monkeypatch)
    item = demo()[0]
    result = start(model_id, [item, item])
    assert result.status_code == 400 and "repeated question IDs" in result.text
    assert not calls and not runner.list_runs()


def test_cancel_and_resume_uses_completed_rows_once(monkeypatch):
    items = demo()
    first_calls = count_calls([build_conditions(items[0], {"scan": True})])
    entered, release = threading.Event(), threading.Event()
    model_id, calls = install_probe(monkeypatch, delay_at=first_calls + 1, entered=entered, release=release)
    rid = start(model_id, items).json()["id"]
    try:
        assert entered.wait(4)
        stopped = c.post(f"/api/runs/{rid}/cancel")
        assert stopped.status_code == 200
        assert c.post(f"/api/runs/{rid}/resume", json={"model_id": model_id}).status_code == 400
    finally:
        release.set()
    cancelled = _wait(rid)
    assert cancelled["status"] == "cancelled" and cancelled["done_items"] == 1
    completed = runner.load_rows(rid)
    assert c.post(f"/api/runs/{rid}/resume", json={"model_id": model_id}).status_code == 200
    assert c.post(f"/api/runs/{rid}/resume", json={"model_id": model_id}).status_code == 400
    done = _wait(rid)
    rows = runner.load_rows(rid)
    assert done["status"] == "done" and done["done_items"] == 3
    assert done["done_calls"] == done["total_calls"] and len(calls) == done["total_calls"] + 1
    assert rows[:1] == completed and len({r["qid"] for r in rows}) == len(rows) == 3


def test_interrupted_run_ignores_partial_final_row_and_resumes(monkeypatch):
    items = demo()
    prepared = [build_conditions(item, {"scan": True}) for item in items]
    first_calls = count_calls(prepared[:1])
    model_id, calls = install_probe(monkeypatch, fail_at=first_calls + 1)
    rid = start(model_id, items).json()["id"]
    assert _wait(rid)["status"] == "failed"
    folder = runner.RUNS / rid
    complete = runner.load_rows(rid)
    assert len(complete) == 1
    # Recreate what remains on disk when the process stops during a checkpoint.
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    (folder / "meta.json").write_text(json.dumps({**meta, "status": "running", "done_items": 0}), encoding="utf-8")
    with (folder / "rows.jsonl").open("ab") as f:
        f.write(b'{"qid": "incomplete')
    view = c.get(f"/api/runs/{rid}").json()
    assert view["status"] == "interrupted" and view["done_items"] == 1
    assert len(c.get(f"/api/runs/{rid}/export.jsonl").text.splitlines()) == 1
    assert c.post(f"/api/runs/{rid}/resume", json={"model_id": model_id}).status_code == 200
    assert _wait(rid)["status"] == "done"
    rows = runner.load_rows(rid)
    assert len({r["qid"] for r in rows}) == len(rows) == 3 and rows[:1] == complete
    assert len(calls) == count_calls(prepared) + 1
    assert "incomplete" not in (folder / "rows.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("filename,content,code,message", [
    ("wrong.txt", b"not audio", 400, "Use WAV"),
    ("empty.wav", b"", 400, "empty"),
    ("long.wav", None, 413, "too large"),
])
def test_invalid_speech_upload_does_not_invoke_recognizer(monkeypatch, filename, content, code, message):
    def unexpected(*_args):
        pytest.fail("invalid uploads must be rejected before transcription")
    monkeypatch.setattr(api_module, "transcribe", unexpected)
    result = c.post("/api/speech/transcribe", data={"lang": "hi"}, files={"file": (filename, content if content is not None else b"0" * (25 * 1024 * 1024 + 1))})
    assert result.status_code == code and message in result.json()["detail"]


def test_undecodable_speech_upload_cleans_up_temporary_recording(monkeypatch):
    paths = []

    def fake_decode(path, *_args):
        paths.append(path)
        assert path.read_bytes() == b"not a WAV stream"
        raise api_module.SpeechError("Could not transcribe this audio: invalid recording")

    monkeypatch.setattr(api_module, "transcribe", fake_decode)
    result = c.post("/api/speech/transcribe", data={"lang": "hi"}, files={"file": ("broken.wav", b"not a WAV stream")})
    assert result.status_code == 503 and "invalid recording" in result.text
    assert len(paths) == 1 and not paths[0].exists()
