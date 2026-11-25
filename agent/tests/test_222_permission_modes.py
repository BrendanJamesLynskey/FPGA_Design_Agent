"""Brief 222: permission modes. No model, no board, no Vivado: the scripted episode of test_episode (a scripted model and a fake runner that stands in for
the flow and for the board programmer) runs the real stage machine under each mode, and the policy, the never-rules and the command line are tested directly.

What is tested: each mode's preset; overrides (and that a deny is never lifted); the never-rules refused in every mode including Full auto; the tool gate;
the headless stop on an ungranted action (status, exit code, what it needs); every gated decision in the run record, the summary and the handover; the
raise_budget check on a resume; a mode change on resume."""

import argparse
import json
import shutil
import types
import uuid

import pytest
import yaml

from agent.core import permissions as P
from agent.core.session import ROOT
from agent.core.security import SecurityError

# ---------------------------------------------------------------------------------------------------------------------------------------
# the presets and the policy (pure code)


def test_every_mode_names_every_action_with_a_valid_value():
    assert tuple(P.MODES) == ("plan", "ask", "auto", "full")
    for m, d in P.MODES.items():
        assert set(d["actions"]) == set(P.ACTION_NAMES), m
        assert set(d["actions"].values()) <= {"allow", "ask", "deny"}
        assert d["plain"] and d["label"]
    assert all(a.plain and a.label for a in P.ACTIONS)


def test_the_instrument_permission_is_named_for_brief_221():
    assert "drive_instrument_output" in P.ACTION_NAMES and P.BY_NAME["drive_instrument_output"].board


def test_the_presets_are_the_ones_the_brief_describes():
    plan, ask, auto, full = (P.MODES[m]["actions"] for m in P.MODE_ORDER)
    gated = [a for a in P.ACTION_NAMES if a not in ("approve_stage",)]
    # Plan: read and plan only: nothing that changes files, runs a tool or touches a board
    for a in ("edit_design_files", "run_simulation", "run_vivado", "program_board_sram", "write_board_register", "drive_instrument_output", "read_board", "raise_budget"):
        assert plan[a] == "deny", a
    assert plan["use_knowledge_bank"] == "allow" and plan["approve_architecture"] == "deny"
    # Ask: simulation and checks without asking, every other gated action asked
    assert ask["run_simulation"] == "allow" and all(ask[a] == "ask" for a in gated if a != "run_simulation")
    # Auto: builds, Vivado and spend free; still asks for the board, registers, instruments and a higher budget
    assert auto["run_vivado"] == auto["spend_model_money"] == auto["edit_design_files"] == "allow"
    assert all(auto[a] == "ask" for a in ("program_board_sram", "write_board_register", "drive_instrument_output", "raise_budget"))
    # Full: also the board, registers and instruments, and it stops at the caps
    assert all(full[a] == "allow" for a in ("program_board_sram", "write_board_register", "drive_instrument_output", "run_vivado")) and full["raise_budget"] == "deny"
    assert P.DEFAULT_MODE == "auto"


def test_an_override_sits_on_the_mode_and_a_deny_is_never_lifted(tmp_path):
    pol = P.Policy("ask", {"run_vivado": "allow"}, "test", run_dir=tmp_path)
    assert pol.decide("run_vivado").result == "allow" and "override" in pol.decide("run_vivado").by
    assert pol.decide("edit_design_files").result == "ask" and "mode ask" in pol.decide("edit_design_files").by
    pol.grant(["edit_design_files"], "you")
    assert pol.decide("edit_design_files").result == "allow" and "granted by you" in pol.decide("edit_design_files").by
    pol2 = P.Policy("full", {"run_vivado": "deny"}, "test", run_dir=tmp_path / "b")
    pol2.grant(["run_vivado"], "you")
    assert pol2.decide("run_vivado").result == "deny"                       # a settings-level deny is not asked about and not lifted by a grant
    pol.refuse(["edit_design_files"], "you")
    assert pol.decide("edit_design_files").result == "deny" and "refused by you" in pol.decide("edit_design_files").by
    with pytest.raises(ValueError):
        pol.set_override("not_an_action", "allow")
    with pytest.raises(ValueError):
        pol.set_override("run_vivado", "maybe")


