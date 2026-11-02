"""Brief 05d, Taylor additions 1, 2, 4 and 6 in the graph: proof methods in the spec, the architecture gate and its
approval, resource-sanity routing, the owner-edit ledger. Scripted model and fake runner: no spend."""

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
import yaml

pytest.importorskip("langgraph")
pytest.importorskip("deepagents")

from agent.core.artefacts import check_artefact  # noqa: E402
from agent.core.security import SecurityError  # noqa: E402
from agent.core.session import ROOT, Session  # noqa: E402
from agent.graph import ownership  # noqa: E402
from agent.graph import run as gr  # noqa: E402
from agent.graph.roles import RoleJail  # noqa: E402
from agent.graph.spec_schema import propose_proof, requirement_errors, validate  # noqa: E402
from agent.graph.stages import MACHINE, classify, exit_check, resource_cause, route_failure  # noqa: E402
from agent.tests.test_episode import FakeRunner, T1, scripted_client  # noqa: E402
from flow import architecture as am  # noqa: E402

SPEC = yaml.safe_load((T1 / "spec.yaml").read_text())


# ---- 1. a proof method per requirement -----------------------------------------------------------------------------

def test_requirements_need_ids_and_methods():
    assert requirement_errors(SPEC) == []
    bad = {"requirements": [{"id": "A", "text": "x"}, {"id": "A", "text": "y", "proof": ["magic"]}]}
    errs = "; ".join(requirement_errors(bad))
    assert "requirement A has no proof method" in errs and "used twice" in errs and "magic" in errs
    assert requirement_errors(bad, need_proof=False)[0].startswith("requirement id A is used twice")
    spec = {**SPEC, "requirements": [{"id": "R", "text": "t"}]}
    assert any("no proof method" in e for e in validate(spec)) and not any("no proof" in e for e in validate(spec, need_proof=False))
    assert any("'requirements'" in e for e in validate({k: v for k, v in SPEC.items() if k != "requirements"}))


def test_proposed_methods_come_with_a_reason():
    assert propose_proof("The design closes timing at 100 MHz")[0] == ["analysis"]
    assert propose_proof("The FIFO never overflows")[0] == ["simulation", "formal"]
    m, why = propose_proof("The counter counts presses")
    assert m == ["simulation"] and why


def test_a_spec_with_a_proofless_requirement_is_refused_at_write_time_only_when_malformed():
    s = dict(SPEC, requirements=[{"id": "R1", "text": "t"}])
    assert check_artefact("spec.yaml", yaml.safe_dump(s)) is None              # the interview fills the method in
    s = dict(SPEC, requirements=[{"id": "R1", "text": "t", "proof": ["magic"]}])
    assert "magic" in check_artefact("spec.yaml", yaml.safe_dump(s))


def test_testplan_proof_shape_is_checked_at_write_time():
    plan = yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    assert check_artefact("verif/testplan.yaml", yaml.safe_dump(plan)) is None
    plan["proof"] = [{"requirement": "R", "method": "vibes", "artefact": "x"}]
    assert "'proof' must be a list" in check_artefact("verif/testplan.yaml", yaml.safe_dump(plan))


@pytest.fixture
def rt(monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off")
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=FakeRunner())
    yield r
    shutil.rmtree(runs, ignore_errors=True)


def test_the_interview_asks_for_a_missing_method_with_default_and_reason(rt):
    spec = dict(SPEC, requirements=[{"id": "R1", "text": "The design closes timing at 100 MHz"},
                                    {"id": "R2", "text": "Counts presses", "proof": ["simulation"]}], open_questions=[])
    spec, summary = gr._interview(rt, spec, {})
    assert summary["asked"] == 1 and summary["defaulted"] == 1
    q = summary["questions"][0]
    assert "requirement R1" in q["text"] and q["default"] == "analysis" and "reports" in q["reason"]
    assert spec["requirements"][0]["proof"] == ["analysis"] and spec["requirements"][1]["proof"] == ["simulation"]


# ---- 2. the architecture gate -----------------------------------------------------------------------------------------

def test_architecture_yaml_is_validated_when_written():
    assert check_artefact("architecture.yaml", (T1 / "architecture.yaml").read_text()) is None
    bad = yaml.safe_load((T1 / "architecture.yaml").read_text())
    del bad["predicted_resources"]["dsp"]
    assert "predicted_resources has no 'dsp'" in check_artefact("architecture.yaml", yaml.safe_dump(bad))


