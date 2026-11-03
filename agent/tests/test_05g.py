"""Brief 05g, offline: the test writer's diagnosed failures (turn starvation, repair deleting its own output, the
shell fixtures it could not read), the turn trace, the QoR warning on the review page, and the knowledge-use log."""

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from agent.claude_code_arm import arm
from agent.core import Session, dispatch
from agent.core.runner import RunResult
from agent.core.session import ROOT
from agent.graph import llm
from agent.graph import run as gr
from agent.graph.roles import RoleJail, role_inputs
from agent.graph.stages import MACHINE

T1 = ROOT / "designs" / "t1_dimmer_counter"


class Runner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        return RunResult(0, "ok", "", 0.0)


@pytest.fixture
def rt(monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter")
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=Runner())
    (r.design / "spec.yaml").write_text("name: x\n")
    yield r
    shutil.rmtree(runs, ignore_errors=True)


def enter(rt, n):
    rt.meter.start_stage(MACHINE[n].limits)
    rt.session.stage = MACHINE[n].name
    rt.visit = 1


def usage(rt):
    f = rt.run_dir / "role_usage.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


# ---- 1. the stage-9 turn starvation (luna run f7ba, visits 1 and 2) --------------------------------------------------

def burn(rt, n_turns):
    """A fake sub-agent: one meter turn per step, as the Deep Agents model wrapper does."""
    def fake(rt_, role, prompt, allowed, repair, spec):
        for _ in range(n_turns):
            rt_.meter.check()
            rt_.meter.stage["turns"] += 1
            rt_.meter.run["turns"] += 1
        return {}
    return fake


def test_the_rtl_writer_cannot_use_the_turns_the_tests_role_needs(rt, monkeypatch):
    enter(rt, 9)
    ran = []

    def fake(rt_, role, prompt, allowed, repair, spec):
        if role == "rtl":
            return burn(rt, 10_000)(rt_, role, prompt, allowed, repair, spec)       # takes everything it is given
        ran.append((role, rt_.meter.turns_left()))
        for _ in range(5):
            rt_.meter.check()
            rt_.meter.stage["turns"] += 1
            rt_.meter.run["turns"] += 1
        return {}
    monkeypatch.setattr(gr, "_run_subagent", fake)
    gr.run_role(rt, "rtl", "p", ())
    assert rt.meter.stage["turns"] == MACHINE[9].limits["turns"] - gr.ROLE_TURN_RESERVE[9]["rtl"]      # the reserve is untouched
    assert rt.budget_notes and "held back for the roles that follow" in rt.budget_notes[0]
    gr.run_role(rt, "tests", "p", ())
    assert ran == [("tests", gr.ROLE_TURN_RESERVE[9]["rtl"])]
    rows = usage(rt)
    assert [(r["role"], r["ended"]) for r in rows] == [("rtl", "stage_budget"), ("tests", "done")]
    assert rows[0]["visit"] == 1 and rows[1]["turns"] == 5 and rows[1]["turns_allowed"] == 15


def test_a_role_that_hits_the_stage_budget_does_not_stop_the_visit(rt, monkeypatch):
    """Before 05g the BudgetExceeded left node_work and the tests role never ran."""
    (rt.design / "probes.yaml").write_text("probes: []\n")
    called = []

    def fake(rt_, role, prompt, allowed, repair, spec):
        called.append(role)
        if role == "rtl":
            return burn(rt, 10_000)(rt_, role, prompt, allowed, repair, spec)
        return {}
    monkeypatch.setattr(gr, "_run_subagent", fake)
    out = gr.node_work({"run_id": rt.run_id, "stage": 9, "visits": {}})
    assert called == ["rtl", "tests"]
    assert out["detail"].startswith("stage visit ended on the turn budget: rtl:")


def test_the_real_run_limit_still_stops_the_run(rt, monkeypatch):
    enter(rt, 9)
    rt.meter.run["turns"] = rt.meter.run_limits["turns"]
    monkeypatch.setattr(gr, "_run_subagent", burn(rt, 1))
    with pytest.raises(llm.BudgetExceeded, match="run turns"):
        gr.run_role(rt, "rtl", "p", ())
    assert usage(rt)[0]["ended"] == "run_budget"


def test_stage_budgets_leave_room(rt):
    assert MACHINE[9].limits["turns"] - gr.ROLE_TURN_RESERVE[9]["rtl"] >= 30         # the RTL writer keeps what it had
    assert MACHINE[2].limits["turns"] - gr.ROLE_TURN_RESERVE[2]["tests"] >= 45 and MACHINE[2].limits["turns"] >= 60


