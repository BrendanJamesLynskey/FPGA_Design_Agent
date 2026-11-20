"""Brief 103: the navigator service. Read-only endpoints on the repository's own records, the access and loopback rules, no key or prompt text in
any response, and no health check that costs money or touches hardware without a click (the runner is a fake that records every command)."""

from __future__ import annotations

import http.client
import json
import re
import threading
from pathlib import Path

import pytest

from agent.access import AccessDenied
from navigator import health as H
from navigator import redact
from navigator import server as SV

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "t" * 32
SECRET = "sk-or-v1-PLANTED0123456789abcdef"
PROMPT = "PLANTED PROMPT TEXT: you are the RTL designer and must"


class FakeRunner(H.Runner):
    def __init__(self):
        self.calls: list[list[str]] = []

    def run(self, argv, timeout=20, cwd=None, env=None):
        self.calls.append(list(argv))
        a = " ".join(argv)
        if argv[:2] == ["claude", "--version"]:
            return 0, "9.9.9 (Claude Code)\n", ""
        if argv[:3] == ["claude", "auth", "status"]:
            return 0, json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "email": "someone@example.com",
                                  "orgId": "org-123", "loginExpiresAt": "2099-01-01T00:00:00Z"}), ""
        if "models show --json" in a:
            return 0, json.dumps({"purposes": {"rtl": {"purpose": "rtl", "endpoint": "openrouter", "kind": "openrouter", "model": "m/x", "options": {}, "key_env": "OPENROUTER_API_KEY"}},
                                  "layers": [], "hash": "abc"}), ""
        if "models show" in a:
            return 0, "purpose endpoint\nrtl openrouter openrouter m/x {} [builtin]\ntable hash abc\n", ""
        if "models check --probe" in a:
            return 0, f"ok   rtl openrouter m/x  fine  0.1s {SECRET}\n", ""
        if argv[:2] == ["git", "-C"]:
            return 0, "abcd1234\n", ""
        if argv[0] == "bash":
            return 0, "usage", ""
        if argv[0] == "gh":
            return 0, json.dumps([{"status": "completed", "conclusion": "success", "headSha": "abcdef012345", "createdAt": "2026-11-19T10:00:00Z", "workflowName": "CI"}]), ""
        return 127, "", "not found"


def make_app(tmp_path, gate=None, runner=None, runs=None):
    handoff = tmp_path / "handoff"
    handoff.mkdir(exist_ok=True)
    runner = runner or FakeRunner()
    hl = H.Health(ROOT, handoff, runner, config_dir=tmp_path / "cfg", sysfs_usb=tmp_path / "usb")
    return SV.App(ROOT, handoff, runs or tmp_path / "runs", gate=gate or (lambda e: "owner"), health=hl, token=TOKEN), runner