def test_stage_2_needs_an_approved_architecture_and_a_later_edit_reopens_it(rt):
    ev = {"arch_approval": {"ok": False, "why": "the architecture has not been approved"}}
    ok, fails = exit_check(MACHINE[2], ev)
    assert not ok and fails[0].startswith("architecture not approved")
    assert route_failure(MACHINE[2], classify(MACHINE[2], fails)) == 1       # back to the architecture stage
    shutil.copy(T1 / "architecture.yaml", rt.design / "architecture.yaml")
    (rt.design / "ARCHITECTURE.md").write_text("# a\n## Block diagram\n```\nx\n```\n")
    # RTL work does not start without an approval
    out = gr.node_work({"run_id": rt.run_id, "stage": 2, "visits": {}})
    assert "did not start" in out["detail"] and not list((rt.design / "rtl").glob("*")) if (rt.design / "rtl").exists() else True
    gate = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert gate["fails"][0].startswith("architecture not approved") and "simulate" not in rt.session.runner.kinds
    am.write_approval(rt.design, "owner", "agent")
    (rt.design / "architecture.yaml").write_text((rt.design / "architecture.yaml").read_text() + "# edited\n")
    assert "changed after it was approved" in am.approval_status(rt.design)[1]


def test_the_rtl_writer_cannot_edit_an_approved_architecture(rt):
    s = rt.session
    RoleJail(s.jail, "rtl").resolve("architecture.yaml", write=True)              # open: allowed (stage 1)
    am.write_approval(rt.design, "auto", "agent")
    with pytest.raises(SecurityError, match="approved and frozen"):
        RoleJail(s.jail, "rtl").resolve("ARCHITECTURE.md", write=True)
    RoleJail(s.jail, "rtl").resolve("rtl/top.sv", write=True)                    # RTL stays writable


# ---- 4. resource sanity routing ------------------------------------------------------------------------------------------

def test_resource_failures_route_to_architecture_or_rtl():
    over = ["post_synth:post_synth_resources_in_range", "resources: lut used 5000 outside the predicted [350.0, 700.0] "
            "by more than 2x (above; allowed [175.0, 1400.0])"]
    assert resource_cause(over) == "arch" and route_failure(MACHINE[4], classify(MACHINE[4], over)) == 1
    ram_as_luts = ["resources: lut used 5000 outside the predicted [1, 2] by more than 2x (above; allowed [1, 4])",
                   "resources: bram_tile used 0 outside the predicted [2.0, 2.0] by more than 2x (below; allowed [1.0, 4.0])"]
    assert classify(MACHINE[4], ram_as_luts) == "rtl" and route_failure(MACHINE[4], "rtl") == 2
    # a standards finding after synthesis is constraint-shaped
    assert classify(MACHINE[4], ["standards STD-CDC-02: x:1: y"]) == "constraints"


def test_post_synth_stage_fails_on_the_resource_gate_with_raw_numbers():
    sanity = am.resource_check({"lut": 5000, "ff": 400, "bram_tile": 0, "dsp": 0},
                               {"predicted_resources": {"lut": [350, 700], "ff": [350, 700], "bram_tile": 0, "dsp": 0}})
    g = {"stages": {"post_synth": {"ran": True, "gates": {"post_synth_resources_in_range": False},
                                   "resource_sanity": sanity}}}
    ok, why = exit_check(MACHINE[4], {"gates_base": g, "standards": {"rules": []}})
    assert not ok and any(w.startswith("resources: lut used 5000") for w in why)


# ---- 6. the owner-edit ledger ---------------------------------------------------------------------------------------------

def _drive(tmp_path, monkeypatch, review, replies, stop_after=3, before_reply=None):
    """The T1 episode with the scripted model, to stage ``stop_after``. ``replies``: stage -> list of replies."""
    from langgraph.types import Command
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    from flow import hw
    monkeypatch.setattr(hw, "load_board", lambda b: {"cable_serial": "TEST0000"})
    hidden = tmp_path / "full.yaml"
    hidden.write_text((T1 / "spec.yaml").read_text())
    where, seen = {}, []
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="oracle", review=review, hidden_spec=hidden,
                    stop_after=stop_after)
    rt = gr.new_runtime(cfg, scripted_client(seen, where), run_id="d", runner=FakeRunner(),
                        oracle_llm=lambda s, u: {"answer": "not specified", "quote": None})
    where["design"] = str(rt.design.relative_to(ROOT))
    graph = gr.build_graph(gr.checkpointer_for(rt.run_dir))
    lg = {"configurable": {"thread_id": "d"}}
    inp = {"run_id": "d", "stage": 0, "visits": {}, "history": []}
    pauses = []
    while True:
        graph.invoke(inp, lg)
        st = graph.get_state(lg)
        pend = [i.value for t in st.tasks for i in (t.interrupts or [])]
        if not pend:
            break
        p = pend[0]
        pauses.append(p["stage"])
        if before_reply:
            before_reply(rt, p, pauses)
        queue = replies.get(p["stage"]) or [{"decision": "approve", "by": "owner"}]
        inp = Command(resume=queue.pop(0) if len(queue) > 1 else queue[0])
    return rt, st, pauses, runs


