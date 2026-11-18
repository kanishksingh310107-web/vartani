"""Install optional packages into the user profile without modifying the core app."""
from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from .config import APP_HOME, PACKAGED, ROOT

COMPONENTS = {
    "speech": ("requirements-speech.txt", ("faster_whisper",)),
    "local-model": ("requirements-local-models.txt", ("torch", "transformers", "accelerate")),
}
_jobs: dict[str, dict[str, str]] = {}
_lock = threading.RLock()


def _location(component: str) -> Path:
    return APP_HOME / "optional" / f"py{sys.version_info.major}{sys.version_info.minor}" / component


def _activate(component: str) -> None:
    root = _location(component)
    if (root / ".vartani-installed").is_file() and str(root) not in sys.path:
        sys.path.append(str(root))
        importlib.invalidate_caches()


def activate_installed() -> None:
    for component in COMPONENTS:
        _activate(component)


def _available(component: str) -> bool:
    return all(importlib.util.find_spec(name) is not None for name in COMPONENTS[component][1])


def status(component: str) -> dict:
    if component not in COMPONENTS:
        raise ValueError("Unknown optional component")
    with _lock:
        job = _jobs.get(component, {"state": "idle", "message": "Ready to set up"})
        return {"installed": job["state"] != "running" and _available(component), **job}


def start(component: str) -> dict:
    with _lock:
        current = status(component)
        if current["state"] == "running":
            return current
        if current["installed"]:
            _jobs[component] = {"state": "done", "message": "Support is already installed."}
        elif any(job["state"] == "running" for job in _jobs.values()):
            return {**current, "state": "failed", "message": "Another setup is running. Wait for it to finish, then retry."}
        else:
            _jobs[component] = {"state": "running", "message": "Downloading and checking optional support. This can take several minutes."}
            threading.Thread(target=_install, args=(component,), daemon=True).start()
        return status(component)


def _install(component: str) -> None:
    requirement, modules = COMPONENTS[component]
    destination = _location(component)
    options = {
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL, "check": True,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    python = Path(sys.executable).with_name("python.exe") if sys.executable.lower().endswith("pythonw.exe") else sys.executable
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
            staging = Path(scratch) / "packages"
            command = [
                python, "-m", "pip", "--isolated", "install", "--no-input",
                "--disable-pip-version-check", "--only-binary=:all:",
                "--timeout", "30", "--retries", "2", "--target", str(staging),
                "-r", str(ROOT / requirement),
            ]
            if PACKAGED:
                command.extend(("-c", str(ROOT / "requirements-windows.lock")))
            subprocess.run(command, timeout=3600, **options)
            probe = "import sys; sys.path.append(sys.argv[1]); " + "; ".join(f"import {name}" for name in modules)
            subprocess.run([python, "-c", probe, str(staging)], timeout=120, **options)
            (staging / ".vartani-installed").touch()
            try:
                staging.rename(destination)
            except FileExistsError:
                if not (destination / ".vartani-installed").is_file():
                    raise
        with _lock:
            _activate(component)
            _jobs[component] = {"state": "done", "message": "Support installed. You can continue."}
    except (OSError, subprocess.SubprocessError):
        with _lock:
            _jobs[component] = {
                "state": "failed",
                "message": "Setup failed. Check your internet connection, free disk space, and package compatibility, then retry.",
            }
