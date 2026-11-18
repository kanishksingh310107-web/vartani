import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from vartani import optional_setup, runner, speech
from vartani.app import app


def test_optional_setup_rejects_unknown_component():
    with pytest.raises(ValueError):
        optional_setup.start("unknown")


def test_installed_support_is_not_reinstalled(monkeypatch):
    monkeypatch.setattr(optional_setup.importlib.util, "find_spec", lambda name: object())
    result = optional_setup.start("speech")
    assert result["installed"] and result["state"] == "done"
    optional_setup._jobs.clear()


def test_old_run_metadata_is_redacted(tmp_path):
    original = {"model": {"hf_token": "secret-token", "api_key": "secret-key", "label": "model"},
                "error": "secret-token and secret-key"}
    metadata = tmp_path / "meta.json"
    metadata.write_text(json.dumps(original), encoding="utf-8")
    safe = runner._read_meta(metadata)
    assert safe["model"] == {"label": "model"}
    assert "secret" not in safe["error"]
    assert json.loads(metadata.read_text(encoding="utf-8")) == safe


def test_installer_requires_explicit_local_request(monkeypatch):
    requests = []
    monkeypatch.setattr(optional_setup, "start", lambda component: requests.append(component) or {"state": "done"})
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as client:
        path = "/api/setup/speech"
        assert client.post(path).status_code == 403
        assert client.post(path, headers={"X-Vartani-Setup": "1", "Origin": "https://outside.example"}).status_code == 403
        assert client.post(path, headers={"X-Vartani-Setup": "1", "Origin": "http://127.0.0.1:8000"}).status_code == 200
        assert requests == ["speech"]


def test_failed_staging_can_retry_without_touching_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(optional_setup, "APP_HOME", tmp_path)
    monkeypatch.setattr(optional_setup, "_jobs", {})
    monkeypatch.setattr(optional_setup.sys, "path", list(optional_setup.sys.path))
    destination = optional_setup._location("speech")
    settings = tmp_path / "profile.json"
    settings.write_text("keep me", encoding="utf-8")

    def fake_pip(command, **kwargs):
        if "--target" in command:
            staging = command[command.index("--target") + 1]
            Path(staging).mkdir()
            if not destination.parent.joinpath("retry").exists():
                raise subprocess.CalledProcessError(1, command)
        return None

    monkeypatch.setattr(optional_setup.subprocess, "run", fake_pip)
    optional_setup._install("speech")
    assert optional_setup.status("speech")["state"] == "failed"
    assert not destination.exists()
    destination.parent.joinpath("retry").touch()
    optional_setup._install("speech")
    assert optional_setup.status("speech")["state"] == "done"
    assert destination.joinpath(".vartani-installed").is_file()
    assert settings.read_text(encoding="utf-8") == "keep me"


def test_speech_uses_cpu_when_cuda_libraries_are_missing(monkeypatch, tmp_path):
    attempts = []
    monkeypatch.setattr(speech, "_models", {})
    monkeypatch.setattr(speech, "_cpu_fallback", set())
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))

    def model(size, device, compute_type):
        attempts.append(device)

        def recognize(*args, **kwargs):
            if device == "cuda":
                raise RuntimeError("Unable to load CUDA library")
            return [SimpleNamespace(text="Namaste")], SimpleNamespace(language="hi", duration=1)

        return SimpleNamespace(transcribe=recognize)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=model))
    assert speech.transcribe(tmp_path / "sound.wav", "hi", "tiny")["text"] == "Namaste"
    assert speech.transcribe(tmp_path / "sound.wav", "hi", "tiny")["text"] == "Namaste"
    assert attempts == ["cuda", "cpu"]
