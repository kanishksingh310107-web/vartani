"""Settings read from environment variables (or a .env file next to main.py)."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
PACKAGED = getattr(sys, "frozen", False) or os.getenv("VARTANI_PACKAGED") == "1"


def _default_home() -> Path:
    if os.getenv("VARTANI_HOME"):
        return Path(os.environ["VARTANI_HOME"])
    if PACKAGED:
        local = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "Vartani"
    return ROOT


def _load_dotenv() -> None:
    candidates = [_default_home() / ".env", ROOT / ".env"]
    for env in dict.fromkeys(candidates):
        try:
            lines = env.read_text(encoding="utf-8").splitlines() if env.is_file() else []
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()
APP_HOME = _default_home()
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DATA_DIR = Path(os.getenv("VARTANI_DATA", APP_HOME / "data" if PACKAGED else ROOT / "data"))
WORKERS = max(1, int(os.getenv("WORKERS", "4")))        # parallel items for HTTP model endpoints
CHANCE = 0.25                                            # four options
LANGS = ("hi", "bn", "ta")
