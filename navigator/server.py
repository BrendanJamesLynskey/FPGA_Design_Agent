"""The navigator's HTTP service: standard library only, 127.0.0.1 only.

What keeps it local and private:
- it binds to 127.0.0.1 and refuses any other host (``make_server``); nothing listens on a LAN address;
- every request's ``Host`` header must be the loopback address (or ``localhost``) and the port it is listening on, which stops a web page on
  another site (DNS rebinding) from talking to it;
- every request except the sign-in carries the session token, generated when the service starts and printed once on the terminal; the browser
  keeps it in an HttpOnly, SameSite=Strict cookie. A request without it gets 401;
- every request first calls the access gate (``agent.access.require``), so a revoked or expired key stops the service answering;
- a POST (an action) additionally needs ``Content-Type: application/json`` and an ``Origin`` that is the service's own, and only runs one of the
  fixed actions of ``health.Health.ACTIONS``;
- it never serves a file named by the request: ids are looked up in lists the service built itself;
- every JSON response passes ``redact.scrub``; every response carries a Content-Security-Policy that allows no external host, so a page cannot
  load a font, script or image from the network.
"""

from __future__ import annotations

import hmac
import json
import re
import secrets
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from navigator import health as H
from navigator import measure, redact
from navigator import sources as S

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
LOOPBACK = "127.0.0.1"
COOKIE = "fda_nav"
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/app.css": "app.css"}
CTYPE = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
#: CSP of the navigator's own pages: no inline script, no external host of any kind
CSP_APP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
#: CSP of the eye page (flow/eyescan/page.py is one self-contained file with inline script and style): still nothing external, and no network at all
CSP_EYE = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class App:
    """The service's state and routes, independent of the socket so tests can call it directly."""

    def __init__(self, root: Path, handoff: Path, runs_dir: Path | None = None, gate: Callable[[str], Any] | None = None, health: H.Health | None = None,
                 extra_captures: list[Path] | None = None, token: str | None = None):
        self.root, self.handoff = Path(root), Path(handoff)
        self.runs_dir = Path(runs_dir) if runs_dir else self.root / "runs"
        self.gate = gate or _default_gate
        self.health = health or H.Health(self.root, self.handoff)
        self.extra = extra_captures or []
        self.token = token or secrets.token_urlsafe(24)
        self.port = 0

    # -- the checks every request passes -------------------------------------------------------------------------------------------
    def host_ok(self, host: str | None) -> bool:
        return bool(host) and host in (f"{LOOPBACK}:{self.port}", f"localhost:{self.port}")

    def origin_ok(self, origin: str | None) -> bool:
        return origin is None or origin in (f"http://{LOOPBACK}:{self.port}", f"http://localhost:{self.port}")

    def token_ok(self, cookie_header: str | None, header_token: str | None) -> bool:
        cands = [header_token or ""]
        for part in (cookie_header or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                cands.append(v)
        return any(c and hmac.compare_digest(c.encode(), self.token.encode()) for c in cands)

    # -- routes: (status, content type, body bytes, extra headers) ----------------------------------------------------------------
    def json(self, status: int, obj: Any) -> tuple[int, str, bytes, dict[str, str]]:
        return status, "application/json; charset=utf-8", json.dumps(redact.scrub(obj), separators=(",", ":")).encode(), {"Content-Security-Policy": CSP_APP}

    def api(self, path: str, q: dict[str, list[str]]) -> tuple[int, str, bytes, dict[str, str]]:
        one = lambda k, d="": (q.get(k) or [d])[0]                 # noqa: E731
        r = self.root
        if path == "/api/session":
            return self.json(200, {"nav_value": self.token})
        if path == "/api/overview":
            return self.json(200, self.overview())
        if path == "/api/projects":
            return self.json(200, {"projects": S.project_list(r)})
        if path == "/api/project":
            v = S.project_tree(r, one("name")) if SEGMENT.match(one("name")) else None
            return self.json(200, v) if v else self.json(404, {"error": "no such managed project"})
        if path == "/api/scope":
            comps = [c for c in one("components").split(",") if c]
            v = S.scope_view(r, one("project"), comps, one("request")) if SEGMENT.match(one("project")) else None
            return self.json(200, v) if v else self.json(404, {"error": "no such managed project"})
        if path == "/api/latency":
            names = S.latency_designs(r)
            d = one("design") or (names[0] if names else "")
            v = S.latency_view(r, d) if d in names else None
            return self.json(200, {"designs": names, "latency": v, "builds": S.builds(r)})
        if path == "/api/runs":
            return self.json(200, {"runs": S.run_list(self.runs_dir, r), "dir": "runs/"})
        if path == "/api/run":
            v = S.run_detail(self.runs_dir, one("id"), r)
            return self.json(200, v) if v else self.json(404, {"error": "no such run"})
        if path == "/api/captures":
            return self.json(200, {"captures": measure.listing(r, self.extra)})
        if path == "/api/measures":
            return self.json(200, {"board": S.board_records(r), "ppm": S.ppm_records(r), "rm_latency": S.sim_latency_records(r)})
        if path == "/api/record":
            v = S.read_record(r, one("file"))
            return self.json(200, v) if v else self.json(404, {"error": "not a record the navigator shows"})
        if path == "/api/health":
            return self.json(200, self.health.all())
        if path == "/api/models":
            return self.json(200, self.health.models_view())
        return self.json(404, {"error": "no such endpoint"})

    def eye_page(self, q: dict[str, list[str]]) -> tuple[int, str, bytes, dict[str, str]]:
        ids = [i for i in (q.get("a", [""])[0], q.get("b", [""])[0]) if i]
        html = measure.page(self.root, ids, self.extra) if ids else None
        if html is None:
            return 404, "text/plain; charset=utf-8", b"no such capture", {}
        return 200, "text/html; charset=utf-8", html.encode(), {"Content-Security-Policy": CSP_EYE}

    def action(self, name: str) -> tuple[int, str, bytes, dict[str, str]]:
        if name not in H.Health.ACTIONS:
            return self.json(404, {"error": "no such action"})
        return self.json(200, self.health.run_action(name))

    def overview(self) -> dict[str, Any]:
        runner = self.health.runner
        rc, head, _ = runner.run(["git", "-C", str(self.root), "rev-parse", "--short=8", "HEAD"], timeout=10)
        rc2, br, _ = runner.run(["git", "-C", str(self.root), "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
        return {"repo": self.root.name, "commit": head.strip() if rc == 0 else None, "branch": br.strip() if rc2 == 0 else None,
                "projects": len(S.design_dirs(self.root)), "latency_designs": S.latency_designs(self.root), "builds": len(S.builds(self.root)),
                "captures": len(S.capture_files(self.root, self.extra)),
                "synthetic_captures": sum(1 for c in measure.listing(self.root, self.extra) if c["synthetic"]),
                "binds": f"{LOOPBACK}:{self.port}", "pages": ["Project", "Timing", "Runs", "Measurements", "Health", "Models"]}


def _default_gate(entry: str) -> Any:
    from agent import access
    return access.require(entry)


def static_file(name: str) -> tuple[int, str, bytes, dict[str, str]]:
    p = STATIC / name
    return 200, CTYPE[p.suffix], p.read_bytes(), {"Content-Security-Policy": CSP_APP}


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "fda-navigator"
        sys_version = ""
        protocol_version = "HTTP/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:               # no access log: URLs can hold ids, and the terminal holds the token
            pass

        def _send(self, status: int, ctype: str, body: bytes, extra: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _refuse(self, status: int, why: str) -> None:
            self._send(status, "text/plain; charset=utf-8", why.encode(), {"Content-Security-Policy": CSP_APP})

        def _common(self) -> tuple[Any, dict[str, list[str]]] | None:
            """The checks every request passes; returns the parsed URL, or None after answering a refusal."""
            if not app.host_ok(self.headers.get("Host")):
                self._refuse(421, "wrong Host header: this service answers only on its own loopback address")
                return None
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/" and q.get("t") and hmac.compare_digest(q["t"][0].encode(), app.token.encode()):
                self._send(303, "text/plain; charset=utf-8", b"", {"Location": "/", "Set-Cookie": f"{COOKIE}={app.token}; HttpOnly; SameSite=Strict; Path=/"})
                return None
            if not app.token_ok(self.headers.get("Cookie"), self.headers.get("X-Navigator-Token")):
                self._refuse(401, "sign-in required: open the address with the token that `python -m navigator` printed")
                return None
            try:
                app.gate("python -m navigator")
            except Exception as e:                                         # AccessDenied: the message never holds a key
                self._refuse(403, f"access gate: {redact.text(str(e))[:200]}")
                return None
            return u, q

        def do_GET(self) -> None:
            c = self._common()
            if c is None:
                return
            u, q = c
            try:
                if u.path in STATIC_FILES:
                    res = static_file(STATIC_FILES[u.path])
                elif u.path == "/measure/page":
                    res = app.eye_page(q)
                elif u.path.startswith("/api/"):
                    res = app.api(u.path, q)
                else:
                    res = 404, "text/plain; charset=utf-8", b"not found", {}
            except Exception:                                              # never send a traceback (it can carry paths and values)
                traceback.print_exc(file=sys.stderr)
                res = app.json(500, {"error": "internal error; see the terminal"})
            self._send(*res)

        def do_POST(self) -> None:
            c = self._common()
            if c is None:
                return
            u, _ = c
            if not app.origin_ok(self.headers.get("Origin")) or (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                self._refuse(403, "an action needs the service's own Origin and Content-Type: application/json")
                return
            m = re.fullmatch(r"/api/action/([a-z_]+)", u.path)
            if not hmac.compare_digest((self.headers.get("X-Navigator-Token") or "").encode(), app.token.encode()):
                self._refuse(403, "an action needs the token in the X-Navigator-Token header (the cookie alone is not enough)")
                return
            try:
                n = max(0, min(int(self.headers.get("Content-Length") or 0), 4096))
                self.rfile.read(n)                                         # the body is ignored: an action takes no argument
                res = app.action(m.group(1)) if m else app.json(404, {"error": "no such endpoint"})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                res = app.json(500, {"error": "internal error; see the terminal"})
            self._send(*res)

        do_PUT = do_DELETE = do_PATCH = lambda self: self._refuse(405, "read-only service: GET, plus POST for the fixed actions")

    return Handler


def make_server(app: App, host: str = LOOPBACK, port: int = 8765) -> ThreadingHTTPServer:
    if host != LOOPBACK:
        raise ValueError(f"the navigator binds to {LOOPBACK} only (asked for {host!r})")
    srv = ThreadingHTTPServer((host, port), make_handler(app))
    app.port = srv.server_address[1]
    return srv
