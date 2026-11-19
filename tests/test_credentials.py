import importlib
import json
import os
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from launcher import SetupError, copy_existing_profile
from vartani import credentials, models, runner
from vartani.backends import Answer, BackendError
from test_api import _wait
from mock_provider import AUTH_MODEL, DUMMY_KEY

api_module = importlib.import_module("vartani.app")
c = TestClient(api_module.app)
KEY = "mock-api+/=credential-4747"
TOKEN = "hf_fake_read_token_4529"
MODEL = {"id": "test-model", "kind": "openai", "label": "Local fake", "base_url": "http://127.0.0.1:1/v1",
         "model": "fake", "needs_key": True}
HF_MODEL = {"id": "test-hf", "kind": "hf", "hf_id": "fake/model", "label": "Fake Hugging Face"}
WINDOWS = pytest.mark.skipif(os.name != "nt", reason="Requires real Windows account protection")


@pytest.fixture(autouse=True)
def separate_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "P", tmp_path / "data" / "user" / "models.json")
    monkeypatch.setattr(runner, "RUNS", tmp_path / "data" / "runs")


def seed_legacy(records):
    models.P.parent.mkdir(parents=True, exist_ok=True)
    models.P.write_text(json.dumps(records), encoding="utf-8")
    return models.P.read_bytes()


@WINDOWS
def test_legacy_credentials_migrate_and_still_reach_both_mock_providers(monkeypatch):
    seed_legacy([{**MODEL, "api_key": KEY}, {**HF_MODEL, "hf_token": TOKEN}])
    seen = []

    def make_backend(cfg):
        seen.append(cfg)
        return type("Probe", (), {"answer": lambda _self, _item: Answer("B", margin=1.0)})()

    monkeypatch.setattr(api_module, "make_backend", make_backend)
    response = c.get("/api/models")
    assert response.status_code == 200
    saved = response.json()["saved"]
    assert saved[0]["has_key"] and saved[1]["has_hf_token"]
    stored = models.P.read_text(encoding="utf-8")
    assert KEY not in stored and TOKEN not in stored and stored.count("dpapi-v1:") == 2
    for model in (MODEL, HF_MODEL):
        assert c.post("/api/models/test", json={"id": model["id"]}).json()["ok"]
    assert seen[0]["api_key"] == KEY and seen[1]["hf_token"] == TOKEN
    blank_edit = c.post("/api/models", json={"id": MODEL["id"], "label": "Renamed", "api_key": ""})
    assert blank_edit.json()["has_key"] and KEY not in blank_edit.text
    assert models.get_model(MODEL["id"])["api_key"] == KEY
    assert "dpapi-v1:" not in response.text + blank_edit.text


@WINDOWS
def test_replace_clear_and_delete_credentials_including_unreadable_blob():
    first = c.post("/api/models", json={**MODEL, "api_key": KEY})
    assert first.status_code == 200 and first.json()["has_key"]
    records = json.loads(models.P.read_text(encoding="utf-8"))
    records[0][credentials.BLOBS]["api_key"] = "dpapi-v1:not-a-valid-blob"
    seed_legacy(records)
    assert c.get("/api/models").json()["saved"][0]["has_key"]
    err = c.post("/api/models/test", json={"id": MODEL["id"]})
    assert err.status_code == 409 and "re-enter" in err.text and "dpapi-v1:" not in err.text
    replacement = "different-dummy-api-key-7647"
    edited = c.post("/api/models", json={"id": MODEL["id"], "api_key": replacement})
    assert edited.status_code == 200 and edited.json()["has_key"] and replacement not in edited.text
    assert models.get_model(MODEL["id"])["api_key"] == replacement
    assert c.post("/api/models", json={"id": MODEL["id"], "clear_api_key": True}).json()["has_key"] is False
    assert c.post("/api/models/test", json={"id": MODEL["id"]}).status_code == 409
    assert c.post("/api/runs", json={"model_id": MODEL["id"], "items": [{}]}).status_code == 409
    assert c.post("/api/models", json={**HF_MODEL, "hf_token": TOKEN}).json()["has_hf_token"]
    assert c.delete(f"/api/models/{HF_MODEL['id']}").status_code == 200
    assert TOKEN not in models.P.read_text(encoding="utf-8") and "dpapi-v1:" not in models.P.read_text(encoding="utf-8")
    assert c.post("/api/models/test", json={"id": HF_MODEL["id"]}).status_code == 404


