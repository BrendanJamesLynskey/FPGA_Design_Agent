"""Per-role model routing (05f), offline: no CLI call, no model, no network."""

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from agent import __main__ as cli
from agent.claude_code_arm import arm
from agent.core.runner import RunResult
from agent.core.session import ROOT
from agent.graph import review as rv
from agent.graph import role_models as rm
from agent.graph import run as gr
from agent.graph.stages import MACHINE

T1 = ROOT / "designs" / "t1_dimmer_counter"


class Runner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        return RunResult(0, "ok", "", 0.0)


@pytest.fixture
def runs(monkeypatch):
    d = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def mk(runs, **kw):
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", **kw)
    rt = gr.new_runtime(cfg, lambda *a, **k: None, runner=Runner())
    (rt.design / "spec.yaml").write_text("name: x\n")
    return rt


def enter(rt, n):
    rt.meter.start_stage(MACHINE[n].limits)
    rt.session.stage = MACHINE[n].name


# ---- 1. the maps -----------------------------------------------------------------------------------------------------

def test_single_is_todays_behaviour_for_both_harnesses():
    d = gr.Config(spec_md=T1 / "spec.md", name="x")
    assert d.profile == "single" and d.roles is None
    assert set(d.role_models()) == set(rm.ROLE_NAMES)
    assert all(s == {"harness": "deepagents", "model": "openai/gpt-6-luna", "effort": None} for s in d.role_models().values())
    c = gr.Config(spec_md=T1 / "spec.md", name="x", harness="claude_code", cc_model="claude-haiku-5-5", cc_effort="low")
    assert all(s == {"harness": "claude_code", "model": "claude-haiku-5-5", "effort": "low"} for s in c.role_models().values())


def test_cvdp_profile_map_and_the_writer_and_blind_model_differ():
    m = gr.Config(spec_md=T1 / "spec.md", name="x", profile="cvdp").role_models()
    assert m["rtl"] == {"harness": "claude_code", "model": "claude-opus-5-5", "effort": None}
    for r in ("model", "tests", "clarify"):
        assert m[r]["harness"] == "claude_code" and m[r]["model"] == "claude-sonnet-5-5"
    assert m["model"]["model"] != m["rtl"]["model"]                  # independence of the blind golden model


def test_explicit_roles_override_the_profile_and_mix_harnesses():
    cfg = gr.Config(spec_md=T1 / "spec.md", name="x", profile="cvdp",
                    roles=rm.parse_roles('{"tests": {"harness": "deepagents", "model": "openai/gpt-6-luna"}, '
                                         '"rtl": {"effort": "high"}}'))
    m = cfg.role_models()
    assert m["tests"]["harness"] == "deepagents" and m["rtl"] == {"harness": "claude_code", "model": "claude-opus-5-5",
                                                                  "effort": "high"}
    assert m["model"]["harness"] == "claude_code"


@pytest.mark.parametrize("bad", ['{"orchestrator": {"model": "x"}}', '{"rtl": {"temperature": 1}}'])
def test_unknown_role_or_key_is_refused(bad):
    with pytest.raises(ValueError):
        rm.parse_roles(bad)


def test_unknown_profile_and_openrouter_forbidden_models_are_refused():
    with pytest.raises(ValueError, match="profile"):
        gr.Config(spec_md=T1 / "spec.md", name="x", profile="nope").role_models()
    with pytest.raises(ValueError, match="OpenRouter"):
        gr.Config(spec_md=T1 / "spec.md", name="x", roles={"rtl": {"harness": "deepagents", "model": "anthropic/claude-opus-5.5"}}
                  ).role_models()
    # the same model through Claude Code (the plan) is fine
    gr.Config(spec_md=T1 / "spec.md", name="x", roles={"rtl": {"harness": "claude_code", "model": "claude-opus-5-5"}}).role_models()


def test_oracle_is_not_a_role_and_stays_on_the_run_model(runs):
    assert "oracle" not in rm.ROLE_NAMES
    rt = mk(runs, profile="cvdp", model="openai/gpt-6-luna")
    assert json.loads((rt.run_dir / "config.json").read_text())["oracle_model"] == "openai/gpt-6-luna"
    assert gr.summary(rt, {"history": []})["oracle_model"] == "openai/gpt-6-luna"