def test_the_state_and_the_decision_log_are_kept_in_the_run_directory(tmp_path):
    pol = P.Policy("ask", {"run_vivado": "deny"}, "command line", run_dir=tmp_path)
    pol.decide("run_simulation", 2, "stage 2")
    pol.decide("edit_design_files", 2, "stage 2")
    pol.grant(["edit_design_files"], "you", 2)
    back = P.Policy.load(tmp_path)
    assert back.mode == "ask" and back.overrides == {"run_vivado": "deny"} and "edit_design_files" in back.granted and back.source == "command line"
    rows = back.decisions()
    assert [(r["action"], r["result"]) for r in rows] == [("run_simulation", "allowed"), ("edit_design_files", "asked"), ("edit_design_files", "granted")]
    assert all(r["when"] and r["by"] for r in rows)
    s = P.summarise(tmp_path, back)
    assert s["mode"] == "ask" and {d["action"] for d in s["decisions"]} == {"run_simulation", "edit_design_files"}


def test_an_asked_row_is_written_once_per_question(tmp_path):
    pol = P.Policy("ask", run_dir=tmp_path)
    for _ in range(3):                                                     # the graph re-runs a node when it resumes from a question
        pol.decide("run_vivado", 3)
    assert [r["result"] for r in pol.decisions()] == ["asked"]


def test_the_command_line_wins_over_the_config_file(tmp_path):
    cfg = tmp_path / "permissions.yaml"
    cfg.write_text(yaml.safe_dump({"mode": "ask", "overrides": {"run_vivado": "allow"}, "projects": {"p1": {"mode": "auto", "overrides": {"edit_design_files": "deny"}}}}))
    assert P.resolve(config_file=cfg)["mode"] == "ask"
    s = P.resolve(project="p1", config_file=cfg)
    assert s["mode"] == "auto" and s["overrides"] == {"run_vivado": "allow", "edit_design_files": "deny"} and "project p1" in s["source"]
    s = P.resolve("plan", ["edit_design_files"], [], None, "p1", config_file=cfg)
    assert s["mode"] == "plan" and s["source"].startswith("command line") and s["overrides"]["edit_design_files"] == "allow"
    s = P.resolve(None, [], ["run_vivado"], 2.5, "other", config_file=cfg)
    assert s["mode"] == "ask" and s["overrides"]["run_vivado"] == "deny" and s["ask_above_usd"] == 2.5
    assert P.resolve(config_file=tmp_path / "none.yaml")["mode"] == "auto"            # no file, no flag: the default
    with pytest.raises(ValueError):
        P.resolve("everything")
    with pytest.raises(ValueError):
        P.resolve(None, ["flash_the_board"])


def test_save_config_keeps_other_entries_and_only_real_differences(tmp_path):
    f = tmp_path / "p.yaml"
    P.save_config("a", "ask", {"run_vivado": "allow", "run_simulation": "allow"}, 2.0, f)       # run_simulation is the mode's own value: not kept
    P.save_config(None, "auto", {}, None, f)
    d = yaml.safe_load(f.read_text())
    assert d["projects"]["a"] == {"mode": "ask", "overrides": {"run_vivado": "allow"}, "ask_above_usd": 2.0} and d["mode"] == "auto"
    with pytest.raises(ValueError):
        P.save_config("../x", "ask", {}, None, f)
    with pytest.raises(ValueError):
        P.save_config("a", "wild", {}, None, f)


def test_the_plan_estimate_is_labelled_as_limits_not_a_prediction():
    from agent.graph.stages import MACHINE, RUN_LIMITS
    e = P.plan_estimate(RUN_LIMITS, MACHINE)
    assert len(e["stages"]) == 10 and e["upper_bound"]["usd"] <= RUN_LIMITS["usd"] and "not a prediction" in e["note"]
    assert len(P.plan_estimate(RUN_LIMITS, MACHINE, 1)["stages"]) == 2


# ---------------------------------------------------------------------------------------------------------------------------------------
# what is never allowed: refused in every mode, including Full auto, whatever the overrides say