@pytest.mark.parametrize("failure", ["encryption", "write"])
def test_migration_failure_preserves_original_and_does_not_release_secrets(monkeypatch, failure):
    original = seed_legacy([{**MODEL, "api_key": KEY}, {**HF_MODEL, "hf_token": TOKEN}])

    def seal(value):
        if value == TOKEN and failure == "encryption":
            raise credentials.CredentialError(f"test error with {value}")
        return "dpapi-v1:fake-encryption-only-for-failure-test"

    monkeypatch.setattr(credentials, "seal", seal)
    if failure == "write":
        def refuse_replace(_self, _path):
            raise PermissionError("cannot replace the old file")
        monkeypatch.setattr(type(models.P), "replace", refuse_replace)
    res = c.get("/api/models")
    assert res.status_code == 409 and "original settings were preserved" in res.text
    assert KEY not in res.text and TOKEN not in res.text
    assert models.P.read_bytes() == original
    assert list(models.P.parent.iterdir()) == [models.P]


@WINDOWS
def test_launcher_import_protects_copies_and_leaves_legacy_source_unchanged(tmp_path):
    old = tmp_path / "old"
    src = old / "user" / "models.json"
    old_meta = old / "runs" / "demo" / "meta.json"
    src.parent.mkdir(parents=True)
    old_meta.parent.mkdir(parents=True)
    src.write_text(json.dumps([{**MODEL, "api_key": KEY}]), encoding="utf-8")
    old_meta.write_text(json.dumps({"id": "demo", "model": {"api_key": KEY}, "error": f"HTTP 400: {KEY}"}), encoding="utf-8")
    assert copy_existing_profile(old, models.P.parent.parent) == (2, 0)
    assert copy_existing_profile(old, models.P.parent.parent) == (0, 2)
    assert models.get_model(MODEL["id"])["api_key"] == KEY
    assert KEY in src.read_text(encoding="utf-8") and KEY in old_meta.read_text(encoding="utf-8")
    assert KEY not in models.P.read_text(encoding="utf-8")
    assert "HTTP 400: [redacted]" in (runner.RUNS / "demo" / "meta.json").read_text(encoding="utf-8")


def test_import_failure_never_copies_plaintext(tmp_path, monkeypatch):
    old = tmp_path / "old-settings"
    src = old / "user" / "models.json"
    src.parent.mkdir(parents=True)
    src.write_text(json.dumps([{**MODEL, "api_key": KEY}]), encoding="utf-8")

    def fail(_value):
        raise credentials.CredentialError("could not protect it")

    monkeypatch.setattr(credentials, "seal", fail)
    with pytest.raises(SetupError, match="original profile was left untouched"):
        copy_existing_profile(old, models.P.parent.parent)
    assert not models.P.exists() and KEY in src.read_text(encoding="utf-8")


def assert_clean_run(rid, expected_error=None):
    paths = ["/api/runs", f"/api/runs/{rid}", f"/api/runs/{rid}/report", f"/api/runs/{rid}/items"]
    paths += [f"/api/runs/{rid}/export.{ext}" for ext in ("csv", "jsonl", "html")]
    for path in paths:
        response = c.get(path)
        assert response.status_code == 200, path
        assert all(value not in response.text for value in (KEY, TOKEN, quote(KEY, safe=""), "dpapi-v1:")), path
    meta = (runner.RUNS / rid / "meta.json").read_text(encoding="utf-8")
    assert all(value not in meta for value in (KEY, TOKEN, quote(KEY, safe=""), "dpapi-v1:"))
    if expected_error:
        assert expected_error in c.get(f"/api/runs/{rid}/report").json()["meta"]["error"]