def test_review_off_records_the_architecture_approval_as_auto(tmp_path, monkeypatch):
    rt, st, pauses, runs = _drive(tmp_path, monkeypatch, "off", {}, stop_after=2)
    try:
        rec = am.read_approval(rt.design)
        assert rec["by"] == "auto" and rec["source"] == "agent" and am.approval_status(rt.design)[0]
        who = {(r["who"], r["what"]) for r in ownership.load(rt.design)}
        assert ("auto", "architecture approved") in who and not any(w == "owner" for w, _ in who)
        assert "Who did what" in (rt.design / "BUILD_NOTE.md").read_text()
        assert pauses == []                                                    # off: no pause at all
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_review_on_pauses_for_the_architecture_and_logs_a_scripted_hand_edit_as_owner(tmp_path, monkeypatch):
    def edit(rt, p, pauses):
        if p["stage"] == 2 and pauses.count(2) == 1:                           # between the pause and the reply
            f = rt.design / "rtl" / "debounce.sv"
            f.write_text(f.read_text() + "\n// owner: note added by hand\n")
    rt, st, pauses, runs = _drive(tmp_path, monkeypatch, "on", {}, stop_after=3, before_reply=edit)
    try:
        assert 1 in pauses                                                     # the architecture gate paused for the owner
        rec = am.read_approval(rt.design)
        assert rec["by"] == "owner" and rec["source"] == "agent"
        rows = ownership.load(rt.design)
        edits = [r for r in rows if r["what"] == "hand edit"]
        assert len(edits) == 1 and edits[0]["who"] == "owner" and "rtl/debounce.sv" in edits[0]["detail"]
        assert pauses.count(2) == 2                                            # an edited stage is gated again, then approved
        authors = subprocess.run(["git", f"--git-dir={rt.run_dir / 'snap.git'}", "log", "--format=%an|%s"],
                                 capture_output=True, text=True).stdout
        assert any(l.startswith("owner|") and "owner hand edit" in l for l in authors.splitlines())
        assert "who-did-what" in (rt.design / "BUILD_NOTE.md").read_text()
        table = (rt.design / "BUILD_NOTE.md").read_text()
        assert "| owner |" in table and "| agent |" in table
        assert (rt.design / "rtl" / "debounce.sv").read_text().rstrip().endswith("owner: note added by hand")   # not rewritten
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_owner_supplied_architecture_is_an_owner_contribution(tmp_path, monkeypatch):
    mine = (T1 / "architecture.yaml").read_text().replace("[350, 700]", "[300, 800]")
    replies = {1: [{"decision": "supply", "by": "owner", "files": {"architecture.yaml": mine}}, {"decision": "approve", "by": "owner"}]}
    rt, st, pauses, runs = _drive(tmp_path, monkeypatch, "on", replies, stop_after=2)
    try:
        rec = am.read_approval(rt.design)
        assert rec["source"] == "owner" and rec["by"] == "owner"
        assert "[300, 800]" in (rt.design / "architecture.yaml").read_text()
        rows = ownership.load(rt.design)
        assert any(r["who"] == "owner" and r["what"] == "supplied architecture" for r in rows)
        assert "owner contribution" in (rt.design / "BUILD_NOTE.md").read_text()
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_an_edit_prompt_goes_to_the_named_role(tmp_path, monkeypatch):
    replies = {1: [{"decision": "edit", "by": "owner", "note": "use two clock domains", "role": "rtl"},
                   {"decision": "approve", "by": "owner"}]}
    rt, st, pauses, runs = _drive(tmp_path, monkeypatch, "on", replies, stop_after=1)
    try:
        rows = ownership.load(rt.design)
        assert any(r["who"] == "owner" and "asked for changes" in r["what"] and "two clock domains" in r["detail"] for r in rows)
        assert pauses.count(1) == 2
    finally:
        shutil.rmtree(runs, ignore_errors=True)