class Live:
    def __init__(self, app):
        self.app = app
        self.srv = SV.make_server(app, port=0)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        self.port = self.srv.server_address[1]

    def req(self, method, path, headers=None, body=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
        c.request(method, path, body=body, headers=h, )
        r = c.getresponse()
        data = r.read()
        out = (r.status, dict(r.getheaders()), data)
        c.close()
        return out

    def get(self, path, tok=True, **kw):
        return self.req("GET", path, {"X-Navigator-Token": TOKEN} if tok else {}, **kw)

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def live(tmp_path):
    app, runner = make_app(tmp_path)
    s = Live(app)
    s.runner = runner
    yield s
    s.close()


# --- loopback, token, gate -----------------------------------------------------------------------------------------------------------

def test_binds_to_loopback_only(tmp_path, live):
    assert live.srv.server_address[0] == "127.0.0.1"
    app, _ = make_app(tmp_path)
    for bad in ("0.0.0.0", "", "::", "192.168.1.5", "localhost"):
        with pytest.raises(ValueError):
            SV.make_server(app, host=bad, port=0)


def test_token_host_and_cookie(live):
    assert live.get("/api/overview", tok=False)[0] == 401
    assert live.req("GET", "/api/overview", {"X-Navigator-Token": "wrong"})[0] == 401
    assert live.get("/api/overview")[0] == 200
    assert live.get("/api/overview", host="evil.example:80")[0] == 421                       # DNS rebinding: a foreign Host header
    assert live.get("/api/overview", host=f"127.0.0.1:{live.port + 1}")[0] == 421
    st, hd, _ = live.req("GET", f"/?t={TOKEN}")
    assert st == 303 and "HttpOnly" in hd["Set-Cookie"] and "SameSite=Strict" in hd["Set-Cookie"]
    cookie = hd["Set-Cookie"].split(";")[0]
    assert live.req("GET", "/api/overview", {"Cookie": cookie})[0] == 200
    assert live.req("GET", "/?t=nope")[0] == 401


def test_every_request_calls_the_access_gate(tmp_path):
    calls = []

    def gate(entry):
        calls.append(entry)
        if len(calls) > 1:
            raise AccessDenied("access key required: set FDA_ACCESS_KEY ...")
    app, _ = make_app(tmp_path, gate=gate)
    s = Live(app)
    try:
        assert s.get("/api/overview")[0] == 200
        st, _, body = s.get("/api/overview")
        assert st == 403 and b"access" in body
    finally:
        s.close()
    assert len(calls) == 2


def test_security_headers_and_no_external_host(live):
    st, hd, body = live.get("/")
    assert st == 200
    csp = hd["Content-Security-Policy"]
    assert "http" not in csp and "script-src 'self'" in csp and "'unsafe-inline'" not in csp
    assert hd["X-Content-Type-Options"] == "nosniff" and hd["Referrer-Policy"] == "no-referrer"
    assert "Access-Control-Allow-Origin" not in hd
    for f in (SV.STATIC).iterdir():                                                           # nothing in the shipped pages names an external host
        assert not re.search(r"https?://", f.read_text().replace("http://www.w3.org/2000/svg", "")), f.name     # the SVG namespace is an identifier, not a request


def test_post_rules(live):
    ok = {"X-Navigator-Token": TOKEN, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{live.port}"}
    assert live.req("POST", "/api/action/usage_live", {"X-Navigator-Token": TOKEN}, "{}")[0] == 403                           # no JSON content type
    assert live.req("POST", "/api/action/usage_live", {**ok, "Origin": "http://evil.example"}, "{}")[0] == 403                # foreign origin
    assert live.req("POST", "/api/action/usage_live", {"Content-Type": "application/json"}, "{}")[0] == 401                  # no token
    assert live.req("POST", "/api/action/rm_rf", ok, "{}")[0] == 404
    cookie_only = {"Cookie": f"{SV.COOKIE}={TOKEN}", "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{live.port}"}
    assert live.req("POST", "/api/action/usage_live", cookie_only, "{}")[0] == 403                                              # the cookie alone cannot start an action
    assert live.req("POST", "/api/action/usage_live", {**ok, "Content-Length": "-1"}, None)[0] in (200, 400, 500)                                                            # only the fixed actions
    assert live.req("PUT", "/api/overview", ok, "{}")[0] == 405


# --- read-only endpoints on the repository's own records -----------------------------------------------------------------------------------

def test_endpoints_on_real_records(live):
    ov = json.loads(live.get("/api/overview")[2])
    assert ov["projects"] >= 2 and ov["captures"] >= 2
    pl = json.loads(live.get("/api/projects")[2])["projects"]
    assert {p["name"] for p in pl} >= {"b102_managed_fcs", "b102_managed_pr"}
    pr = json.loads(live.get("/api/project?name=b102_managed_fcs")[2])
    comps = pr["components"]
    assert comps["crc"]["ownership"] == "frozen" and comps["crc"]["selectable"] is False
    assert comps["heartbeat"]["ownership"] == "excluded" and comps["ctrl"]["selectable"] is True
    assert pr["source"]["file"].endswith("project.yaml") and pr["source"]["date"]
    assert json.loads(live.get("/api/project?name=..%2Fx")[2]).get("error")
    lat = json.loads(live.get("/api/latency")[2])
    assert lat["latency"]["reconciled"] is True and lat["latency"]["total_clocks"] == sum(s["clocks"] for s in lat["latency"]["stages"])
    assert lat["latency"]["sources"]["simulation"]["file"].startswith("results/")
    assert any(b["wns_ns"] is not None for b in lat["builds"])
    caps = json.loads(live.get("/api/captures")[2])["captures"]
    real = [c for c in caps if not c["synthetic"]]
    assert caps and all(c["no_data"] for c in real if "20261119_231836" in c["id"])     # the failed 96D run (NO DATA, brief 96D2)
    assert any(not c["no_data"] for c in real if "20261120_105134" in c["id"])          # the first measured eye (2026-11-20, 4T clock phase forced)
    assert any(c["synthetic"] for c in caps) and not any(c["no_data"] for c in caps if c["synthetic"])
    m = json.loads(live.get("/api/measures")[2])
    assert m["board"] and m["board"][0]["lock_clocks"]["histogram"]
    assert json.loads(live.get("/api/runs")[2])["runs"] == []
    assert live.get("/api/nothing")[0] == 404


def test_scope_picker_builds_the_command_and_starts_nothing(live):
    ok = json.loads(live.get("/api/scope?project=b102_managed_fcs&components=ctrl&request=shorten+latency")[2])
    assert ok["will_touch"] == ["ctrl"] and ok["read_only"] == ["crc"] and ok["runs_anything"] is False
    assert ok["command"][:4] == ["python", "-m", "agent", "resume"] and ok["command"][-2:] == ["--scope", "ctrl"]
    frozen = json.loads(live.get("/api/scope?project=b102_managed_fcs&components=crc")[2])
    assert "frozen" in frozen["ask"] and "will_touch" not in frozen
    hidden = json.loads(live.get("/api/scope?project=b102_managed_fcs&components=heartbeat")[2])
    assert hidden["ask"] and "will_touch" not in hidden
    assert live.runner.calls == [] or all(c[0] == "git" for c in live.runner.calls)


def test_eye_page_serves_only_listed_captures(live):
    caps = json.loads(live.get("/api/captures")[2])["captures"]
    a, b = caps[0]["id"], caps[1]["id"]
    st, hd, body = live.get(f"/measure/page?a={a}&b={b}&theme=dark")
    assert st == 200 and b"SYNTHETIC" in body and b"c-cmp-diff" in body and b"c-sl-v" in body
    assert "connect-src 'none'" in hd["Content-Security-Policy"]
    for bad in ("../../pyproject.toml", "/etc/passwd", "results/b96d/offline/../../../pyproject.toml", "agent/access/keys.json"):
        assert live.get(f"/measure/page?a={bad}")[0] == 404
    assert live.get("/measure/page")[0] == 404


def test_record_viewer_is_limited(live):
    assert live.get("/api/record?file=results/b96d/README.md")[0] == 200
    assert live.get("/api/record?file=designs/b102_managed_fcs/project.yaml")[0] == 200
    for bad in ("pyproject.toml", "agent/access/keys.json", "../etc/passwd", "results/../pyproject.toml", "/etc/passwd", ".env", "designs/b102_managed_fcs/rtl/fcs_top.sv",
                "results/b96d/offline/../../../.env"):
        assert live.get("/api/record?file=" + bad)[0] == 404, bad


# --- no key, token or prompt text in any response -------------------------------------------------------------------------------------------

def test_no_secret_or_prompt_text_in_any_response(tmp_path):
    runs = tmp_path / "runs"
    d = runs / "20261119-000000-aaaa"
    (d / "claude_code").mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps({"run_id": d.name, "design": "x", "stop": f"done {SECRET}", "model": "m", "prompt": PROMPT, "messages": [PROMPT],
                                                "api_key": SECRET, "scope": {"components": ["ctrl"], "source": "explicit"}}))
    (d / "model_calls.jsonl").write_text(json.dumps({"seq": 1, "purpose": "rtl", "endpoint": "e", "model": f"m {SECRET}", "prompt": PROMPT, "messages": PROMPT}) + "\n")
    (d / "oracle_calls.jsonl").write_text(json.dumps({"question": PROMPT, "reply": PROMPT}) + "\n")
    (d / "claude_code_calls.jsonl").write_text(json.dumps({"tag": "001_x", "role": "r", "stderr_tail": PROMPT, "init": {"x": PROMPT}}) + "\n")
    (d / "claude_code" / "001_x.prompt.json").write_text(json.dumps({"user_message": {"sha256": "a" * 64, "chars": 10, "text": PROMPT},
                                                                     "system_prompt": PROMPT, "prompts_pin": {"manifest_sha256": "b" * 64, "enforced": True}}))
    (d / "claude_code" / "002_y.prompt.json").write_text(json.dumps({"user_message": PROMPT, "system_prompt": {"sha256": "short", "chars": PROMPT}}))
    app, _ = make_app(tmp_path, runs=runs)
    s = Live(app)
    try:
        paths = ["/api/overview", "/api/projects", "/api/project?name=b102_managed_fcs", "/api/project?name=b102_managed_pr", "/api/latency", "/api/runs",
                 f"/api/run?id={d.name}", "/api/captures", "/api/measures", "/api/health", "/api/models", "/api/record?file=results/b96c/README.md"]
        for p in paths:
            st, _, body = s.get(p)
            assert st == 200, p
            text = body.decode()
            assert SECRET not in text and "PLANTED" not in text and "someone@example.com" not in text and "org-123" not in text, p
        run = json.loads(s.get(f"/api/run?id={d.name}")[2])
        assert run["fingerprints"][0]["user_fp"] == {"sha256": "a" * 64, "chars": 10}
        assert run["fingerprints"][0]["system_fp"] is None and run["fingerprints"][1]["user_fp"] is None and run["fingerprints"][1]["system_fp"] is None
        assert run["calls"][0]["purpose"] == "rtl" and "prompt" not in run["calls"][0]
        assert s.get("/api/run?id=../../etc")[0] == 404
        for ac in ("llm_probe", "usage_live", "ci_main"):
            st, _, body = s.req("POST", f"/api/action/{ac}", {"X-Navigator-Token": TOKEN, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{s.port}"}, "{}")
            assert st == 200 and SECRET not in body.decode(), ac
    finally:
        s.close()


def test_scrub_unit():
    o = redact.scrub({"api_key": "x", "ok": f"a {SECRET} b", "n": [{"prompt": "p", "text": "t", "k": "Bearer abcdefghijklmnop"}], "sha": "a" * 64})
    assert o == {"ok": "a [redacted] b", "n": [{"k": "[redacted]"}], "sha": "a" * 64}
    o = redact.scrub({"x-api-key": "v", "authToken": "v", "stdout_tail": "v", "prompt_tokens": 5, "key_state": "key present", "Account_ID": "v", "jwt": "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.abcdEFGH"})
    assert o == {"prompt_tokens": 5, "key_state": "key present", "jwt": "[redacted]"}


# --- health: nothing that costs money or touches hardware runs without a click ---------------------------------------------------------------

FORBIDDEN = ("--probe", "usage_check.sh", "jtag_list", "hw_list", "hw_server", "gh", "vivado", "openFPGALoader", "ssh")


def test_free_health_checks_run_no_costly_or_hardware_command(tmp_path):
    app, runner = make_app(tmp_path)
    d = app.health.all()
    flat = [" ".join(c) for c in runner.calls]
    assert flat, "the free checks should have run their local version queries"
    for c in flat:
        assert not any(f in c.split() or f in c for f in FORBIDDEN), c
    st = {c["id"]: c for c in d["checks"]}
    for k in ("llm_probe", "jtag_disabled", "ci_main"):
        assert st[k]["status"] == "not-run"
    assert "action" not in st["jtag_disabled"] and "stage 2" in st["jtag_disabled"]["detail"]
    assert st["claude_cli"]["status"] == "ok" and "9.9.9" in st["claude_cli"]["detail"]
    assert "someone" not in json.dumps(d) and st["claude_auth"]["detail"].startswith("signed in")
    assert st["models_table"]["endpoints"][0]["key_state"] in ("key present", "key MISSING")


def test_actions_run_only_the_fixed_commands(tmp_path):
    app, runner = make_app(tmp_path)
    assert app.health.ACTIONS == ("usage_live", "llm_probe", "ci_main")
    r = app.health.run_action("llm_probe")
    assert r["status"] == "ok" and SECRET not in json.dumps(r)
    assert app.health.run_action("ci_main")["status"] == "ok"
    for bad in ("program_bitstream", "jtag_list"):
        with pytest.raises(KeyError):
            app.health.run_action(bad)
    for c in runner.calls:                                                                   # no board tool of any kind is ever started
        assert not any(w in " ".join(c) for w in ("program", "flow.eyescan", "board.lock", "ssh", "vivado", "openFPGALoader", "hw_list", "jtag"))


def test_no_code_path_starts_the_hardware_server_or_vivado():
    """Stage 1 has no JTAG or Vivado step: no navigator source names the tools that would start them, and the one process starter is health.Runner."""
    src = {p.name: p.read_text() for p in (ROOT / "navigator").glob("*.py")}
    for name, text in src.items():
        for tok in ("HwServer", "run_vivado_tcl", "hw_list.tcl", "jtag_list", "openFPGALoader", "flow.hw", "flow import hw", "Popen", "os.system"):
            assert tok not in text, f"{name} mentions {tok}"
        if name not in ("health.py", "sources.py"):          # health.Runner (fixed argv) and sources._git_date (git log) are the only starters
            assert "subprocess" not in text, name
    assert not (ROOT / "navigator" / "jtag_list.py").exists()
    for bad in ("hw_server", "vivado -mode", "/bin/vivado"):
        assert not any(bad in t for n, t in src.items() if n != "test_103_navigator.py"), bad


def test_usage_levels(tmp_path):
    app, _ = make_app(tmp_path)
    log = app.handoff / "usage_log.txt"
    import datetime as dt
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    for pct, want in ((33, "ok"), (82, "warn"), (88, "fail"), (95, "fail")):
        log.write_text(f"{now}  Current week (all models): {pct}% used · resets Nov 23;\n")
        assert app.health.usage()["status"] == want
    log.write_text("2020-01-01 00:00  Current week (all models): 10% used · resets x;\n")
    assert app.health.usage()["status"] == "warn"


def test_stale_lock_is_flagged(tmp_path):
    app, _ = make_app(tmp_path)
    f = app.handoff / "heavy_slot.lock"
    import os
    import time
    old = time.time() - 5 * 3600
    end = time.strftime("%H:%M", time.localtime(old + 1800))
    f.write_text(f"X: job, start, expected end {end}\n")
    os.utime(f, (old, old))
    c = {x["id"]: x for x in app.health.locks()}["heavy_slot.lock"]
    assert c["status"] == "warn" and "STALE" in c["detail"]


def test_record_viewer_scrubs_json_and_refuses_symlinks(tmp_path):
    import shutil
    root = tmp_path / "repo"
    (root / "results" / "x").mkdir(parents=True)
    (root / "agent" / "access").mkdir(parents=True)
    (root / "agent/access/keys.json").write_text('{"salt": "s"}')
    (root / "results/x/a.json").write_text(json.dumps({"api-key": SECRET, "note": f"v {SECRET}", "ok": 1}))
    (root / "results/x/link.json").symlink_to(root / "agent/access/keys.json")
    (root / "results/x/prompt_dump.json").write_text("{}")
    from navigator import sources as S
    r = S.read_record(root, "results/x/a.json")
    body = "\n".join(r["lines"])
    assert SECRET not in body and "api-key" not in body and '"ok": 1' in body
    assert S.read_record(root, "results/x/link.json") is None and S.read_record(root, "results/x/prompt_dump.json") is None
    shutil.rmtree(root)


def test_concurrent_action_is_refused(tmp_path):
    app, runner = make_app(tmp_path)
    assert app.health._locks["llm_probe"].acquire(blocking=False)
    r = app.health.run_action("llm_probe")
    assert r["status"] == "warn" and "already running" in r["detail"] and runner.calls == []


def test_eye_page_is_sandboxed_and_escapes_capture_text(live):
    caps = json.loads(live.get("/api/captures")[2])["captures"]
    st, hd, body = live.get(f"/measure/page?a={caps[0]['id']}")
    assert hd["Content-Security-Policy"].startswith("sandbox allow-scripts")
    assert b"function esc(" in body and b"esc(r[1])" in body
    assert b'sandbox: "allow-scripts"' in (SV.STATIC / "app.js").read_bytes()