# ---- 2. the Claude Code arm's repair deleted the tests role's own output (05f runs 0d63 and 9b4d) ------------------------

def _cc(rt, monkeypatch, writes):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token")

    def fake_run(argv, **kw):
        if argv[1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "2.1.317 (Claude Code)\n", "")
        for rel, text in writes.items():
            (rt.design / rel).parent.mkdir(parents=True, exist_ok=True)
            (rt.design / rel).write_text(text)
        return subprocess.CompletedProcess(argv, 0, json.dumps({"type": "result", "num_turns": 3, "subtype": "success",
                                                                 "is_error": False, "result": "DONE"}), "")
    monkeypatch.setattr(arm.subprocess, "run", fake_run)
    monkeypatch.setattr(arm.shutil, "which", lambda n: "/bin/claude")


def _tests_dir(rt):
    for rel in ("tests/test_t1_dimmer_counter_rtl.py", "tests/bench.py", "verif/testplan.yaml"):
        (rt.design / rel).parent.mkdir(parents=True, exist_ok=True)
        (rt.design / rel).write_text("old\n")


def test_a_tests_repair_through_the_cc_arm_keeps_the_files_it_did_not_rewrite(rt, monkeypatch):
    rt.cfg.harness, rt.cfg.cc_model = "claude_code", "claude-haiku-5-5"
    enter(rt, 2)
    _tests_dir(rt)
    _cc(rt, monkeypatch, {"verif/formal/job.sby": "x\n"})          # what run 0d63's last repair wrote
    gr.run_subagent(rt, "tests", "P", ("search_docs",), repair=True)
    assert (rt.design / "tests" / "bench.py").is_file() and (rt.design / "verif" / "testplan.yaml").is_file()
    assert (rt.design / "tests" / "test_t1_dimmer_counter_rtl.py").is_file()


def test_a_fresh_tests_write_still_replaces_the_old_output(rt, monkeypatch):
    rt.cfg.harness, rt.cfg.cc_model = "claude_code", "claude-haiku-5-5"
    enter(rt, 2)
    _tests_dir(rt)
    _cc(rt, monkeypatch, {"tests/test_t1_dimmer_counter_rtl.py": "new\n", "verif/testplan.yaml": "new\n"})
    gr.run_subagent(rt, "tests", "P", ("search_docs",), repair=False)
    assert not (rt.design / "tests" / "bench.py").exists() and (rt.design / "verif" / "testplan.yaml").read_text() == "new\n"


# ---- 3. what the tests role can read and is told ---------------------------------------------------------------------

def test_the_tests_role_reads_the_shell_protocol_and_host_classes_but_not_its_rtl_or_the_design_rtl(rt):
    j = RoleJail(rt.session.jail, "tests")
    for ok in ("@shell/PROTOCOL.md", "@shell/host/protocol.py", "@shell/host/fpga_shell.py"):
        assert j.resolve(ok).is_file(), ok
    from agent.core.security import SecurityError
    for bad in ("@shell/rtl/fpga_shell.sv", "@shell/../flow/build.tcl", "rtl/top.sv"):
        with pytest.raises(SecurityError):
            j.resolve(bad)
    with pytest.raises(SecurityError):
        j.resolve("@shell/host/fpga_shell.py", write=True)
    r = RoleJail(rt.session.jail, "rtl")
    with pytest.raises(SecurityError):
        r.resolve("@shell/host/fpga_shell.py")                       # the RTL writer's view is unchanged


def test_tests_inputs_carry_the_shell_reference_files(rt):
    enter(rt, 2)
    keys2 = role_inputs(rt.session, "tests")
    assert "shell_ref/PROTOCOL.md" in keys2 and "shell_ref/host/fpga_shell.py" not in keys2
    enter(rt, 9)
    keys9 = role_inputs(rt.session, "tests")
    assert {"shell_ref/PROTOCOL.md", "shell_ref/host/fpga_shell.py", "shell_ref/host/protocol.py"} <= set(keys9)
    assert "FpgaShell" in keys9["shell_ref/host/fpga_shell.py"]
    assert not any(k.startswith("rtl/") for k in role_inputs(rt.session, "tests"))


