"""Escape-rate fields for a course run record (brief 08a).

A run record is results/course/<task>/run_N.json.  This module derives the fields that make the escape rate
measurable and writes them next to the fields the executor recorded by hand:

  internal_pass        true when V0-V3 and every post-route gate passed; else "stopped at stage N (name)";
                       "unknown" when the record has no gate evidence
  hidden_pass          the hidden bench verdict (true / false / "unknown")
  hidden_tests_passed, hidden_tests_total
  outcome              pass | escape | caught_and_repaired | internal_stop_hidden_pass | fail | unknown
  escape_level         for an escape only: V0 | V1 | V2 | V3 | post-route | spec-interpretation | unclassified
  tool_runs            how many times the agent called simulate / mutate / formal / build (+ lint, gates)
  tokens, plan_cost_estimate_usd, wall_h_total   from the run logs when they exist, else "unknown"
  split                dev | held-out
  agent_commit         the agent commit the run used, else "unknown"

Outcome rules (internal = the agent's own gates, hidden = the held-out-style bench run by run_task.py):
  internal pass, hidden pass, no gate failure before the pass   -> pass
  internal pass, hidden pass, an internal gate failed and was repaired -> caught_and_repaired
  internal pass, hidden fail                                     -> escape
  internal stop, hidden pass                                     -> internal_stop_hidden_pass
  internal stop, hidden fail                                     -> fail

"Gate failed at least once" is read from the repair loop and the stage visit counts: a stage-2 repair loop with more
than one visit, or any gated stage (not clarify, board planning or configuration-and-debug, which are re-entered for
other reasons) visited more than once.

CLI:  python tools/run_record.py backfill results/course [--runs-root DIR ...]   (rewrites the run_*.json files)
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

ESCAPE_LEVELS = ("V0", "V1", "V2", "V3", "post-route", "spec-interpretation", "unclassified")
OUTCOMES = ("pass", "escape", "caught_and_repaired", "internal_stop_hidden_pass", "fail", "unknown")
FLOW_TOOLS = ("simulate", "mutate", "formal", "build", "lint", "gates")
UNKNOWN = "unknown"
# Stages that are re-entered without a gate failure (second clarify pass, planning after approval, hardware approval).
NOT_REPAIR_STAGES = ("clarify", "board-and-device-planning", "configuration-and-debug")

# Level a known escape should have been caught at, with the evidence.  Everything else is derived from the record.
KNOWN_ESCAPE_LEVELS = {
    "20261107-074755-3941": ("spec-interpretation", "c10 run 1: the clarify step lost the oracle's packing answer, the agent's tests encoded the wrong packing"),
}


#: Values of the post-route gate summary that count as passed ("pass" is what the batch 2 records say). A hardware-pause
#: run has no board, so its SIGNOFF and V-HW are "pending", never failed (07a2 fix 7).
POST_ROUTE_OK = ("all pass", "pass", "pending")
HW_GATES = ("SIGNOFF", "V-HW")


def _hw_pause(rec: dict) -> bool:
    """True when the run ended at the stage-9 hardware pause (approval awaited, no board attached)."""
    stop = rec.get("stop") or {}
    return stop.get("stage") == 9


def _is_stopped(rec: dict) -> str | None:
    stop = rec.get("stop") or {}
    stage = stop.get("stage")
    if stage is None:
        return None
    if stage == 9:                       # configuration-and-debug: awaiting hardware approval, everything before passed
        return None
    return f"stopped at stage {stage} ({stop.get('name', UNKNOWN)})"


def internal_pass(rec: dict):
    stopped = _is_stopped(rec)
    if stopped:
        return stopped
    if not rec.get("stop") and not rec.get("gates"):
        return UNKNOWN
    gates = rec.get("gates") or {}
    for lvl in ("V0", "V1", "V2", "V3"):
        v = str(gates.get(lvl, "")).lower()
        if gates and v and not v.startswith("pass"):
            return f"{lvl} failed"
    post = str(gates.get("stage_gates_post_route", "")).lower()
    if post and not post.startswith(POST_ROUTE_OK):
        return "post-route gates failed"
    for k, v in gates.items():                       # 07a2 fix 7: with no board the hardware gates stay open
        if k.upper().replace("_", "-") in HW_GATES and not str(v).lower().startswith(("pass", "all pass", "pending", "open")):
            if not _hw_pause(rec):
                return f"{k} failed"
    return True


def hidden_result(rec: dict) -> tuple:
    """(hidden_pass, passed, total) from the score block; counts come from the per-test map when missing."""
    s = rec.get("score") or {}
    passed, total = s.get("tests_passed"), s.get("tests_total")
    tests = s.get("tests")
    if (passed is None or total is None) and isinstance(tests, dict) and tests:
        total = len(tests)
        passed = sum(1 for v in tests.values() if v is True)
    ok = s.get("pass")
    if ok is None and passed is not None and total:
        ok = passed == total
    if ok is None:
        return UNKNOWN, UNKNOWN, UNKNOWN
    return bool(ok), UNKNOWN if passed is None else passed, UNKNOWN if total is None else total


def gate_failed_before_pass(rec: dict):
    """True / False, or "unknown" when the record has neither stage visits nor a repair loop."""
    loop = (rec.get("stage2_repair_loop") or {}).get("visits")
    visits = rec.get("stage_visits")
    if loop is None and not visits:
        return UNKNOWN
    if loop and loop > 1:
        return True
    for stage, n in (visits or {}).items():
        if stage not in NOT_REPAIR_STAGES and n > 1:
            return True
    return False


def outcome_of(internal, hidden, repaired) -> str:
    if hidden == UNKNOWN or internal == UNKNOWN:
        return "unknown"
    if internal is True:
        if not hidden:
            return "escape"
        return "caught_and_repaired" if repaired is True else "pass"
    return "internal_stop_hidden_pass" if hidden else "fail"


def escape_level_of(rec: dict, outcome: str):
    """Which check level should have caught an escape.  None for any other outcome."""
    if outcome != "escape":
        return None
    explicit = (rec.get("failure") or {}).get("escape_level")
    if explicit in ESCAPE_LEVELS:
        return explicit
    known = KNOWN_ESCAPE_LEVELS.get(rec.get("run_id", ""))
    if known:
        return known[0]
    cls = str((rec.get("failure") or {}).get("class", "")).lower()
    if "spec ambiguity" in cls or "spec/task gap" in cls or "spec gap" in cls or "clarify-stage" in cls or "spec-interpretation" in cls:
        return "spec-interpretation"
    return "unclassified"


def agent_commit_of(rec: dict) -> str:
    raw = str(rec.get("harness_commit", ""))
    m = re.search(r"\b[0-9a-f]{7,40}\b", raw)
    return m.group(0) if m else UNKNOWN


def split_of(rec: dict) -> str:
    s = str(rec.get("split", "")).lower()
    if s.startswith("dev"):
        return "dev"
    if s.startswith("held"):
        return "held-out"
    return UNKNOWN


def run_stats(run_dir: Path | None) -> dict:
    """tool_runs, tokens, plan cost and wall from a run directory's logs; "unknown" for what is not there."""
    out = {"tool_runs": UNKNOWN, "tokens": UNKNOWN, "plan_cost_estimate_usd": UNKNOWN}
    if run_dir is None or not run_dir.is_dir():
        return out
    trace = run_dir / "trace.jsonl"
    if trace.is_file():
        c = collections.Counter()
        for line in trace.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("kind") == "tool":
                c[d.get("tool")] += 1
        out["tool_runs"] = {t: c.get(t, 0) for t in FLOW_TOOLS}
        out["tool_runs"]["simulate_mutate_build"] = c.get("simulate", 0) + c.get("mutate", 0) + c.get("build", 0)
    usage = run_dir / "role_usage.jsonl"
    if usage.is_file():
        tok, cost, wall, n = 0, 0.0, 0.0, 0
        for line in usage.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            n += 1
            tok += d.get("tokens") or 0
            cost += d.get("plan_cost_estimate_usd") or 0.0
            wall += d.get("wall_s") or 0.0
        if n:
            out["tokens"] = tok
            out["plan_cost_estimate_usd"] = round(cost, 4)
            out["agent_call_wall_h"] = round(wall / 3600, 2)
    return out