EVERYTHING_ALLOWED = {a: "allow" for a in P.ACTION_NAMES}
NEVER_CALLS = [("program", {"variant": "base", "target": "flash"}, "flash"), ("program", {"target": "qspi"}, "flash"),
               ("write_file", {"path": "BOOT.BIN", "content": "x"}, "boot_image"), ("write_file", {"path": "build/image.mcs", "content": "x"}, "flash"),
               ("write_file", {"path": "keys/dev.nky", "content": "x"}, "keys"),
               ("bringup", {"note": "then program_hw_efuse the key"}, "efuse_bbram"), ("debug_capture", {"probeset": "write_bbram"}, "efuse_bbram"),
               ("debug_capture", {"note": "program the aes key into the device"}, "keys"),
               ("axi_board_run", {"note": "write_cfgmem to the qspi"}, "flash"), ("debug_capture", {"note": "enable the laser"}, "laser"),
               ("drive_instrument", {"output": "laser", "state": "on"}, "laser"), ("program", {"note": "boot.bin for the sd card"}, "boot_image")]


@pytest.mark.parametrize("mode", P.MODE_ORDER)
@pytest.mark.parametrize("tool,args,rule", NEVER_CALLS)
def test_a_never_rule_refuses_in_every_mode_even_with_every_action_allowed(tmp_path, mode, tool, args, rule):
    P.Policy(mode, EVERYTHING_ALLOWED, "test", run_dir=tmp_path).save()
    s = types.SimpleNamespace(stage="configuration-and-debug", permissions_run_dir=tmp_path)
    with pytest.raises(P.NeverRefused) as e:
        P.tool_gate(s, tool, args)
    assert e.value.never == rule and isinstance(e.value, SecurityError) and "never allowed in any mode" in str(e.value)


def test_the_bringup_step_itself_may_name_a_laser_but_no_other_tool_may_enable_one():
    assert P.never_violation("bringup", {"note": "laser off check"}) is None
    assert P.never_violation("simulate", {"test": "aes key expansion, flash controller"}) is None      # simulation arguments are not scanned
    assert P.never_violation("write_file", {"path": "rtl/aes_key_sched.sv", "content": "module key_flash_laser;"}) is None     # RTL may say key


def test_a_program_refusal_keeps_the_rule_name_the_tool_has_always_used(session, board_file):
    from agent.core.registry import dispatch
    session.stage = "configuration-and-debug"
    for mode in P.MODE_ORDER:
        session.permissions_run_dir = session.design.parent / mode
        P.Policy(mode, EVERYTHING_ALLOWED, "test", run_dir=session.permissions_run_dir).save()
        assert dispatch(session, "program", {"target": "flash"})["rule"] == "hardware-flash"


def test_script_text_with_flash_boot_efuse_or_keys_is_refused():
    for t, rule in (("write_cfgmem -format mcs -interface spix4 out.mcs", "flash"), ("copy BOOT.BIN to the card", "boot_image"), ("program_hw_efuse -efuse_data x", "efuse_bbram"),
                    ("set_property AES_KEY 0x00 [current_hw_device]", "efuse_bbram")):
        assert P.check_script(t)[0] == rule, t
    assert P.check_script("get_hw_targets; get_hw_devices") is None


def test_lab_limits_are_checked_and_an_unstated_limit_is_zero():
    lim = {"max_voltage_v": 3.3, "max_current_a": 0.5, "never_enable": ["laser_tx"]}
    assert P.lab_limits_violation({"output": "vcc", "voltage_v": 3.3, "current_a": 0.4}, lim) is None
    assert "above the lab file's max_voltage_v" in P.lab_limits_violation({"output": "vcc", "voltage_v": 5.0}, lim)
    assert "never enabled" in P.lab_limits_violation({"output": "laser_tx"}, lim)
    assert "states no limit" in P.lab_limits_violation({"output": "gen", "frequency_hz": 1e6}, lim)
    assert "not a number" in P.lab_limits_violation({"output": "vcc", "voltage_v": "high"}, lim)


