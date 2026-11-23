"""Brief 196: the production_secure switch (profiles, pin, interview, the build tool's environment) and the request of flow/security.py.
Scripted: no model, no Vivado. The build evidence itself is tested in flow/tests/test_196_security.py."""

import json
import shutil
import uuid

import pytest
import yaml

from agent.graph import assurance as A, profiles as P


def test_the_switches_exist_default_off_and_change_no_profile():
    for name in P.PROFILES:
        eff = P.resolve(name)["effective"]
        assert eff["production_secure"] is False
        assert P.security_request(eff)["production_secure"] is False
    assert P.ip_release_ok(P.resolve("ip_release", {"sec_encrypt": False})["effective"]) == []      # orthogonal to the IP label
    assert not [k for k in P.resolve("standard", {"production_secure": True})["not_wired"] if k in P.SECURITY]


def test_set_production_secure_becomes_the_request():
    rec = P.from_cli("standard", ["production_secure=on", "sec_strip_debug=off"])
    req = P.security_request(rec["effective"])
    assert req == {"production_secure": True, "encrypt": True, "authenticate": True, "readback_off": True, "strip_debug": False, "sysmon_shutdown": True}
    assert rec["overrides"]["production_secure"] == {"profile_value": False, "value": True}
    with pytest.raises(P.ProfileError):
        P.from_cli("standard", ["production_secure=maybe"])


def test_the_security_environment_comes_from_the_pin(tmp_path):
    assert P.security_env(tmp_path) == {}                                   # no pin, no request: the build.yaml stands
    P.write_pin(tmp_path, "standard", {"production_secure": True})
    env = P.security_env(tmp_path)
    assert json.loads(env["FDA_SECURITY"])["production_secure"] is True
    P.write_pin(tmp_path, "standard", {}, replace=True)                    # the interview replaced it with an off answer
    assert json.loads(P.security_env(tmp_path)["FDA_SECURITY"])["production_secure"] is False


def test_the_interview_question_has_a_default_and_a_reason():
    text, default, reason = A.security_question({"title": "A production packet filter"})
    assert default == "yes" and "production" in reason and "BBRAM" in text and "never makes" in text
    assert A.security_question({"title": "A PWM dimmer"})[1] == "no"
    assert A.security_from_answer("Yes, it ships", "no") is True and A.security_from_answer("no thanks", "yes") is False
    assert A.security_from_answer("", "yes") is True                        # an empty answer takes the default


@pytest.fixture
def rt(monkeypatch):
    pytest.importorskip("langgraph")
    pytest.importorskip("deepagents")
    from agent.core.session import ROOT
    from agent.graph import run as gr
    from agent.tests.test_episode import FakeRunner, T1
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="on", verif_ask=False)
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=FakeRunner())
    (r.design / "spec.md").write_text("A PWM dimmer counter for the board.\n")
    yield r, gr, T1
    shutil.rmtree(runs, ignore_errors=True)


def test_the_answer_joins_the_pin_and_the_builds_environment(rt, monkeypatch):
    r, gr, T1 = rt
    import langgraph.types
    monkeypatch.setattr(langgraph.types, "interrupt", lambda payload: {"answer": "yes"})
    spec = dict(yaml.safe_load((T1 / "spec.yaml").read_text()), open_questions=[],
                requirements=[{"id": "R1", "text": "Counts presses", "proof": ["simulation"]}])
    gr._pin_run(r)
    spec, summary = gr._interview(r, spec, {})
    q = [x for x in summary["questions"] if x["text"].startswith(A.SECURITY_QUESTION)]
    assert len(q) == 1 and q[0]["reason"]
    assert r.cfg.verif_sets["production_secure"] is True and spec["production_secure"]["value"] is True
    pin = json.loads((r.run_dir / "policy.json").read_text())
    assert pin["overrides"]["production_secure"] is True and "security question" in pin["set_by"]
    assert json.loads(P.security_env(r.run_dir)["FDA_SECURITY"])["strip_debug"] is True
    assert r.session.policy_run_dir == r.run_dir
    # no second question when the user already set it on the command line
    r.cfg.verif_sets = {"production_secure": False}
    _, summary = gr._interview(r, dict(spec, resolved_questions=[]), {})
    assert not [x for x in summary["questions"] if x["text"].startswith(A.SECURITY_QUESTION)]


def test_the_build_tool_passes_the_pinned_request(rt):
    r, gr, T1 = rt
    from agent.core import dispatch
    P.write_pin(r.run_dir, "standard", {"production_secure": True}, replace=True)
    seen = {}

    class Rec:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            seen["env"] = env
            from agent.core.runner import RunResult
            return RunResult(1, "", "stub", 0.0)

    r.session.runner = Rec()
    (r.design / "rtl").mkdir(exist_ok=True)
    (r.design / "rtl" / "x.sv").write_text("module t(input logic c, output logic q); always_ff @(posedge c) q <= ~q; endmodule\n")
    rel = r.design.relative_to(r.session.root)
    (r.design / "c.xdc").write_text("create_clock -period 10.000 -name c [get_ports c]\n")
    (r.design / "build.yaml").write_text(yaml.safe_dump({"top": "t", "part": "xc7a100tcsg324-1", "sources": [f"{rel}/rtl/x.sv"], "constraints": [f"{rel}/c.xdc"]}))
    dispatch(r.session, "build", {"until": "synth"})                       # the stub run fails; only the environment it was given matters
    assert json.loads(seen["env"]["FDA_SECURITY"])["production_secure"] is True and seen["env"]["FDA_STOP_AFTER"] == "synth"
