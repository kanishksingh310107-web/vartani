"""Windows-first GUI launcher for the packaged Vartani application."""
from __future__ import annotations

import logging
import os
import queue
import socket
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4


class SetupError(RuntimeError):
    """An actionable setup or startup error for the launcher UI."""


@dataclass(frozen=True)
class ProfilePaths:
    home: Path
    data: Path
    logs: Path


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def resolve_profile_paths(environment=None, frozen=None, script_root=None) -> ProfilePaths:
    env = os.environ if environment is None else environment
    packaged = (bool(getattr(sys, "frozen", False)) or env.get("VARTANI_PACKAGED") == "1") if frozen is None else frozen
    root = Path(script_root) if script_root is not None else Path(__file__).resolve().parent
    if env.get("VARTANI_HOME"):
        home = Path(env["VARTANI_HOME"]).expanduser()
    elif env.get("VARTANI_DATA"):
        home = Path(env["VARTANI_DATA"]).expanduser().parent
    elif packaged:
        local = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        home = Path(local).expanduser() / "Vartani"
    else:
        home = root
    data = Path(env.get("VARTANI_DATA", home / "data")).expanduser()
    return ProfilePaths(home=home, data=data, logs=home / "logs")


def ensure_bundle(root: Path) -> None:
    missing = [str(p) for p in (root / "web" / "index.html", root / "data" / "starter", root / "data" / "paper") if not p.exists()]
    if missing:
        raise SetupError("Vartani's application files are incomplete. Re-extract the full Windows package to a new folder and launch it again. Missing: " + ", ".join(missing))


def ensure_profile(paths: ProfilePaths) -> None:
    """Create only missing folders and prove the profile drive is writable."""
    try:
        for folder in (paths.home, paths.data, paths.data / "runs", paths.data / "user", paths.logs):
            folder.mkdir(parents=True, exist_ok=True)
        probe = paths.data / f".write-check-{uuid4().hex}.tmp"
        with probe.open("xb") as f:
            f.write(b"Vartani write check\n")
            f.flush()
            os.fsync(f.fileno())
        probe.unlink()
    except OSError as e:
        reason = "The drive may be full." if getattr(e, "errno", None) == 28 or getattr(e, "winerror", None) == 112 else "Check that you have permission to write there."
        raise SetupError(f"Vartani could not prepare its user-data folder at:\n{paths.data}\n{reason}\nFree some disk space or choose a writable VARTANI_HOME folder, then retry. Details: {e}") from e


def copy_existing_profile(source_data: Path, destination_data: Path) -> tuple[int, int]:
    """Copy old runs/settings without deleting or replacing any existing file."""
    source_data = Path(source_data)
    if not source_data.is_dir():
        raise SetupError(f"That folder does not exist:\n{source_data}")
    copied = skipped = 0
    try:
        for name in ("user", "runs"):
            source = source_data / name
            if not source.is_dir():
                continue
            for item in source.rglob("*"):
                rel = item.relative_to(source_data)
                target = destination_data / rel
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif item.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        skipped += 1
                    else:
                        copy2(item, target)
                        copied += 1
    except OSError as e:
        reason = "The destination drive may be full." if getattr(e, "errno", None) == 28 or getattr(e, "winerror", None) == 112 else "Check read/write access to both folders."
        raise SetupError(f"Some old data could not be copied. The original folder was left untouched; retrying will skip existing files. {reason}\nDetails: {e}") from e
    return copied, skipped


def _port_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
        return True
    except OSError:
        return False


def _choose_port(host: str, preferred: int, explicit: bool) -> int:
    if _port_available(host, preferred):
        return preferred
    if explicit:
        raise SetupError(f"Vartani cannot use {host}:{preferred}; another app is already using that port. Close the other app or change PORT in your Vartani .env settings, then retry.")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])
    except OSError as e:
        raise SetupError(f"Vartani could not find an available local network port. Close other local servers and retry. Details: {e}") from e


