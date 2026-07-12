#!/usr/bin/env python3
"""
tools/ui/server.py — the workbench's HTTP FACE over the actions catalog.

Transport only: routes JSON over actions.py, serves the static Lit app.
Zero logic beyond dispatch (the actions/faces boundary, 2026-07-12).
stdlib ThreadingHTTPServer — no dependencies, auditable in one read.
Failures are loud: an action raising returns 500 with the full traceback
in the JSON body, never a silent blank.

Run: python -m tools.ui [--port 8787]
"""

from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import actions

STATIC = Path(__file__).resolve().parent / "static"

ROUTES = {
    ("GET", "katas"): (actions.list_katas, []),
    ("GET", "flow"): (actions.flow, ["kata"]),
    ("GET", "witness"): (actions.witness, ["kata", "req_id"]),
    ("GET", "gate"): (actions.gate, ["kata", "name"]),
    ("GET", "evidence"): (actions.evidence, ["kata"]),
    ("GET", "adrs"): (actions.adrs, ["kata"]),
    ("POST", "run/eval"): (actions.run_eval, ["kata"]),
    ("POST", "run/proof"): (actions.run_proof, ["kata"]),
    ("POST", "run/regress"): (actions.run_regress, ["kata"]),
    ("POST", "run/lint"): (actions.run_lint, ["kata"]),
}

MIME = {".html": "text/html", ".js": "text/javascript",
        ".css": "text/css", ".json": "application/json",
        ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api(self, method: str):
        u = urlparse(self.path)
        route = u.path.removeprefix("/api/")
        entry = ROUTES.get((method, route))
        if entry is None:
            return self._json({"error": f"no action for {method} /api/{route}"}, 404)
        fn, params = entry
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        kwargs = {p: q[p] for p in params if p in q}
        try:
            return self._json(fn(**kwargs))
        except Exception:
            # loud by doctrine: full traceback in the body, never a count
            return self._json({"error": "action failed",
                               "traceback": traceback.format_exc()}, 500)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        rel = urlparse(self.path).path.lstrip("/") or "index.html"
        f = (STATIC / rel).resolve()
        if not f.is_file() or STATIC not in f.parents and f != STATIC / rel:
            return self._json({"error": f"not found: {rel}"}, 404)
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(f.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        return self._json({"error": "POST is /api/ only"}, 404)

    def log_message(self, fmt, *args):
        print(f"  [ui] {args[0]} {args[1]}")


def main(port: int = 8787):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"opis workbench — http://127.0.0.1:{port}  (Ctrl-C stops)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
