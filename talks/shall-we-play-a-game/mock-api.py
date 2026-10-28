#!/usr/bin/env python3
"""A fake Mission Log API for demos: GET /api/missions and PATCH /api/missions/<id>. Stdlib only."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

MISSIONS = [
    {"id": "m-1", "title": "Calibrate the dish", "status": "open", "priority": 1},
    {"id": "m-2", "title": "Rotate the launch codes", "status": "done", "priority": 2},
    {"id": "m-3", "title": "Play tic-tac-toe with Joshua", "status": "open", "priority": 3},
    {"id": "m-4", "title": "Patch the modem firmware", "status": "done", "priority": 2},
    {"id": "m-5", "title": "Write the audit report", "status": "open", "priority": 1},
]

class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path == "/api/missions":
            return self._send(200, MISSIONS)
        self._send(404, {"error": "not found"})
    def do_PATCH(self):
        mid = self.path.rsplit("/", 1)[-1]
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or b"{}"))
        for m in MISSIONS:
            if m["id"] == mid:
                m["status"] = body.get("status", m["status"])
                return self._send(200, m)
        self._send(404, {"error": "no mission with that id"})
    def log_message(self, *a): pass

if __name__ == "__main__":
    print("mock Mission Log API on http://localhost:8080/api/missions", flush=True)
    HTTPServer(("127.0.0.1", 8080), H).serve_forever()
