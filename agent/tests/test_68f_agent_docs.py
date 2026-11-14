"""Brief 68F: the fix round after the independent re-review of the agent-written handovers. Each finding has a test:
a gate detail that contradicts the run's own build records is caught and explained; verification entries name the V-stage
reached; provenance, build time and coverage come from the records; builds from an earlier Vivado release publish no number;
a stop before the gate is not written up as a failure of the stage; empty files are marked; spec rates reach the parameters."""

from __future__ import annotations

import copy
import json
import re
import shutil
import uuid
from pathlib import Path

import pytest

from agent.graph import document as D
from agent.graph import stages as ST
from flow import handover as H

ROOT = H.ROOT
REC = ROOT / "results" / "68_agent_docs"
C14, A8F2, S5A32 = "20261107-005621-8deb", "20261102-135505-a8f2", "20261102-114228-5a32"
DESIGN = {C14: "c14_int8_dot_requant", A8F2: "t1_dimmer_counter", S5A32: "t1_dimmer_counter"}


def _draft(run: str, design: Path | None = None, run_dir: Path | None = None):
    rd = run_dir or REC / run
    s = json.loads((REC / run / "summary.json").read_text())
    return D.draft(design or rd / DESIGN[run], rd, run_id=s["run_id"], board="nexys_a7_100t", gates_last=s["gates_last"],
                   stop=s["stop"])


@pytest.fixture
def run_copy(request):
    """A recorded run copied under runs/ (gitignored) so a record can be changed; no renderings."""
    run = getattr(request, "param", A8F2)
    dst = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    shutil.copytree(REC / run, dst)
    yield run, dst
    shutil.rmtree(dst, ignore_errors=True)


# --- finding 1: a gate detail that contradicts the build records ------------------------------------------------------

def test_stage9_detail_is_reconciled_with_the_build_records() -> None:
    h, _ = _draft(A8F2)
    gap = next(g for g in h["gaps"] if g["about"] == "configuration-and-debug")["text"]
    assert "bitstream: did not run" in gap and D.RECON in gap
    assert "base build's bitstream stage ran" in gap and "error stub" in gap and "debug build with the ILA" in gap
    h5, _ = _draft(S5A32)
    gap5 = next(g for g in h5["gaps"] if g["about"] == "configuration-and-debug")["text"]
    assert "no build/ila record" in gap5 and "no debug build with the ILA was attempted or recorded" in gap5


def test_gap_quoting_a_contradicted_detail_without_saying_so_is_flagged() -> None:
    d = REC / A8F2 / DESIGN[A8F2]
    bad = {"gaps": [{"about": "configuration-and-debug",
                     "text": "stage configuration-and-debug did not pass its gates in this run; at its last visit: bitstream: did not run FAIL"}]}
    assert any("contradict" in e for e in D.contradictions(d, bad))
    h, _ = _draft(A8F2)
    assert D.contradictions(d, h) == []                       # the generated gap carries the reconciliation
    assert D.contradictions(d, {"gaps": [{"about": "latency", "text": "latency not measured: none"}]}) == []


def test_stage_gate_status_follows_the_records_when_the_summary_is_a_phantom_entry() -> None:
    """5a32 stopped on 'stage 6 visited more than 4 times'; its old summary wrote the refused fifth entry as a failure and its
    review page listed stage 9's bitstream failure under timing-closure. The base build's gates show stage 6 passing."""
    d = REC / S5A32 / DESIGN[S5A32]
    assert D.records_verdict(d, "timing-closure") is True
    h, req = _draft(S5A32)
    assert h["state"]["gates"]["timing-closure"] == "pass" and "timing-closure" not in req
    assert "refused by the visit limit" in h["history"][0]["note"]
    # a stage whose gates the record shows failing is not flipped; c14's stage 2 is not a record-checkable stage
    h14, req14 = _draft(C14)
    assert h14["state"]["gates"]["rtl-design-creation"] == "fail" and "rtl-design-creation" in req14


