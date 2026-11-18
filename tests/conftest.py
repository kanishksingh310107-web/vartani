import json, os, shutil, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())
for sub in ("starter", "paper"):
    shutil.copytree(ROOT / "data" / sub, tmp / sub)
os.environ["VARTANI_DATA"] = str(tmp)
sys.path.insert(0, str(ROOT))

import pytest


class FakeLLM(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible server: answers 'B' unless the prompt is in Roman script with a long word, then 'C'."""
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][0]["content"]
        letter = "B" if sum(ord(c) > 0x900 for c in prompt) > 20 else "C"
        resp = {"choices": [{"message": {"content": letter},
                             "logprobs": {"content": [{"top_logprobs": [{"token": letter, "logprob": -0.1}, {"token": "A", "logprob": -2.0}, {"token": "D", "logprob": -3.0}]}]}}]}
        data = json.dumps(resp).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


@pytest.fixture(scope="session")
def fake_llm():
    srv = HTTPServer(("127.0.0.1", 0), FakeLLM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()