def test_cli_builds_the_oracle_client_on_the_run_model_whatever_the_profile(runs, monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(cli, "_client", lambda model, replay, record: asked.append(model) or (lambda *a, **k: None))
    monkeypatch.setattr(cli, "_drive", lambda *a, **k: {})
    monkeypatch.setattr(gr, "container_available", lambda: False)
    monkeypatch.setenv("FDA_ALLOW_HOST_SANDBOX", "1")          # QR1: a hidden-spec run is otherwise refused without the image
    hidden = tmp_path / "h.yaml"
    hidden.write_text("name: x\n")
    cli.main(["run", str(T1 / "spec.md"), "--profile", "cvdp", "--interview", "oracle", "--hidden-spec", str(hidden)])
    assert asked == ["openai/gpt-6-luna"]


# ---- 2. config.json / resume -----------------------------------------------------------------------------------------

def test_profile_and_roles_round_trip_through_config_json(runs):
    roles = {"rtl": {"effort": "high"}, "tests": {"harness": "deepagents", "model": "openai/gpt-6-luna", "effort": None}}
    rt = mk(runs, profile="cvdp", roles=roles)
    c = json.loads((rt.run_dir / "config.json").read_text())
    assert c["profile"] == "cvdp" and c["roles"] == roles and c["role_models"] == rt.cfg.role_models()
    assert cli.config_from_json(c).role_models() == rt.cfg.role_models()


def test_an_older_config_json_resumes_as_single(runs):
    rt = mk(runs, harness="claude_code", cc_model="claude-opus-5-5")
    c = json.loads((rt.run_dir / "config.json").read_text())
    for k in ("profile", "roles", "role_models", "oracle_model"):
        c.pop(k)
    back = cli.config_from_json(c)
    assert back.profile == "single" and back.role_models() == rt.cfg.role_models()


# ---- 3. dispatch -----------------------------------------------------------------------------------------------------

def test_each_role_goes_to_its_own_harness_model_and_effort(runs, monkeypatch):
    import deepagents
    rt = mk(runs, profile="cvdp", roles={"tests": {"harness": "deepagents", "model": "openai/gpt-6-luna", "effort": None}})
    got, da = [], []
    monkeypatch.setattr(arm, "run_subagent_cc", lambda rt_, plan: got.append((plan["role"], plan["model"], plan["effort"])) or {})

    class Stub:
        def invoke(self, *a, **k):
            return {"files": {}}
    monkeypatch.setattr(deepagents, "create_deep_agent", lambda **kw: Stub())
    monkeypatch.setattr(gr, "chat_model", lambda client, *a, **k: da.append(client) or object())
    enter(rt, 2)
    for role in ("model", "tests", "rtl"):
        gr.run_subagent(rt, role, "p", ())
    assert got == [("model", "claude-sonnet-5-5", "medium"), ("rtl", "claude-opus-5-5", None)]
    assert len(da) == 1                                              # the luna tests role ran on Deep Agents
    enter(rt, 0)
    gr.run_subagent(rt, "clarify", "p", ())
    assert got[-1] == ("clarify", "claude-sonnet-5-5", "medium")


def test_a_deep_agents_role_on_another_model_gets_that_models_client(runs, monkeypatch):
    import deepagents
    rt = mk(runs, roles={"rtl": {"harness": "deepagents", "model": "openai/other"}})
    made = []
    rt.client_for = lambda m: made.append(m) or (lambda *a, **k: None)

    class Stub:
        def invoke(self, *a, **k):
            return {"files": {}}
    monkeypatch.setattr(deepagents, "create_deep_agent", lambda **kw: Stub())
    monkeypatch.setattr(gr, "chat_model", lambda *a, **k: object())
    enter(rt, 2)
    gr.run_subagent(rt, "rtl", "p", ())
    gr.run_subagent(rt, "tests", "p", ())                            # the run's own model: no factory call
    assert made == ["openai/other"]
    rt.client_for = None
    with pytest.raises(ValueError, match="no client"):
        gr.role_client(rt, "openai/third")


def test_effort_none_omits_the_flag_and_a_set_effort_is_passed(runs):
    rt = mk(runs)
    enter(rt, 2)
    plan = gr.subagent_plan(rt, "rtl", "p", MACHINE[2].tools)
    off = arm.cli_argv(rt, plan, Path("/x/m.json"), "claude-opus-5-5", None, 10)
    on = arm.cli_argv(rt, plan, Path("/x/m.json"), "claude-opus-5-5", "high", 10)
    assert "--effort" not in off and on[on.index("--effort") + 1] == "high"
    assert off[off.index("--model") + 1] == "claude-opus-5-5"
    # the lean profile is unchanged: our system prompt, no built-in tools, no settings, no slash commands
    assert off[off.index("--tools") + 1] == "" and off[off.index("--setting-sources") + 1] == ""
    assert "--disable-slash-commands" in off and "--strict-mcp-config" in off


# ---- 4. accounting ---------------------------------------------------------------------------------------------------

def test_per_role_and_per_stage_accounting_in_summary_and_pages(runs, monkeypatch):
    rt = mk(runs, profile="cvdp", roles={"tests": {"harness": "deepagents", "model": "openai/gpt-6-luna", "effort": None}})

    def fake(rt_, role, prompt, allowed, repair, spec):
        rt_.meter.run["turns"] += 3
        rt_.meter.run["tokens"] += 100
        if spec["harness"] == "deepagents":
            rt_.meter.run["usd"] += 0.01
        else:
            with (rt_.run_dir / "claude_code_calls.jsonl").open("a") as f:
                f.write(json.dumps({"claude_code_version": "2.1.316", "plan_cost_estimate_usd": 0.2}) + "\n")
        return {}
    monkeypatch.setattr(gr, "_run_subagent", fake)
    enter(rt, 2)
    for role in ("model", "tests", "rtl", "rtl"):
        gr.run_subagent(rt, role, "p", (), repair=role == "rtl")
    enter(rt, 4)
    gr.run_subagent(rt, "rtl", "p", ())
    s = gr.summary(rt, {"history": []})
    pr = s["per_role"]
    assert pr["rtl"]["calls"] == 3 and pr["rtl"]["turns"] == 9 and pr["rtl"]["plan_cost_estimate_usd"] == 0.6
    assert pr["tests"]["cost_usd"] == 0.01 and pr["tests"]["plan_cost_estimate_usd"] == 0.0
    assert pr["model"]["cost_usd"] == 0.0 and pr["model"]["plan_cost_estimate_usd"] == 0.2
    assert s["per_stage"][MACHINE[2].name]["calls"] == 4 and s["per_stage"][MACHINE[4].name]["calls"] == 1
    assert s["harness"] == "mixed" and s["model"] == "per-role" and s["profile"] == "cvdp"
    assert s["role_models"]["rtl"]["model"] == "claude-opus-5-5"
    rows = [u for u in gr.role_usage(rt) if u["stage"] == MACHINE[2].name]
    html = rv.roles_html(rt.cfg.role_models(), rows)
    assert "claude-opus-5-5" in html and "claude-sonnet-5-5" in html and "gpt-6-luna" in html and "CLI default" in html
    assert "6 turns" in html or "9 turns" in html
    idx = rv.write_index(rt.design, [], rt.cfg.role_models()).read_text()
    assert "Models by role" in idx and "claude-opus-5-5" in idx


def test_a_failed_turn_is_still_accounted(runs, monkeypatch):
    rt = mk(runs)

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(gr, "_run_subagent", boom)
    enter(rt, 2)
    with pytest.raises(RuntimeError):
        gr.run_subagent(rt, "rtl", "p", ())
    assert [u["role"] for u in gr.role_usage(rt)] == ["rtl"]


def test_build_note_names_the_models_by_role(runs):
    rt = mk(runs, profile="cvdp")
    note = (rt.design / "BUILD_NOTE.md").read_text()
    assert "models by role (profile cvdp)" in note and "rtl: claude_code claude-opus-5-5" in note
    assert "oracle" in note.lower() and "plain code" in note


# ---- 5. per-stage overrides ------------------------------------------------------------------------------------------

def test_stage_override_precedence():
    """base < profile role < explicit role < profile role@stage < explicit role@stage; each layer is partial."""
    S = "timing-closure"
    cfg = gr.Config(spec_md=T1 / "spec.md", name="x", profile="cvdp",
                    roles={"rtl": {"effort": "high"}, f"rtl@{S}": {"model": "claude-fable-5-1"}})
    assert cfg.role_models()["rtl"] == {"harness": "claude_code", "model": "claude-opus-5-5", "effort": "high"}
    assert cfg.role_models("rtl-design-creation")["rtl"] == cfg.role_models()["rtl"]          # other stages: no override
    assert cfg.role_models(S)["rtl"] == {"harness": "claude_code", "model": "claude-fable-5-1", "effort": "high"}
    assert cfg.role_models(S)["tests"] == cfg.role_models()["tests"]                          # other roles unaffected
    # the explicit stage key beats a profile stage key
    rm.PROFILES["_t"] = {f"rtl@{S}": {"model": "claude-sonnet-5-5", "effort": "low"}}
    try:
        c2 = gr.Config(spec_md=T1 / "spec.md", name="x", profile="_t", roles={f"rtl@{S}": {"effort": "max"}})
        assert c2.role_models(S)["rtl"]["model"] == "claude-sonnet-5-5" and c2.role_models(S)["rtl"]["effort"] == "max"
        assert rm.stage_overrides(c2) == [f"rtl@{S}"]
    finally:
        del rm.PROFILES["_t"]
    assert rm.stage_overrides(gr.Config(spec_md=T1 / "spec.md", name="x", profile="cvdp")) == []     # cvdp sets none


def test_bad_stage_keys_are_refused():
    with pytest.raises(ValueError, match="stage"):
        rm.parse_roles('{"rtl@nope": {"model": "x"}}')
    with pytest.raises(ValueError, match="role"):
        rm.parse_roles('{"oracle@constraints": {"model": "x"}}')
    with pytest.raises(ValueError, match="stage"):
        gr.Config(spec_md=T1 / "spec.md", name="x", roles={"rtl@nope": {"model": "x"}}).role_models()


def test_stage_override_round_trips_and_is_dispatched_and_accounted(runs, monkeypatch):
    roles = {"rtl@timing-closure": {"harness": "claude_code", "model": "claude-fable-5-1", "effort": "high"}}
    rt = mk(runs, profile="cvdp", roles=roles)
    c = json.loads((rt.run_dir / "config.json").read_text())
    assert c["roles"] == roles and cli.config_from_json(c).role_models("timing-closure") == rt.cfg.role_models("timing-closure")
    got = []
    monkeypatch.setattr(arm, "run_subagent_cc", lambda rt_, plan: got.append((plan["stage"], plan["model"], plan["effort"])) or {})
    enter(rt, 2)
    gr.run_subagent(rt, "rtl", "p", ())
    enter(rt, 6)
    gr.run_subagent(rt, "rtl", "p", ())
    assert got == [("rtl-design-creation", "claude-opus-5-5", None), ("timing-closure", "claude-fable-5-1", "high")]
    rows = gr.role_usage(rt)
    assert [(u["stage"], u["model"], u["stage_override"]) for u in rows] == [
        ("rtl-design-creation", "claude-opus-5-5", False), ("timing-closure", "claude-fable-5-1", True)]
    assert gr.summary(rt, {"history": []})["stage_overrides"] == ["rtl@timing-closure"]


# ---- 6. device know-how stays on -------------------------------------------------------------------------------------

@pytest.mark.parametrize("n,role,allowed", [(0, "clarify", ("search_docs", "load_skill")), (2, "tests", ("search_docs", "load_skill")),
                                              (2, "rtl", MACHINE[2].tools), (3, "rtl", MACHINE[3].tools)])
def test_profiles_do_not_change_the_knowledge_tools_or_prompts(runs, n, role, allowed):
    a, b = mk(runs, profile="single"), mk(runs, profile="cvdp")
    for rt in (a, b):
        enter(rt, n)
    pa, pb = gr.subagent_plan(a, role, "P", allowed), gr.subagent_plan(b, role, "P", allowed)
    assert pa["core_tools"] == pb["core_tools"] and pa["file_tools"] == pb["file_tools"]
    assert pa["system_prompt"] == pb["system_prompt"] and pa["user_message"] == pb["user_message"]    # no pack injection
    assert {t for t in gr.KNOWLEDGE_TOOLS if t in allowed} <= set(pb["core_tools"]) | set(pb["file_tools"])


def test_knowledge_use_is_logged_per_role_and_stage(runs):
    from agent.core import dispatch
    rt = mk(runs, profile="cvdp")
    for role, stage, tool, args in [("rtl", "rtl-design-creation", "load_skill", {"sections": ["clocking"]}),
                                    ("rtl", "rtl-design-creation", "load_skill", {"sections": ["clocking", "dsp"]}),
                                    ("tests", "rtl-design-creation", "search_docs", {"query": "x"})]:
        rs = gr.role_session(rt.session, role)
        rs.stage = stage
        dispatch(rs, tool, args)
    ku = gr.summary(rt, {"history": []})["knowledge_use"]
    assert ku["rtl/rtl-design-creation"]["load_skill"]["calls"] == 2
    assert ku["rtl/rtl-design-creation"]["load_skill"]["sections"] == ["clocking", "dsp"]
    assert ku["tests/rtl-design-creation"]["search_docs"]["calls"] == 1