class VartaniLauncher:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.paths = resolve_profile_paths()
        self.events = queue.Queue()
        self.server = None
        self.server_thread = None
        self.url = None
        self.starting = False
        self.root = tk.Tk()
        self.root.title("Vartani")
        self.root.geometry("560x320")
        self.root.minsize(500, 290)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Vartani", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Local setup and launcher", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 16))
        ttk.Label(frame, text="The first start prepares your user profile. Your saved models and runs stay in your Windows user folder across app updates.", wraplength=500).pack(anchor="w", pady=(0, 12))
        self.status = tk.StringVar(value="Ready to start. No internet is needed for setup.")
        ttk.Label(frame, textvariable=self.status, wraplength=500).pack(anchor="w", pady=(2, 8))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.pack(anchor="w", fill="x")
        self.start_button = ttk.Button(actions, text="Start Vartani", command=self.start)
        self.start_button.pack(side="left")
        self.import_button = ttk.Button(actions, text="Import old Vartani data…", command=self.import_data)
        self.import_button.pack(side="left", padx=(8, 0))
        self.open_button = ttk.Button(actions, text="Open Vartani", command=self.open_app, state="disabled")
        self.open_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Stop and close", command=self.close).pack(side="right")
        self.url_text = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.url_text, foreground="#7256d8").pack(anchor="w", pady=(12, 0))
        self.log_hint = tk.StringVar(value="Setup log: created after startup")
        ttk.Label(frame, textvariable=self.log_hint, wraplength=500, foreground="#666666").pack(anchor="w", pady=(8, 0))
        self.drain_timer = self.root.after(150, self._drain_events)

    def _log(self, message: str) -> None:
        try:
            self.paths.logs.mkdir(parents=True, exist_ok=True)
            with (self.paths.logs / "launcher.log").open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
        except OSError:
            pass

    def import_data(self):
        from tkinter import filedialog, messagebox
        source = filedialog.askdirectory(title="Choose the old Vartani data folder (contains user and/or runs)")
        if not source:
            return
        try:
            ensure_profile(self.paths)
            copied, skipped = copy_existing_profile(Path(source), self.paths.data)
            messagebox.showinfo("Import complete", f"Copied {copied} file(s). Left {skipped} existing file(s) unchanged. The source folder was not modified.")
            self.status.set("Old settings and run data imported safely. Start Vartani when ready.")
        except SetupError as e:
            messagebox.showerror("Could not import data", str(e))

    def start(self):
        if self.starting or self.server_thread and self.server_thread.is_alive():
            return
        self.starting = True
        self.open_button.configure(state="disabled")
        self.start_button.configure(state="disabled", text="Starting…")
        self.import_button.configure(state="disabled")
        self.progress.start(12)
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _bootstrap(self):
        try:
            root = bundle_root()
            self.events.put(("status", "Checking the bundled application files…"))
            ensure_bundle(root)
            if getattr(self, "closing", False):
                return
            os.environ.setdefault("VARTANI_HOME", str(self.paths.home))
            os.environ.setdefault("VARTANI_DATA", str(self.paths.data))
            self.events.put(("status", "Preparing your saved settings and run folder…"))
            ensure_profile(self.paths)
            if getattr(self, "closing", False):
                return
            self.events.put(("log_hint", f"Setup log: {self.paths.logs / 'launcher.log'}"))
            self._log("profile ready; bundled-resource check passed")

            self.events.put(("status", "Starting the local Vartani server…"))
            from vartani import config
            import uvicorn
            explicit_port = "PORT" in os.environ
            port = _choose_port(config.HOST, config.PORT, explicit_port)
            config.PORT = port
            self.url = f"http://{config.HOST}:{port}"
            from vartani.app import app
            if getattr(self, "closing", False):
                return
            server_config = uvicorn.Config(app, host=config.HOST, port=port, log_level="warning", access_log=False, http="h11", ws="none")
            self.server = uvicorn.Server(server_config)
            self.server.install_signal_handlers = lambda: None
            self.server_thread = threading.Thread(target=self.server.run, name="VartaniServer", daemon=True)
            self.server_thread.start()
            self._log(f"server thread started on {self.url}")

            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and not getattr(self, "closing", False):
                if not self.server_thread.is_alive():
                    raise SetupError(f"The local server stopped while starting. Check the log at {self.paths.logs / 'launcher.log'} and retry.")
                try:
                    with urlopen(self.url + "/api/health", timeout=0.8) as response:
                        if response.status == 200:
                            self._log("health check passed")
                            self.events.put(("ready", self.url))
                            return
                except (OSError, URLError, TimeoutError):
                    time.sleep(0.3)
            if getattr(self, "closing", False):
                return
            raise SetupError(f"Vartani did not finish starting within 45 seconds. Check local security software and the log at {self.paths.logs / 'launcher.log'}, then retry.")
        except SetupError as e:
            self._stop_server_after_error()
            self._log(f"setup error: {e}")
            self.events.put(("error", str(e)))
        except Exception as e:
            self._stop_server_after_error()
            self._log(f"startup error: {type(e).__name__}: {e}")
            self.events.put(("error", f"Vartani could not start ({type(e).__name__}). Check the log at:\n{self.paths.logs / 'launcher.log'}\n\nDetails: {e}"))

    def _stop_server_after_error(self):
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread is not None:
            self.server_thread.join(timeout=2)
        self.server = None
        self.server_thread = None

    def _drain_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    self.status.set(value)
                elif kind == "log_hint":
                    self.log_hint.set(value)
                elif kind == "ready":
                    self.progress.stop()
                    self.status.set("Vartani is ready. You can close this launcher to stop the local server.")
                    self.url_text.set(f"If the browser did not open, go to {value}")
                    self.log_hint.set(f"Setup log: {self.paths.logs / 'launcher.log'}")
                    self.start_button.configure(state="disabled", text="Vartani is running")
                    self.open_button.configure(state="normal")
                    try:
                        opened = webbrowser.open(value)
                        if not opened:
                            self._log("default browser could not be opened; URL shown in launcher")
                    except Exception as e:
                        self._log(f"browser launch error: {e}")
                elif kind == "error":
                    self.progress.stop()
                    self.starting = False
                    self.start_button.configure(state="normal", text="Retry setup")
                    self.import_button.configure(state="normal")
                    self.status.set(value)
        except queue.Empty:
            pass
        self.drain_timer = self.root.after(150, self._drain_events)

    def open_app(self):
        if self.url:
            try:
                webbrowser.open(self.url)
            except Exception as e:
                self._log(f"browser launch error: {e}")

    def close(self):
        self.closing = True
        self.root.after_cancel(self.drain_timer)
        if self.server is not None:
            self.server.should_exit = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def packaged_smoke_test(log_path: Path) -> int:
    """Exercise the frozen imports, static resources, and API in isolation."""
    import tempfile
    def log(message: str):
        Path(log_path).write_text(message + "\n", encoding="utf-8")
    try:
        log("Checking bundled resources…")
        ensure_bundle(bundle_root())
        with tempfile.TemporaryDirectory(prefix="vartani-smoke-") as temp:
            home = Path(temp) / "profile"
            os.environ["VARTANI_HOME"] = str(home)
            os.environ["VARTANI_DATA"] = str(home / "data")
            log("Preparing an isolated smoke-test profile…")
            ensure_profile(resolve_profile_paths(frozen=True, script_root=Path(temp)))
            log("Importing the app…")
            from vartani.app import app, get_models, health, samples
            from vartani.optional_setup import status
            log("Checking the app handlers and bundled pages…")
            if not health().get("version"):
                raise SetupError("The packaged health handler did not return the app version.")
            if len(samples()) < 3:
                raise SetupError("The packaged starter-set handler did not find all language sets.")
            if not any(p.get("preset") == "groq" for p in get_models()["presets"]):
                raise SetupError("The packaged model preset handler did not include the Groq preset.")
            paths = {getattr(route, "path", "") for route in app.routes}
            if not {"/api/health", "/api/samples", "/api/models", "/api/setup/{component}"} <= paths:
                raise SetupError("The packaged app is missing a required API route.")
            if not Path(sys.executable).with_name("python.exe").is_file():
                raise SetupError("The package is missing its optional setup interpreter.")
            if any(status(component)["installed"] for component in ("speech", "local-model")):
                raise SetupError("The core Windows package unexpectedly contains optional dependencies.")
            for relative, expected in (("web/index.html", "Vartani"),
                                       ("web/speech.html", "Speech-to-text robustness"),
                                       ("web/speech.js", "/setup/speech")):
                log(f"Checking {relative}…")
                asset = bundle_root() / relative
                if not asset.is_file() or expected not in asset.read_text(encoding="utf-8"):
                    raise SetupError(f"Packaged file is missing or invalid: {relative}")
            if "torch" in sys.modules or "faster_whisper" in sys.modules:
                raise SetupError("The core Windows package unexpectedly loaded optional local-model or speech dependencies.")
        log("PASS: bundled app imports, route handlers, starter sets, saved-model presets, web UI, and optional-dependency boundary.")
        return 0
    except Exception as e:
        try:
            Path(log_path).write_text(f"FAIL: {type(e).__name__}: {e}\n", encoding="utf-8")
        except OSError:
            pass
        return 1


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--smoke-test":
        raise SystemExit(packaged_smoke_test(Path(sys.argv[2])))
    try:
        VartaniLauncher().run()
    except Exception as e:
        try:
            from tkinter import messagebox
            messagebox.showerror("Vartani could not open", f"{e}\n\nTry extracting the complete package to a writable folder and starting Vartani.exe again.")
        except Exception:
            print(f"Vartani could not open: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
