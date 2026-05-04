#!/usr/bin/env python3
"""Governance Dashboard server — port 5056."""
import json, os, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

PORT = 5056
DASHBOARD_DIR = Path(__file__).parent
STATE_FILE = DASHBOARD_DIR / "state.json"
DEFAULT_STATE = {
    "pipeline": "governed-dev",
    "stages": {
        "critical":     {"status": "pending", "output": "", "started": None, "completed": None},
        "fetch":        {"status": "pending", "output": "", "started": None, "completed": None},
        "thinking":     {"status": "pending", "output": "", "started": None, "completed": None},
        "implement":    {"status": "pending", "output": "", "started": None, "completed": None},
        "review":       {"status": "pending", "output": "", "started": None, "completed": None},
        "meta_review":  {"status": "pending", "output": "", "started": None, "completed": None},
        "verify":       {"status": "pending", "output": "", "started": None, "completed": None},
        "evolve":       {"status": "pending", "output": "", "started": None, "completed": None},
    },
    "activity_log": [],
    "intent_packet": {},
    "dispatch_plan": {},
    "active_task": "",
    "session_id": ""
}

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return DEFAULT_STATE.copy()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self.serve_file("index.html", "text/html")
            elif path == "/style.css":
                self.serve_file("style.css", "text/css")
            elif path == "/app.js":
                self.serve_file("app.js", "application/javascript")
            elif path == "/api/state":
                self.respond_json(load_state())
            elif path == "/favicon.ico":
                self.send_response(204); self.end_headers()
            else:
                self.send_error(404)
        except Exception as exc:
            self.send_error(500, str(exc))

    def serve_file(self, filename, mime):
        filepath = DASHBOARD_DIR / filename
        if not filepath.exists():
            self.send_error(404)
            return
        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return  # silence


# Initialize state file if missing
if not STATE_FILE.exists():
    STATE_FILE.write_text(json.dumps(DEFAULT_STATE, indent=2))

if __name__ == "__main__":
    print(f"Governance Dashboard on http://0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
