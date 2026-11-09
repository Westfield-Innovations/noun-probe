"""A stand-in for the official address, served on this machine.

The tests point the reader at it, so they never reach the real address or
anything else outside this machine. The publication it serves has the shape
the publishing step writes, with stand-in words instead of the tool's words.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFIX = "/tools/noun-probe/"


def publication(**changes) -> dict:
    """A source.json as published. A change set to None leaves the field out."""
    data = {
        "tool": "Noun Probe",
        "edition": 1,
        "issued": "2026-11-06",
        "modes": ["AUDIT", "VISION"],
        "words": "STAND-IN WORDS",
        "official_address": "https://azus.ai/tools/noun-probe/",
        "toolbox_address": "https://azus.ai/tools/",
        "connections": [{"label": "Azus", "address": "https://azus.ai"}],
        "tools": [{"name": "Noun Probe", "address": "https://azus.ai/tools/noun-probe/"}],
        "terms": "1. Stand-in term one.\n2. Stand-in term two.",
    }
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def free_port() -> int:
    """A port on this machine that nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class StandIn:
    """Serves set answers under /tools/noun-probe/ and records every request."""

    def __init__(self):
        self.routes = {}
        self.requests = []
        self.headers = []

    def serve(self, path, body, status=200, headers=None):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.routes[PREFIX + path] = (status, body, headers or {})

    def __enter__(self):
        standin = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                standin.requests.append(self.path)
                standin.headers.append(dict(self.headers))
                status, body, headers = standin.routes.get(
                    self.path, (404, b"not found", {})
                )
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:{0}{1}".format(self.port, PREFIX)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