def test_review_does_not_write_up_a_stop_before_the_gate_as_a_failure(monkeypatch) -> None:
    from agent.graph import run as gr
    from agent.tests.request_golden import T1, _Ok
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    try:
        cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter")
        rt = gr.new_runtime(cfg, lambda *a, **k: None, runner=_Ok())
        state = {"run_id": rt.run_id, "stage": 6, "stop": "stage 6 visited more than 4 times",
                 "fails": ["bitstream: did not run"], "history": [], "visits": {"6": 5}, "evidence": {}}
        out = gr.node_review(state)
        e = out["history"][-1]
        assert e["gated"] is False and e["passed"] is False
        page = Path(e["page"]).read_text()
        assert "bitstream: did not run" not in page and "not gated" in page
        assert gr.gates_last({"history": out["history"]}) == {}          # an entry that ran no gate is not a stage result
        assert gr.gates_last({"history": [{"stage": "timing-closure", "passed": True}, e]}) == {"timing-closure": True}
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_ila_gate_failure_names_the_build_and_the_unreadable_record() -> None:
    ok, why = ST._stage_pass({"pass": False, "stages": {}, "error": "JSONDecodeError: Expecting value"}, "bitstream",
                             label="debug build with the ILA")
    assert not ok and "debug build with the ILA" in why[0] and "unreadable" in why[0] and "did not run" in why[0]
    ok, why = ST._stage_pass(None, "bitstream")
    assert why == ["bitstream: did not run (no gates record)"]
    from agent.graph.stages import MACHINE, classify
    assert classify(MACHINE[9], ["bitstream (debug build with the ILA): did not run"]) is None    # still a retry, not timing


# --- finding 2: verification entries name the V-stage reached ----------------------------------------------------------

def test_verification_entries_name_the_stage_reached_and_what_did_not_run() -> None:
    h, _ = _draft(A8F2)
    e = next(x for x in h["evidence"] if x["activity"] == "simulation")
    assert e["result"] == "partial"                                   # V1 of V3 is never a bare "pass"
    assert "reached V1 of V3" in e["what"] and "V1 means every spec item is traced" in e["what"]
    assert "V2" in e["what"] and "seeds run none" in e["what"] and "constrained random test ran False" in e["what"]
    assert "V3" in e["what"] and "no board result" in e["what"]
    gaps = {g["about"]: g["text"] for g in h["gaps"]}
    assert "reached V1 of V3" in gaps[e["id"]]
    h14, _ = _draft(C14)
    e14 = next(x for x in h14["evidence"] if x["activity"] == "simulation")
    assert "reached V2 of V3" in e14["what"] and "cover properties pct 0.0" in e14["what"]


# --- finding 3: what the repository answers ----------------------------------------------------------------------------

def test_empty_design_files_and_shared_sources_are_marked() -> None:
    h, _ = _draft(C14)
    f = {x["path"].rsplit("/", 1)[-1]: x["what"] for x in h["files"]}
    assert "empty" in f["reset_sync.sv"] and "shell/rtl/reset_sync.sv" in f["reset_sync.sv"]
    assert "shell/rtl/reset_sync.sv" in f["build.yaml"] and "did not write" in f["build.yaml"]
    d = REC / C14 / DESIGN[C14]
    user = D.user_prompt(d, h, [])
    assert "SOURCES THE BUILD READS" in user and "shell/rtl/reset_sync.sv" in user and "SHARED SOURCES" in user
    assert "module reset_sync" in user                                # the shared file's body is shown to the Designer
    assert "not found" in D.DOC_SYSTEM and "do\n  not put in open_questions" in D.DOC_SYSTEM