def test_a_cost_cap_above_the_hard_cap_is_refused_in_every_mode(tmp_path):
    from agent.graph import run as gr
    assert P.check_hard_cap(P.HARD_CAP_USD) is None and "hard cap" in P.check_hard_cap(P.HARD_CAP_USD + 1)
    for mode in P.MODE_ORDER:
        cfg = gr.Config(spec_md=tmp_path / "spec.md", name="x", permissions={"mode": mode, "overrides": EVERYTHING_ALLOWED})
        cfg.run_limits["usd"] = P.HARD_CAP_USD + 1
        with pytest.raises(P.NeverRefused) as e:
            gr.new_runtime(cfg, None, run_id="cap-" + uuid.uuid4().hex[:6])
        assert e.value.never == "hard_cap"


# ---------------------------------------------------------------------------------------------------------------------------------------
# the tool gate


def _gate(tmp_path, mode, stage, tool, args=None, overrides=None, grant=()):
    pol = P.Policy(mode, overrides, "test", run_dir=tmp_path)
    if grant:
        pol.grant(list(grant), "you")
    pol.save()
    P.tool_gate(types.SimpleNamespace(stage=stage, permissions_run_dir=tmp_path), tool, args or {})


def test_the_tool_gate_follows_the_mode(tmp_path):
    _gate(tmp_path / "a", "ask", "rtl-design-creation", "simulate")                       # Ask runs simulation itself
    _gate(tmp_path / "b", "ask", "clarify", "write_file", {"path": "spec.yaml"})           # the plan files of the first two stages are not gated
    for t, tool in (("c", "build"), ("d", "program"), ("e", "bringup")):
        with pytest.raises(SecurityError) as e:
            _gate(tmp_path / t, "ask", "configuration-and-debug", tool)
        assert e.value.rule == "permission-not-granted" and "has not been granted in mode ask" in str(e.value)
    with pytest.raises(SecurityError) as e:
        _gate(tmp_path / "f", "ask", "rtl-design-creation", "write_file", {"path": "rtl/a.sv", "content": ""})
    assert e.value.rule == "permission-not-granted" and "edit_design_files" in str(e.value)
    _gate(tmp_path / "g", "ask", "rtl-design-creation", "write_file", {"path": "rtl/a.sv", "content": ""}, grant=["edit_design_files"])       # once granted
    with pytest.raises(SecurityError) as e:
        _gate(tmp_path / "h", "plan", "rtl-design-creation", "simulate")
    assert e.value.rule == "permission-denied" and "denied (mode plan)" in str(e.value)
    _gate(tmp_path / "i", "full", "configuration-and-debug", "bringup")
    with pytest.raises(SecurityError):                                                     # Auto asks for the board
        _gate(tmp_path / "j", "auto", "configuration-and-debug", "program")
    _gate(tmp_path / "k", "auto", "configuration-and-debug", "program", overrides={"program_board_sram": "allow"})
    with pytest.raises(SecurityError) as e:                                                # a deny override
        _gate(tmp_path / "l", "full", "synthesis", "build", overrides={"run_vivado": "deny"})
    assert e.value.rule == "permission-denied"
    rows = P.Policy.load(tmp_path / "l").decisions()
    assert rows and rows[-1]["result"] == "refused-at-tool"


def test_a_session_without_a_run_policy_only_meets_the_never_rules(session):
    from agent.core.registry import dispatch
    assert session.permissions_run_dir is None
    assert dispatch(session, "program", {"variant": "base"})["rule"] == "hardware-stage"       # the existing refusal, not a permission one


def test_a_tool_the_next_brief_adds_is_gated_by_registering_its_action(tmp_path):
    P.register_tool_action("lab_drive_test", "drive_instrument_output")
    try:
        with pytest.raises(SecurityError) as e:
            _gate(tmp_path / "a", "auto", "configuration-and-debug", "lab_drive_test", {"output": "vcc"})
        assert "drive_instrument_output" in str(e.value)
        _gate(tmp_path / "b", "full", "configuration-and-debug", "lab_drive_test", {"output": "vcc"})
        with pytest.raises(P.NeverRefused):                                                  # registered tools are scanned by the never-rules too
            _gate(tmp_path / "c", "full", "configuration-and-debug", "lab_drive_test", {"output": "laser", "state": "on"})
        with pytest.raises(ValueError):
            P.register_tool_action("x", "not_an_action")
    finally:
        P._EXTRA_TOOL_ACTIONS.pop("lab_drive_test", None)


