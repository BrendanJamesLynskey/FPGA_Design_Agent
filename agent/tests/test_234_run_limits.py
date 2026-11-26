"""Brief 234: run-limit follow-ups, tested on the recorded records of the 224 arm and brief 213's A/B (no model, no tools).

1. a visit-limit stop names the most recent FAILED gate, with its stage and where it was routed (p4 run 1);
2. a route back gives the stages it passes again fresh visits; the failing stage and the target keep their counts (p4 run 1, brief 213's run, an endless loop);
3. the thinking tokens of a reply are recorded (usage.output_tokens_details, thinking blocks, visible characters);
4. the run turn cap scales with the design's size (p5 run 2 turn table).
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.graph.repair import last_failure, stop_diagnosis
from agent.graph.stages import MACHINE, RUN_LIMITS, run_turn_cap, visit_limit, visits_after_route
from agent.models.endpoints import assemble_stream

DATA = json.loads((Path(__file__).parent / "data" / "run_limits_234.json").read_text())
P4 = DATA["p4_r1_20261125-174731-a2e5"]
B213 = DATA["b213_run1_20261126-042626-10d5"]


def replay(stages: list[dict], rule: bool) -> tuple[dict, int | None]:
    """Walk the recorded stage entries; apply the visit limit (and, with ``rule``, the route-back reset). Returns (visits, the
    index of the first refused entry or None). The last recorded entry of a visit-limit run is the refused one."""
    visits: dict = {}
    for i, e in enumerate(stages):
        n = e["n"]
        visits[str(n)] = visits.get(str(n), 0) + 1
        if visits[str(n)] > visit_limit(n, RUN_LIMITS):
            return visits, i
        nxt = stages[i + 1]["n"] if i + 1 < len(stages) else None
        if rule and not e["passed"] and nxt is not None and nxt < n:
            visits = visits_after_route(visits, n, nxt)
    return visits, None


def test_recorded_p4_run1_was_refused_at_the_fifth_stage_3_entry_without_the_rule():
    visits, refused = replay(P4["stages"], rule=False)
    assert refused == len(P4["stages"]) - 1 and P4["stages"][refused]["n"] == 3 and visits["3"] == 5


def test_p4_run1_with_the_rule_is_not_refused_there():
    visits, refused = replay(P4["stages"], rule=True)
    assert refused is None
    assert visits["3"] == 1               # stages 2 and 3 were reset by the stage 4 -> 1 loop, then entered once each


def test_brief_213_stage_2_to_stage_1_loop_still_stops_on_stage_1():
    """Stage 2 failed lint/standards and went back to stage 1 until stage 1's limit: stage 1 is the target and keeps its count."""
    _, refused = replay(B213["stages"], rule=True)
    assert refused == len(B213["stages"]) - 1 and B213["stages"][refused]["n"] == 1


def test_route_back_resets_only_the_stages_between():
    v = {"0": 2, "1": 1, "2": 5, "3": 4, "4": 1}
    assert visits_after_route(v, 4, 1) == {"0": 2, "1": 1, "4": 1}          # 2 and 3 are passed again; 1 (target) and 4 (failed) keep theirs
    assert visits_after_route(v, 4, 4) == v and visits_after_route(v, 3, 4) == v      # a retry or a forward move changes nothing
    assert visits_after_route(v, 3, 2) == v                                  # nothing between 2 and 3


def test_an_endless_loop_still_ends_on_the_failing_stage():
    """Stage 4 always fails and routes to stage 1; stages 1 to 3 always pass. Stages 2 and 3 get fresh visits each time round, but the
    target (1) and the failing stage (4) keep theirs, so the loop ends after four stage-4 failures, on stage 1's limit."""
    visits: dict = {}
    entries, n = 0, 0
    while entries < 1000:
        visits[str(n)] = visits.get(str(n), 0) + 1
        entries += 1
        if visits[str(n)] > visit_limit(n, RUN_LIMITS):
            break
        if n == 4:
            visits = visits_after_route(visits, 4, 1)
            n = 1
        else:
            n += 1
    assert n == 1 and visits["1"] == visit_limit(1, RUN_LIMITS) + 1 and visits["4"] == 4 and entries == 18       # ends on the target's limit


def test_an_endless_loop_between_two_failing_stages_ends():
    """3 fails back to 2 and 2 passes, forever: stage 3 is the highest stage of the cycle and keeps its count."""
    visits: dict = {}
    n, entries = 2, 0
    while entries < 1000:
        visits[str(n)] = visits.get(str(n), 0) + 1
        entries += 1
        if visits[str(n)] > visit_limit(n, RUN_LIMITS):
            break
        if n == 3:
            visits = visits_after_route(visits, 3, 2)
            n = 2
        else:
            n = 3
    assert n == 3 and entries == 10


def _history(stages: list[dict], fails4: list[str] | None) -> list[dict]:
    out = []
    for e in stages[:-1]:                      # the last entry is the refused one: it was not gated
        h = {"n": e["n"], "stage": MACHINE[e["n"]].name, "passed": e["passed"], "visit": e["visit"]}
        if not e["passed"] and e["n"] == 4 and fails4:
            h["fails"] = fails4
        out.append(h)
    out.append({"n": 3, "stage": "constraints", "passed": False, "visit": 5, "gated": False})
    return out