def test_spec_rates_reach_the_parameter_notes() -> None:
    h, _ = _draft(A8F2)
    pwm = next(p for p in h["parameters"] if p["name"] == "PWM_PERIOD_CYCLES")
    assert "24.4 kHz" in pwm["_spec_timing"]
    merged = D.merge(h, {"parameters": [{"name": "PWM_PERIOD_CYCLES", "legal": "a positive count", "note": "PWM period."}]},
                     [g["about"] for g in h["gaps"]])
    p = next(p for p in merged["parameters"] if p["name"] == "PWM_PERIOD_CYCLES")
    assert "24.4 kHz" in p["note"] and "_spec_timing" not in p


# --- finding 4: facts the records hold ---------------------------------------------------------------------------------

def test_provenance_coverage_mutation_and_probes_come_from_the_records() -> None:
    h, _ = _draft(C14)
    ar = h["agent_run"]
    assert ar["model"] == "claude-sonnet-5-5" and ar["turns"] == 101 and ar["tokens"] == 2482927 and ar["wall_s"] == 3379.0
    assert ar["harness"] == "claude_code" and ar["plan_cost_estimate_usd"] == 2.9032 and "cost_usd" not in ar
    ms = {m["what"]: m for m in h["measurements"]}
    assert ms["line coverage"]["field"] == "stages.V3.checks.line_pct.value"
    assert {"simulation seeds run", "toggle coverage", "functional coverage bins hit", "cover properties hit"} <= set(ms)
    ev = next(x for x in h["evidence"] if x["activity"] == "faults")
    assert "17 sampled of 32 candidates" in ev["what"] and "17 killed" in ev["what"]
    h2, _ = _draft(A8F2)
    assert next(m for m in h2["measurements"] if m["category"] == "cost")["value" if False else "field"] == "cost_usd"
    assert not any(m["category"] == "verification" for m in h2["measurements"])      # nothing ran: nothing to quote
    probes = next(x for x in h2["files"] if x["path"].endswith("probes.yaml"))["what"]
    assert "counter (16 bits)" in probes and "pwm_phase (12 bits)" in probes and "depth 512" in probes


def test_build_time_and_memory_fill_only_for_a_build_on_the_pinned_release(run_copy) -> None:
    run, dst = run_copy
    d = dst / DESIGN[run]
    h, _ = _draft(run, d, dst)
    assert h["commands"][-1]["minutes"] is None and "peak memory" not in h["commands"][-1]["needs"]     # earlier release
    rj = json.loads((d / "build" / "base" / "run.json").read_text())
    rj["vivado_version"] = H.VIVADO
    (d / "build" / "base" / "run.json").write_text(json.dumps(rj))
    h, _ = _draft(run, d, dst)
    assert h["commands"][-1]["minutes"] == round(rj["wall_s"] / 60, 1)
    assert f"peak memory {rj['scope_anon_peak_mib']} MiB" in h["commands"][-1]["needs"]
    assert h["state"]["evidence_vivado"] in ("current", "earlier")        # the ILA record has no run.json


def test_agent_md_keeps_run_facts_and_is_smaller_for_the_same_content() -> None:
    h, _ = _draft(C14)
    h = copy.deepcopy(h)
    md = H.render_agent(h, REC / C14 / DESIGN[C14])
    assert "run: model claude-sonnet-5-5" in md and "101 turns" in md
    assert "stage constraints was not run" not in md or "(each of these)" in md
    assert re.search(r"\[constraints, synthesis.*\] stage \(each of these\) was not run", md)
    assert "paths under the design directory are relative to it" in md


# --- finding 5: builds from an earlier release publish no number -------------------------------------------------------

def test_earlier_release_builds_publish_no_number_and_make_remeasuring_the_first_step() -> None:
    h, req = _draft(A8F2)
    base = next(e for e in h["evidence"] if e["record"].endswith("base/gates.json"))
    assert base["result"] == "partial" and "withdrawn" in base["what"] and "reached bitstream" in base["what"]
    assert "timing was met" in base["what"]
    assert not re.findall(r"\d", base["what"].replace("2026.1", ""))      # no number from the earlier build
    assert not {m["category"] for m in h["measurements"]} & {"timing", "resources", "power"}
    gap = next(g for g in h["gaps"] if g["about"] == base["id"])["text"]
    assert "python -m agent resume" in gap and "earlier Vivado release" in gap
    for text in (base["what"], gap):
        assert not H.BANNED[0][0].search(text)
    h["next_steps"] = ["Fix the debounce width."]
    assert D.remeasure_first(h)
    h["next_steps"] = ["Run the Verifier's tests.", "Later, re-measure the build with python -m agent resume."]
    assert D.remeasure_first(h) == []                       # required, but not necessarily first


