import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import brain, store

STATIC = Path(__file__).with_name("static")
DEFAULT_MODEL = os.environ.get("FLEETBOX_MODEL", "ollama/qwen2.5-coder:7b")
MAX_BODY = 200_000
RUN_PATH = re.compile(r"^/api/runs/([a-f0-9]{12})(/events|/files)?$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/config":
            return self._send(200, {"default_model": DEFAULT_MODEL, "max_concurrent": brain.MAX_CONCURRENT})
        if url.path == "/api/runs":
            return self._send(200, store.list_runs())
        match = RUN_PATH.match(url.path)
        if not match:
            return self._send(404, {"error": "not found"})
        run_id, sub = match.groups()
        run = store.get_run(run_id)
        if not run:
            return self._send(404, {"error": "run not found"})
        if sub == "/events":
            after = int(parse_qs(url.query).get("after", ["0"])[0] or 0)
            return self._send(200, store.get_events(run_id, after))
        if sub == "/files":
            return self._send(200, store.get_files(run_id))
        return self._send(200, run)

    def do_POST(self):
        if urlparse(self.path).path != "/api/fleets":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._send(400, {"error": "body missing or too large"})
        try:
            body = json.loads(self.rfile.read(length))
            tasks = body["tasks"]
            if not isinstance(tasks, list) or not all(isinstance(t, str) for t in tasks):
                raise ValueError("tasks must be a list of strings")
            result = brain.launch(tasks, str(body.get("model") or DEFAULT_MODEL))
        except (KeyError, ValueError, json.JSONDecodeError, RuntimeError) as err:
            return self._send(400, {"error": str(err)})
        return self._send(202, result)


def serve(host: str = "127.0.0.1", port: int = 8790) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"fleetbox on http://{host}:{port}  model={DEFAULT_MODEL}  max_concurrent={brain.MAX_CONCURRENT}")
    server.serve_forever()
