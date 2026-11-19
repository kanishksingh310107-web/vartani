"""Local stand-in for an OpenAI-compatible provider; useful for package smoke tests."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

DUMMY_KEY = "vartani-demo-key"
AUTH_MODEL = "requires-dummy-auth"


class FakeLLM(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._json(404, {"error": "Use /v1/chat/completions"})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body.get("model") == AUTH_MODEL and self.headers.get("Authorization") != f"Bearer {DUMMY_KEY}":
            return self._json(401, {"error": "Missing or incorrect dummy key"})
        prompt = body["messages"][0]["content"]
        letter = "B" if sum(ord(c) > 0x900 for c in prompt) > 20 else "C"
        self._json(200, {"choices": [{"message": {"content": letter}, "logprobs": {"content": [{
            "top_logprobs": [{"token": letter, "logprob": -0.1}, {"token": "A", "logprob": -2.0},
                             {"token": "D", "logprob": -3.0}]
        }]}}]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), FakeLLM) as server:
        print(f"Mock model ready at http://127.0.0.1:{server.server_port}/v1", flush=True)
        server.serve_forever()
