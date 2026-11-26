"""Brief 195 in the navigator: the Examples page's routes, the start guards for an example (pinned setup, cost cap, confirmation, usage, one at a time), and redaction.
Fakes stand in for the spawner, the usage check and the slot script; no model, Vivado or simulator is started."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from agent.repro import compare as C
from agent.repro import registry as R
from agent.repro import runner as RN
from navigator import health as H
from navigator import runctl as RC
from navigator import server as SV
from navigator.tests.test_103_navigator import TOKEN
from navigator.tests.test_103s2_navigator import MODELS, FakeRunner, FakeSpawner, FakeTransport, Live, env, make_rc, locks_in  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
EX = {"kind": "example", "example": "gray_stepper", "max_usd": 6, "confirm": "start"}


def result_record(name="gray_stepper", rtl="a" * 64, passed=True):
    return {"schema": C.SCHEMA, "example": name, "run_id": "x", "setup": {"claude_cli_version": "2.1.321"}, "outcome": {"hidden_pass": passed, "tests_passed": 3, "tests_total": 3, "internal_pass": True},
            "tool_results": {"rtl_sha256": rtl, "lut": 10, "wns_ns": 1.0}, "varies": {"wall_s": 100, "cost_usd": 1.0}}


def test_an_example_start_builds_the_pinned_command_and_nothing_else(env):
    rc, runner, sp = make_rc(env)
    r = rc.start(dict(EX))
    assert r["started"], r
    argv = sp.calls[0]["argv"]
    assert argv[1:] == ["-m", "agent", "example", "run", "gray_stepper", "--no-slot", "--max-usd", "6"]
    assert r["record"]["summary"]["model"] == "claude-sonnet-5-5" and r["record"]["summary"]["target"] == "ex_gray_stepper"
    assert (env["handoff"] / "heavy_slot.lock").read_text().startswith("103S2: agent run ex_gray_stepper")
    sp.procs[0].finish(0)
    for _ in range(100):
        if rc.records()[0]["status"] == "ended":
            break
        time.sleep(0.05)
    assert rc.records()[0]["slot"]["released"] is True and locks_in(env) == []


@pytest.mark.parametrize("body,why", [({"example": "nope"}, "pick an example"), ({"example": "../x"}, "pick an example"), ({"example": None}, "pick an example"),
                                       ({"max_usd": 99}, "at most the pinned"), ({"max_usd": 0}, "at most the pinned"), ({"max_usd": True}, "at most the pinned"), ({"max_usd": "6"}, "at most the pinned"),
                                       ({"confirm": None}, "confirmation")])
def test_bad_example_requests_are_refused_and_start_nothing(env, body, why):
    rc, _, sp = make_rc(env)
    r = rc.start({**EX, **body})
    assert r["started"] is False and why in r["refused"] and sp.calls == [] and locks_in(env) == []


def test_the_browser_cannot_change_the_pinned_model_effort_or_flags(env):
    rc, _, sp = make_rc(env)
    r = rc.start({**EX, "model": "claude-opus-5-5", "harness": "deepagents", "effort": "high", "arms": ["H2"], "allow_fable": True, "stop_after": 9})
    assert r["started"], r
    argv = sp.calls[0]["argv"]
    assert "claude-opus-5-5" not in argv and "--allow-fable" not in argv and "deepagents" not in argv and "H2" not in argv and "9" not in argv
    assert r["record"]["summary"]["effort"] == "medium"
    sp.procs[0].finish()


def test_a_lower_cost_cap_is_passed_a_higher_one_refused(env):
    rc, _, sp = make_rc(env)
    assert rc.start({**EX, "max_usd": 2.5})["started"] and sp.calls[0]["argv"][-1] == "2.5"
    sp.procs[0].finish()


def test_usage_and_one_at_a_time_guards_apply_to_examples_too(env):
    rc, _, sp = make_rc(env, pct=95)
    assert "at or above" in rc.start(dict(EX))["refused"] and sp.calls == []
    rc, _, sp = make_rc(env, pct=10)
    assert rc.start(dict(EX))["started"] and "one at a time" in rc.start(dict(EX))["refused"]
    sp.procs[0].finish()


@pytest.fixture
def web(env):
    runner = FakeRunner(env["handoff"])
    hl = H.Health(ROOT, env["handoff"], runner, config_dir=env["cfg"], sysfs_usb=env["tmp"] / "usb")
    hl._cache["models_view"] = (time.monotonic() + 1e6, MODELS)
    sp = FakeSpawner()
    app = SV.App(ROOT, env["handoff"], env["runs"], gate=lambda e: "owner", health=hl, token=TOKEN, state_dir=env["state"], spawner=sp, transport=FakeTransport(env["handoff"]))
    s = Live(app)
    s.sp, s.env = sp, env
    yield s
    s.close()


def test_the_examples_route_lists_examples_pins_limits_and_the_preflight(web, monkeypatch):
    import navigator.examples as EXM
    monkeypatch.setattr(EXM, "preflight", lambda: {"ok": False, "checks": [{"name": "claude_cli", "ok": False, "detail": "no pinned copy", "hard": True}]})
    st, _, body = web.get("/api/examples")
    j = json.loads(body)
    assert st == 200 and [e["name"] for e in j["examples"]] == ["gray_stepper", "elevator_fsm", "median3x3", "pattern_sequencer"]
    assert j["pins"]["cc_model"] == "claude-sonnet-5-5" and j["preflight"]["ok"] is False and any("no temperature and no seed" in x for x in j["limits"])
    assert web.req("GET", "/api/examples", {})[0] == 401


def test_the_compare_route_reads_one_listed_run_and_never_a_path(web):
    rd = web.env["runs"] / "20261123-000000-abcd"
    rd.mkdir(parents=True)
    (rd / "config.json").write_text(json.dumps({"name": "ex_gray_stepper"}))
    (rd / RN.RESULT_FILE).write_text(json.dumps(result_record()))
    st, _, body = web.get("/api/examples/compare?id=20261123-000000-abcd")
    j = json.loads(body)
    assert st == 200 and j["example"] == "gray_stepper" and j["result_file"] == "runs/20261123-000000-abcd/example_result.json" and "outcome" in j and "deterministic" in j and "varies" in j
    assert web.get("/api/examples/compare?id=../../etc")[0] == 404 and web.get("/api/examples/compare?id=nope")[0] == 404
    listing = json.loads(web.get("/api/examples")[2])
    assert listing["runs"] == [{"id": "20261123-000000-abcd", "example": "gray_stepper", "hidden_pass": True}]


def test_a_secret_in_a_result_record_never_reaches_the_browser(web):
    key = "sk-or-v1-PLANTED0123456789abcdef"
    rec = result_record()
    rec["outcome"]["stop"] = "token " + key
    rec["setup"]["api_key"] = key
    rd = web.env["runs"] / "20261123-000000-abcd"
    rd.mkdir(parents=True)
    (rd / "config.json").write_text("{}")
    (rd / RN.RESULT_FILE).write_text(json.dumps(rec))
    body = web.get("/api/examples/compare?id=20261123-000000-abcd")[2].decode()
    assert key not in body


def test_example_routes_add_no_post_route():
    src = Path(SV.__file__).read_text()
    assert "/api/examples" not in src[src.index("def post"):src.index("def action")]


def test_the_page_and_the_shipped_files_name_no_host():
    js = (ROOT / "navigator" / "static" / "app.js").read_text()
    assert "pageExamples" in js and "examples: pageExamples" in js and "http://" not in js.split("pageExamples")[1].split("/* ---------- board")[0].replace("http://evil", "")