def test_the_stage_actions_cover_what_the_graph_runs_itself():
    assert "run_simulation" in P.stage_actions(2) and "run_vivado" not in P.stage_actions(2)
    assert "run_vivado" in P.stage_actions(3) and "edit_design_files" in P.stage_actions(3) and "edit_design_files" not in P.stage_actions(1)
    assert set(P.HW_APPROVAL_ACTIONS) <= set(P.stage_actions(9)) and not set(P.HW_APPROVAL_ACTIONS) & set(P.stage_actions(8))


# ---------------------------------------------------------------------------------------------------------------------------------------
# the real stage machine under each mode (scripted model, fake runner and fake programmer)

pytest.importorskip("langgraph")
pytest.importorskip("deepagents")

from langgraph.types import Command  # noqa: E402

from agent.graph import run as gr  # noqa: E402
from agent.tests.test_episode import FakeRunner, T1, scripted_client  # noqa: E402


@pytest.fixture
def world(monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    from flow import hw
    monkeypatch.setattr(hw, "load_board", lambda b: {"cable_serial": "TEST0000"})
    monkeypatch.setattr(hw, "power_ok", lambda d, b: {"pass": True, "total_w": 0.15, "junction_c": 42.7, "source": "wall"})
    yield runs
    shutil.rmtree(runs, ignore_errors=True)


def start(mode, overrides=None, rid=None, stop_after=None, **kw):
    seen, where = [], {}
    perm = {"mode": mode, "overrides": overrides or {}, "source": "test", "ask_above_usd": kw.pop("ask_above_usd", 1.0)}
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off", review="off", stop_after=stop_after, permissions=perm, **kw)
    rid = rid or "r222" + uuid.uuid4().hex[:4]
    runner = FakeRunner()
    rt = gr.new_runtime(cfg, scripted_client(seen, where), run_id=rid, runner=runner)
    (rt.design / "spec.md").write_text("A PWM dimmer counter for the board.\n")
    where["design"] = str(rt.design.relative_to(ROOT))
    graph = gr.build_graph(gr.checkpointer_for(rt.run_dir))
    return rt, graph, {"configurable": {"thread_id": rid}}, runner


def drive(rt, graph, lg, answer=None, limit=80):
    """Answer every interrupt: a permission question with ``answer(p)`` (default allow), a review with approve. Returns the final state and every interrupt, in order."""
    inp, seen = {"run_id": rt.run_id, "stage": 0, "visits": {}, "history": []}, []
    for _ in range(limit):
        graph.invoke(inp, lg)
        st = graph.get_state(lg)
        pend = [i.value for t in st.tasks for i in (t.interrupts or [])]
        if not pend:
            return st, seen
        p = pend[0]
        seen.append(p)
        if p["kind"] == "permission":
            inp = Command(resume=(answer(p) if answer else {"decision": "allow", "by": "planner"}))
        else:
            inp = Command(resume={"decision": "approve", "by": "planner"})
    raise AssertionError("the run did not end: " + json.dumps(seen[-3:], default=str))


def test_plan_mode_plans_estimates_and_stops_with_the_architecture_unapproved(world):
    rt, graph, lg, runner = start("plan")
    st, seen = drive(rt, graph, lg)
    assert not seen                                                                   # nobody is asked anything in Plan
    assert [h["n"] for h in st.values["history"]] == [0, 1] and st.values["stop"].startswith("plan complete")
    assert "simulate" not in runner.kinds and "build" not in runner.kinds and "bringup" not in runner.kinds        # no tool ran
    from flow import architecture as am
    assert not am.approval_status(rt.design)[0]                                        # the architecture is left for a person to approve
    est = json.loads((rt.run_dir / "plan_estimate.json").read_text())
    assert est["upper_bound"]["usd"] > 0 and "not a prediction" in est["note"]
    s = gr.summary(rt, st.values)
    assert s["permissions"]["mode"] == "plan" and s["plan_estimate"]["note"] and s["clean_stop"] is False
    assert any(d["action"] == "approve_architecture" and d["result"] == "denied" for d in s["permissions"]["decisions"])


def test_ask_mode_asks_for_each_gated_action_and_records_who_allowed_it(world):
    rt, graph, lg, runner = start("ask")
    st, seen = drive(rt, graph, lg)
    perms = [p for p in seen if p["kind"] == "permission"]
    asked = [(p["stage"], tuple(p["needs"])) for p in perms]
    assert asked[0] == (0, ("use_knowledge_bank",))                                      # the first stage asks for the bank
    assert any(n == ("edit_design_files",) and s == 2 for s, n in asked)                  # RTL: edit asked, simulation not (allowed by the mode)
    assert not any("run_simulation" in n for _, n in asked)
    assert any(s == 3 and "run_vivado" in n for s, n in asked)                           # Vivado asked when the first build stage starts
    assert all("program_board_sram" not in n for _, n in asked)                           # the board is asked at the hardware approval, not at the stage start
    reviews = [(p["stage"], p.get("hardware")) for p in seen if p["kind"] == "review"]
    assert [s for s, _ in reviews if s != 9][:3] == [0, 1, 2] and (9, True) in reviews     # a review for every stage, and the hardware approval
    assert any(p.get("permission") == ["approve_architecture", "approve_stage"] for p in seen if p["kind"] == "review")    # stage 1 is both
    assert st.values["stop"] == "done" and "bringup" in runner.kinds
    s = gr.summary(rt, st.values)
    pm = s["permissions"]
    assert pm["mode"] == "ask" and pm["granted"]["use_knowledge_bank"] == "planner"
    granted = {d["action"] for d in pm["decisions"] if d["result"] == "granted"}
    assert {"use_knowledge_bank", "edit_design_files", "run_vivado", "program_board_sram", "write_board_register"} <= granted
    rows = P.Policy.load(rt.run_dir).decisions()
    assert all(r["when"] and r["by"] and r["action"] in P.ACTION_NAMES for r in rows)
    assert any(r["result"] == "allowed" and r["action"] == "run_simulation" and r["by"] == "mode ask" for r in rows)


def test_auto_mode_asks_only_at_the_board(world):
    rt, graph, lg, runner = start("auto")
    st, seen = drive(rt, graph, lg)
    assert [p for p in seen if p["kind"] == "permission"] == []
    assert [(p["stage"], p["hardware"]) for p in seen] == [(9, True)]                    # the existing hardware pause, and nothing else
    assert st.values["stop"] == "done" and "bringup" in runner.kinds
    pm = gr.summary(rt, st.values)["permissions"]
    assert pm["mode"] == "auto" and pm["granted"]["program_board_sram"].startswith("owner")
    assert any(d["action"] == "run_vivado" and d["result"] == "allowed" and d["by"] == "mode auto" for d in pm["decisions"])


def test_full_mode_programs_the_mock_board_without_asking(world):
    rt, graph, lg, runner = start("full")
    st, seen = drive(rt, graph, lg)
    assert seen == []                                                                  # no question, no review, no hardware pause
    assert st.values["stop"] == "done" and st.values["evidence"]["bringup"]["pass"] and "bringup" in runner.kinds        # the mock programmer ran
    pm = gr.summary(rt, st.values)["permissions"]
    assert pm["mode"] == "full" and any(d["action"] == "program_board_sram" and d["result"] == "allowed" and d["by"] == "mode full" for d in pm["decisions"])
    assert pm["granted"]["write_board_register"].startswith("mode full")


def test_a_deny_override_stops_the_run_where_it_is_needed_with_the_reason(world):
    rt, graph, lg, runner = start("auto", {"run_vivado": "deny"})
    st, seen = drive(rt, graph, lg)
    assert st.values["stop"].startswith("permission denied: Run Vivado synthesis and implementation (run_vivado)") and "override deny run_vivado" in st.values["stop"]
    assert [h["n"] for h in st.values["history"]][-1] == 3 and "build" not in runner.kinds
    assert st.values["stop_detail"]["permission"]["needs"] == ["run_vivado"] and "resume" in st.values["stop_detail"]["permission"]["change"]
    from agent.__main__ import drive_exit
    assert drive_exit({"stop": st.values["stop"]}) == 4


def test_declining_a_question_stops_the_run_and_is_recorded(world):
    rt, graph, lg, runner = start("ask")
    st, seen = drive(rt, graph, lg, answer=lambda p: {"decision": "deny", "by": "you"})
    assert st.values["stop"].startswith("permission denied: Use the knowledge bank and IP library (use_knowledge_bank) was declined by you")
    assert [h["n"] for h in st.values["history"]] == [0] and not runner.kinds
    assert P.Policy.load(rt.run_dir).refused["use_knowledge_bank"]["by"] == "you"


def test_a_partial_answer_grants_what_was_named_and_declines_the_rest(world):
    rt, graph, lg, runner = start("ask", {"use_knowledge_bank": "allow"})
    st, seen = drive(rt, graph, lg, answer=lambda p: {"allow": ["edit_design_files"], "by": "you"} if "run_vivado" not in p["needs"] else {"allow": [], "by": "you"})
    assert st.values["stop"].startswith("permission denied") and "run_vivado" in st.values["stop"] and "edit_design_files" not in st.values["stop"]


def test_spending_past_the_threshold_is_a_gated_action(world):
    rt, graph, lg, runner = start("ask", {"use_knowledge_bank": "allow", "edit_design_files": "allow", "run_vivado": "allow", "approve_architecture": "allow", "approve_stage": "allow"},
                                  ask_above_usd=0.0)
    st, seen = drive(rt, graph, lg)
    assert any(p["kind"] == "permission" and p["needs"] == ["spend_model_money"] for p in seen)
    rt2, graph2, lg2, _ = start("plan", ask_above_usd=0.0, rid="r222plan0")
    st2, _ = drive(rt2, graph2, lg2)
    assert st2.values["stop"].startswith("permission denied") and "spend_model_money" in st2.values["stop"]       # Plan never spends past the threshold


def test_the_headless_run_stops_at_the_first_ungranted_action_with_what_it_needs(world, capsys):
    from agent.__main__ import NEEDS_PERMISSION, _drive, drive_exit
    rt, graph, lg, runner = start("ask")
    res = _drive(graph, rt, lg, {"run_id": rt.run_id, "stage": 0, "visits": {}, "history": []}, [])
    out = json.loads(capsys.readouterr().out)
    assert res["status"] == NEEDS_PERMISSION == out["status"] and out["needs"] == ["use_knowledge_bank"] and out["paused"]["kind"] == "permission"
    assert "--allow <action>" in out["or"] and "--reply" in out["how"]
    assert drive_exit(res) == 3
    pend = json.loads((rt.run_dir / "pending.json").read_text())
    assert pend["paused"]["kind"] == "permission" and pend["paused"]["actions"][0]["plain"]
    from navigator import summary as NS                                                  # the Navigator's question panel reads the same file
    p = NS._pending(rt.run_dir)
    assert p["kind"] == "permission" and p["needs"] == ["use_knowledge_bank"] and p["actions"][0]["label"] == "Use the knowledge bank and IP library"
    assert not runner.kinds                                                              # nothing ran, nothing was skipped silently
    res2 = _drive(graph, rt, lg, None, [{"decision": "allow", "by": "you"}, {"decision": "approve"}, {"decision": "approve"}])   # a reply resumes it; two reviews, then the RTL stage asks to edit
    assert res2["paused"]["kind"] == "permission" and res2["paused"]["needs"] == ["edit_design_files"]


def test_a_run_started_with_no_flag_is_auto_and_says_so(world):
    seen, where = [], {}
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off", review="off")
    rt = gr.new_runtime(cfg, scripted_client(seen, where), run_id="r222def", runner=FakeRunner())
    assert rt.policy.mode == "auto" and "before brief 222" in rt.policy.source
    assert json.loads((rt.run_dir / "config.json").read_text())["permissions"]["mode"] == "auto"
    assert json.loads((rt.run_dir / "permissions.json").read_text())["mode"] == "auto"


def test_a_resume_keeps_the_runs_own_policy_and_a_new_mode_drops_its_grants(world):
    rt, graph, lg, runner = start("ask", rid="r222res")
    rt.policy.grant(["run_vivado"], "you")
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off", review="off", permissions={"mode": "full"})
    rt2 = gr.new_runtime(cfg, None, run_id="r222res", runner=FakeRunner())
    assert rt2.policy.mode == "ask" and "run_vivado" in rt2.policy.granted                  # the run's own state wins over a config default
    from agent.__main__ import resume_permissions
    a = argparse.Namespace(permissions="auto", allow=["run_vivado"], deny=[], ask=[], ask_above_usd=None, max_usd=None, budget_scale=None)
    assert resume_permissions(a, rt2, {"run_limits": {"usd": 3.0}}) is None
    assert rt2.policy.mode == "auto" and rt2.policy.granted == {} and rt2.policy.history[-1]["from"] == "ask" and rt2.policy.overrides == {"run_vivado": "allow"}


def test_raising_the_cost_cap_on_a_resume_is_a_gated_action(world, capsys):
    from agent.__main__ import resume_permissions
    rt, *_ = start("auto", rid="r222rb1")
    ns = lambda **k: argparse.Namespace(**{"permissions": None, "allow": [], "deny": [], "ask": [], "ask_above_usd": None, "max_usd": 6.0, "budget_scale": None, **k})   # noqa: E731
    assert resume_permissions(ns(), rt, {"run_limits": {"usd": 3.0}}) == 3                      # Auto asks
    assert json.loads(capsys.readouterr().out)["needs"] == ["raise_budget"]
    assert resume_permissions(ns(max_usd=2.0), rt, {"run_limits": {"usd": 3.0}}) is None          # lowering is not raising
    assert resume_permissions(ns(allow=["raise_budget"]), rt, {"run_limits": {"usd": 3.0}}) is None
    rt2, *_ = start("full", rid="r222rb2")
    capsys.readouterr()
    assert resume_permissions(ns(), rt2, {"run_limits": {"usd": 3.0}}) == 4                      # Full stops at the caps
    assert json.loads(capsys.readouterr().out)["status"] == "permission_denied"


def test_the_handover_lists_the_mode_and_every_decision(world):
    from agent.graph import document as D
    from flow import handover as H
    rt, graph, lg, runner = start("full")
    st, _ = drive(rt, graph, lg)
    s = gr.summary(rt, st.values)
    f = D.agent_facts({**s, "model": "m", "harness": "deepagents"})
    assert f["permissions"]["mode"] == "full" and any(x.startswith("allowed program_board_sram by mode full at stage configuration-and-debug") for x in f["permissions"]["decisions"])
    assert not any(ch.isdigit() for x in f["permissions"]["decisions"] for ch in x.split(" (")[0])          # no times in the handover: they are in permissions.jsonl
    assert "permission mode full" in H.run_line({**f})


def test_the_cli_takes_the_flags_and_refuses_unknown_names():
    from agent.__main__ import build_parser
    ap = build_parser()
    a = ap.parse_args(["run", "spec.md", "--permissions", "ask", "--allow", "run_vivado", "--deny", "program_board_sram", "--ask", "read_board", "--ask-above-usd", "2"])
    assert (a.permissions, a.allow, a.deny, a.ask, a.ask_above_usd) == ("ask", ["run_vivado"], ["program_board_sram"], ["read_board"], 2.0)
    for bad in (["--permissions", "yolo"], ["--allow", "flash_everything"]):
        with pytest.raises(SystemExit):
            ap.parse_args(["run", "spec.md", *bad])
    r = ap.parse_args(["resume", "r1", "--permissions", "auto"])
    assert r.permissions == "auto"


def test_the_handover_schema_accepts_the_permissions_block_and_refuses_a_stray_key():
    import jsonschema
    schema = json.loads((ROOT / "flow" / "handover.schema.json").read_text())
    ar = schema["properties"]["agent_run"]
    good = {"run_id": "r", "record": "runs/r/summary.json", "permissions": {"mode": "ask", "source": "command line", "overrides": {"run_vivado": "deny"},
                                                                          "decisions": ["allowed run_simulation by mode ask at stage rtl-design-creation"]}}
    jsonschema.validate(good, {**ar, "$defs": schema.get("$defs", {})})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**good, "permissions": {"mode": "ask", "extra": 1}}, {**ar, "$defs": schema.get("$defs", {})})
