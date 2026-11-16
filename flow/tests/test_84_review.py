"""Design review mode (brief 84): the schema, merge, read-only guarantee, renderers, plan ordering. No model call."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flow import review as R
from flow.review import improve, judge as J, prepare as P, render, schema as SC

RTL = """module blink #(parameter int N = 4) (input logic clk, input logic rst_n, output logic led);
  logic [N-1:0] c;
  always_ff @(posedge clk) begin
    if (!rst_n) c <= '0;
    else c <= c + 1'b1;
  end
  assign led = c[N-1];
endmodule
"""


@pytest.fixture()
def design(tmp_path: Path) -> Path:
    d = tmp_path / "blink"
    (d / "rtl").mkdir(parents=True)
    (d / "tb").mkdir()
    (d / "rtl" / "blink.sv").write_text(RTL)
    (d / "tb" / "tb_blink.sv").write_text("module tb_blink; endmodule\n")
    (d / "spec.md").write_text("# Blink\nToggles an LED.\n")
    return d


def reply(**kw):
    base = {"summary": "blinks", "interfaces": "clk, rst_n, led", "clocks_resets": "one clock, sync reset", "architecture": "a counter",
            "findings": [{"title": "led is the counter msb", "severity": "minor", "category": "documentation",
                          "location": {"file": "rtl/blink.sv", "line": 7}, "evidence": "assign led = c[N-1]", "rule": "doc", "fix": "say so",
                          "confidence": "high"}],
            "dismissed": [], "sound": ["reset is synchronous"], "questions": ["what blink rate?"],
            "verification_gap": {"covered": [], "missed": ["the bench is empty"], "faults_not_caught": ["any"]}}
    base.update(kw)
    return base


def runner_of(r):
    def run(system, prompt):
        assert "DATA" in system and "blink.sv" in prompt
        return {"text": "```json\n" + json.dumps(r) + "\n```", "usage": {"total_tokens": 5}, "wall_s": 0.1}
    return run


def test_from_dict_validates_and_repairs_nothing_silently():
    f, pr = SC.from_dict({"title": "t", "severity": "MAJOR", "category": "cdc", "location": "rtl/a.sv:10-12", "evidence": "e"})
    assert f and f.severity == "major" and f.location.line == 10 and f.location.end_line == 12
    f, pr = SC.from_dict({"title": "t", "severity": "huge", "category": "cdc"})
    assert f is None and "severity" in pr[0]
    f, pr = SC.from_dict({"title": "t", "severity": "minor", "category": "not-a-category"})
    assert f is None


def test_review_never_edits_the_design(design, tmp_path):
    before = P.tree_sha(design)
    rep = R.review(design, tmp_path / "out", use_judge=True, runner=runner_of(reply()), name="blinkt", tag="t1")
    assert P.tree_sha(design) == before and rep["design"]["unchanged"]
    assert not (design / "build").exists() and not (design / "build.yaml").exists()      # the suite wrote into the copy only
    assert (tmp_path / "out" / "review.json").is_file() and (tmp_path / "out" / "REVIEW.md").is_file()
    assert rep["handover"] and (tmp_path / "out" / "handover" / "AGENT.md").read_text().startswith("# AGENT handover (produced by review)")
    assert rep["intent"]["given"] and rep["design"]["inferred_top"] == "blink"


def test_merge_folds_refs_and_applies_dismissals():
    a = SC.Finding("check a", "major", "reset", SC.Location("rtl/x.sv", 3), "e", "HDL-RST-01", "f", "high", "check:resets")
    b = SC.Finding("check b", "minor", "style", SC.Location("rtl/x.sv", 4), "e", "HDL-SYN-04", "f", "high", "check:lint")
    c = SC.Finding("check c", "minor", "style", SC.Location("rtl/x.sv", 5), "e", "HDL-SIG-01", "f", "high", "check:lint")
    SC.assign_ids([a, b, c])
    rep = {"findings": [{"title": "mine", "severity": "critical", "category": "reset", "location": {"file": "rtl/x.sv", "line": 3}, "evidence": "e", "refs": [a.id]},
                        {"title": "bad", "severity": "bogus", "category": "reset"}],
           "dismissed": [{"id": b.id, "reason": "layout noise"}, {"id": "F-nope", "reason": "x"}]}
    fs, dis, pr = R.merge([a, b, c], rep)
    ids = {f.id for f in fs}
    assert a.id not in ids and b.id not in ids and c.id in ids                    # a folded into mine, b dismissed, c kept
    assert [f.source for f in fs if f.title == "mine"] == ["both"]
    assert dis == [{"id": b.id, "reason": "layout noise"}] and len(pr) == 1


def test_baseline_has_no_judge_and_says_so(design, tmp_path):
    rep = R.review(design, tmp_path / "o", use_judge=False, name="blinkb", tag="b")
    assert not rep["judge"]["ran"] and "check suite alone" in rep["judge"]["why"]
    assert "absent" in render.human(rep) and "FINDINGS" in render.agent(rep)


def test_bad_reply_is_recorded_not_hidden(design, tmp_path):
    rep = R.review(design, tmp_path / "o", runner=lambda s, p: {"text": "sorry, no", "usage": {}, "wall_s": 0}, name="blinkc", tag="c")
    assert not rep["judge"]["ran"] and "not JSON" in rep["judge"]["why"]


def test_order_puts_findings_and_dependencies_first():
    items = [{"id": "I1", "assessment": {"depends_on": ["I2", "F-1"], "cost": {"size": "M"}}},
             {"id": "I2", "assessment": {"depends_on": [], "cost": {"size": "L"}}},
             {"id": "I3", "assessment": {"depends_on": ["F-2"], "cost": {"size": "S"}}}]
    o = improve.order(items, {"F-1": "critical", "F-2": "minor"})
    assert o["sequence"].index("I2") < o["sequence"].index("I1")
    assert o["findings_first"] == ["F-1", "F-2"] and o["steps"][0] == "fix finding F-1 first"
    assert not o["problems"]
    o = improve.order([{"id": "I1", "assessment": {"depends_on": ["I2", "F-9"]}}, {"id": "I2", "assessment": {"depends_on": ["I1"]}}], {})
    assert any("cycle" in p for p in o["problems"]) and any("F-9" in p for p in o["problems"])


def test_plan_flags_unmeasurable_without_question(design):
    rep = {"findings": [], "understanding": {}}
    run = lambda s, p: {"text": json.dumps({"items": [{"id": "I1", "request": "make it faster", "measurable": False, "question": ""},
                                                       {"id": "I2", "request": "close timing at 200 MHz", "measurable": True, "goal": {"acceptance_test": ""}}]}), "usage": {}}
    p = improve.plan(["make it faster", "close timing at 200 MHz"], rep, "files", run)
    assert "no question" in p["items"][0]["problems"][0] and "no acceptance test" in p["items"][1]["problems"][0]
    assert p["items"][1]["entry"]["kind"] == "timing"


def test_prompt_has_files_numbered_and_data_warning(design, tmp_path):
    prep = P.prepare(design, name="blinkp")
    under = R.understand.analyse(prep["src"], prep["rtl"], prep["top"], prep["tb"], prep["constraints"], prep["docs"])
    suite = {"findings": [], "digest": "checks PASS", "ran": {}, "not_run": {}}
    pr = J.build_prompt(prep, under, suite, "intent text")
    assert "=== FILE rtl/blink.sv" in pr and "   8| endmodule" in pr and "intent text" in pr
    assert "build.yaml" not in pr.split("FACTS MADE BY CODE")[0]       # the file made by the tool is not shown as the design's
    assert "DATA" in J.SYSTEM
