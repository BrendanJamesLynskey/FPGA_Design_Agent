"""Brief 227: the stage-0 rounds (agent/graph/readiness.py) with scripted model replies. No model is called.

Covered: a set the readers agree on is frozen in one round; a disagreement becomes a question, the oracle's answer an amendment, the next round's agreement
freezes it; with nobody to answer the run stops (not a guess) with REQUIREMENTS_NEEDED.md; the round limit and the call budget stop it; the amender cannot reuse
an id; the reviewer's verdict follows its findings; the readers see only the English and the interface (not the request, not the reviewer); the third reader's
layer 2 is compared in code; a person's answers file is applied; the checklist comes from the knowledge-bank skill when the bank is at hand."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from agent.graph import readiness as G
from flow import readiness as R

FIX = Path(__file__).resolve().parents[2] / "flow" / "tests" / "fixtures" / "readiness" / "freqmeter"
REQUEST = "Count edges of clk_in over a window of 8 clk_ref cycles after a start pulse. SECRET-REQUEST-WORDS"

PROBES = {"probes": [
    {"id": "P1", "category": "reset", "requirements": ["REQ-01"], "scenario": "reset released", "question": "Is busy low after release?", "answer_kind": "bool"},
    {"id": "P2", "category": "simultaneous", "requirements": ["REQ-02"], "scenario": "start while busy", "question": "Does the window restart?", "answer_kind": "bool"},
    {"id": "P3", "category": "boundary", "requirements": ["REQ-03"], "scenario": "a read in the last window cycle", "question": "Is valid high?", "answer_kind": "bool"},
    {"id": "P4", "category": "back_pressure", "requirements": ["REQ-05"], "scenario": "reg_rd held 3 cycles", "question": "Cycles of reg_rvalid?", "answer_kind": "int"},
    {"id": "P5", "category": "unmapped", "requirements": ["REQ-05"], "scenario": "reg_addr is 15", "question": "Is reg_rvalid high after a read?", "answer_kind": "bool"}]}


def spec_of_fixture() -> dict:
    s = yaml.safe_load((FIX / "spec.yaml").read_text())
    s["ports"].append({"name": "reg_addr", "dir": "in", "width": 4, "clock": "clk_ref"})
    s["latencies"].append({"output": "reg_rvalid", "from": "reg_rd", "cycles": 1, "clock": "clk_ref"})
    return s


class Fake:
    """Scripted replies by role (recognised from the system prompt); every call is recorded with its user message. ``readers`` is a function
    ``(reader call index, amendments made so far) -> reply dict``; the default has both readers give the same answers."""

    def __init__(self, review=None, readers=None, amend=None, probes=None, l3=None, formal=None):
        self.calls: list[tuple[str, str]] = []
        self.review_r = review or [{"findings": [], "compliance": [], "verdict": "ready"}]
        same = {"answers": [{"id": f"P{i}", "answer": a} for i, a in enumerate(["yes", "no", "yes", "3", "yes"], 1)]}
        self.readers = readers or (lambda i, n_amend: same)
        self.amend_r = amend or {"upsert": [], "delete": []}
        self.probes = probes or PROBES
        self.l3 = l3
        self.formal = formal or {}
        self.n = {"review": 0, "reader": 0, "amend": 0}

    def __call__(self, system, user):
        for role, marker in (("review", "requirements reviewer"), ("probes", "write probe scenarios"), ("reader", "careful reader"), ("reader3", "structured form"), ("amend", "update a hardware requirements set"), ("formalise", "structure of hardware requirements")):
            if marker in system:
                break
        else:
            raise AssertionError("unknown role: " + system[:60])
        self.calls.append((role, user))
        if role == "review":
            r = self.review_r[min(self.n["review"], len(self.review_r) - 1)]
            self.n["review"] += 1
            return json.dumps(r)
        if role == "probes":
            return json.dumps(self.probes)
        if role == "amend":
            self.n["amend"] += 1
            return "```json\n" + json.dumps(self.amend_r) + "\n```"
        if role == "reader3":
            return json.dumps(self.l3)
        if role == "formalise":
            return json.dumps(self.formal)
        i = self.n["reader"]
        self.n["reader"] += 1
        return json.dumps(self.readers(i, self.n["amend"]))

    def llms(self):
        return G.LLMs(review=self, reader=self, reader3=self if self.l3 is not None else None)


class Oracle:
    name = "oracle"

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def answer(self, q):
        self.asked.append(q.text)
        return self.answers(q)


def fresh(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    (d / "spec.yaml").write_text((FIX / "spec.yaml").read_text())
    (d / "spec.md").write_text(REQUEST)
    return d


def test_a_set_the_readers_agree_on_is_frozen_in_one_round(tmp_path):
    d, f = fresh(tmp_path), Fake()
    res = G.run_stage0(d, spec_of_fixture(), REQUEST, level="standard", llms=f.llms())
    assert res.frozen and res.stop is None and len(res.state["rounds"]) == 1
    rd = res.state["rounds"][0]
    assert rd["agreement"]["rate"] == 1.0 and rd["probes"]["count"] == 5 and rd["probe_set"][0]["id"] == "P1"
    fr = R.read_frozen(d)
    assert fr["status"] == "frozen" and fr["ids"][0] == "REQ-01" and fr["rounds"] == 1
    assert res.state["model_calls"] == 4 and res.state["calls_by_role"] == {"probes": 1, "reader_a": 1, "reader_b": 1, "review": 1}
    G.write_records(d, res)
    assert json.loads((d / "build" / "requirements" / "readiness.json").read_text())["frozen"]["version"] == 1
    assert "frozen" in (d / "REQUIREMENTS_READINESS.md").read_text() and not (d / "REQUIREMENTS_NEEDED.md").exists()


def test_the_readers_see_only_the_english_and_the_interface_never_the_request_or_the_reviewer(tmp_path):
    d, f = fresh(tmp_path), Fake(review=[{"findings": [], "compliance": [], "verdict": "ready"}])
    spec = spec_of_fixture()
    spec["requirements"][1]["l2"] = {"condition": "L2-ONLY-MARK"}
    G.run_stage0(d, spec, REQUEST, level="standard", llms=f.llms())
    users = [u for k, u in f.calls if k == "reader"]
    assert len(users) == 2 and users[0] == users[1]                                  # two separate fresh calls, the same inputs
    for u in users:
        assert "SECRET-REQUEST-WORDS" not in u and "L2-ONLY-MARK" not in u and "Checklist" not in u and "verdict" not in u
        assert "REQ-01: After reset, busy and valid are low." in u and "- busy (out, 1 bit" in u
    assert "SECRET-REQUEST-WORDS" in [u for k, u in f.calls if k == "review"][0]


def test_a_disagreement_becomes_a_question_the_oracle_answers_and_the_next_round_freezes(tmp_path):
    d = fresh(tmp_path)
    ans = lambda p2: {"answers": [{"id": "P1", "answer": "yes"}, {"id": "P2", "answer": p2}, {"id": "P3", "answer": "yes"}, {"id": "P4", "answer": "3"}, {"id": "P5", "answer": "yes"}]}
    # before the amendment reader A says "no" and reader B "yes" to P2; after it both say "no"
    f = Fake(readers=lambda i, n_amend: ans("no") if (n_amend or i % 2 == 0) else ans("yes"),
             amend={"upsert": [{"id": "REQ-06", "text": "When start is high while busy is high, valid stays low and the window does not restart.", "proof": ["simulation"], "source": "answer Q1"}],
                    "delete": [], "reason": "the oracle said the window does not restart"})
    o = Oracle(lambda q: ("The window does not restart; start is ignored while busy.", "start while busy is ignored") if "restart" in q.text.lower() else ("not specified", None))
    res = G.run_stage0(d, spec_of_fixture(), REQUEST, level="standard", llms=f.llms(), answerer=o, limits=R.Limits(max_rounds=3))
    assert res.frozen and len(res.state["rounds"]) == 2
    r1, r2 = res.state["rounds"]
    assert r1["agreement"]["rate"] == 0.8 and [x["probe"] for x in r1["agreement"]["disagreements"]] == ["P2"]
    assert any("restart" in q["text"].lower() and q["answer"] and q["by"] == "oracle" for q in r1["questions"])
    assert r1["amendments"] == ["REQ-06"] and r2["agreement"]["rate"] == 1.0
    assert next(r for r in res.spec["requirements"] if r["id"] == "REQ-06")["text"].endswith("does not restart.")
    assert R.read_ledger(d)["ids"]["REQ-06"]["deleted"] is False and res.state["frozen"]["rounds"] == 2


def test_with_nobody_to_answer_the_run_stops_with_the_questions_and_never_guesses(tmp_path):
    d = fresh(tmp_path)
    f = Fake(review=[{"findings": [{"topic": "reset strategy", "ids": ["REQ-01"], "missing_fact": "reset value of count", "question": "What does count hold during reset?", "blocking": True, "why": "w"}], "verdict": "ready"}])
    res = G.run_stage0(d, spec_of_fixture(), REQUEST, level="standard", llms=f.llms(), answerer=None)
    assert not res.frozen and res.stop == "no answer was available for the open questions" and len(res.state["rounds"]) == 1
    assert [q.text for q in res.open_questions] == ["What does count hold during reset?"] and res.open_questions[0].id == "Q1" and res.open_questions[0].source == "reviewer"
    G.write_records(d, res)
    needed = (d / "REQUIREMENTS_NEEDED.md").read_text()
    assert "What does count hold during reset?" in needed and "requirements_answers.yaml" in needed and R.read_frozen(d) is None
    assert G.stop_text(res).startswith("requirements: readiness:")
    from agent.graph import requirements as RQ
    assert RQ.is_requirements_stop(G.stop_text(res))                 # exit status 3 by the existing rule


def test_a_non_blocking_finding_is_not_a_question_and_the_verdict_follows_the_findings(tmp_path):
    f = Fake(review=[{"findings": [{"topic": "requirement", "question": "Would you prefer a different name?", "blocking": False}], "verdict": "not_ready"}])
    d = fresh(tmp_path)
    res = G.run_stage0(d, spec_of_fixture(), REQUEST, level="standard", llms=f.llms())
    assert res.frozen and res.state["rounds"][0]["review"]["verdict"] == "ready"
    assert G.clean_review({"findings": [{"question": "q", "blocking": True}], "verdict": "ready"})["verdict"] == "not_ready"


def test_the_round_limit_and_the_call_budget_are_stops_not_silent_guesses(tmp_path):
    d = fresh(tmp_path)
    always = {"findings": [{"topic": "requirement", "question": "Never settled?", "blocking": True}]}
    f = Fake(review=[always])
    o = Oracle(lambda q: ("some answer", "q"))
    res = G.run_stage0(d, spec_of_fixture(), REQUEST, level="standard", llms=f.llms(), answerer=o, limits=R.Limits(max_rounds=2))
    assert res.stop == "the round limit (2) was reached with questions still open" and len(res.state["rounds"]) == 2 and not res.frozen
    d2 = tmp_path / "d2"
    d2.mkdir()
    (d2 / "spec.yaml").write_text("x: 1")
    f2 = Fake(review=[always])
    res2 = G.run_stage0(d2, spec_of_fixture(), REQUEST, level="standard", llms=f2.llms(), answerer=o, limits=R.Limits(max_rounds=5, max_calls=6))
    assert res2.stop == "the model-call budget (6) is used up" and res2.state["model_calls"] == 6


def test_the_amender_cannot_reuse_an_id_or_change_what_it_was_not_asked_about(tmp_path):
    led = {"ids": {"REQ-09": {"deleted": True, "text_sha": "x"}, "REQ-01": {"deleted": False, "text_sha": "y"}}}
    spec = spec_of_fixture()
    new, rev, ref = G.apply_amendment(spec, led, {"upsert": [{"id": "REQ-09", "text": "A reused id must be refused."}, {"id": "REQ-01", "text": "After reset, busy, valid and ovf are low."},
                                                              {"id": "REQ-20", "text": "Ovf is low after reset."}, {"text": "no id"}], "delete": ["REQ-08"]})
    assert rev == ["REQ-01"] and any("REQ-09 was used before" in r for r in ref) and any("without id or text" in r for r in ref)
    ids = [r["id"] for r in new["requirements"]]
    assert "REQ-09" not in ids and "REQ-20" in ids and "REQ-08" not in ids
    assert next(r for r in new["requirements"] if r["id"] == "REQ-20")["proof"] == ["simulation"]
    assert [r["id"] for r in spec["requirements"]].count("REQ-08") == 1             # the input is not changed in place


def test_a_persons_answers_file_is_applied_before_the_first_round(tmp_path):
    d = fresh(tmp_path)
    (d / "build" / "requirements").mkdir(parents=True)
    (d / "build" / "requirements" / "readiness_open.yaml").write_text(yaml.safe_dump({"open": [{"id": "Q1", "text": "What does count hold in reset?", "code": "RDY-REV-01", "topic": "reset strategy", "ids": [], "blocking": True, "source": "reviewer"}]}))
    (d / R.ANSWERS_FILE).write_text("answers:\n  Q1: {answer: zero, who: owner}\n")
    f = Fake(amend={"upsert": [{"id": "REQ-09", "text": "Count is zero during and after reset.", "proof": ["simulation"], "source": "answer Q1"}]})
    res = G.run_stage0(d, spec_of_fixture(), REQUEST, level="standard", llms=f.llms(), answers=G.load_answers(d))
    assert res.frozen and "REQ-09" in {r["id"] for r in res.spec["requirements"]}
    q = res.state["rounds"][0]["questions"][0]
    assert q["answer"] == "zero" and q["by"] == "owner" and [r for r in res.state["rounds"][0]["amendments"]] == []


def test_the_third_reader_at_strict_is_a_different_call_and_its_difference_is_a_question(tmp_path):
    d = fresh(tmp_path)
    spec = spec_of_fixture()
    spec["requirements"][1]["l2"] = {"scope": "always", "condition": "start is high and busy is low", "component": "the meter", "timing": {"kind": "after", "n": 1, "clock": "clk_ref", "from": "start"}, "response": "busy is high"}
    third = {"scope": "always", "condition": "start high and busy low", "component": "meter", "timing": {"kind": "within", "n": 2, "clock": "clk_ref", "from": "start"}, "response": "busy is high"}
    f = Fake(l3=third)
    res = G.run_stage0(d, spec, REQUEST, level="strict", llms=f.llms(), limits=R.Limits(max_rounds=1))
    diffs = res.state["rounds"][0]["l2_diffs"]
    assert diffs and diffs[0]["id"] == "REQ-02" and any("timing.kind" in x for x in diffs[0]["diff"])
    assert any(q["code"] == "RDY-L2-07" for q in res.state["rounds"][0]["questions"])
    assert [k for k, _ in f.calls].count("reader3") == 1


def test_the_checklist_comes_from_the_knowledge_bank_skill_when_it_is_at_hand(tmp_path):
    txt, src = G.load_checklist(tmp_path)
    assert src == "public fallback checklist" and "clocks and their sources" in txt
    sk = tmp_path / "procedures" / "requirements-review" / "pre-build-review"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("# requirements-review\nASK-ABOUT-THE-RESET-OF-EVERY-OUTPUT\n")
    txt, src = G.load_checklist(tmp_path)
    assert "ASK-ABOUT-THE-RESET" in txt and src.startswith("procedures/requirements-review/pre-build-review@sha256:")


def test_json_in_a_fence_or_a_sentence_is_read_and_garbage_is_none():
    assert G.parse_json('Here you go: {"a": 1} thanks') == {"a": 1} and G.parse_json("```json\n{\"a\": 2}\n```") == {"a": 2}
    assert G.parse_json("no json") is None and G.parse_json("[1, 2]") is None


# ---- the run hook ---------------------------------------------------------------------------------------------------------------------------
def _rt(tmp_path, d, f, **cfg):
    from types import SimpleNamespace
    resolver = SimpleNamespace(text=lambda purpose, **kw: f)
    return SimpleNamespace(cfg=SimpleNamespace(board="nexys_a7_100t", readiness="on", readiness_limits={"max_rounds": 2}, **cfg), design=d, run_dir=tmp_path, resolver=resolver)


def test_the_run_hook_freezes_skips_when_unchanged_and_returns_to_stage_0_on_a_change(tmp_path):
    d, f = fresh(tmp_path), Fake()
    rt = _rt(tmp_path, d, f)
    spec, summ = G.gate_step(rt, spec_of_fixture(), "standard", None)
    assert summ["readiness"]["frozen"] is True and "requirements_stop" not in summ
    assert (d / "build" / "requirements" / "frozen.json").is_file() and (d / "REQUIREMENTS_READINESS.md").is_file()
    n = len(f.calls)
    spec2, summ2 = G.gate_step(rt, spec, "standard", None)                                   # unchanged: no model call
    assert summ2["readiness"]["skipped"] == "the frozen set is unchanged" and len(f.calls) == n
    changed = copy.deepcopy(spec)
    changed["requirements"][0]["text"] = "After reset, busy, valid and ovf are low."
    _, summ3 = G.gate_step(rt, changed, "standard", None)
    fr = R.read_frozen(d)
    assert summ3["readiness"]["frozen"] is True and fr["reopened"][0]["ids"] == ["REQ-01"] and fr["version"] == 2 and len(f.calls) > n


def test_the_run_hook_reports_a_stop_that_the_run_turns_into_exit_status_3(tmp_path):
    d = fresh(tmp_path)
    f = Fake(review=[{"findings": [{"topic": "reset strategy", "question": "What does count hold in reset?", "blocking": True}]}])
    _, summ = G.gate_step(_rt(tmp_path, d, f), spec_of_fixture(), "standard", None)
    from agent.__main__ import exit_status
    assert summ["readiness"]["frozen"] is False and summ["requirements_stop"].startswith("requirements: readiness:")
    assert exit_status({"stop": summ["requirements_stop"]}) == 3 and (d / "REQUIREMENTS_NEEDED.md").is_file()


def test_readiness_is_off_by_default_and_round_trips_through_the_saved_config():
    from agent.__main__ import config_from_json
    from agent.graph.run import Config
    assert Config.__dataclass_fields__["readiness"].default == "off"
    base = {"spec_md": "s.md", "name": "n", "board": "b", "interview": "off", "review": "off", "model": "m"}
    c = config_from_json({**base, "readiness": "on", "readiness_limits": {"max_rounds": 2}})
    assert (c.readiness, c.readiness_limits) == ("on", {"max_rounds": 2}) and config_from_json(base).readiness == "off"


def test_a_requirement_resting_on_an_unanswered_question_is_marked_derived():
    spec = {"requirements": [{"id": "REQ-01", "text": "A write of GATE_LEN below 1000 is clamped to 1000.", "proof": ["simulation"]},
                             {"id": "REQ-02", "text": "Busy is low after reset.", "proof": ["simulation"], "origin": "the request"}],
            "resolved_questions": [{"question": "What happens when GATE_LEN is written below 1000?", "answer": "Clamp to 1000.", "status": "defaulted", "by": "oracle", "risk": "high"}]}
    out = G.mark_derived(spec, "Busy is low after reset.")
    assert out["requirements"][0]["derived"] is True and out["requirements"][0]["origin"]["kind"] == "default" and "derived" not in out["requirements"][1]
    assert R.unconfirmed_defaults(out) == ["REQ-01"] and "derived" not in spec["requirements"][0]


def test_the_spec_oracle_can_answer_a_stage_0_question_and_a_quote_not_in_the_hidden_spec_is_refused(tmp_path):
    from agent.graph.interview import SpecOracle
    hidden = tmp_path / "hidden.md"
    hidden.write_text("The window does not restart when start arrives while busy.\n")
    replies = iter([{"answer": "No restart.", "quote": "The window does not restart when start arrives while busy."}, {"answer": "Yes, it restarts.", "quote": "made up"}])
    o = SpecOracle(hidden, lambda system, user: next(replies))
    q = G.Q(id="Q1", text="Does a start while busy restart the window?")
    assert o.answer(q) == ("No restart.", "The window does not restart when start arrives while busy.")
    assert o.answer(q) == ("not specified", None)
    d = fresh(tmp_path)
    f = Fake(review=[{"findings": [{"topic": "requirement", "question": "Does a start while busy restart the window?", "blocking": True}]}, {"findings": []}],
             amend={"upsert": [{"id": "REQ-06", "text": "When start is high while busy is high, the window does not restart.", "proof": ["simulation"]}]})
    o2 = SpecOracle(hidden, lambda system, user: {"answer": "No restart.", "quote": "The window does not restart when start arrives while busy."})
    res = G.run_stage0(d, spec_of_fixture(), REQUEST, level="standard", llms=f.llms(), answerer=o2, limits=R.Limits(max_rounds=2))
    assert res.frozen and res.state["rounds"][0]["questions"][0]["by"] == "oracle"


def test_a_compound_row_is_repaired_by_the_amender_without_asking_the_user_and_the_new_row_gets_a_new_id(tmp_path):
    d = fresh(tmp_path)
    spec = spec_of_fixture()
    spec["requirements"].append({"id": "REQ-09", "text": "Busy goes high and valid goes low after start.", "proof": ["simulation"]})
    f = Fake(amend={"upsert": [{"id": "REQ-09", "text": "Busy goes high after start.", "proof": ["simulation"]}, {"id": "REQ-10", "text": "Valid goes low after start.", "proof": ["simulation"]}], "delete": []})
    res = G.run_stage0(d, spec, REQUEST, level="standard", llms=f.llms(), limits=R.Limits(max_rounds=2))
    assert res.frozen
    r1 = res.state["rounds"][0]
    assert r1["repairs"]["revised"][0] == "REQ-09" and r1["questions"] == [] and r1["repairs"]["refused"] == []
    ids = [r["id"] for r in res.spec["requirements"]]
    assert "REQ-10" in ids and f.calls[0][0] == "amend" and "Busy goes high and valid goes low" in f.calls[0][1] and "Ids already used" in f.calls[0][1]
    assert res.state["calls_by_role"]["repair"] == 1


def test_a_repair_that_did_not_work_is_put_to_the_user_as_a_question(tmp_path):
    d = fresh(tmp_path)
    spec = spec_of_fixture()
    spec["requirements"].append({"id": "REQ-09", "text": "Busy goes high and valid goes low after start.", "proof": ["simulation"]})
    f = Fake(amend={"upsert": [], "delete": []})                     # the amender changes nothing
    res = G.run_stage0(d, spec, REQUEST, level="standard", llms=f.llms(), answerer=None)
    assert not res.frozen and any(q.code == "RDY-CLEAR-01" for q in res.open_questions)


FORMAL = {"goals": [{"id": "G1", "text": "measure clk_in against clk_ref"}, {"id": "G2", "text": "read the result"}],
          "rows": [{"id": "REQ-02", "kind": "timing", "modal": "shall", "method": "test", "evidence": "test_start_busy", "trace_up": "G1",
                    "l2": {"scope": "always", "condition": "start is high and busy is low", "component": "the meter", "timing": {"kind": "after", "n": 1, "clock": "clk_ref", "from": "start"}, "response": "busy is high"},
                    "worked": ["start at cycle 3: busy high at cycle 4"], "never": "busy low in the cycle after an accepted start", "l3": {"sva": True}},
                   {"id": "REQ-03", "kind": "sideways", "modal": "must", "trace_up": "G9", "l2": {"timing": {"kind": "soon"}}}]}


def test_at_strict_the_agent_proposes_the_structure_and_code_refuses_what_is_not_valid_and_never_overwrites(tmp_path):
    spec = spec_of_fixture()
    for r in spec["requirements"]:
        for k in ("kind", "modal", "trace_up", "source"):
            r.pop(k, None)
    spec["requirements"][1]["modal"] = "should"                                  # written by a person: not overwritten
    out, ref = G.apply_formalisation(spec, FORMAL)
    r2, r3 = out["requirements"][1], out["requirements"][2]
    assert r2["modal"] == "should" and r2["kind"] == "timing" and r2["method"] == "Test" and r2["l2"]["timing"]["kind"] == "after" and r2["formalised_by"] == "agent"
    assert out["goals"][0]["id"] == "G1" and r2["trace_up"] == "G1" and r2["source"].endswith("(to be confirmed)")
    assert "kind" not in r3 and "modal" not in r3 and "l2" not in r3
    assert any("kind 'sideways'" in x for x in ref) and any("modal 'must'" in x for x in ref) and any("trace_up 'G9'" in x for x in ref) and any("l2.timing.kind 'soon'" in x for x in ref)
    assert spec["requirements"][1].get("l2") is None                              # the input is not changed in place


def test_strict_never_freezes_without_the_users_validation_even_when_every_layer_is_written(tmp_path):
    d = fresh(tmp_path)
    f = Fake(formal=FORMAL)
    spec = spec_of_fixture()
    for r in spec["requirements"]:
        for k in ("kind", "modal", "trace_up", "source"):
            r.pop(k, None)
    res = G.run_stage0(d, spec, REQUEST, level="strict", llms=f.llms(), answerer=None, limits=R.Limits(max_rounds=1))
    assert not res.frozen and res.state["rounds"][0]["formalised"]["refused"]
    codes = {q["code"] for q in res.state["rounds"][0]["questions"]}
    assert "RDY-VAL-01" in codes and res.state["calls_by_role"]["formalise"] == 1
