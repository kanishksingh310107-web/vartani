"""Run against a Windows installer in an isolated test location.

Usage: python tests/desktop_smoke.py INSTALLER TEMPORARY_DIRECTORY [WHISPER_AUDIO]
The target directory must not exist. Setup/uninstall affects only this app's package,
the Vartani Start menu group, and its installed-app entry; do not run alongside a real install.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
import time

import httpx
from mock_provider import AUTH_MODEL, DUMMY_KEY, FakeLLM


def wait_for(fn, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError("Timed out waiting for a smoke check")


def quiet(exe, *args, env=None):
    subprocess.run([str(exe), *args], check=True, env=env,
                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=240)


def check_secret(text):
    assert DUMMY_KEY not in text and "hf_desktop_dummy" not in text and "dpapi-v1:" not in text


class Desktop:
    def __init__(self, binary, root, env, tag):
        self.path = root / f"{tag}-window.log"
        self.process = subprocess.Popen([str(binary), "--window-check", str(self.path)], env=env,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            val = wait_for(self.ready, 60)
            assert val.startswith("PASS http://127.0.0.1:"), val
            self.client = httpx.Client(base_url=val.split()[1], timeout=30, trust_env=False)
            assert self.client.get("/api/health").is_success
        except BaseException:
            self.stop()
            raise

    def ready(self):
        if self.path.exists():
            return self.path.read_text(encoding="utf-8-sig").strip()
        if self.process.poll() is not None:
            raise AssertionError(f"Desktop exited with {self.process.returncode}")
        return None

    def stop(self):
        if self.process.poll() is None:
            assert os.name == "nt"
            import ctypes
            from ctypes import wintypes
            user = ctypes.windll.user32
            cb_func = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            sent = []

            @cb_func
            def close(hwnd, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == self.process.pid and user.IsWindowVisible(hwnd):
                    user.PostMessageW(hwnd, 0x0010, 0, 0)
                    sent.append(hwnd)
                return True

            user.EnumWindows(close, 0)
            if sent:
                self.process.wait(timeout=12)
            else:
                self.process.kill()
                self.process.wait(timeout=10)
        if hasattr(self, "client"):
            try:
                self.client.get("/api/health", timeout=2)
            except httpx.TransportError:
                pass
            else:
                raise AssertionError("The loopback server survived the window")
            finally:
                self.client.close()

    def __enter__(self):
        return self.client

    def __exit__(self, *_):
        self.stop()


def check_optional(client, audio):
    for name in ("speech", "local-model"):
        url = f"/api/setup/{name}"
        running = client.post(url, headers={"X-Vartani-Setup": "1"}).json()
        assert running["state"] == "running", running
        def finished():
            data = client.get(url).json()
            return data if data["state"] in ("done", "failed") else None
        result = wait_for(finished, 360)
        assert result["installed"], result
        print(f"{name}: installed from the packaged app", flush=True)
    res = client.post("/api/speech/transcribe", data={"lang": "hi", "model_size": "tiny"},
                      files={"file": ("sample.wav", audio.read_bytes(), "audio/wav")}, timeout=180)
    assert res.is_success and res.json()["text"].strip(), res.text
    print("Packaged Whisper returned a transcript", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("location", type=Path)
    parser.add_argument("audio", nargs="?", type=Path)
    parser.add_argument("--cache", type=Path, help="Copy test model weights to the isolated cache before testing")
    flags = parser.parse_args()
    root = flags.location.resolve()
    root.mkdir(exist_ok=False)
    binary = root / "installed" / "Vartani.exe"
    profile = root / "profile"
    env = {**os.environ, "VARTANI_HOME": str(profile), "VARTANI_DATA": str(profile / "data"),
           "HF_HOME": str(profile / "hf")}
    if flags.cache:
        env["HF_HUB_OFFLINE"] = "1"
        import shutil
        shutil.copytree(flags.cache, Path(env["HF_HOME"]))
    group = "Vartani"
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs" / group / "Vartani.lnk"
    import winreg
    uninstall_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{A688DBB9-773F-4947-947E-6B67663E0FB7}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, uninstall_key):
            raise RuntimeError("Use a clean Windows account or VM without an existing Vartani installer entry.")
    except FileNotFoundError:
        pass
    if start_menu.exists():
        raise RuntimeError("The Vartani Start menu shortcut already exists. Use a clean test account.")
    models_file = profile / "data" / "user" / "models.json"
    install = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCLOSEAPPLICATIONS",
               f"/DIR={binary.parent}", f"/LOG={root / 'setup.log'}"]
    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLM)
    Thread(target=provider.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{provider.server_port}/v1"
    installed = False
    try:
        quiet(flags.installer.resolve(), *install, env=env)
        installed = True
        assert binary.is_file() and start_menu.is_file()
        print("Setup created the app and its Start menu shortcut", flush=True)
        with Desktop(binary, root, env, "first") as client:
            assert len(client.get("/api/samples").json()) == 3
            for component in ("speech", "local-model"):
                state = client.get(f"/api/setup/{component}").json()
                assert not state["installed"], state
        # Simulate upgrading from a legacy ZIP/profile and carry forward a saved run.
        models_file.parent.mkdir(parents=True, exist_ok=True)
        models_file.write_text(json.dumps([
            {"id": "probe", "label": "Dummy connection", "kind": "openai", "api_key": DUMMY_KEY,
             "needs_key": True, "model": AUTH_MODEL, "base_url": base},
            {"id": "hf", "label": "Dummy HF token", "kind": "hf", "hf_id": "fixture/placeholder",
             "hf_token": "hf_desktop_dummy"}
        ]), encoding="utf-8")
        old_run = profile / "data" / "runs" / "legacy"
        old_run.mkdir(parents=True, exist_ok=True)
        (old_run / "meta.json").write_text(json.dumps({"id": "legacy", "name": "Old report", "created": 1,
                                                       "status": "failed", "model": {"api_key": DUMMY_KEY},
                                                       "error": f"HTTP 401: {DUMMY_KEY}"}), encoding="utf-8")
        quiet(flags.installer.resolve(), *install, env=env)
        with Desktop(binary, root, env, "upgrade") as client:
            assert client.get("/api/runs/legacy").json()["error"] == "HTTP 401: [redacted]"
            saved = client.get("/api/models")
            check_secret(saved.text)
            assert {m["id"]: m["has_key"] or m["has_hf_token"] for m in saved.json()["saved"]} == {"probe": True, "hf": True}
            text = models_file.read_text(encoding="utf-8")
            assert text.count("dpapi-v1:") == 2 and DUMMY_KEY not in text and "hf_desktop_dummy" not in text
            assert client.post("/api/models/test", json={"id": "probe"}).json()["ok"]
            items = client.get("/api/samples/hi_demo").json()["items"]
            run = client.post("/api/runs", json={"name": "Installed smoke", "items": items, "model_id": "probe"}).json()
            runid = run["id"]
            def done():
                value = client.get(f"/api/runs/{runid}").json()
                return value if value["status"] not in ("queued", "running") else None
            assert wait_for(done)["done_items"] == 6
            for ext in ("csv", "jsonl", "html"):
                response = client.get(f"/api/runs/{runid}/export.{ext}")
                assert response.is_success and "attachment" in response.headers.get("Content-Disposition", "")
                check_secret(response.text)
            if flags.audio:
                check_optional(client, flags.audio)
        print("Upgrade kept the run, protected the credentials, connected to the mock provider, and exported all three formats", flush=True)
        with Desktop(binary, root, env, "repeat") as client:
            assert client.get(f"/api/runs/{runid}").json()["status"] == "done"
            assert client.post("/api/models/test", json={"id": "probe"}).json()["ok"]
            if flags.audio:
                assert all(client.get(f"/api/setup/{c}").json()["installed"] for c in ("speech", "local-model"))
            client.post("/api/models", json={"id": "probe", "api_key": "wrong-dummy-key"}).raise_for_status()
            assert "HTTP 401" in client.post("/api/models/test", json={"id": "probe"}).json()["error"]
            client.post("/api/models", json={"id": "probe", "clear_api_key": True}).raise_for_status()
            assert client.post("/api/models/test", json={"id": "probe"}).status_code == 409
            client.delete("/api/models/hf").raise_for_status()
            assert "dpapi-v1:" not in models_file.read_text(encoding="utf-8")
        saved_hash = hashlib.sha256(models_file.read_bytes()).hexdigest()
        uninstall = next(binary.parent.glob("unins*.exe"))
        quiet(uninstall, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={root / 'uninstall.log'}", env=env)
        installed = False
        assert not binary.exists() and not start_menu.exists()
        assert hashlib.sha256(models_file.read_bytes()).hexdigest() == saved_hash
        assert (profile / "data" / "runs" / runid / "rows.jsonl").is_file()
        print("Repeat launch, key replacement/removal, server shutdown and uninstall retention passed", flush=True)
    finally:
        provider.shutdown()
        provider.server_close()
        if installed:
            uninstaller = next(binary.parent.glob("unins*.exe"), None)
            if uninstaller:
                quiet(uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", env=env)


if __name__ == "__main__":
    main()