def test_legacy_report_scrubs_fields_and_echoes_before_returning_or_exporting():
    rid = "legacy-run"
    raw = {"id": rid, "name": f"Legacy {TOKEN}", "model_label": f"Model {KEY}", "status": "failed", "created": 1,
           "n_items": 0, "model": {"api_key": KEY}, "config": {"extra": [{"hf_token": TOKEN}, {"detail": KEY}]},
           "error": f"HTTP 403: rejected {quote(KEY, safe='')} and {TOKEN}"}
    folder = runner.RUNS / rid
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps(raw), encoding="utf-8")
    assert_clean_run(rid, "HTTP 403: rejected [redacted] and [redacted]")
    assert c.get(f"/api/runs/{rid}/export.html").text.find("Legacy [redacted]") >= 0


@WINDOWS
def test_new_run_and_provider_errors_do_not_expose_credentials(monkeypatch):
    def fail(cfg):
        assert cfg["api_key"] == KEY
        raise BackendError(f"HTTP 403: provider rejected {KEY}")

    monkeypatch.setattr(api_module, "make_backend", fail)
    monkeypatch.setattr(runner, "make_backend", fail)
    model = c.post("/api/models", json={**MODEL, "api_key": KEY}).json()
    probe = c.post("/api/models/test", json={"id": model["id"]})
    assert probe.json() == {"ok": False, "error": "HTTP 403: provider rejected [redacted]"}
    items = c.get("/api/samples/hi_demo").json()["items"][:1]
    start = c.post("/api/runs", json={"model_id": model["id"], "items": items, "name": f"Test {KEY}",
                                     "config": {"custom": [{"authorization": TOKEN, "note": TOKEN}]}})
    assert start.status_code == 200 and KEY not in start.text and TOKEN not in start.text
    rid = start.json()["id"]
    assert _wait(rid)["status"] == "failed"
    assert_clean_run(rid, "HTTP 403: provider rejected [redacted]")


def test_provider_error_redacts_before_shortening(monkeypatch):
    import httpx
    from vartani.backends import OpenAICompat, _hf_load_error

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(400, text="x" * 294 + KEY + " end"))
    with pytest.raises(BackendError) as error:
        OpenAICompat("http://localhost/v1", "test", KEY).answer({"passage": "", "question": "Test?", "options": list("ABCD")})
    assert str(error.value).startswith("HTTP 400:") and KEY[:6] not in str(error.value)
    hf = _hf_load_error("test/model", RuntimeError("x" * 894 + TOKEN), TOKEN)
    assert hf.startswith("Model test/model failed") and TOKEN[:6] not in hf


@WINDOWS
def test_migrated_key_authenticates_to_a_local_provider_after_startup(fake_llm):
    seed_legacy([{**MODEL, "base_url": fake_llm, "model": AUTH_MODEL, "api_key": DUMMY_KEY}])
    old = runner.RUNS / "old" / "meta.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"id": "old", "model": {"api_key": DUMMY_KEY}}), encoding="utf-8")
    with TestClient(api_module.app) as app_client:
        # Startup migrations run before the first request, even for runs no one has opened.
        assert DUMMY_KEY not in models.P.read_text(encoding="utf-8")
        assert DUMMY_KEY not in old.read_text(encoding="utf-8")
        assert app_client.post("/api/models/test", json={"id": MODEL["id"]}).json()["ok"]
        app_client.post("/api/models", json={"id": MODEL["id"], "api_key": "wrong-dummy-key"})
        err = app_client.post("/api/models/test", json={"id": MODEL["id"]}).json()
        assert err["ok"] is False and "HTTP 401" in err["error"]
