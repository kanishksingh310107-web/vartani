import os, shutil, sys, tempfile, threading
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())
for sub in ("starter", "paper"):
    shutil.copytree(ROOT / "data" / sub, tmp / sub)
os.environ["VARTANI_DATA"] = str(tmp)
sys.path.insert(0, str(ROOT))

import pytest
from mock_provider import FakeLLM


@pytest.fixture(scope="session")
def fake_llm():
    srv = HTTPServer(("127.0.0.1", 0), FakeLLM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()
    srv.server_close()
