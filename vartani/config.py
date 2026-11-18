"""Settings read from environment variables (or a .env file next to main.py)."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DATA_DIR = Path(os.getenv("VARTANI_DATA", ROOT / "data"))
WEB_DIR = ROOT / "web"
WORKERS = max(1, int(os.getenv("WORKERS", "4")))        # parallel items for HTTP model endpoints
CHANCE = 0.25                                            # four options
LANGS = ("hi", "bn", "ta")
