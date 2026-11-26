"""Brief 227: the requirements readiness gate, the code half (flow/readiness.py). No model is called.

Covered: the six properties of a requirement (and the two this brief adds, necessary and achievable), SHALL/SHOULD/WILL, implementation-specific wording, the id
ledger (an id is never reused), layers 2 and 3 (completeness, the text regenerated from layer 2, the comparison with a third reader's layer 2, vacuous and
failed properties), the interface contract, consistency, the confirmation rules (a default the agent chose is derived and must be validated; a stale
confirmation; an all-OK batch), the show-back packet, reader agreement (a disagreement and a gap become questions), the frozen set and the return to stage 0, the
two scores and failure attribution, the early compliance assessment and its calibration, the VCRM, and the oracle note that never carries a vector.

The frequency meter of research/228 section 8(e) (reduced to a window of 8 cycles) is a fixture: with recorded model replies its rows go through the real formal
flow (skipped without ``sby``): reset, next-cycle, same-cycle and handshake rows are proved with a reachable trigger; the saturation row is **vacuous** (the 228
prediction); the cross-clock accuracy row is simulation-only."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

from flow import readiness as R

FIX = Path(__file__).parent / "fixtures" / "readiness" / "freqmeter"


def spec_of_fixture() -> dict:
    return yaml.safe_load((FIX / "spec.yaml").read_text())


def row(**kw) -> dict:
    base = {"id": "REQ-01", "text": "After reset, busy is low.", "proof": ["simulation"]}
    base.update(kw)
    return base


def codes(problems) -> list[str]:
    return sorted(p.code for p in problems)


# ---- the six properties -----------------------------------------------------------------------------------------------------------------
def test_a_clean_row_has_no_core_problem_at_standard(tmp_path):
    spec = {"requirements": [row()]}
    assert [p for p in R.six_properties(row(), spec) if p.blocks("standard")] == []


def test_vague_and_compound_rows_are_not_simple_and_clear_and_only_the_compound_one_is_repaired_without_the_user():
    vague = [p for p in R.six_properties(row(text="The design should be fast."), {}) if p.code == "RDY-CLEAR-01"]
    comp = [p for p in R.six_properties(row(text="Busy goes high and valid goes low after start."), {}) if p.code == "RDY-CLEAR-01"]
    assert vague and comp and not vague[0].repair and comp[0].repair


def test_no_verification_method_is_a_question_and_proof_maps_to_a_method():
    r = row(proof=None)
    assert "RDY-VER-01" in codes(R.six_properties(r, {}))
    assert R.method_of(row(proof=["formal"])) == "Analysis"
    assert R.method_of(row(proof=["hardware"])) == "Demonstration"
    assert R.method_of(row(method="inspection")) == "Inspection"
    assert R.method_of(row(proof=["simulation"])) == "Test"


def test_necessary_and_achievable_and_traceable_block_only_at_strict():
    spec = {"goals": [{"id": "G1", "text": "x"}], "requirements": []}
    r = row()
    std = codes([p for p in R.six_properties(r, spec, level="standard") if p.blocks("standard")])
    stl = codes([p for p in R.six_properties(r, spec, level="strict") if p.blocks("strict")])
    assert std == []
    assert {"RDY-NEC-01", "RDY-ACH-01", "RDY-TRACE-01", "RDY-MODAL-01", "RDY-VER-02"} <= set(stl)
    ok = row(modal="shall", trace_up="G1", source="the request", evidence="test_busy", compliance={"status": "compliant"})
    assert [p for p in R.six_properties(ok, spec, level="strict") if p.blocks("strict")] == []
    bad = row(modal="shall", trace_up="G9", source="x", evidence="e", compliance={"status": "compliant"})
    assert "RDY-NEC-02" in codes(R.six_properties(bad, spec, level="strict"))


def test_a_non_compliant_or_tbc_row_needs_a_named_risk():
    r = row(modal="shall", trace_up="G1", source="s", evidence="e", compliance={"status": "tbc", "why": "timing at 400 MHz is doubtful"})
    assert "RDY-ACH-02" in codes(R.six_properties(r, {"goals": [{"id": "G1"}]}, level="strict"))
    r["compliance"]["risk"] = {"owner": "agent", "mitigation": "prototype the path"}
    assert "RDY-ACH-02" not in codes(R.six_properties(r, {"goals": [{"id": "G1"}]}, level="strict"))
    assert R.risks_from_assessment({"requirements": [r]})[0]["mitigation"] == "prototype the path"


def test_shall_should_will():
    assert R.modal_of(row(text="Busy shall rise.")) == "shall"
    assert R.modal_of(row(text="Busy should rise.")) == "should"
    assert R.modal_of(row(text="The board will be powered from USB.", modal="will")) == "will"
    assert R.modal_of(row(text="Busy rises.")) is None
    assert R.is_verified_kind(row(text="Busy rises.")) and not R.is_verified_kind(row(modal="will")) and not R.is_verified_kind(row(modal="should"))


def test_an_implementation_named_in_a_requirement_is_a_question_unless_kept_as_a_constraint():
    spec = {"requirements": [row(id="REQ-09", text="Frames shall be stored using the VDMA and MIG.")]}
    assert codes(R.implementation_problems(spec)) == ["RDY-IMPL-01"]
    spec["requirements"][0]["design_constraint"] = True
    assert R.implementation_problems(spec) == []
    assert R.implementation_problems({"requirements": [row(text="Frames shall be stored in an external buffer at 60 frames per second.")]}) == []


# ---- the id ledger ------------------------------------------------------------------------------------------------------------------------
def test_an_id_is_never_reused_even_after_deletion(tmp_path):
    s1 = {"requirements": [row(id="REQ-01"), row(id="REQ-02", text="Valid is low after reset.")]}
    R.update_ledger(tmp_path, s1)
    s2 = {"requirements": [row(id="REQ-01")]}                              # REQ-02 deleted
    led = R.update_ledger(tmp_path, s2)
    assert led["ids"]["REQ-02"]["deleted"] is True
    s3 = {"requirements": [row(id="REQ-01"), row(id="REQ-02", text="Something else entirely happens.")]}
    assert R.reused_ids(R.read_ledger(tmp_path), s3, revised=["REQ-02"]) == ["REQ-02"]      # deleted: reused, whatever the new row claims
    # a changed wording of a live id that is not declared revised is a reuse as well; declared revised it is not
    s4 = {"requirements": [row(id="REQ-01", text="After reset, busy and valid are low.")]}
    assert R.reused_ids(R.read_ledger(tmp_path), s4) == ["REQ-01"]
    assert R.reused_ids(R.read_ledger(tmp_path), s4, revised=["REQ-01"]) == []
    assert "RDY-UNIQ-01" in codes(R.six_properties(s4["requirements"][0], s4, ledger=R.read_ledger(tmp_path)))


# ---- layer 2 ------------------------------------------------------------------------------------------------------------------------------
L2 = {"scope": "always", "condition": "start is high and busy is low", "component": "the frequency meter",
      "timing": {"kind": "within", "n": 2, "clock": "clk_ref", "from": "start"}, "response": "busy is high"}


def test_layer_2_needs_every_field_a_clock_of_the_design_and_a_kind():
    spec = spec_of_fixture()
    r = row(id="REQ-02", kind="timing", l2=copy.deepcopy(L2))
    assert [p.code for p in R.l2_problems(r, spec)] == []
    bad = copy.deepcopy(r)
    bad["l2"]["timing"] = {"kind": "within", "n": None, "clock": "slow_clk", "from": ""}
    assert {"RDY-L2-04", "RDY-L2-05", "RDY-L2-06"} == {p.code for p in R.l2_problems(bad, spec)}
    bad["l2"]["timing"] = {"n": 2}
    assert "RDY-L2-03" in codes(R.l2_problems(bad, spec))                    # within against after must be stated
    assert "RDY-L2-01" in codes(R.l2_problems(row(id="X-1"), spec))
    nocond = copy.deepcopy(r)
    nocond["l2"]["condition"] = ""
    assert "RDY-L2-02" in codes(R.l2_problems(nocond, spec))


def test_the_english_is_regenerated_from_layer_2_in_ears_form():
    t = R.ears_text(row(modal="shall", l2=copy.deepcopy(L2)))
    assert t == "WHEN start is high and busy is low, the frequency meter SHALL within 2 clk_ref cycles of start busy is high."
    after = copy.deepcopy(L2)
    after["timing"]["kind"] = "after"
    assert "exactly 2 clk_ref cycles after start" in R.ears_text(row(l2=after))
    st = copy.deepcopy(L2)
    st.update(scope="the window is open", timing={"kind": "always"}, condition="")
    assert R.ears_text(row(l2=st)).startswith("WHILE the window is open, the frequency meter SHALL busy is high at all times")
    un = copy.deepcopy(L2)
    un["condition"] = "not a valid start"
    assert " THEN " in R.ears_text(row(l2=un))


def test_a_third_readers_layer_2_that_differs_is_found_and_an_equal_one_is_not():
    other = copy.deepcopy(L2)
    other["response"] = "busy is high"
    other["condition"] = "start high while busy low"
    assert R.l2_diff(L2, other) == []
    other["timing"] = {"kind": "after", "n": 2, "clock": "clk_ref", "from": "start"}
    assert any(d.startswith("timing.kind") for d in R.l2_diff(L2, other))
    third = copy.deepcopy(L2)
    third["timing"]["n"] = 3
    assert any("timing.n" in d for d in R.l2_diff(L2, third))
    unrelated = copy.deepcopy(L2)
    unrelated["response"] = "the LED blinks"
    assert any(d.startswith("response") for d in R.l2_diff(L2, unrelated))


# ---- layer 3 -------------------------------------------------------------------------------------------------------------------------------
def test_layer_3_is_a_proved_property_a_named_check_or_a_stated_reason():
    spec = spec_of_fixture()
    r = row(id="REQ-02", kind="timing")
    assert codes(R.l3_problems(r, spec)) == ["RDY-L3-01"]
    assert R.l3_problems(row(id="REQ-02", kind="timing", l3={"check": "sva_REQ_02"}), spec) == []
    assert codes(R.l3_problems(row(id="REQ-02", kind="timing", l3={"sim_only": "x"}), spec)) == ["RDY-L3-03"]
    assert R.l3_problems(row(id="REQ-02", kind="timing", l3={"sim_only": "two unrelated clocks and no stated relation"}), spec) == []
    assert R.l3_problems(row(id="REQ-02", kind="budget"), spec) == []                         # a budget is not a temporal property
    assert R.l3_problems(row(id="REQ-02", kind="timing"), spec, {"requirements": {"REQ-02": {"status": "proved"}}}) == []
    # a vacuous or failed property is not layer 3: it is a question
    for st in ("vacuous", "failed"):
        assert codes(R.l3_problems(row(id="REQ-02", kind="timing", l3={"check": "x"}), spec, {"requirements": {"REQ-02": {"status": st, "why": "never reached"}}})) == ["RDY-L3-02"]


# ---- the interface contract ----------------------------------------------------------------------------------------------------------------
def test_the_fixture_interface_is_complete():
    assert [p.code for p in R.interface_problems(spec_of_fixture()) if p.blocks("strict")] == []


def test_missing_interface_items_are_questions_not_defaults():
    spec = spec_of_fixture()
    spec["ports"][5].pop("reset_value")                                     # busy
    spec["ports"].append({"name": "m_valid", "dir": "out", "width": 1, "clock": "clk_ref", "reset_value": 0})
    spec["ports"].append({"name": "m_ready", "dir": "in", "width": 1, "clock": "clk_ref"})
    spec["ports"].append({"name": "weird", "dir": "sideways", "width": "n", "clock": "clk_ref"})
    spec["ports"][3].pop("clock")                                           # start: two clocks, so a clock domain is needed
    spec["latencies"] = [x for x in spec["latencies"] if x["output"] != "valid"] + [{"output": "count", "from": "", "cycles": 0, "clock": "clk_ref"}]
    got = {p.code for p in R.interface_problems(spec)}
    assert {"RDY-IF-01", "RDY-IF-02", "RDY-IF-03", "RDY-IF-04", "RDY-IF-05", "RDY-IF-06", "RDY-IF-07"} <= got
    spec["handshakes"] = [{"name": "m", "rule": "valid held until ready"}]
    assert "RDY-IF-07" not in {p.code for p in R.interface_problems(spec)}


def test_an_arithmetic_row_without_a_number_format_is_a_question_at_strict():
    spec = {"requirements": [row(text="The output is the sum of the last four samples.")]}
    p = [x for x in R.interface_problems(spec) if x.code == "RDY-NUM-01"]
    assert p and p[0].level == "strict"
    spec["requirements"][0]["text"] = "The output is the unsigned sum of the last four samples, saturating at 65535."
    assert not [x for x in R.interface_problems(spec) if x.code == "RDY-NUM-01"]


def test_two_rows_that_give_one_quantity_two_values_conflict():
    spec = {"requirements": [row(id="REQ-01", text="The gate length is 1000 cycles."), row(id="REQ-02", text="The gate length equals 2000 cycles.")]}
    assert "RDY-CONS-02" in codes(R.consistency_problems(spec))
    spec = {"requirements": [row(id="A-1", text="Busy is low after reset."), row(id="A-2", text="Busy is low after reset.")]}
    assert codes(R.consistency_problems(spec)) == ["RDY-CONS-01"]
    assert R.consistency_problems({"requirements": [row(id="A-1", text="Busy is 1 after start."), row(id="A-2", text="Valid is 0 after start.")]}) == []


# ---- validation, derived rows, the all-OK risk ---------------------------------------------------------------------------------------------
def test_a_default_that_became_a_requirement_is_derived_and_must_be_validated():
    spec = {"requirements": [row(id="REQ-01", origin={"kind": "default", "detail": "d"}), row(id="REQ-02", text="Valid is low after reset.", origin="the request")]}
    std = R.confirmation_problems(spec, level="standard")
    assert [(p.code, p.blocks("standard"), p.blocks("strict")) for p in std] == [("RDY-DEF-01", False, True)]       # listed at standard, blocks at strict
    assert R.unconfirmed_defaults(spec) == ["REQ-01"]
    stl = {p.code for p in R.confirmation_problems(spec, level="strict")}
    assert stl == {"RDY-DEF-01", "RDY-VAL-01"}                                # REQ-02 is not derived but still not validated
    spec["requirements"][0]["validated_by_user"] = {"who": "owner", "when": "2026-11-26"}
    spec["requirements"][1]["validated_by_user"] = True
    assert R.confirmation_problems(spec, level="strict") == []


def test_a_confirmation_of_an_older_packet_is_stale():
    r = row(id="REQ-01", modal="shall", l2=copy.deepcopy(L2), worked=["2 cycles"], never="busy low after start")
    r["validated_by_user"] = {"who": "owner", "when": "2026-11-26", "shown": R.packet_hash(r)}
    assert R.confirmation_problems({"requirements": [r]}, level="strict") == []
    r["text"] = "After reset, busy is low and valid is low."
    assert [p.code for p in R.confirmation_problems({"requirements": [r]}, level="strict")] == ["RDY-VAL-02"]


def test_confirmations_from_the_file_count_and_a_long_all_ok_batch_is_flagged():
    spec = {"requirements": [row(id=f"R-{i}", text=f"Output {i} is low after reset.") for i in range(10)]}
    conf = {"confirmed": {f"R-{i}": {"who": "owner", "when": "2026-11-26T10:00"} for i in range(10)}}
    assert R.confirmation_problems(spec, level="strict", confirmations=conf) == []
    assert "10 requirements were confirmed in one batch" in R.all_ok_risk(conf)
    assert R.all_ok_risk({**conf, "edits_made": 1}) is None
    assert R.all_ok_risk({"confirmed": {"R-1": {"when": "a"}}}) is None


# ---- the show-back packet ---------------------------------------------------------------------------------------------------------------
def test_the_showback_packet_names_what_it_lacks():
    r = row(id="REQ-02", kind="timing", modal="shall", l2=copy.deepcopy(L2))
    pk = R.showback(r)
    assert pk["regenerated"].startswith("WHEN start is high") and set(pk["missing"]) == {"worked numbers", "a 'must never happen' example",
                                                                                          "a timing diagram from a cover trace (pending until the formal flow produces one)"}
    r.update(worked=["start at cycle 3: busy high at cycle 4"], never="busy low in the cycle after an accepted start")
    pk = R.showback(r, cover_trace={"signal": []})
    assert pk["missing"] == [] and pk["hash"] == R.packet_hash(r)
    assert codes(R.showback_problems(row(id="REQ-02", kind="timing", l2=copy.deepcopy(L2)))) == ["RDY-SHOW-01"]      # the diagram alone is advisory, not blocking
    assert R.showback_problems(row(id="REQ-02", kind="budget")) == []


# ---- reader agreement -------------------------------------------------------------------------------------------------------------------
PROBES = [
    {"id": "P1", "category": "reset", "scenario": "reset held for 1 cycle, then released", "question": "Is busy low in the cycle after release?", "answer_kind": "bool", "requirements": ["REQ-01"]},
    {"id": "P2", "category": "simultaneous", "scenario": "start and reg_rd in the same cycle", "question": "How many cycles after start is busy high?", "answer_kind": "int", "requirements": ["REQ-02"]},
    {"id": "P3", "category": "boundary", "scenario": "the count is exactly 2^32-1", "question": "What does ovf do?", "answer_kind": "choice", "choices": ["set", "hold", "wrap"], "requirements": ["REQ-07"]},
    {"id": "P4", "category": "back_pressure", "scenario": "reg_rd held for 3 cycles", "question": "How many cycles is reg_rvalid high?", "answer_kind": "int", "requirements": ["REQ-05"]},
]


def test_two_readers_that_agree_pass_and_unspecified_is_never_agreement():
    a = {"P1": "yes", "P2": "1", "P3": "set", "P4": "3"}
    ag = R.compare_readers(PROBES, {"A": a, "B": dict(a, P1="True", P4="three cycles: 3")})
    assert ag.ok and ag.rate == 1.0
    both_unspec = R.compare_readers(PROBES, {"A": dict(a, P3="unspecified"), "B": dict(a, P3="Not specified")})
    assert not both_unspec.ok and [g["probe"] for g in both_unspec.gaps] == ["P3"] and both_unspec.disagreements == []


def test_a_disagreement_becomes_a_question_and_the_rate_is_recorded():
    a = {"P1": "yes", "P2": "1", "P3": "set", "P4": "3"}
    b = {"P1": "yes", "P2": "2", "P3": "unspecified", "P4": "3"}
    ag = R.compare_readers(PROBES, {"A": a, "B": b})
    assert not ag.ok and [d["probe"] for d in ag.disagreements] == ["P2", "P3"] and ag.agreed == 2 and ag.rate == 0.5
    qs = R.questions_from_agreement(ag)
    assert [q.code for q in qs] == ["RDY-READ-01", "RDY-READ-01"] and "REQ-02" in qs[0].id and "disagree" in qs[0].question
    assert R.compare_readers(PROBES, {"A": a, "B": {"P1": "yes"}}).disagreements          # a probe a reader skipped counts as unspecified


def test_a_probe_set_must_reach_the_categories_that_apply():
    spec = spec_of_fixture()
    assert R.probe_problems(PROBES, spec) == []
    errs = R.probe_problems([p for p in PROBES if p["category"] != "reset"], spec)
    assert any("'reset'" in e for e in errs)
    errs = R.probe_problems([dict(PROBES[0], answer_kind="essay"), dict(PROBES[0], id="P1")], spec)
    assert any("answer_kind" in e for e in errs) and any("repeated" in e for e in errs)
    assert any("choices" in e for e in R.probe_problems([dict(PROBES[2], choices=["set"]), PROBES[0]], spec))


# ---- the frozen set and the return to stage 0 -----------------------------------------------------------------------------------------------
def test_freezing_records_the_set_and_a_later_change_returns_to_stage_0(tmp_path):
    spec = {"requirements": [row(id="REQ-01"), row(id="REQ-02", text="Valid is low after reset.")]}
    fr = R.freeze(tmp_path, spec, level="standard", rounds=2)
    assert fr["version"] == 1 and fr["ids"] == ["REQ-01", "REQ-02"] and R.changed_since_freeze(tmp_path, spec) == []
    spec2 = copy.deepcopy(spec)
    spec2["requirements"][1]["text"] = "Valid is low and busy is low after reset."
    spec2["requirements"].append(row(id="REQ-03", text="Ovf is low after reset."))
    assert R.changed_since_freeze(tmp_path, spec2) == ["REQ-02", "REQ-03"]
    ch = R.check_frozen_or_reopen(tmp_path, spec2, who="stage 2 repair")
    assert ch == ["REQ-02", "REQ-03"]
    st = R.read_frozen(tmp_path)
    assert st["status"] == "reopened" and st["frozen_at"] is None and st["reopened"][0]["who"] == "stage 2 repair" and st["reopened"][0]["ids"] == ["REQ-02", "REQ-03"]
    again = R.freeze(tmp_path, spec2, level="standard", rounds=1)           # frozen again: the return is kept in the record
    assert again["version"] == 1 + 1 and len(again["reopened"]) == 1
    assert R.check_frozen_or_reopen(tmp_path, spec2) == []


# ---- the whole mechanical gate -----------------------------------------------------------------------------------------------------------
def test_the_fixture_passes_the_mechanical_gate_at_standard_and_names_its_gaps_at_strict():
    spec = spec_of_fixture()
    probs = R.mechanical_problems(FIX, spec, level="standard")
    assert [p for p in probs if p.blocks("standard")] == [], [p.text for p in probs if p.blocks("standard")]
    strict = R.mechanical_problems(FIX, spec, level="strict")
    got = {p.code for p in R.blocking(strict, "strict")}
    assert {"RDY-L2-01", "RDY-L3-01", "RDY-SHOW-01", "RDY-ACH-01", "RDY-VER-02", "RDY-VAL-01"} <= got              # the three layers are not written yet
    assert "RDY-NEC-01" not in got and "RDY-MODAL-01" not in got                                         # trace_up and modal are there


def test_no_requirements_is_a_question(tmp_path):
    assert codes(R.mechanical_problems(tmp_path, {})) == ["RDY-SET-01"]


def test_a_test_that_traces_to_no_requirement_is_flagged_but_not_blocking(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("# req: REQ-01\nasync def test_reset(dut):\n    pass\n\nasync def test_mystery(dut):\n    pass\n")
    probs = R.upward_trace(tmp_path, {"requirements": [row(id="REQ-01")]})
    assert [p.text for p in probs] == ["test test_mystery in test_x.py traces to no requirement"] and not probs[0].blocking


# ---- the VCRM, the assessment and its calibration, the two scores ----------------------------------------------------------------------------
def test_vcrm_has_the_columns_and_will_rows_are_never_verified():
    spec = {"requirements": [row(id="REQ-01", modal="shall", evidence="test_reset", compliance="compliant", validated_by_user={"who": "owner", "when": "2026-11-26"}),
                             row(id="REQ-02", text="The board will be powered from USB.", modal="will"),
                             row(id="REQ-03", text="Busy should settle quickly in practice.", modal="should", derived=True)]}
    md = R.vcrm_markdown(spec, {"requirements": [{"id": "REQ-01", "result": "pass"}]}, independent={"REQ-01": "hidden bench (not the agent's)"})
    lines = md.splitlines()
    assert lines[0].startswith("| Id | Modal | Requirement | Method | Evidence | Validated by user | Verified | Early compliance | Independent check |")
    assert "| REQ-01 | SHALL |" in md and "yes (owner, 2026-11-26) | pass | compliant | hidden bench (not the agent's)" in md
    assert "never (WILL)" in md and "no (derived)" in md and "(SHOULD: not mandatory)" in md


def test_the_early_assessment_is_calibrated_against_the_verified_outcome():
    cal = R.calibration({"A": "compliant", "B": "compliant", "C": "non_compliant", "D": "non_compliant", "E": "tbc", "F": "compliant"},
                        {"A": "pass", "B": "fail", "C": "fail", "D": "pass", "E": "pass", "F": "pending"})
    assert (cal["compared"], cal["agree"], cal["missed_risk"], cal["false_alarm"], cal["unsharp"]) == (5, 2, 1, 1, 1)


def test_a_failure_is_attributed_to_one_stage_and_benchmark_limited_is_counted_apart():
    assert R.attribute_failure("requirement_missing") == "stage0" and R.attribute_failure("requirement_wrong") == "stage0"
    assert all(R.attribute_failure(c) == "stage2" for c in ("interface", "timing", "reset", "handshake", "functional", "testbench_wrong", "tool", "cut_off_reply", "budget"))
    assert R.attribute_failure("benchmark_limited") == "benchmark_limited"
    with pytest.raises(ValueError):
        R.attribute_failure("bad luck")


def test_two_scores_are_reported_separately_and_a_stage_0_stop_has_no_build_score():
    state = {"rounds": [{"questions": [1, 2], "agreement": {"rate": 0.5}}, {"questions": [3], "agreement": {"rate": 1.0}}], "frozen": {"x": 1}, "model_calls": 12}
    s = R.two_scores(state, {"own_pass": True, "independent_pass": False, "failure_class": "requirement_wrong"})
    assert s["requirements_quality"]["rounds"] == 2 and s["requirements_quality"]["questions"] == 3 and s["requirements_quality"]["agreement_per_round"] == [0.5, 1.0]
    assert s["build_and_verify"]["agree"] is False and s["build_and_verify"]["stage"] == "stage0"
    assert R.two_scores({"rounds": [], "stop": "limit"}, None)["build_and_verify"] is None


def test_fact_coverage_separates_a_missed_fact_from_a_benchmark_limited_one():
    facts = [{"id": "F1", "tokens": ["10", "short"], "in_source": True}, {"id": "F2", "tokens": ["lut"], "in_source": True}, {"id": "F3", "tokens": ["x"], "in_source": False}]
    cov = R.fact_coverage(facts, [{"text": "The SHORT timer is 10 cycles."}])
    assert cov == {"covered": ["F1"], "missed": ["F2"], "benchmark_limited": ["F3"], "coverage": 0.5}


# ---- the oracle note never carries a vector ---------------------------------------------------------------------------------------------------
def test_an_oracle_note_with_a_test_vector_is_refused():
    ok = ["The count output is 32 bits, valid one cycle after the window closes.", "Reset is active low and synchronous.", "The default window is 100000 reference cycles."]
    assert R.build_note(ok).count("\n") == 3
    for bad in ("expected output = 0x1F4A for input 5", "test vector: din = 5 -> dout = 25", "assert result == 25000", "golden value: 32'hDEADBEEF"):
        with pytest.raises(ValueError):
            R.build_note([*ok, bad])
    assert R.note_vectors("\n".join(ok)) == []


# ---- the frequency meter through the formal flow, with recorded replies ---------------------------------------------------------------------
def _have_formal() -> bool:
    from flow import sva_req as S
    env = S.formal_env()
    return env is not None and shutil.which("z3", path=env.get("PATH")) is not None


@pytest.mark.skipif(not _have_formal(), reason="needs sby and z3")
def test_the_frequency_meter_example_goes_through_the_formal_flow(tmp_path):
    from flow import sva_req as S
    d = tmp_path / "fm"
    shutil.copytree(FIX, d)
    rec = json.loads((FIX / "replies.json").read_text())
    cur = {}

    def gen(system, user):
        import re
        rid = re.match(r"Requirement (\S+):", user).group(1)
        cur["id"] = rid
        return rec["replies"][rid]["generator"]

    def back(system, user):
        return rec["replies"][cur["id"]]["back"]
    out = S.process(d, gen, back)
    got = {k: v["status"] for k, v in out["requirements"].items()}
    assert got == rec["statuses"]
    assert got["REQ-01"] == got["REQ-02"] == got["REQ-04"] == got["REQ-05"] == "proved"
    assert got["REQ-07"] == "vacuous"                       # the saturation row is the vacuity trap of research 228: a proof of a trigger that never happens
    assert got["REQ-08"] == "unusable"                      # the cross-clock accuracy row cannot be stated on the ports
    # the vacuous and the failed rows are questions to the user, not layer 3
    spec = yaml.safe_load((d / "spec.yaml").read_text())
    r7 = next(r for r in spec["requirements"] if r["id"] == "REQ-07")
    assert "RDY-L3-02" in codes(R.l3_problems(r7, spec, out))
    r2 = next(r for r in spec["requirements"] if r["id"] == "REQ-02")
    assert R.l3_problems(r2, spec, out) == []


def test_the_requirements_report_gets_a_vcrm_section_only_when_a_row_carries_brief_227_fields(tmp_path):
    from flow import requirements_report as RR
    spec = {"requirements": [row(id="REQ-01", modal="shall", method="Test", compliance="compliant")], "name": "x"}
    d = tmp_path / "d"
    d.mkdir()
    rows = [{"id": "REQ-01", "text": "t", "origin": {"kind": "spec", "detail": "d", "unconfirmed": False}, "result": "pass", "reason": "", "rests_on_unconfirmed": False, "high_risk_default": False,
             "methods": [{"method": "simulation", "status": "pass", "evidence": [{"name": "test_x", "link": "", "result": "pass"}]}, {"method": "formal", "status": "pass", "evidence": [{"name": "sva_REQ_01", "link": "", "result": "pass"}]}]}]
    assert R.independence_of(rows[0]) == "own testbench: NOT independent; property written without the RTL, read back by a different model"
    t = {"requirements": [{"id": "REQ-01", "text": "Busy is low", "status": "pass", "methods": [{"method": "simulation", "status": "pass", "verifications": []}]}], "evidence_sources": {}, "pass": True}
    rep = RR.build_report(d, t, spec, "")
    assert "| REQ-01 | SHALL | After reset, busy is low. | Test |" in rep["vcrm"] and "| compliant |" in rep["vcrm"]
    assert "## Verification cross-reference matrix" in RR.to_markdown(rep)
    plain = RR.build_report(d, t, {"requirements": [row(id="REQ-01")], "name": "x"}, "")
    assert plain["vcrm"] is None and "cross-reference matrix" not in RR.to_markdown(plain)
