"""The review benchmark's scorer (brief 84) on a synthetic truth: a missed finding must never count as found."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from benchmark.review import score as S

TRUTH = {"design": "rb99", "split": "heldout", "control": False, "benign": [{"file": "docs/a.md", "cats": ["documentation"]}],
         "issues": [
             {"id": "rb99-1", "class": "cdc", "severity": "critical", "categories": ["cdc"], "tool_codes": [],
              "regions": [{"file": "rtl/x.sv", "lines": [20, 22]}]},
             {"id": "rb99-2", "class": "test_gap", "severity": "major", "categories": ["verification"], "tool_codes": [], "keywords": ["full", "empty"],
              "regions": [{"file": "tb/tb_x.sv"}]},
             {"id": "rb99-3", "class": "scalability_limit", "severity": "major", "categories": ["scalability"], "tool_codes": ["WIDTH"],
              "regions": [{"file": "rtl/y.sv", "lines": [5, 5]}]}]}


def f(i, file, line, cat, sev="major", conf="high", rule="", end=None):
    return {"id": i, "severity": sev, "category": cat, "confidence": conf, "rule": rule,
            "location": {"file": file, "line": line, "end_line": end, "object": ""}}


def test_found_needs_category_and_place():
    r = {"findings": [f("a", "rtl/x.sv", 21, "cdc"), f("b", "rtl/x.sv", 21, "style"), f("c", "rtl/x.sv", 40, "cdc")]}
    s = S.score_review(r, TRUTH)
    assert s["found"] == ["rb99-1"]
    assert "rb99-2" in s["missed"]
    assert sorted(s["false_alarms"]) == ["b", "c"]


def test_line_tolerance_and_ranges():
    assert S.in_region(f("a", "rtl/x.sv", 24, "cdc"), TRUTH["issues"][0]["regions"][0])       # within LINE_TOL
    assert not S.in_region(f("a", "rtl/x.sv", 25, "cdc"), TRUTH["issues"][0]["regions"][0])
    assert S.in_region(f("a", "rtl/x.sv", 14, "cdc", end=19), TRUTH["issues"][0]["regions"][0])   # a range reaching the region
    assert not S.in_region(f("a", "rtl/x.sv", None, "cdc"), TRUTH["issues"][0]["regions"][0])     # no line: not a match for a line region
    assert S.in_region(f("a", "tb/tb_x.sv", None, "verification"), TRUTH["issues"][1]["regions"][0])  # whole-file region


def test_whole_file_issue_needs_its_words():
    a = f("a", "tb/tb_x.sv", 3, "verification")
    a.update(title="the bench has no checker", evidence="no compare", fix="add one")
    b = dict(a, id="b", title="the bench never fills the queue", evidence="never reaches full")
    assert S.score_review({"findings": [a]}, TRUTH)["found"] == []
    assert S.score_review({"findings": [b]}, TRUTH)["found"] == ["rb99-2"]


def test_same_file_other_place_is_not_found():
    r = {"findings": [f("a", "rtl/other.sv", 21, "cdc"), f("b", "tb/tb_x.sv", 3, "cdc")]}
    s = S.score_review(r, TRUTH)
    assert s["found"] == [] and len(s["false_alarms"]) == 2


def test_info_ignored_duplicates_benign_and_one_finding_one_issue():
    r = {"findings": [f("a", "rtl/x.sv", 21, "cdc", "info"),                     # info never counts as found
                      f("b", "rtl/x.sv", 21, "cdc"), f("c", "rtl/x.sv", 22, "cdc", "minor"),   # second finding on the same issue
                      f("d", "docs/a.md", 1, "documentation", "minor"),            # benign
                      f("e", "docs/a.md", 1, "documentation", "major")]}           # benign only up to minor
    s = S.score_review(r, TRUTH)
    assert s["found"] == ["rb99-1"] and s["duplicates"] == ["c"] and s["benign"] == ["d"] and s["false_alarms"] == ["e"]
    g = score = S.score_review({"findings": [f("g", "rtl/z.sv", 1, "style", "minor"), f("h", "rtl/z.sv", 1, "documentation", "minor"),
                                              f("i", "rtl/z.sv", 1, "documentation", "major"), f("j", "rtl/z.sv", 1, "reset", "minor")]}, TRUTH)
    assert g["advisory"] == ["g", "h"] and g["false_alarms"] == ["i", "j"]
    assert s["info_ignored"] == 1


def test_check_findings_count_only_through_tool_codes():
    a = f("a", "rtl/x.sv", 21, "cdc")
    a["source"] = "check:standards"                                   # right place, right category, but no listed tool code
    assert S.score_review({"findings": [a]}, TRUTH)["found"] == []
    b = f("b", "rtl/y.sv", 5, "scalability", rule="HDL-LINT-00 (WIDTH)")
    b["source"] = "check:lint"
    assert S.score_review({"findings": [b]}, TRUTH)["found"] == ["rb99-3"]
    c = dict(a, source="both")                                         # a reviewer finding that builds on a check finding
    assert S.score_review({"findings": [c]}, TRUTH)["found"] == ["rb99-1"]


def test_tool_code_credit_and_severity_choice():
    r = {"findings": [f("a", "rtl/y.sv", 5, "style", "minor", rule="HDL-LINT-00 (WIDTHEXPAND)")]}
    s = S.score_review(r, TRUTH)
    assert s["found"] == ["rb99-3"] and s["severity_exact"] == 0 and s["severity_within_one"] == 1
    r = {"findings": [f("a", "rtl/x.sv", 21, "cdc", "minor"), f("b", "rtl/x.sv", 21, "cdc", "critical")]}
    assert S.score_review(r, TRUTH)["severity_exact"] == 1                           # the closest severity wins the issue


def _write(tmp: Path, rid: str, arm: str, k: int, findings, ran=True):
    p = tmp / "reviews" / arm / rid / f"r{k}"
    p.mkdir(parents=True)
    (p / "review.json").write_text(json.dumps({"findings": findings, "judge": {"ran": ran, "prompt_version": "2", "call": {"usage": {"total_tokens": 10, "output_tokens": 2}, "wall_s": 1}}}))


def test_missing_runs_stay_in_the_denominator(tmp_path):
    (tmp_path / "bench" / "truth").mkdir(parents=True)
    (tmp_path / "bench" / "truth" / "rb99.yaml").write_text(yaml.safe_dump(TRUTH))
    _write(tmp_path, "rb99", "agent", 1, [f("a", "rtl/x.sv", 21, "cdc")])
    _write(tmp_path, "rb99", "agent", 2, [], ran=False)                             # an unusable reply: not run
    truth = S.load_truth(tmp_path / "bench")
    col = S.collect(truth, tmp_path / "reviews", "agent", "heldout", 3)
    assert len(col["not_run"]) == 2                                                # r2 unusable, r3 absent
    s = S.summarise(truth, col, 3, True)
    assert s["classes"]["cdc"]["issue_reviews"] == 3 and s["classes"]["cdc"]["found"] == 1
    assert s["overall"]["issue_reviews"] == 9                                      # 3 issues x 3 repeats, none dropped
    s2 = S.summarise(truth, col, 3, False)
    assert s2["overall"]["issue_reviews"] == 3


def test_empty_review_scores_zero_not_found():
    s = S.score_review({"findings": []}, TRUTH)
    assert s["found"] == [] and len(s["missed"]) == 3


def test_wilson_and_bootstrap_are_deterministic():
    assert S.wilson(0, 3)[0] == 0.0 and S.wilson(3, 3)[1] == 1.0
    d = {"a": (1.0, 1.0), "b": (0.0, 1.0), "c": (0.0, 1.0)}
    fn = lambda s: sum(x for x, _ in s) / len(s)
    assert S.boot(d, fn) == S.boot(d, fn)
