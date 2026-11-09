"""Brief 08a: escape-rate fields of a course run record (tools/run_record.py) and results/course/summarise.py."""
import importlib.util
import json
from pathlib import Path

from tools import run_record as rr

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("summarise", ROOT / "results" / "course" / "summarise.py")
summarise = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summarise)

GOOD = {"V0": "pass", "V1": "pass", "V2": "pass", "V3": "pass (3 seeds)", "stage_gates_post_route": "all pass"}


def rec(**kw):
    base = {"task": "cX", "run_id": "r1", "split": "development", "stop": {"stage": 9, "name": "configuration-and-debug"},
            "gates": dict(GOOD), "score": {"pass": True, "tests_passed": 3, "tests_total": 3},
            "stage_visits": {"clarify": 2, "rtl-design-creation": 1, "configuration-and-debug": 2}}
    base.update(kw)
    return base


def test_clean_pass():
    f = rr.derive(rec())
    assert f["internal_pass"] is True and f["hidden_pass"] is True and f["outcome"] == "pass"
    assert f["split"] == "dev" and f["escape_level"] is None


def test_caught_and_repaired_needs_a_gate_failure_before_the_pass():
    r = rec(stage_visits={"clarify": 2, "rtl-design-creation": 3})
    assert rr.derive(r)["outcome"] == "caught_and_repaired"
    r = rec(stage_visits={"clarify": 2, "board-and-device-planning": 2, "configuration-and-debug": 2})
    assert rr.derive(r)["outcome"] == "pass"           # re-entries that are not repairs do not count


def test_escape_is_internal_pass_with_hidden_fail():
    r = rec(score={"pass": False, "tests_passed": 1, "tests_total": 3}, failure={"class": "model error"})
    f = rr.derive(r)
    assert f["outcome"] == "escape" and f["hidden_tests_passed"] == 1 and f["hidden_tests_total"] == 3
    assert f["escape_level"] == "unclassified"


def test_known_c10_escape_is_spec_interpretation():
    r = rec(run_id="20261107-074755-3941", score={"pass": False, "tests_passed": 1, "tests_total": 3})
    assert rr.derive(r)["escape_level"] == "spec-interpretation"


def test_internal_stop_with_hidden_pass_and_with_hidden_fail():
    stop = {"stage": 2, "name": "rtl-design-creation"}
    f = rr.derive(rec(stop=stop))
    assert f["outcome"] == "internal_stop_hidden_pass" and f["internal_pass"].startswith("stopped at stage 2")
    f = rr.derive(rec(stop=stop, score={"pass": False, "tests": {"a": False, "b": False}}))
    assert f["outcome"] == "fail" and f["hidden_tests_total"] == 2 and f["hidden_tests_passed"] == 0


def test_failed_gate_level_is_named():
    g = dict(GOOD, V3="fail (coverage)")
    assert rr.derive(rec(gates=g, stop={"stage": 2, "name": "x"}))["internal_pass"].startswith("stopped")
    assert rr.internal_pass(rec(gates=g, stop={})) == "V3 failed"


def test_unknown_when_no_evidence():
    f = rr.derive({"task": "t", "run_id": "x"})
    assert f["outcome"] == "unknown" and f["hidden_pass"] == "unknown" and f["tool_runs"] == "unknown"
    assert f["agent_commit"] == "unknown" and f["tokens"] == "unknown"


def test_agent_commit_is_parsed():
    assert rr.agent_commit_of({"harness_commit": "main 73c135c (FPGA_Design_Agent), Knowledge main 62f0425"}) == "73c135c"
    assert rr.agent_commit_of({"harness_commit": "f4-07a2-fix4 (PR #52)"}) == "unknown"


def test_run_stats_from_logs(tmp_path):
    d = tmp_path / "r1"
    d.mkdir()
    lines = [{"kind": "tool", "tool": t} for t in ("simulate", "simulate", "build", "mutate", "read_file")]
    (d / "trace.jsonl").write_text("\n".join(json.dumps(x) for x in lines + [{"kind": "model"}]))
    (d / "role_usage.jsonl").write_text("\n".join(json.dumps(x) for x in (
        {"tokens": 100, "wall_s": 1800, "plan_cost_estimate_usd": 0.5},
        {"tokens": 50, "wall_s": 1800, "plan_cost_estimate_usd": 0.25})))
    s = rr.run_stats(d)
    assert s["tool_runs"]["simulate"] == 2 and s["tool_runs"]["simulate_mutate_build"] == 4
    assert s["tokens"] == 150 and s["plan_cost_estimate_usd"] == 0.75 and s["agent_call_wall_h"] == 1.0


def test_backfill_writes_fields_and_is_idempotent(tmp_path):
    task = tmp_path / "course" / "cX"
    task.mkdir(parents=True)
    p = task / "run_1.json"
    p.write_text(json.dumps(rec()))
    rr.backfill(tmp_path / "course", [tmp_path / "none"])
    first = p.read_text()
    assert json.loads(first)["outcome"] == "pass"
    rr.backfill(tmp_path / "course", [tmp_path / "none"])
    assert p.read_text() == first


def test_summary_counts_and_escape_levels():
    runs = [dict(task="a", split="dev", hidden_pass=True, outcome="pass"),
            dict(task="a", split="dev", hidden_pass=False, outcome="escape", escape_level="V2"),
            dict(task="a", split="dev", hidden_pass="unknown", outcome="unknown"),
            dict(task="b", split="dev", hidden_pass=True, outcome="caught_and_repaired", tokens=10,
                 plan_cost_estimate_usd=2.0, wall_h_total=1.0, tool_runs={"simulate_mutate_build": 4})]
    text = summarise.summarise(runs)
    assert "1 of 2" in text and "1 of 1" in text
    assert "escapes by level: V2=1" in text
    assert "mean plan-cost estimate USD 2.00 (1 runs" in text


def test_committed_records_all_carry_the_new_fields():
    for path in (ROOT / "results" / "course").glob("*/run_*.json"):
        d = json.loads(path.read_text())
        for k in ("internal_pass", "hidden_pass", "outcome", "escape_level", "tool_runs", "split", "agent_commit"):
            assert k in d, f"{path}: {k}"
        assert d["outcome"] in rr.OUTCOMES and d["split"] in ("dev", "held-out", "unknown")


def test_hardware_pause_without_a_board_is_pending_not_failed():
    """07a2 fix 7: batch 2 wrote 'pass' for the post-route summary and a stage-9 pause; that must not read as a failure."""
    f = rr.derive(rec(gates={**GOOD, "stage_gates_post_route": "pass", "SIGNOFF": "open", "V-HW": "fail (no board)"}))
    assert f["internal_pass"] is True and f["outcome"] == "pass"
    f = rr.derive(rec(gates={**GOOD, "stage_gates_post_route": "pending"}))
    assert f["internal_pass"] is True
    f = rr.derive(rec(gates={**GOOD, "stage_gates_post_route": "fail (WNS -0.2)"}))
    assert f["internal_pass"] == "post-route gates failed"


def test_spec_level_gap_with_a_passing_internal_verdict_is_a_spec_interpretation_escape():
    r = rec(score={"pass": False, "tests_passed": 0, "tests_total": 0},
            failure={"class": "spec/task gap (hidden bench needs a port the public spec does not name)"})
    f = rr.derive(r)
    assert f["outcome"] == "escape" and f["escape_level"] == "spec-interpretation"