def test_the_checklist_names_the_files_the_gates_read(rt, monkeypatch):
    import agent.core.runner as runner
    monkeypatch.setattr(runner, "tool_available", lambda n: False)
    t2 = gr.tests_checklist(rt, 2, repair=False)
    for needle in ("tests/test_t1_dimmer_counter_rtl.py", "verif/testplan.yaml", "proof_methods_discharged", "bench.modules",
                   "parameters=", "200,000 cycles",
                   "NOT installed", "replan:", "A file you leave out is a failed gate"):
        assert needle in t2, needle
    monkeypatch.setattr(runner, "tool_available", lambda n: True)
    t2i = gr.tests_checklist(rt, 2, repair=False)
    assert "SymbiYosys is installed" in t2i and "replan:" not in t2i
    t9 = gr.tests_checklist(rt, 9, repair=True)
    for needle in ("tests/test_t1_dimmer_counter_hw.py", "hw_checks.py", "shell_ref/host/fpga_shell.py", "never delete another"):
        assert needle in t9, needle


def test_the_checklist_reaches_both_harness_prompts(rt, monkeypatch):
    enter(rt, 2)
    seen = {}
    monkeypatch.setattr(gr, "run_role", lambda rt_, role, prompt, allowed=(), repair=False: seen.setdefault(role, prompt) or {})
    (rt.design / "model.py").write_text("x = 1\n")
    (rt.design / "rtl").mkdir()
    (rt.design / "rtl" / "a.sv").write_text("module a; endmodule\n")
    from flow import architecture as am
    monkeypatch.setattr(am, "approval_status", lambda d: (True, ""))
    gr.node_work({"run_id": rt.run_id, "stage": 2, "visits": {}})
    assert "STAGE-ENTRY CHECKLIST" in seen["tests"]


# ---- 4. the turn trace ---------------------------------------------------------------------------------------------

def test_the_turn_trace_lists_tools_refusals_and_files(rt, monkeypatch):
    enter(rt, 2)

    def fake(rt_, role, prompt, allowed, repair, spec):
        s = gr.role_session(rt_.session, role)
        dispatch(s, "read_file", {"path": "rtl/none.sv"})
        dispatch(s, "write_file", {"path": "rtl/x.sv", "content": "x"})                  # both refused: the tests role may not read or write rtl/
        rt_.meter.stage["turns"] += 2
        rt_.meter.run["turns"] += 2
        (rt_.design / "rtl").mkdir(exist_ok=True)
        (rt_.design / "rtl" / "written_through_a_backend.sv").write_text("x")      # not in the returned dict
        return {"tests/a.py": "x"}
    monkeypatch.setattr(gr, "_run_subagent", fake)
    gr.run_subagent(rt, "tests", "p", ())
    rec = usage(rt)[0]
    assert rec["tools"] == {"read_file": 1, "write_file": 1} and rec["refused"] == {"role": 2}
    assert rec["files_written"] == ["tests/a.py"] and rec["ended"] == "done" and rec["turns"] == 2 and rec["visit"] == 1
    assert rec["model_tool_calls"] == {}                         # nothing was logged by the fake model
    assert rec["files_changed"] == ["rtl/written_through_a_backend.sv"]
    tr = gr.usage_trace(usage(rt))
    assert tr[0]["role"] == "tests" and tr[0]["turns_allowed"] == MACHINE[2].limits["turns"]


# ---- 5. QoR warning on the review page ---------------------------------------------------------------------------------

def test_the_review_page_shows_the_recorded_qor_warning(tmp_path):
    from agent.graph.review import write_page
    d = tmp_path / "d"
    (d / "build" / "base").mkdir(parents=True)
    (d / "spec.yaml").write_text("name: x\n")
    (d / "build" / "base" / "gates.json").write_text(json.dumps({"warnings": [
        {"name": "post_synth_qor_assessment", "stage": "post_synth", "score": 3, "min": 4,
         "meaning": "Design will likely not meet timing", "note": "post-synthesis score is a prediction"}]}))
    html = write_page(d, 4, "synthesis", {"gates": [["post_synth_drc_clean", True, ""]], "approval": None}).read_text()
    assert "Warnings (recorded, not gates)" in html and "post_synth_qor_assessment" in html and "score 3 (min 4)" in html


# ---- 6. knowledge use -----------------------------------------------------------------------------------------------

