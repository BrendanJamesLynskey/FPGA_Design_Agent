"""The navigator's HTTP service: standard library only, 127.0.0.1 only.

What keeps it local and private:
- it binds to 127.0.0.1 and refuses any other host (``make_server``); nothing listens on a LAN address;
- every request's ``Host`` header must be the loopback address (or ``localhost``) and the port it is listening on, which stops a web page on
  another site (DNS rebinding) from talking to it;
- every request except the sign-in carries the session token, generated when the service starts and printed once on the terminal; the browser
  keeps it in an HttpOnly, SameSite=Strict cookie. A request without it gets 401;
- every request first calls the access gate (``agent.access.require``), so a revoked or expired key stops the service answering;
- a POST (an action) additionally needs ``Content-Type: application/json`` and an ``Origin`` that is the service's own, and only runs one of the
  fixed actions of ``health.Health.ACTIONS`` or the fixed run and board routes (stage 2) and, for stage 3, ``/api/run/ask``, ``/api/run/request`` and ``/api/run/answer``, each
  with a confirmation field and only the keys the route takes;
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

from navigator import ask as NA
from navigator import boardops, guards, measure, redact, runctl
from navigator import examples as EX
from navigator import console as NC
from navigator import summary as NS
from navigator import health as H
from navigator import progress as PG
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
                 extra_captures: list[Path] | None = None, token: str | None = None, state_dir: Path | None = None, config_dir: Path | None = None,
                 spawner: runctl.Spawner | None = None, transport: boardops.Transport | None = None, killpg: Any = None):
        self.root, self.handoff = Path(root), Path(handoff)
        self.ask_llm: Callable[[str, str], Any] | None = None       # tests inject a fake model call; None = the model table's review purpose
        self.runs_dir = Path(runs_dir) if runs_dir else self.root / "runs"
        self.gate = gate or _default_gate
        self.health = health or H.Health(self.root, self.handoff)
        self.extra = extra_captures or []
        self.token = token or secrets.token_urlsafe(24)
        self.port = 0
        self.state_dir = Path(state_dir) if state_dir else Path.home() / ".local" / "state" / "fpga_design_agent" / "navigator"
        self.config_dir = Path(config_dir) if config_dir is not None else self.health.config_dir
        self.perm_file = self.config_dir / "permissions.yaml"           # brief 222: the saved permission settings; `python -m agent` reads the same file
        self.runctl = runctl.RunControl(self.root, self.handoff, self.runs_dir, self.health.runner, self.state_dir, lambda: self.health._cached("models_view", self.health.models_view),
                                        spawner=spawner, gate=self.gate, perm_file=self.perm_file, **({"killpg": killpg} if killpg else {}))
        self.runctl.reconcile()
        self.board = boardops.BoardOps(self.handoff, self.health.runner, config_dir if config_dir is not None else self.health.config_dir,
                                       transport or boardops.VivadoTransport(self.state_dir / "board"))

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
        if path == "/api/live":
            return self.json(200, {"runs": PG.live_list(self.runs_dir, 15), "started": self.runctl.records(), "dir": "runs/"})
        if path == "/api/live/run":
            v = PG.run_progress(self.runs_dir, one("id"), tail=int(one("tail", "40")) if one("tail", "40").isdigit() else 40)
            return self.json(200, v) if v else self.json(404, {"error": "no such run"})
        if path == "/api/live/summary":
            v = NS.summarise(self.runs_dir, one("id")) if self.known_run(one("id")) else None
            return self.json(200, v) if v else self.json(404, {"error": "no such run"})
        if path == "/api/live/requests":
            v = NS.summarise(self.runs_dir, one("id")) if self.known_run(one("id")) else None
            if not v:
                return self.json(404, {"error": "no such run"})
            return self.json(200, {"id": v["id"], "requests": v["requests"], "pending": v["pending"], "mode": v["mode"], "qa": [
                {k: r.get(k) for k in ("when", "q", "a", "cited", "records_read", "model", "cost_usd", "plan_estimate_usd")} for r in NA.history(self.runs_dir / v["id"])[-20:]],
                "qa_spent_usd": round(NA.spent(self.runs_dir / v["id"])[0], 4), "qa_cap_usd": NA.QA_USD, "qa_max": NA.QA_MAX})
        if path == "/api/console/steps":
            v = NC.steps(self.runs_dir, one("id")) if self.known_run(one("id")) else None
            return self.json(200, v) if v else self.json(404, {"error": "no such run"})
        if path == "/api/console/read":
            off = one("offset")
            v = NC.read(self.runs_dir, one("id"), one("step"), int(off) if off.isdigit() else None) if self.known_run(one("id")) else None
            return self.json(200, v) if v else self.json(404, {"error": "no such step"})
        if path == "/api/examples":
            return self.json(200, {**EX.listing(self.root), "runs": EX.example_runs(self.runs_dir, PG.run_ids(self.runs_dir, 200)), "started": self.runctl.records(), "usage": self.health.usage(), "slots": self.health.locks()})
        if path == "/api/examples/compare":
            v = EX.comparison(self.runs_dir, one("id")) if self.known_run(one("id")) else None
            return self.json(200, v) if v else self.json(404, {"error": "no example result in that run"})
        if path == "/api/start/options":
            return self.json(200, {**self.runctl.options(), "usage": self.health.usage(), "slots": self.health.locks(), "started": self.runctl.records()})
        if path == "/api/board":
            return self.json(200, {**self.board.listing(), "permission": self.board_permission()})
        if path == "/api/permissions":
            return self.json(200, self.permissions_view(one("project")))
        if path == "/api/trace":
            return self.json(200, S.trace_view(r))
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

    def post(self, path: str, body: Any) -> tuple[int, str, bytes, dict[str, str]]:
        """The POST routes: the fixed health actions, and (stage 2) start/stop a run and a read-only board action. Each takes a small JSON body."""
        m = re.fullmatch(r"/api/action/([a-z_]+)", path)
        if m:
            return self.action(m.group(1))
        if not isinstance(body, dict):
            return self.json(400, {"error": "the body must be a JSON object"})
        if path == "/api/run/start":
            return self.json(200, self.runctl.start(body))
        if path == "/api/run/stop":
            return self.json(200, self.runctl.stop(body.get("id")))
        if path in ("/api/run/ask", "/api/run/request", "/api/run/answer"):
            return self.live_post(path, body)
        if path == "/api/permissions/save":
            return self.permissions_save(body)
        if path == "/api/board/run":
            try:
                self.gate("python -m navigator (board action)")
            except Exception as e:
                return self.json(403, {"ok": False, "refused": "access gate: " + redact.text(str(e))[:160]})
            if body.get("confirm") != "read":
                return self.json(200, {"ok": False, "refused": "a board action needs the confirmation the page sends"})
            bp = self.board_permission()
            if bp["result"] == "deny":                                # brief 222: the default settings turn the read-only board actions off
                return self.json(200, {"ok": False, "refused": f"read-only board actions are off in the saved permission settings ({bp['by']}); change them on the Permissions page"})
            return self.json(200, self.board.run(body.get("board"), body.get("action")))
        return self.json(404, {"error": "no such endpoint"})

    # -- permissions (brief 222) --------------------------------------------------------------------------------------------------------
    def board_permission(self) -> dict[str, Any]:
        """The read-only board actions against the default settings: ``deny`` refuses them; ``ask`` and ``allow`` both go on, because every board action already
        needs the confirmation the page sends (that click is the ask)."""
        from agent.core import permissions as P
        spec = self.runctl.saved_permissions(None)
        d = P.Policy.from_spec(spec).decide("read_board", log=False)
        return {"result": d.result, "by": d.by, "mode": spec["mode"]}

    def permissions_view(self, project: str) -> dict[str, Any]:
        from agent.core import permissions as P
        names = self.runctl.permission_options()["projects"]
        proj = project if project and project in names else ""
        spec = self.runctl.saved_permissions(proj or None)
        pol = P.Policy.from_spec(spec)
        eff = {a.name: {"value": pol.base(a.name)[0], "rule": pol.base(a.name)[1]} for a in P.ACTIONS}
        flags = ["--permissions", spec["mode"], *sum((["--allow" if v == P.ALLOW else "--deny" if v == P.DENY else "--ask", k] for k, v in sorted(spec["overrides"].items())
                                                      if v != P.MODES[spec["mode"]]["actions"][k]), [])]
        return {**P.view(), "projects": names, "project": proj, "settings": {k: spec[k] for k in ("mode", "overrides", "source", "ask_above_usd", "saved")},
                "effective": eff, "file": str(self.perm_file), "cli": "python -m agent run <spec> " + " ".join(flags),
                "stops": "A run started from the Start page stops after stage 8, so it never reaches the board; Full auto reaches the board only from the command line."}

    def permissions_save(self, body: dict[str, Any]) -> tuple[int, str, bytes, dict[str, str]]:
        from agent.core import permissions as P
        extra = sorted(set(body) - {"project", "mode", "overrides", "ask_above_usd", "confirm"})
        if extra:
            return self.json(200, {"ok": False, "refused": "the request has fields this action does not take: " + ", ".join(redact.text(str(k))[:20] for k in extra[:5])})
        if body.get("confirm") != "save":
            return self.json(200, {"ok": False, "refused": "saving permissions needs the confirmation the page sends"})
        try:
            self.gate("python -m navigator (save permissions)")
        except Exception as e:
            return self.json(403, {"ok": False, "refused": "access gate: " + redact.text(str(e))[:160]})
        names = self.runctl.permission_options()["projects"]
        project = body.get("project") or None
        if project is not None and project not in names:
            return self.json(200, {"ok": False, "refused": "pick a project from the list (or none, for the default)"})
        ask_above = body.get("ask_above_usd")
        if ask_above is not None and (isinstance(ask_above, bool) or not isinstance(ask_above, (int, float)) or not (0 <= ask_above <= runctl.MAX_USD)):
            return self.json(200, {"ok": False, "refused": f"the ask-above amount is between 0 and ${runctl.MAX_USD:g}"})
        try:
            P.save_config(project, body.get("mode"), body.get("overrides") or {}, ask_above, self.perm_file)
        except (ValueError, TypeError, AttributeError) as e:
            return self.json(200, {"ok": False, "refused": redact.text(str(e))[:200]})
        return self.json(200, {"ok": True, **self.permissions_view(project or "")})

    def known_run(self, rid: str) -> bool:
        """The run is one of the directories this service lists: a request never names a path."""
        return isinstance(rid, str) and rid in PG.run_ids(self.runs_dir, 200)

    def live_post(self, path: str, body: dict[str, Any]) -> tuple[int, str, bytes, dict[str, str]]:
        """Stage 3 actions on a run: ask a question, queue a request, answer a pending question. Fixed keys only; a key the route does not know is refused."""
        try:
            self.gate("python -m navigator (run request)")
        except Exception as e:
            return self.json(403, {"ok": False, "refused": "access gate: " + redact.text(str(e))[:160]})
        spec = {"/api/run/ask": ("ask", {"id", "question", "confirm"}), "/api/run/request": ("request", {"id", "kind", "action", "stage", "text", "confirm"}),
                "/api/run/answer": ("answer", {"id", "answer", "confirm"})}[path]
        extra = sorted(set(body) - spec[1])
        if extra:
            return self.json(200, {"ok": False, "refused": "the request has fields this action does not take: " + ", ".join(redact.text(str(k))[:20] for k in extra[:5])})
        if body.get("confirm") != spec[0]:
            return self.json(200, {"ok": False, "refused": f"this needs the confirmation the page sends ({spec[0]})"})
        rid = body.get("id")
        if not self.known_run(rid):
            return self.json(200, {"ok": False, "refused": "pick a run from the list"})
        try:
            if path == "/api/run/ask":
                r = NA.ask(self.runs_dir, rid, body.get("question"), llm=self.ask_llm)
                return self.json(200, {"ok": True, **r})
            if path == "/api/run/request":
                from agent.core.session import STAGES
                from agent.graph import requests as rq
                kind = body.get("kind")
                if kind == "control":
                    if body.get("text") is not None:
                        raise rq.RequestError("a control request takes no text")
                    act = body.get("action")
                    if not isinstance(act, str) or act not in rq.CONTROL:
                        raise rq.RequestError("action must be one of " + ", ".join(rq.CONTROL))
                    r = rq.submit(self.runs_dir / rid, control=act, stage=body.get("stage"), source="navigator", stages=tuple(STAGES))
                elif kind == "design":
                    if body.get("action") is not None or body.get("stage") is not None:
                        raise rq.RequestError("a design request takes only text")
                    if not isinstance(body.get("text"), str):
                        raise rq.RequestError("the request text must be a string")
                    r = rq.submit(self.runs_dir / rid, design=body["text"], source="navigator", stages=tuple(STAGES))
                else:
                    raise rq.RequestError("kind must be control or design")
                return self.json(200, {"ok": True, "request": {k: r.get(k) for k in ("id", "kind", "action", "stage", "status", "applies", "affects")}, "what": r.get("text")})
            r = self.runctl.start({"kind": "answer", "run": rid, "answer": body.get("answer"), "confirm": "start"})
            return self.json(200, {**r, "ok": bool(r.get("started"))})
        except (NA.AskError, ValueError) as e:                    # AskError and RequestError (both ValueError): the reason, nothing was done
            return self.json(200, {"ok": False, "refused": redact.text(str(e))[:300]})

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
                "binds": f"{LOOPBACK}:{self.port}", "pages": ["Project", "Timing", "Runs", "Live", "Start", "Permissions", "Examples", "Board", "Measurements", "Health", "Models"]}


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
            if not hmac.compare_digest((self.headers.get("X-Navigator-Token") or "").encode(), app.token.encode()):
                self._refuse(403, "an action needs the token in the X-Navigator-Token header (the cookie alone is not enough)")
                return
            try:
                n = max(0, min(int(self.headers.get("Content-Length") or 0), 16384))
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw) if raw.strip() else {}
                except ValueError:
                    body = None
                res = app.post(u.path, body)
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