def test_stop_diagnosis_reports_the_last_failed_gate_for_p4_run1():
    state = {"stage": 3, "fails": [], "sig": "", "history": _history(P4["stages"], P4["stage4_fails"])}
    why, detail = stop_diagnosis(3, 4, state)
    assert why.startswith("stage 3 visited more than 4 times; last failing gate: post_synth:post_synth_cdc_no_critical")
    assert "none recorded" not in why
    assert "the failure was in stage 4 synthesis (visit 1), routed to stage 1" in why and "refused before any gate ran" in why
    assert detail["last_failed_gate"]["stage"] == 4 and detail["last_failed_gate"]["routed_to"] == {"stage": 1}


def test_stop_diagnosis_uses_the_routing_record_of_the_history_entry():
    h = _history(P4["stages"], P4["stage4_fails"])
    h[[x["n"] for x in h].index(4)].update(cause="arch", routed_to={"stage": 1, "stage_name": "board-and-device-planning"})
    why, detail = stop_diagnosis(3, 4, {"stage": 3, "fails": [], "history": h})
    assert "routed to stage 1 board-and-device-planning" in why and detail["last_failed_gate"]["fails"][0].startswith("post_synth")


def test_a_failure_that_the_same_stage_later_passed_is_not_the_open_one():
    """p4 run 1: stage 2 failed on its 4th visit and passed on the 5th; the open failure is stage 4's."""
    lf = last_failure({"history": _history(P4["stages"], P4["stage4_fails"])})
    assert lf["stage"] == 4
    all_repaired = [{"n": 2, "passed": False, "visit": 1, "stage": "x"}, {"n": 2, "passed": True, "visit": 2, "stage": "x"}]
    assert last_failure({"history": all_repaired})["stage"] == 2          # nothing open: the latest failure


def test_an_old_record_without_fails_still_names_the_stage():
    state = {"stage": 3, "fails": [], "history": _history(P4["stages"], None)}
    why, _ = stop_diagnosis(3, 4, state)
    assert "stage 4 synthesis" in why and "none recorded" not in why


def test_a_stage_2_stop_keeps_its_own_gates():
    state = {"stage": 2, "sig": "rtl:standards", "owners": {"rtl": ["x"]}, "repeat": 2,
             "history": [{"n": 2, "stage": "rtl-design-creation", "passed": False, "visit": 6, "fails": ["design standards"]}]}
    why, _ = stop_diagnosis(2, 6, state)
    assert "last failing gate: design standards" in why and "the same failure on 3 consecutive visits" in why
    assert last_failure({"history": []}) is None


# ---- item 3: the thinking record ----------------------------------------------------------------------------------------------

def _sse(events: list[dict]) -> list[str]:
    return ["data: " + json.dumps(e) for e in events]


def test_stream_records_thinking_tokens_blocks_and_visible_characters():
    ev = [{"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
          {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
          {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "abc"}},
          {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "t1", "name": "write_file"}},
          {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"path\": \"a.sv\"}"}},
          {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
           "usage": {"output_tokens": 9000, "output_tokens_details": {"thinking_tokens": 8700}}},
          {"type": "message_stop"}]
    d = assemble_stream(_sse(ev))
    assert d["usage"]["output_tokens"] == 9000 and d["output_details"] == {"thinking_tokens": 8700}
    assert d["thinking"] == {"blocks": 1, "chars": 0} and d["visible_chars"] == len(json.dumps({"path": "a.sv"}))


def test_stream_without_a_thinking_count_leaves_it_unreported():
    ev = [{"type": "message_start", "message": {"usage": {"input_tokens": 1}}},
          {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
          {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hi"}},
          {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 3}}, {"type": "message_stop"}]
    d = assemble_stream(_sse(ev))
    assert d["output_details"] == {} and d["thinking"]["blocks"] == 0 and d["visible_chars"] == 2


# ---- item 4: the turn cap ------------------------------------------------------------------------------------------------------

def test_turn_cap_scales_with_blocks_between_the_old_floor_and_a_ceiling():
    assert run_turn_cap(0) == run_turn_cap(4) == run_turn_cap(5) == RUN_LIMITS["turns"] == 300      # the 224 arm's designs (4 to 6 blocks)
    assert run_turn_cap(8) == 480 and run_turn_cap(15) == run_turn_cap(40) == 900


def test_p5_run2_turn_table_sums_to_the_cap_and_the_loop_not_the_size_used_them():
    rows = DATA["p5_r2_20261125-233045-dfe1_turns"]
    assert sum(r["turns"] for r in rows) == 300
    by: dict = {}
    for r in rows:
        by[r["stage"]] = by.get(r["stage"], 0) + r["turns"]
    assert by["rtl-design-creation"] == 172 and by["constraints"] == 101
    # stage 3 ran four visits; three used their whole 30-turn budget and the fourth (11 turns) was cut by the run cap
    c = [r for r in rows if r["stage"] == "constraints"]
    assert [r["turns"] for r in c] == [30, 30, 30, 11] and c[-1]["ended"] == "run_budget"
    assert DATA["p4_r2_20261125-213244-466b_clean_pass"]["turns"] <= run_turn_cap(DATA["p4_r2_20261125-213244-466b_clean_pass"]["blocks"])