class FakeBank:
    def __init__(self):
        self.calls = []

    def skills(self, board, family, sections, primary_only=True, procedures=False):
        self.calls.append((tuple(sections), procedures))
        db = {("reset", False): [("techniques/reset/a/SKILL.md", "reset")],
              ("verification-stages", True): [("procedures/verification-stages/v0/SKILL.md", "verification-stages"),
                                              ("procedures/verification-stages/v1/SKILL.md", "verification-stages")]}
        return [{"path": p, "section": sec, "axis": "x", "name": "n", "description": "", "text": f"text of {p}"}
                for sec in sections for (k, pr), v in db.items() if k == sec and pr == procedures for p, sec2 in v]

    def search(self, query, k=5, sections=None):
        return [{"id": "ross/a", "doc": "d", "section": "reset", "score": 1.0, "text": "t"}]


def _bank_session(tmp_path):
    return Session(design=tmp_path, board="nexys_a7_100t", bank=FakeBank())


def test_load_skill_reaches_a_procedures_only_section_and_logs_what_it_returned(tmp_path):
    s = _bank_session(tmp_path)
    r = dispatch(s, "load_skill", {"sections": ["reset", "verification-stages"]})
    assert r["skills"] == ["techniques/reset/a/SKILL.md", "procedures/verification-stages/v0/SKILL.md",
                           "procedures/verification-stages/v1/SKILL.md"]
    assert r["procedures_fallback"] == ["verification-stages"] and r["sections_empty"] == []
    rec = s.audit.records[-1]
    assert rec["skills"] == r["skills"] and rec["procedures_fallback"] == ["verification-stages"]


def test_load_skill_records_an_empty_section_and_an_empty_call(tmp_path):
    s = _bank_session(tmp_path)
    r = dispatch(s, "load_skill", {"sections": ["debug-ila-vio"]})
    assert r["skills"] == [] and r["sections_empty"] == ["debug-ila-vio"] and "no skill matches" in r["output"]
    rec = s.audit.records[-1]
    assert rec["skills"] == [] and rec["sections_empty"] == ["debug-ila-vio"]        # the empty list is logged, not dropped


def test_knowledge_use_summarises_sections_skills_hits_and_empty_calls(rt):
    s = Session(design=rt.design, board="nexys_a7_100t", bank=FakeBank(), stage="rtl-design-creation")
    s.jail = RoleJail(s.jail, "tests")
    dispatch(s, "load_skill", {"sections": ["reset", "verification-stages"]})
    dispatch(s, "load_skill", {"sections": ["debug-ila-vio"]})
    dispatch(s, "search_docs", {"query": "x"})
    rt.session = s
    ku = gr.knowledge_use(rt)["tests/rtl-design-creation"]
    assert ku["load_skill"]["calls"] == 2 and ku["load_skill"]["empty_calls"] == 1
    assert ku["load_skill"]["procedures_fallback"] == ["verification-stages"] and ku["load_skill"]["sections_empty"] == ["debug-ila-vio"]
    assert len(ku["load_skill"]["skills"]) == 3 and ku["search_docs"]["hits"] == ["ross/a"]


def test_the_bank_status_says_whether_the_bank_was_reachable(rt, monkeypatch):
    monkeypatch.setattr("agent.core.bank.DEFAULT_BANK", Path("/nonexistent/FPGA_Design_Agent_Knowledge"))
    st = gr.knowledge_bank_status(rt)
    assert st["present"] is False and st["root"] == "FPGA_Design_Agent_Knowledge" and st["head"] is None
    monkeypatch.setenv("FDA_KNOWLEDGE", "/x")
    assert gr.knowledge_bank_status(rt)["chosen_by"] == "FDA_KNOWLEDGE"
    rt.session.bank = None
    assert gr.knowledge_bank_status(rt)["loaded"] is False


def test_model_tool_calls_include_the_harness_built_ins(rt, monkeypatch):
    enter(rt, 9)

    def fake(rt_, role, prompt, allowed, repair, spec):
        for names in (["ls"], ["read_file", "write_todos"], ["write_file"], []):       # built-ins the audit never sees
            rt_.llm_log.append({"turn": 1, "cost": 0.0, "tokens": 1, "tools": names})
        return {}
    monkeypatch.setattr(gr, "_run_subagent", fake)
    rt.llm_log.append({"turn": 0, "cost": 0.0, "tokens": 1, "tools": ["earlier_call"]})
    gr.run_subagent(rt, "tests", "p", (), repair=True)
    assert usage(rt)[0]["model_tool_calls"] == {"ls": 1, "read_file": 1, "write_file": 1, "write_todos": 1}
    assert gr.usage_trace(usage(rt))[0]["model_tool_calls"]["write_todos"] == 1