def find_run_dir(run_id: str, roots) -> Path | None:
    for root in roots:
        p = Path(root) / run_id
        if p.is_dir():
            return p
    return None


def derive(rec: dict, run_dir: Path | None = None) -> dict:
    """The new fields for one record.  Values the executor recorded by hand are kept, not overwritten."""
    internal = internal_pass(rec)
    hidden, passed, total = hidden_result(rec)
    repaired = gate_failed_before_pass(rec)
    outcome = outcome_of(internal, hidden, repaired)
    fields = {
        "split": split_of(rec),
        "agent_commit": agent_commit_of(rec),
        "internal_pass": internal,
        "hidden_pass": hidden,
        "hidden_tests_passed": passed,
        "hidden_tests_total": total,
        "internal_gate_failed_before_pass": repaired,
        "outcome": outcome,
        "escape_level": escape_level_of(rec, outcome),
    }
    stats = run_stats(run_dir)
    fields["tool_runs"] = stats["tool_runs"]
    fields["tokens"] = stats["tokens"]
    old_cost = rec.get("claude_code_plan_cost_estimate_usd")
    fields["plan_cost_estimate_usd"] = stats["plan_cost_estimate_usd"] if stats["plan_cost_estimate_usd"] != UNKNOWN else (
        old_cost if old_cost is not None else UNKNOWN)
    if "wall_h_total" not in rec and "wall_s" in rec:
        fields["wall_h_total"] = round(rec["wall_s"] / 3600, 2)
    elif "wall_h_total" not in rec:
        fields["wall_h_total"] = UNKNOWN
    return fields


# Fields read from the run logs: kept when the record already has a real value; the others are re-derived each time.
FILL_IF_UNKNOWN = ("tool_runs", "tokens", "plan_cost_estimate_usd", "wall_h_total")


def backfill(course_dir: Path, roots) -> list:
    done = []
    for path in sorted(Path(course_dir).glob("*/run_*.json")):
        rec = json.loads(path.read_text())
        run_dir = find_run_dir(rec.get("run_id", ""), roots)
        for k, v in derive(rec, run_dir).items():
            if k in FILL_IF_UNKNOWN and rec.get(k) not in (None, UNKNOWN):
                continue            # a value taken from a log or written by hand stays
            rec[k] = v
        path.write_text(json.dumps(rec, indent=1) + "\n")
        done.append((str(path), rec["outcome"], str(run_dir) if run_dir else None))
    return done


def default_roots(repo: Path) -> list:
    roots = [repo / "runs"]
    roots += [Path(p) for p in sorted(glob.glob(str(repo.parent / "_wt_fda_*" / "runs")))]
    roots += [repo.parent / "FPGA_Design_Agent" / "runs"]
    return roots


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("course_dir")
    b.add_argument("--runs-root", action="append", default=None)
    a = ap.parse_args(argv)
    repo = Path(__file__).resolve().parent.parent
    roots = a.runs_root or default_roots(repo)
    for row in backfill(Path(a.course_dir), roots):
        print(*row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
