"""Brief 218, part 2: an assertion written from each requirement (flow/sva_req.py).

Pure cases (no tool): which requirements are candidates, what a generator reply must look like, the code comparison of a back-translation with the
requirement (a changed latency, a dropped negation, a signal the requirement never names, a sentence about something else: each discarded with its
reason), the verdict rule for formal results, the timing diagram from a cover trace and the pipeline with scripted model replies.

Formal cases (need ``sby`` and ``z3``; skipped without) on ``fixtures/sva_req/pulse_ext``: a correct next-cycle property and a reset property are
**proved** with a reachable trigger; a wrong latency **fails** with a counterexample; a property whose trigger never happens is **vacuous** and is not
evidence; the proved ones are installed as ``verif/formal/sva_<id>.sby`` tagged with their requirement, and the traceability matrix links them."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from flow import requirements_report as rr
from flow import sva_req as S
from flow import traceability as tr

FIX = Path(__file__).parent / "fixtures" / "sva_req" / "pulse_ext"
SPEC = yaml.safe_load((FIX / "spec.yaml").read_text())


def req(rid: str) -> dict:
    return next(r for r in SPEC["requirements"] if r["id"] == rid)


def gen(kind="next", ante="start && !busy", cons="busy") -> dict:
    g, why = S.parse_generation(json.dumps({"kind": kind, "ante": ante, "cons": cons, "why": "w"}), SPEC)
    assert g is not None, why
    return g


# ---- which rows -------------------------------------------------------------------------------------------------------------------------
def test_candidates_and_skipped_rows():
    cands, skipped = S.select(SPEC)
    assert [r["id"] for r in cands] == ["REQ-01", "REQ-02", "REQ-03", "REQ-04", "REQ-07"]
    why = {s["id"]: s["reason"] for s in skipped}
    assert "analysis" in why["REQ-05"] and "analysis" in why["REQ-06"]


def test_a_row_naming_two_clocks_without_a_stated_relation_is_simulation_only():
    spec = {**SPEC, "clocks": [{"name": "clk_a", "port": "clk_a"}, {"name": "clk_b", "port": "clk_b"}],
            "requirements": [{"id": "R1", "text": "When clk_a sees start, clk_b output is high within 3 cycles", "proof": ["simulation"]}]}
    assert S.select(spec)[0] == [] and "no clock relation" in S.select(spec)[1][0]["reason"]
    spec["assumptions"] = ["clock relation: clk_b is an integer multiple of clk_a, from the same source"]
    assert [r["id"] for r in S.select(spec)[0]] == ["R1"]


def test_ids_narrow_the_selection():
    assert [r["id"] for r in S.select(SPEC, ["REQ-02"])[0]] == ["REQ-02"]


# ---- what a generator reply must be -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("reply,bad", [
    ("no json at all", "no JSON"),
    ('{"kind": "sometimes", "ante": "1", "cons": "busy"}', "not one of"),
    ('{"kind": "same", "ante": "start", "cons": "ready"}', "not a port of the module: ready"),
    ('{"kind": "same", "ante": "start |-> busy", "cons": "busy"}', "forbidden construct"),
    ('{"kind": "same", "ante": "start", "cons": "busy; foo"}', "forbidden construct"),
    ('{"kind": "same", "ante": "$past(start, 40)", "cons": "busy"}', "$past depth 40"),
    ('{"kind": "same", "ante": "(start", "cons": "busy"}', "unbalanced"),
    ('{"kind": "same", "ante": "start", "cons": ""}', "empty"),
    ('{"kind": "none", "why": "needs an internal signal"}', "cannot be stated on the ports"),
])
def test_an_unusable_reply_is_refused_with_its_reason(reply, bad):
    g, why = S.parse_generation(reply, SPEC)
    assert g is None and bad in why


def test_a_good_reply_is_parsed_with_its_signals_and_history_depth():
    g, why = S.parse_generation('Here it is: {"kind": "same", "ante": "$past(start && !busy, 5)", "cons": "done", "why": "x"}', SPEC)
    assert why == "" and g["signals"] == ["busy", "done", "start"] and g["past"] == 5 and g["kind"] == "same"
    g, _ = S.parse_generation('{"kind": "reset", "ante": "start", "cons": "!busy && 1\'b1"}', SPEC)
    assert g["ante"] == "1" and "rst" not in g["signals"]                      # a reset property ignores its antecedent


# ---- the code comparison ----------------------------------------------------------------------------------------------------------------
def test_a_faithful_back_translation_matches():
    c = S.compare(req("REQ-01"), gen(), "Whenever start was high and busy was low in the previous cycle, busy is high now.", SPEC)
    assert c["match"] and c["reasons"] == []


def test_a_changed_latency_is_a_mismatch():
    g = gen("same", "$past(start && !busy, 4)", "done")
    c = S.compare({"id": "R", "text": "Done is high exactly 5 cycles after an accepted start"}, g,
                  "Whenever start was high and busy was low 4 cycles earlier, done is high now.", SPEC)
    assert not c["match"] and any("the property uses 4, which the requirement does not give" in r for r in c["reasons"])


def test_a_dropped_negation_is_a_mismatch():
    g = gen("same", "busy", "!done")
    c = S.compare({"id": "R", "text": "Done is never high while busy is high"}, g, "Whenever busy is high, done is high.", SPEC)
    assert not c["match"] and any(r.startswith("negation") for r in c["reasons"])


def test_a_property_over_signals_the_requirement_never_names_is_a_mismatch():
    c = S.compare({"id": "R", "text": "After reset the design is idle"}, gen("same", "start", "start"), "Whenever start is high, start is high.", SPEC)
    assert not c["match"] and any(r.startswith("signals") for r in c["reasons"])


def test_a_sentence_about_something_else_is_a_mismatch():
    c = S.compare(req("REQ-01"), gen(), "The module counts down from three and then raises a flag for exactly 7 milliseconds.", SPEC)
    assert not c["match"] and any(r.startswith("words") for r in c["reasons"]) and any("states 7" in r for r in c["reasons"])


def test_an_l2_signal_the_property_leaves_out_is_a_mismatch():
    r = {**req("REQ-01"), "l2": {"trigger": "start", "response": "done"}}
    c = S.compare(r, gen(), "Whenever start was high and busy was low in the previous cycle, busy is high now.", SPEC)
    assert not c["match"] and any("L2 field response names done" in x for x in c["reasons"])


def test_a_property_that_says_part_of_a_long_requirement_is_marked_partial():
    long = {"id": "R", "text": "When start is high while busy is low busy rises, done pulses afterwards, and the extension lasts four cycles in total"}
    c = S.compare(long, gen(), "Whenever start was high and busy was low in the previous cycle, busy is high now.", SPEC)
    assert c["match"] and c["partial"]


# ---- the verdict rule -------------------------------------------------------------------------------------------------------------------
def st(bmc="PASS", prove="PASS", cover="PASS") -> dict:
    return {"bmc": {"status": bmc}, "prove": {"status": prove}, "cover": {"status": cover}}


def test_the_verdict_rule():
    assert S.judge(st())["status"] == "proved" and S.judge(st())["evidence"]
    assert S.judge(st(prove="UNKNOWN"))["status"] == "bounded" and S.judge(st(prove="UNKNOWN"))["evidence"]
    assert S.judge(st(cover="FAIL"))["status"] == "vacuous" and not S.judge(st(cover="FAIL"))["evidence"]       # a proof with no reachable trigger
    assert S.judge(st(prove="PASS", cover="FAIL"))["status"] == "vacuous"
    assert S.judge(st(bmc="FAIL"))["status"] == "failed" and S.judge(st(prove="FAIL"))["status"] == "failed"
    assert S.judge(st(bmc="FAIL", cover="FAIL"))["status"] == "failed"                                           # a counterexample outranks vacuity
    e = S.judge({"bmc": {"status": "ERROR", "error": "shell_core.sv:64: ERROR: syntax error"}, "prove": {"status": "ERROR"}, "cover": {"status": "ERROR"}})
    assert e["status"] == "error" and "syntax error" in e["why"] and not e["evidence"]


# ---- the cover trace as a diagram -------------------------------------------------------------------------------------------------------
VCD = """$timescale 1ns $end
$scope module sva_R $end
$var wire 1 ! clk $end
$var wire 1 " busy $end
$var wire 4 # cnt [3:0] $end
$scope module dut $end
$var wire 1 $ inner $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0!
0"
b0000 #
#5
1!
#10
0!
1"
b0011 #
#15
1!
#20
0!
#25
1!
"""


def test_a_cover_trace_becomes_a_wavedrom_document():
    wd = S.wavedrom(VCD, ["busy", "cnt", "inner"], "R: the trigger is reachable")
    sig = {s["name"]: s for s in wd["signal"]}
    assert sig["clk"]["wave"] == "p.." and "inner" not in sig                         # inner scope signals are not shown
    assert sig["busy"]["wave"] == "01."                                              # sampled at each rising clock edge
    assert sig["cnt"]["data"] == ["0x0", "0x3"] and wd["head"]["text"].startswith("R:") and "3 cycles" in wd["foot"]["text"]
    json.dumps(wd)


# ---- the pipeline with scripted replies -------------------------------------------------------------------------------------------------
GOOD = {"REQ-01": ('{"kind": "next", "ante": "start && !busy", "cons": "busy"}', "Whenever start was high and busy was low in the previous cycle, busy is high now."),
        "REQ-02": ("not json", ""),
        "REQ-03": ('{"kind": "same", "ante": "$past(start && !busy, 4)", "cons": "done"}', "Whenever start was high and busy was low 4 cycles earlier, done is high now."),
        "REQ-04": ('{"kind": "same", "ante": "busy", "cons": "done"}', "Whenever busy is high, done is high."),
        "REQ-07": ('{"kind": "same", "ante": "$past(start && !busy, 4)", "cons": "done"}', "Whenever start was high and busy was low 4 cycles earlier, done is high now.")}


def scripted(replies: dict):
    cur = {}

    def g(system, user):
        rid = user.split(":")[0].split()[-1]
        cur["id"] = rid
        return replies[rid][0]

    def b(system, user):
        return replies[cur["id"]][1]
    return g, b


def copy_fix(tmp: Path) -> Path:
    d = tmp / "pulse_ext"
    shutil.copytree(FIX, d)
    return d


def test_the_pipeline_discards_a_mismatch_and_an_unusable_reply_with_their_reasons(tmp_path):
    d = copy_fix(tmp_path)
    g, b = scripted(GOOD)
    rec = S.process(d, g, b, formal=False)
    r = rec["requirements"]
    assert r["REQ-02"]["status"] == "unusable" and "no JSON" in r["REQ-02"]["why"]
    assert r["REQ-07"]["status"] == "mismatch" and "the property uses 4" in r["REQ-07"]["why"]      # REQ-07 says 5 cycles; the generator wrote 4
    assert r["REQ-01"]["status"] == "not_run" and r["REQ-01"]["comparison"]["match"] and r["REQ-03"]["status"] == "not_run"
    assert {x["id"] for x in rec["skipped"]} == {"REQ-05", "REQ-06"}
    assert S.read_evidence(d)["counts"] == rec["counts"]


def test_a_requirement_unchanged_is_not_asked_again(tmp_path):
    d = copy_fix(tmp_path)
    calls = []
    g, b = scripted(GOOD)
    S.process(d, lambda s, u: (calls.append(u), g(s, u))[1], b, formal=False)
    n = len(calls)
    S.process(d, lambda s, u: (calls.append(u), g(s, u))[1], b, formal=False)
    assert len(calls) - n == 3        # REQ-01, 03 and 04 reached not_run (no formal result to keep) and are asked again; the unusable REQ-02 and the mismatch REQ-07 are kept


# ---- formal: needs sby ------------------------------------------------------------------------------------------------------------------
def _have_formal() -> bool:
    env = S.formal_env()
    return env is not None and shutil.which("z3", path=env.get("PATH")) is not None


needs_sby = pytest.mark.skipif(not _have_formal(), reason="needs sby and z3")

FORMAL = {k: v for k, v in GOOD.items()}
FORMAL["REQ-02"] = ('{"kind": "reset", "ante": "1", "cons": "!busy && !done"}', "In the cycle right after reset, busy and done are both low.")
FORMAL["REQ-03"] = ('{"kind": "same", "ante": "$past(start && !busy, 4)", "cons": "done"}', "Whenever start was high and busy was low 4 cycles earlier, done is high now.")
FORMAL["REQ-07"] = ('{"kind": "same", "ante": "$past(start && !busy, 5)", "cons": "done"}', "Whenever start was high and busy was low 5 cycles earlier, done is high now.")
FORMAL["REQ-04"] = ('{"kind": "same", "ante": "busy && done", "cons": "done"}', "Whenever busy and done are both high, done is high.")


@needs_sby
def test_proved_failed_and_vacuous_properties_on_a_real_design(tmp_path):
    d = copy_fix(tmp_path)
    spec = yaml.safe_load((d / "spec.yaml").read_text())
    for r in spec["requirements"]:                                  # REQ-04 reworded so a faithful back-translation matches
        if r["id"] == "REQ-04":
            r["text"] = "Done is high whenever busy and done are both high"
    (d / "spec.yaml").write_text(yaml.safe_dump(spec))
    g, b = scripted(FORMAL)
    rec = S.process(d, g, b)
    r = rec["requirements"]
    assert r["REQ-01"]["status"] == "proved" and r["REQ-02"]["status"] == "proved" and r["REQ-07"]["status"] == "proved"
    assert r["REQ-03"]["status"] == "failed" and not r["REQ-03"]["evidence"]                  # done comes 5 cycles after start: a counterexample
    assert r["REQ-04"]["status"] == "vacuous" and not r["REQ-04"]["evidence"] and "never reached" in r["REQ-04"]["why"]
    assert (d / "verif" / "formal" / "sva_REQ_01.sby").is_file() and not (d / "verif" / "formal" / "sva_REQ_03.sby").exists()
    assert not (d / "verif" / "formal" / "sva_REQ_04.sby").exists()                            # a vacuous proof is never installed
    wd = json.loads((d / r["REQ-01"]["cover_trace"]).read_text())
    assert [s["name"] for s in wd["signal"]][:2] == ["clk", "rst"] and "trigger" in wd["foot"]["text"]
    # a proved property is linked to its requirement: the traceability matrix reads the installed job as formal evidence on REQ-01
    known = {x["id"] for x in spec["requirements"]}
    arts = {a["name"]: a for a in tr.formal_artefacts(d / "verif" / "formal", known)}
    assert arts["sva_REQ_01"]["cites"] == ["REQ-01"] and arts["sva_REQ_02"]["cites"] == ["REQ-02"] and "sva_REQ_03" not in arts
    from flow import verif_gates as vg
    fr = vg.read_formal(d / "build" / "verif" / "formal")
    assert tr.formal_result("sva_REQ_01", fr, tr.sby_tasks(d / "verif" / "formal" / "sva_REQ_01.sby"))["result"] == "pass"
    # and the requirements report shows it
    sv = rr._sva_rows(d)
    assert sv["REQ-01"]["evidence"] and sv["REQ-01"]["job"] == "verif/formal/sva_REQ_01.sby" and not sv["REQ-04"]["evidence"] and sv["REQ-05"]["status"] == "skipped"
    summ = rr._sva_summary([{"id": k, "assertion": v} for k, v in sv.items()], sv)
    assert summ["with_evidence"] == 3 and summ["ids_with_evidence"] == ["REQ-01", "REQ-02", "REQ-07"]


@needs_sby
def test_a_changed_design_withdraws_an_installed_proof(tmp_path):
    d = copy_fix(tmp_path)
    g, b = scripted({"REQ-01": GOOD["REQ-01"]})
    assert S.process(d, g, b, ids=["REQ-01"])["requirements"]["REQ-01"]["status"] == "proved"
    assert (d / "verif" / "formal" / "sva_REQ_01.sby").is_file()
    rtl = d / "rtl" / "pulse_ext.sv"
    rtl.write_text(rtl.read_text().replace("busy <= 1'b1;", "busy <= 1'b0;"))                 # a bug: start no longer raises busy
    rec = S.process(d, g, b, ids=["REQ-01"])
    assert rec["requirements"]["REQ-01"]["status"] == "failed"
    assert not (d / "verif" / "formal" / "sva_REQ_01.sby").exists()                            # the earlier proof is not kept on trust


# ---- the module the properties are about ------------------------------------------------------------------------------------------------
CORE = Path(__file__).parent / "fixtures" / "sva_req" / "reg_core"


def test_a_register_core_behind_a_primitive_is_the_module_of_the_properties():
    spec = yaml.safe_load((CORE / "spec.yaml").read_text())
    es, how = S.effective_spec(CORE, spec)
    assert es["top"] == "reg_core" and "has primitives" in how
    ports = {p["name"]: (p["dir"], p["width"]) for p in es["ports"]}
    assert ports == {"clk": ("in", 1), "rst": ("in", 1), "h_we": ("in", 1), "h_addr": ("in", 12), "h_wdata": ("in", 32), "h_rdata": ("out", 32)}
    assert [c["port"] for c in es["clocks"]] == ["clk"] and S.reset_of(es) == ("rst", False)
    assert next(p for p in es["ports"] if p["name"] == "h_we")["note"] == "register port write pulse"      # the spec's description follows the port
    assert S.undefined_cells(sorted((CORE / "rtl").glob("*.sv"))) == {"reg_core": set(), "top": {"MMCME4_BASE"}}


def test_the_spec_top_is_kept_when_it_can_be_elaborated():
    es, how = S.effective_spec(FIX, SPEC)
    assert es["top"] == "pulse_ext" and "has primitives" not in how


@needs_sby
def test_a_property_of_a_register_core_is_proved_where_the_top_cannot_be_read(tmp_path):
    d = tmp_path / "reg_core"
    shutil.copytree(CORE, d)
    g, b = scripted({"REQ-01": ('{"kind": "next", "ante": "h_we && h_addr == 12\'d8", "cons": "h_rdata == $past(h_wdata)", "why": "w"}',
                                "Whenever h_we was high with h_addr equal to 8 in the previous cycle, h_rdata equals the h_wdata of that cycle.")})
    rec = S.process(d, g, b)
    assert rec["module"] == "reg_core" and rec["requirements"]["REQ-01"]["status"] == "proved", rec["requirements"]["REQ-01"]