# --- finding 6: covers against functional coverage ---------------------------------------------------------------------

def test_cover_properties_at_zero_with_all_bins_hit_are_diagnosed() -> None:
    h, req = _draft(C14)
    gap = next(g for g in h["gaps"] if g["about"] == "cover_properties")["text"]
    assert "C_led_fall" in gap and "100.0 (50/50)" in gap and "disagree" in gap and "before proposing any new stimulus" in gap
    assert "binds clk to CLK100MHZ" in gap and "led to LED0" in gap and "not settled by the records" in gap
    assert "cover_properties" in req
    h2, _ = _draft(A8F2)
    assert not any(g["about"] == "cover_properties" for g in h2["gaps"])          # nothing ran: no diagnosis to make


# --- round two (planner, 2026-11-13) ----------------------------------------------------------------------------------

def test_approval_is_stated_as_automatic_and_prose_may_not_say_signed_off() -> None:
    h, req = _draft(C14)
    e1 = next(e for e in h["evidence"] if e["activity"] == "review")
    assert e1["result"] == "partial" and "approved automatically by a model, with no human review" in e1["what"]
    assert "E1" in req
    d = REC / C14 / DESIGN[C14]
    bad = copy.deepcopy(h)
    bad["summary"] = "The specification was signed off and the design is documented here."
    assert any("without saying it was automatic" in x for x in D.prose_claims(d, bad))
    bad["summary"] = "The specification was approved automatically by a model, with no human review."
    assert D.prose_claims(d, bad) == []


def test_oracle_records_that_disagree_are_a_gap() -> None:
    h, req = _draft(C14)
    g = next(g for g in h["gaps"] if g["about"] == "oracle_record")["text"]
    assert "BUILD_NOTE.md names the interview oracle" in g and "summary.json names" in g and "oracle_record" in req


def test_formal_assertions_and_register_map_come_from_the_records() -> None:
    h, _ = _draft(C14)
    gaps = {g["about"]: g["text"] for g in h["gaps"]}
    assert "SymbiYosys is not installed" in gaps["formal"] and "REQ-01" in gaps["formal"]
    assert "A_led_boolean (c14_int8_dot_requant_checker.sv:20)" in gaps["assertions"]
    assert {r["name"] for r in h["registers"]} >= {"A_LO", "GO", "STATUS"}
    md = H.render_readme(copy.deepcopy(h) | {"state": {**h["state"], "build_id": None, "kb_pin": None}}, REC / C14 / DESIGN[C14], {}, {})
    assert "| 0x07 | `GO` | WO |" in md


def test_a_gate_the_summary_calls_failed_is_reconciled_on_its_own_line() -> None:
    h, _ = _draft(S5A32)
    note = h["state"]["gate_notes"]["timing-closure"]
    assert note.startswith(D.RECON) and "visit limit" in note
    md = H.render_readme(copy.deepcopy(h) | {"state": {**h["state"], "build_id": None, "kb_pin": None}}, REC / S5A32 / DESIGN[S5A32], {}, {})
    line = next(l for l in md.splitlines() if l.startswith("Gates at handover"))
    assert "`timing-closure` pass (Build records:" in line
    d = REC / S5A32 / DESIGN[S5A32]
    bad = copy.deepcopy(h)
    bad["summary"] = "The ILA debug build did not complete in this run and the stage failed."
    assert any("none was attempted" in x for x in D.prose_claims(d, bad))
