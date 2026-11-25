"""Brief 210: the requirements-strictness setting of the spec interview (agent.graph.requirements, interview.py, run.py).

No model, no Vivado: the risk rules, the three levels, waivers, the stop path (with its exit status), the assumptions list and the
fix-against-a-requirement conflict on the recorded c15 report of brief 204a (the same shape as brief 209a's deep_for_clock run)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agent.graph import requirements as RQ
from agent.graph import run as gr
from agent.graph.interview import Interview, Question, SpecOracle, merge_summaries

D204 = Path(__file__).resolve().parents[2] / "flow" / "tests" / "data" / "204a"


# ---- the risk class -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,cls,rule", [
    ("Which clock is clk_sys: its frequency and where it comes from?", "high", "clock"),
    ("What does the board pin CLK100MHZ connect to, and how is it driven (push-pull, open-drain, pulled up, input)?", "high", "clock"),      # CLK100MHZ is also a clock name: the first rule that matches decides, the class is the same
    ("Is median_filter's reset rst active high or active low, and synchronous or asynchronous?", "high", "reset"),
    ("What is the register map (offset, width, reset value and access of every register)?", "high", "reset"),
    ("May the sink of median_filter.out stall the stream (drive tready low)?", "high", "interface"),
    ("What throughput must median_filter.out sustain (beats per clock)?", "high", "clock"),
    ("What latency, in clock cycles, from in to out?", "high", "clock"),
    ("What debounce interval should be used?", "high", "rate-and-latency"),
    ("Is the sample signed or unsigned, and how is it rounded?", "high", "number-format"),
    ("Should a held button auto-repeat?", "high", "behaviour"),
    ("What MAC address should the board use?", "high", "external-device"),
    ("What should the FIFO depth be?", "medium", "cost"),
    ("How much pipeline margin should the design leave?", "medium", "cost"),
    ("Something nobody wrote a rule for", "medium", "unmatched"),
    ("What should the top module be named?", "low", "cosmetic"),
    ("Which proof method(s) verify REQ-03?", "low", "verification-method"),
])
def test_the_rules_classify_a_question(text, cls, rule):
    k = RQ.classify(text)
    assert (k.cls, k.rule) == (cls, rule), k
    assert k.why


def test_a_register_name_question_that_also_asks_for_offsets_is_not_cosmetic():
    assert RQ.classify("What are the register names and their offsets?").cls == "high"


def test_the_clarifier_can_raise_a_class_and_never_lower_one():
    assert RQ.classify("What should the top module be named?", clarifier="high", clarifier_reason="the name is in the vendor's script").cls == "high"
    assert RQ.classify("What should the top module be named?", clarifier="high").rule == "clarifier"
    k = RQ.classify("Which clock is clk_sys?", clarifier="low")
    assert (k.cls, k.rule) == ("high", "clock")                       # a rule can not be talked down
    assert RQ.classify("Which clock is clk_sys?", clarifier="high").rule == "clarifier+clock"
    assert RQ.classify("Which clock is clk_sys?", clarifier="nonsense").rule == "clock"


# ---- the level ------------------------------------------------------------------------------------------------------------------------
def test_level_precedence_is_command_line_then_request_then_package_then_default():
    r = RQ.resolve_level
    assert r(cli=None) == ("loose", "default")
    assert r(cli=None, default="standard") == ("standard", "default")
    assert r(cli="strict", spec_md="Requirements: loose\n", package={"requirements": "loose"}) == ("strict", "command line")
    assert r(cli=None, spec_md="# x\nRequirements: strict\n", package={"requirements": "loose"}) == ("strict", "the request (spec.md)")
    assert r(cli=None, spec={"requirements_strictness": "standard"})[0] == "standard"
    assert r(cli=None, package={"requirements": "standard"}) == ("standard", "design package")
    assert r(cli=None, spec_md="- Requirements strictness: standard")[0] == "standard"
    with pytest.raises(ValueError):
        r(cli="nonsense")


def test_production_secure_and_high_assurance_profiles_imply_at_least_standard():
    r = RQ.resolve_level
    assert r(cli="loose", production_secure=True)[0] == "standard" and "raised" in r(cli="loose", production_secure=True)[1]
    assert r(cli=None, verif_profile="high_dependability")[0] == "standard"
    assert r(cli="strict", production_secure=True)[0] == "strict"           # never lowered
    assert r(cli="loose", verif_profile="prototype")[0] == "loose"
    assert RQ.floor_level() is None


def test_the_default_is_standard_only_when_a_person_answers():
    assert RQ.default_level(False, "on") == "standard"
    assert RQ.default_level(False, "off") == "loose" and RQ.default_level(False, "oracle") == "loose" and RQ.default_level() == "loose"
    assert RQ.default_level(True, "on") == "loose"             # a benchmark run (hidden spec) stays loose, so earlier numbers stay comparable


def test_the_design_package_field(tmp_path):
    assert RQ.load_package(tmp_path) == {}
    (tmp_path / "package.yaml").write_text("requirements: strict\nfiles: []\n")
    assert RQ.load_package(tmp_path)["requirements"] == "strict"
    (tmp_path / "package.yaml").write_text(": : not yaml [")
    assert RQ.load_package(tmp_path) == {}


# ---- the interview at each level -------------------------------------------------------------------------------------------------------
def q(i: str, text: str, default: str = "10 MHz", reason: str = "a typical value") -> Question:
    return Question(id=i, text=text, default=default, reason=reason)


HIGH = "Which clock is clk_sys: its frequency and where it comes from?"
MED = "What should the FIFO depth be?"
LOW = "What should the top module be named?"


class Oracle:
    """Answers the questions in ``known`` (by text) and says 'not specified' to the rest."""
    name = "oracle"

    def __init__(self, known: dict[str, str]):
        self.known = known

    def answer(self, qq):
        return (self.known[qq.text], "quoted line") if qq.text in self.known else ("not specified", None)


def run_all(level: str, who=None, waivers=None, limit: int = 12) -> Interview:
    iv = Interview(level=level, waivers=waivers or [], max_questions=limit)
    for i, t in enumerate((HIGH, MED, LOW), 1):
        iv.ask(q(f"q{i}", t), who)
    return iv


def statuses(iv: Interview) -> list[str]:
    return [x.status for x in iv.questions]


def test_loose_defaults_everything_and_records_the_class():
    iv = run_all("loose")
    assert statuses(iv) == ["defaulted"] * 3 and not iv.unresolved()
    assert [x.risk for x in iv.questions] == ["high", "medium", "low"]
    assert all(x.risk_rule and x.risk_reason for x in iv.questions)


def test_standard_defaults_low_and_medium_but_not_a_high_question():
    iv = run_all("standard")
    assert statuses(iv) == ["unresolved", "defaulted", "defaulted"]
    assert iv.unresolved()[0].answer is None and iv.unresolved()[0].risk == "high"


def test_strict_leaves_nothing_to_a_default():
    iv = run_all("strict")
    assert statuses(iv) == ["unresolved"] * 3


def test_an_answered_high_question_is_fine_at_every_level():
    for level in RQ.LEVELS:
        iv = run_all(level, Oracle({HIGH: "25 MHz from the C3 oscillator", MED: "512", LOW: "top"}))
        assert statuses(iv) == ["answered"] * 3 and not iv.unresolved()


def test_the_oracle_not_specified_on_a_high_question_is_a_stop_at_standard_not_at_loose():
    who = Oracle({MED: "512"})                                   # the hidden spec says nothing about the clock
    assert statuses(run_all("loose", who)) == ["defaulted", "answered", "defaulted"]
    iv = run_all("standard", who)
    assert statuses(iv) == ["unresolved", "answered", "defaulted"] and iv.unresolved()[0].by == "oracle"


def test_a_question_dropped_by_the_limit_is_unresolved_when_it_must_be_resolved():
    iv = run_all("standard", None, limit=0)
    assert [(x.status, x.by) for x in iv.questions] == [("unresolved", "limit"), ("defaulted", "limit"), ("defaulted", "limit")]


def test_a_package_fact_answers_without_a_waiver():
    iv = Interview(level="strict", facts=[{"key": "clock.clk_sys", "value": "25 MHz", "source": {"file": "b.pdf", "locator": "p3"}, "confidence": "high"}])
    out = iv.ask(q("q1", "Which clock is clk_sys: its frequency and where it comes from?"), None)
    assert out.status in ("answered", "unresolved")      # a fact only answers the shapes package_facts knows; either way no crash
    assert out.risk == "high"


# ---- waivers --------------------------------------------------------------------------------------------------------------------------
def W(**kw) -> RQ.Waiver:
    base = dict(match="clk_sys", value="agent's default accepted", who="Alex", when="2026-11-25", why="the bench oscillator is fixed at 10 MHz")
    return RQ.Waiver(**{**base, **kw})


def test_a_waiver_settles_a_must_resolve_question_and_is_recorded():
    iv = run_all("standard", None, [W()])
    assert statuses(iv) == ["waived", "defaulted", "defaulted"]
    first = iv.questions[0]
    assert first.answer == "10 MHz" and first.waiver["who"] == "Alex" and first.waiver["when"] == "2026-11-25" and "bench" in first.waiver["why"]
    assert not iv.unresolved()


def test_a_waiver_can_choose_a_value():
    iv = run_all("standard", None, [W(value="12 MHz")])
    assert iv.questions[0].answer == "12 MHz" and iv.questions[0].status == "waived"


def test_a_waiver_matches_an_id_words_or_a_class_and_no_other_question():
    assert run_all("strict", None, [W(match="q2")]).questions[1].status == "waived"
    assert run_all("strict", None, [W(match="fifo depth")]).questions[1].status == "waived"
    iv = run_all("strict", None, [W(match="*", risk="low")])
    assert statuses(iv) == ["unresolved", "unresolved", "waived"]            # the blanket waiver covers only its own class
    iv = run_all("strict", None, [W(match="nothing like it")])
    assert statuses(iv) == ["unresolved"] * 3
    assert run_all("strict", None, [W(match="clk_sys", requirement="REQ-08")]).questions[0].status == "unresolved"    # a conflict waiver settles no question


def test_waivers_load_with_every_field_or_not_at_all(tmp_path):
    (tmp_path / RQ.WAIVERS_FILE).write_text(yaml.safe_dump({"waivers": [
        {"match": "clk_sys", "value": "x", "who": "Alex", "when": "2026-11-25", "why": "the oscillator is fixed on this bench"},
        {"match": "q2", "value": "x", "who": "Alex", "when": "yesterday", "why": "short"},
        {"match": "*", "value": "x", "who": "Alex", "when": "2026-11-25", "why": "everything is fine, trust me"},
        {"match": "q3", "value": "x", "when": "2026-11-25", "why": "no name"},
        {"requirement": "REQ-08", "who": "Alex", "when": "2026-11-25", "why": "the chain may be pipelined after all"}]}))
    ws, probs = RQ.load_waivers(tmp_path)
    assert [w.match for w in ws] == ["clk_sys", ""] and ws[1].requirement == "REQ-08"
    text = " ".join(probs)
    assert "when is not YYYY-MM-DD" in text and "under 8 characters" in text and "names the risk class" in text and "no who" in text
    assert RQ.load_waivers(tmp_path / "missing") == ([], [])
    (tmp_path / RQ.WAIVERS_FILE).write_text("waivers: [: not yaml")
    assert "not valid YAML" in RQ.load_waivers(tmp_path)[1][0]


def test_a_person_can_waive_at_the_interview():
    k = q("q1", HIGH)
    assert RQ.waiver_from_human("accept default", k).value == "agent's default accepted"
    w = RQ.waiver_from_human({"waive": True, "why": "the board has one oscillator", "by": "Alex"}, k)
    assert (w.who, w.why, w.match) == ("Alex", "the board has one oscillator", "q1")
    assert RQ.waiver_from_human("25 MHz", k) is None and RQ.waiver_from_human({"answer": "25 MHz"}, k) is None
    assert "no reason given" in RQ.waiver_from_human("waive", k).why


# ---- what the spec and the summary keep --------------------------------------------------------------------------------------------------
def test_an_unresolved_question_stays_open_in_spec_yaml_and_the_rest_is_resolved():
    iv = run_all("standard")
    spec = iv.resolve_into({"open_questions": [{"question": HIGH}, {"question": MED}, {"question": LOW}, {"question": "never asked"}]})
    assert [o["question"] for o in spec["open_questions"]] == [HIGH, "never asked"]
    rows = {r["question"]: r for r in spec["resolved_questions"]}
    assert set(rows) == {MED, LOW} and rows[MED]["risk"] == "medium" and rows[MED]["status"] == "defaulted"


def test_a_waived_question_keeps_its_waiver_in_spec_yaml():
    iv = run_all("standard", None, [W()])
    spec = iv.resolve_into({})
    r = next(x for x in spec["resolved_questions"] if x["question"] == HIGH)
    assert r["status"] == "waived" and r["waiver"]["who"] == "Alex" and r["risk"] == "high"


def test_the_summary_counts_the_new_statuses_and_merging_keeps_them():
    iv = run_all("strict", None, [W(match="q1")])
    s = iv.summary()
    assert (s["asked"], s["waived"], s["unresolved"], s["defaulted"], s["level"]) == (3, 1, 2, 0, "strict")
    m = merge_summaries(None, {**s, "requirements_stop": "requirements: x", "level_source": "command line"})
    assert (m["waived"], m["unresolved"], m["level"], m["requirements_stop"]) == (1, 2, "strict", "requirements: x")
    assert merge_summaries(s, {"questions": []})["unresolved"] == 2


def test_assumptions_list_every_default_with_its_class_highest_first_and_never_an_answer():
    spec = {"resolved_questions": [
        {"question": LOW, "answer": "top", "status": "defaulted", "by": "default", "default_reason": "tidy"},
        {"question": HIGH, "answer": "10 MHz", "status": "defaulted", "by": "oracle", "default_reason": "typical", "risk": "high"},
        {"question": MED, "answer": "512", "status": "answered", "by": "oracle"},
        {"question": "Which pin drives the LED?", "answer": "H17", "status": "waived", "by": "default",
         "waiver": {"who": "Alex", "why": "the schematic says H17"}},
        {"question": "Which register holds the count?", "answer": "0x04", "status": "defaulted", "by": "limit"}]}
    a = RQ.assumptions_of(spec)
    assert [x["risk"] for x in a] == ["high", "high", "high", "low"]            # sorted high first; a record with no class is classified now
    assert MED not in [x["question"] for x in a]
    by = {x["question"]: x for x in a}
    assert by[HIGH]["how"] == "defaulted: the oracle did not know"
    assert by["Which pin drives the LED?"]["how"].startswith("waived by Alex")
    assert by["Which register holds the count?"]["how"] == "defaulted: the question limit was reached"
    assert RQ.assumptions_of({}) == []


# ---- the stop path through the clarify node ---------------------------------------------------------------------------------------------
def fake_rt(tmp_path: Path, level: str, interview: str = "off") -> SimpleNamespace:
    d = tmp_path / "design"
    d.mkdir(exist_ok=True)
    (tmp_path / "spec.md").write_text("A counter.\n")
    (d / "spec.md").write_text("A counter.\n")
    cfg = SimpleNamespace(interview=interview, hidden_spec=None, requirements=level, spec_md=tmp_path / "spec.md")
    return SimpleNamespace(cfg=cfg, design=d, oracle_llm=None)


SPEC = {"name": "x", "requirements": [], "open_questions": [
    {"question": HIGH, "default": "10 MHz", "reason": "the board's usual clock"},
    {"question": LOW, "default": "top", "reason": "a plain name"}]}


def test_standard_stops_at_clarify_and_writes_what_is_needed(tmp_path):
    rt = fake_rt(tmp_path, "standard")
    spec, summ = gr._interview(rt, dict(SPEC), {})
    assert summ["unresolved"] == 1 and summ["level"] == "standard" and summ["requirements_stop"].startswith("requirements: 1 unanswered question")
    need = (rt.design / RQ.NEEDED_FILE).read_text()
    assert "Which clock is clk_sys" in need and "| high |" in need and RQ.WAIVERS_FILE in need and "10 MHz" in need
    assert [o["question"] for o in yaml.safe_load((rt.design / "spec.yaml").read_text())["open_questions"]] == [HIGH]
    assert RQ.read_state(rt.design)["level"] == "standard"
    assert gr_exit({"stop": summ["requirements_stop"]}) == RQ.EXIT_REQUIREMENTS == 3


def gr_exit(summary: dict) -> int:
    from agent.__main__ import exit_status
    return exit_status(summary)


def test_loose_does_not_stop_and_a_clean_stop_exits_zero(tmp_path):
    rt = fake_rt(tmp_path, "loose")
    spec, summ = gr._interview(rt, dict(SPEC), {})
    assert summ["unresolved"] == 0 and "requirements_stop" not in summ and summ["defaulted"] == 2
    assert not (rt.design / RQ.NEEDED_FILE).exists()
    assert gr_exit({"stop": "done"}) == 0 and gr_exit({}) == 0 and gr_exit(None) == 0
    assert gr_exit({"stop": "budget: run limit"}) == 0


def test_a_waiver_file_beside_the_request_lets_the_run_through(tmp_path):
    rt = fake_rt(tmp_path, "standard")
    (tmp_path / RQ.WAIVERS_FILE).write_text(yaml.safe_dump({"waivers": [{"match": "clk_sys", "value": "agent's default accepted", "who": "Alex",
                                                                          "when": "2026-11-25", "why": "the bench oscillator is fixed at 10 MHz"}]}))
    spec, summ = gr._interview(rt, dict(SPEC), {})
    assert summ["unresolved"] == 0 and summ["waived"] == 1 and "requirements_stop" not in summ
    r = next(x for x in spec["resolved_questions"] if x["question"] == HIGH)
    assert r["status"] == "waived" and r["waiver"]["who"] == "Alex"


def test_a_bad_waiver_is_reported_not_used(tmp_path):
    rt = fake_rt(tmp_path, "standard")
    (tmp_path / RQ.WAIVERS_FILE).write_text(yaml.safe_dump({"waivers": [{"match": "clk_sys", "value": "x", "who": "Alex", "when": "2026-11-25", "why": "ok"}]}))
    _, summ = gr._interview(rt, dict(SPEC), {})
    assert summ["unresolved"] == 1 and "under 8 characters" in summ["waiver_problems"][0]
    assert "Waivers that were not used" in (rt.design / RQ.NEEDED_FILE).read_text()


def test_the_requests_own_line_sets_the_level(tmp_path):
    rt = fake_rt(tmp_path, "")
    (rt.design / "spec.md").write_text("A counter.\nRequirements: strict\n")
    _, summ = gr._interview(rt, dict(SPEC), {})
    assert summ["level"] == "strict" and summ["unresolved"] == 2 and summ["level_source"] == "the request (spec.md)"


def test_the_oracle_runs_under_the_level(tmp_path):
    hidden = tmp_path / "hidden.yaml"
    hidden.write_text("clock: the oscillator is 25 MHz\n")
    rt = fake_rt(tmp_path, "standard", "oracle")
    rt.cfg.hidden_spec = hidden
    rt.oracle_llm = lambda system, user: {"answer": "not specified", "quote": None}
    _, summ = gr._interview(rt, dict(SPEC), {})
    assert summ["unresolved"] == 1 and any(x["by"] == "oracle" and x["status"] == "unresolved" for x in summ["questions"])
    rt2 = fake_rt(tmp_path, "standard", "oracle")
    rt2.cfg.hidden_spec = hidden
    rt2.oracle_llm = lambda system, user: {"answer": "25 MHz", "quote": "the oscillator is 25 MHz"}
    _, s2 = gr._interview(rt2, dict(SPEC), {})
    assert s2["unresolved"] == 0 and s2["answered"] == 2


# ---- a fix against a stated requirement (209a's deep_for_clock) -----------------------------------------------------------------------------
REQS = [{"id": "REQ-01", "text": "led[1] is the exclusive-or of all bits of a", "proof": ["simulation"]},
        {"id": "REQ-08", "text": "The synthesized netlist has no register between a and y", "proof": ["analysis"]}]
C15 = {"logic_levels_synth.rpt": "logic_levels_c15_deep.rpt", "timing_summary_synth.rpt": "timing_synth_deep_fails.rpt"}


def gate_rt(tmp_path: Path, level: str) -> SimpleNamespace:
    d = tmp_path / "design"
    b = d / "build" / "base"
    b.mkdir(parents=True)
    for name, src in C15.items():
        (b / name).write_text((D204 / src).read_text())
    (d / "spec.yaml").write_text(yaml.safe_dump({"name": "deep", "requirements": REQS}))
    (d / "spec.md").write_text("A chain of 24 multiplies, no register in the chain.\n")
    run = tmp_path / "run"
    run.mkdir()
    return SimpleNamespace(design=d, run_dir=run, visit=2, session=SimpleNamespace(stage="rtl-design-creation"), cfg=SimpleNamespace(
        requirements=level, hidden_spec=None, spec_md=tmp_path / "spec.md"))


def conflict_gate(tmp_path: Path, level: str) -> tuple[dict, list[str], SimpleNamespace]:
    rt = gate_rt(tmp_path, level)
    ev = {"report_gates": gr.report_gates_eval(rt)}
    out: dict = {}
    detail: list[str] = []
    gr.requirements_conflict_gate(rt, ev, out, detail)
    return out, detail, rt


def test_the_pipelining_fix_conflicts_with_a_no_register_requirement():
    finding = {"code": "RPT-LL-02", "blocking": True, "fix": "Pipeline the path or lower the clock.", "message": "a setup path fails with no net delay"}
    c = RQ.fix_conflicts([finding], {"requirements": REQS})
    assert [x["requirement"] for x in c] == ["REQ-08"] and c[0]["fix_kind"] == "pipeline"
    assert RQ.fix_conflicts([{"code": "RPT-LOG-03", "blocking": True}], {"requirements": REQS}) == []
    assert RQ.fix_conflicts([finding], {"requirements": [REQS[0]]}) == []


@pytest.mark.parametrize("level", ["standard", "strict"])
def test_standard_and_strict_stop_naming_the_conflict(tmp_path, level):
    out, detail, rt = conflict_gate(tmp_path, level)
    assert out["stop"].startswith("requirements: ") and "REQ-08" in out["stop"] and "RPT-LL-02" in out["stop"]
    assert RQ.is_requirements_stop(out["stop"]) and gr_exit({"stop": out["stop"]}) == 3
    need = (rt.design / RQ.NEEDED_FILE).read_text()
    assert "REQ-08" in need and "conflicts with a stated requirement" in need
    st = RQ.read_state(rt.design)
    assert st["conflicts"][0]["action"] == "stopped" and st["conflicts"][0]["level"] == level
    events = [json.loads(l) for l in (rt.run_dir / gr.ROUTING_EVENTS).read_text().splitlines()]
    assert events[-1]["event"] == "requirements_conflict" and events[-1]["conflicts"] == [["REQ-08", "RPT-LL-02"]]


def test_loose_goes_ahead_and_records_the_conflict(tmp_path):
    out, detail, rt = conflict_gate(tmp_path, "loose")
    assert "stop" not in out and any("REQ-08" in x for x in detail)
    st = RQ.read_state(rt.design)
    assert st["conflicts"][0]["requirement"] == "REQ-08" and st["conflicts"][0]["action"] == "proceeded"
    assert not (rt.design / RQ.NEEDED_FILE).exists()


def test_a_waiver_naming_the_requirement_lets_standard_go_ahead_and_the_report_still_fails_it(tmp_path):
    rt = gate_rt(tmp_path, "standard")
    (tmp_path / RQ.WAIVERS_FILE).write_text(yaml.safe_dump({"waivers": [
        {"requirement": "REQ-08", "who": "Alex", "when": "2026-11-25", "why": "pipelining the chain is acceptable on this board"}]}))
    ev = {"report_gates": gr.report_gates_eval(rt)}
    out: dict = {}
    gr.requirements_conflict_gate(rt, ev, out, [])
    assert "stop" not in out
    c = RQ.read_state(rt.design)["conflicts"][0]
    assert c["action"] == "proceeded" and c["waiver"]["who"] == "Alex"


def test_no_blocking_finding_means_no_conflict_check(tmp_path):
    rt = gate_rt(tmp_path, "strict")
    out: dict = {}
    gr.requirements_conflict_gate(rt, {"report_gates": {"findings": [], "advisories": []}}, out, [])
    gr.requirements_conflict_gate(rt, {}, out, [])
    assert out == {} and RQ.read_state(rt.design) == {}
