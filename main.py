"""Start Vartani:  python main.py
First run creates a private Python environment and installs the small requirements (about a minute).
The web interface is pre-built, so Node.js is NOT needed."""
from __future__ import annotations
import os
import subprocess
import sys
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".venv"
PY = ENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_env() -> None:
    if Path(sys.prefix).resolve() == ENV.resolve():
        return
    if not PY.exists():
        print("Creating a private Python environment…", flush=True)
        venv.EnvBuilder(with_pip=True).create(ENV)
    probe = [str(PY), "-c", "import fastapi, uvicorn, httpx, multipart, indic_transliteration"]
    if subprocess.run(probe, capture_output=True).returncode != 0:
        print("Installing requirements (first run only)…", flush=True)
        subprocess.run([str(PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=True)
    raise SystemExit(subprocess.call([str(PY), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT))


def main() -> None:
    ensure_env()
    import uvicorn
    from vartani import config
    url = f"http://{config.HOST}:{config.PORT}"
    print(f"\nVartani is running at {url}   (Ctrl+C to stop)\n", flush=True)
    if os.getenv("NO_BROWSER") != "1":
        webbrowser.open(url)
    uvicorn.run("vartani.app:app", host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
