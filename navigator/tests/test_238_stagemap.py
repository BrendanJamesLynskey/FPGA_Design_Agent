"""Brief 238: the stage map. The event-to-state mapping, on recorded run folders (three 213 runs, trimmed to the files the map reads, in fixtures_238/) and on
a synthetic run that has the trace and audit log those folders lack. Nothing is started, nothing is written to a run folder, no model is called."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from agent.graph.stages import MACHINE
from navigator import stagemap as SM
from navigator.tests.test_103_navigator import make_app
from navigator.tests.test_182_navigator_s3 import STD, Live, ev, fake_run, jl

FIX = Path(__file__).parent / "fixtures_238"
NOW = 1_800_000_000.0
PASS_RUN, ROUTE_RUN, LIMIT_RUN = "10_p2_bram_rom_k3_control", "10_p2_bram_rom_k3_control", "2_p1_clkmeter_k3_treatment"


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode() + p.read_bytes())
    return h.hexdigest()


def fixture_runs(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    for r in FIX.iterdir():
        shutil.copytree(r, runs / r.name)
    return runs


def kinds(m):
    return [f["kind"] for f in m["frames"]]


# --- the stages come from the stage machine ---------------------------------------------------------------------------------------------

def test_the_stages_limits_and_route_backs_are_the_stage_machines_own():
    m = SM.machine()
    assert [s["name"] for s in m] == [s.name for s in MACHINE] and [s["loops_to"] for s in m] == [list(s.loops_to) for s in MACHINE]
    assert m[2]["limit"] == 6 and m[3]["limit"] == 4                                  # stage 2 has its own, larger visit limit
    assert SM.machine({"visits_per_stage": 2})[3]["limit"] == 2                       # a run's own limit is used


# --- a run that passes (213 run 10, stopped after stage 2; it also routed back once) ---------------------------------------------------

def test_a_passing_run_ends_with_a_pass_and_every_stage_it_reached_shows_pass(tmp_path):
    runs = fixture_runs(tmp_path)
    m = SM.stage_map(runs, PASS_RUN, now=NOW)
    assert m["status"] == "finished" and m["source"]["mode"] == "role_usage" and m["can_replay"]
    last = m["frames"][-1]
    assert last["kind"] == "end" and last["ok"] is True and last["stop"] == "done" and last["line"] == "Run ended: done"
    assert [x[1] for x in last["st"][:3]] == ["pass", "pass", "pass"] and [x[1] for x in last["st"][3:]] == [None] * 7        # stages not reached stay empty
    assert [x[0] for x in last["st"][:3]] == [2, 4, 3]                                                                  # the run's own visit numbers
    roles = [f["name"] for f in m["frames"] if f["kind"] == "role"]
    assert roles[:2] == ["Clarifier", "Clarifier"] and {"Modeller", "Verifier", "Designer"} <= set(roles)                # the site's role names


# --- a route back (the same run: stage 2 went back to stage 1) --------------------------------------------------------------------------

def test_a_route_back_is_an_enter_that_goes_to_an_earlier_stage_and_says_where_from(tmp_path):
    m = SM.stage_map(fixture_runs(tmp_path), ROUTE_RUN, now=NOW)
    back = [f for f in m["frames"] if f.get("back")]
    assert len(back) == 1 and (back[0]["from_n"], back[0]["n"], back[0]["visit"]) == (2, 1, 3)
    assert back[0]["route"] == "failing gate not recorded: back to stage 1"            # the folder records no failing gate, so none is named
    assert "route back from stage 2" in back[0]["line"]
    retry = [f for f in m["frames"] if f.get("retry")]
    assert retry and all(f["from_n"] == f["n"] for f in retry)


# --- a run stopped on a visit limit (213 run 2, lint failed on six visits of stage 2) --------------------------------------------------

def test_a_run_stopped_on_a_visit_limit_shows_the_limit_the_failing_gate_and_the_stop_reason(tmp_path):
    m = SM.stage_map(fixture_runs(tmp_path), LIMIT_RUN, now=NOW)
    last = m["frames"][-1]
    assert last["kind"] == "end" and last["ok"] is False and "visited more than 6 times" in last["stop"] and "lint" in last["stop"]
    assert last["st"][2] == [6, "fail", 0, 6]                                          # visit 6 (of 6), failed, six failing gate checks, none passed
    enters = [f for f in m["frames"] if f["kind"] == "enter" and f["n"] == 2]
    assert [f["visit"] for f in enters] == [1, 2, 3, 4, 5, 6] and all(f["limit"] == 6 for f in enters)
    assert all(f["route"] == "lint: again" for f in enters[1:])                         # the gate named by the ledger, not invented
    assert sum(1 for f in m["frames"] if f["kind"] == "gate") == 6 and all(not f["ok"] and f["flash"] == "fail" for f in m["frames"] if f["kind"] == "gate")
    assert not any(f.get("back") for f in m["frames"])                                  # it never left stage 2 for an earlier one


def test_the_leave_of_each_visit_is_read_from_where_the_run_went_next_and_says_so(tmp_path):
    m = SM.stage_map(fixture_runs(tmp_path), LIMIT_RUN, now=NOW)
    leaves = [f for f in m["frames"] if f["kind"] == "leave"]
    assert all(f["inferred"] for f in leaves) and "read from where the run went next" in leaves[0]["line"]
    assert [f["ok"] for f in leaves[:3]] == [False, True, False]                        # clarify 1 ran again; clarify 2 moved on; planning 1 ran again


# --- the trace mode: a synthetic run with the trace and audit log ------------------------------------------------------------------------

def gates_row(t, stage, verdict, failing=()):
    lines = [f"gates: d1 (base): {verdict} wns=0.1", "  rtl: " + ("pass" if verdict == "PASS" else "FAIL")] + [f"    FAIL {g}" for g in failing]
    return {"t": t, "tool": "gates", "stage": stage, "ok": verdict == "PASS", "result_summary": "\n".join(lines)}


def trace_run(tmp_path, extra=(), finished=None, pending=None, age=0):
    ev_ = [ev("stage_start", NOW - 900, "clarify", n=0, visit=1), ev("stage_end", NOW - 800, "clarify", n=0, visit=1, passed=True),
           ev("stage_start", NOW - 790, "board-and-device-planning", n=1, visit=1), ev("stage_end", NOW - 700, "board-and-device-planning", n=1, visit=1, passed=True),
           ev("stage_start", NOW - 690, "rtl-design-creation", n=2, visit=1), ev("stage_end", NOW - 500, "rtl-design-creation", n=2, visit=1, passed=False),
           ev("stage_start", NOW - 490, "board-and-device-planning", n=1, visit=2), ev("stage_end", NOW - 450, "board-and-device-planning", n=1, visit=2, passed=True),
           ev("stage_start", NOW - 440, "rtl-design-creation", n=2, visit=2), *extra]
    rd = fake_run(tmp_path / "runs", events=[], finished=False)
    (rd / "trace.jsonl").write_text("")
    jl(rd / "trace.jsonl", ev_)
    (rd / "role_usage.jsonl").write_text("")
    jl(rd / "role_usage.jsonl", [{"stage": "clarify", "visit": 1, "role": "clarify"}, {"stage": "rtl-design-creation", "visit": 1, "role": "model"}, {"stage": "rtl-design-creation", "visit": 1, "role": "rtl", "repair": False, "turns": 9},
                                 {"stage": "rtl-design-creation", "visit": 2, "role": "rtl", "repair": True, "turns": 3}])
    jl(rd / "t1" / "build" / "audit.jsonl", [gates_row(NOW - 520, "rtl-design-creation", "FAIL", ["lint"]), {"t": NOW - 510, "tool": "write_file", "stage": "rtl-design-creation"}])
    if finished:
        (rd / "summary.json").write_text(json.dumps({"stop": finished}))
    if pending:
        (rd / "pending.json").write_text(json.dumps({"paused": pending}))
    for f in rd.rglob("*"):
        if f.is_file():
            os.utime(f, (NOW - age, NOW - age))
    return rd


def test_the_trace_mode_orders_events_by_time_places_roles_after_their_entry_and_names_the_failing_gate_of_a_route_back(tmp_path):
    rd = trace_run(tmp_path)
    m = SM.stage_map(tmp_path / "runs", rd.name, now=NOW)
    assert m["source"]["mode"] == "trace" and m["status"] == "active" and not m["can_replay"]
    k = kinds(m)
    i = k.index("enter", 4)                                                              # the entry of stage 2, visit 1
    assert k[i:i + 5] == ["enter", "role", "role", "gate", "leave"]                      # roles right after the entry; the gate (t - 520) before the leave (t - 500)
    back = [f for f in m["frames"] if f.get("back")]
    assert len(back) == 1 and back[0]["route"] == "lint: back to stage 1" and (back[0]["from_n"], back[0]["n"]) == (2, 1)
    last = m["frames"][-1]
    assert last["kind"] == "role" and last["cur"] == 2 and last["open"] is True and last["role"] == "rtl" and last["st"][2][0] == 2 and last["st"][2][1] == "fail"
    assert last["st"][2][3] == 1 and last["st"][2][2] == 0                               # one failing gate call so far at stage 2, none passing
    assert not any(f["kind"] == "gate" and f["n"] != 2 for f in m["frames"])


def test_tool_steps_waits_and_resumes_are_mapped(tmp_path):
    extra = [ev("build_step", NOW - 300, "rtl-design-creation", state="start", until="route", variant="base"),
             ev("slot_wait", NOW - 100, "rtl-design-creation", waited_s=45, reason="another Vivado holds the PC's slot")]
    m = SM.stage_map(tmp_path / "runs", trace_run(tmp_path, extra).name, now=NOW)
    last = m["frames"][-1]
    assert last["kind"] == "wait" and last["wait"]["kind"] == "slot" and "waiting for a Vivado slot" in last["wait"]["why"] and last["step"]["what"] == "Vivado route build"
    m2 = SM.stage_map(tmp_path / "b" / "runs", trace_run(tmp_path / "b", extra + [ev("build_step", NOW - 50, "rtl-design-creation", state="end", until="route", variant="base", ok=True, seconds=250)]).name, now=NOW)
    assert m2["frames"][-1]["wait"] is None and m2["frames"][-1]["step"] is None                      # the build ended: no spinner, no wait
    m3 = SM.stage_map(tmp_path / "c" / "runs", trace_run(tmp_path / "c", extra).name, now=NOW + 400)
    assert m3["frames"][-1]["wait"] is None                                                           # a slot wait older than 5 min is not shown (cannot be told from a running build)
    perm = [ev("permission_stop", NOW - 40, "rtl-design-creation", n=2, needs=["run_vivado"], why="x"), ev("permission_granted", NOW - 20, "rtl-design-creation", n=2, actions=["run_vivado"], by="owner")]
    m4 = SM.stage_map(tmp_path / "d" / "runs", trace_run(tmp_path / "d", perm).name, now=NOW)
    assert [f["kind"] for f in m4["frames"][-2:]] == ["wait", "resume"] and m4["frames"][-2]["wait"]["kind"] == "permission" and m4["frames"][-1]["wait"] is None


def test_a_run_waiting_on_you_shows_a_still_waiting_state_from_pending_json_with_its_reason(tmp_path):
    rd = trace_run(tmp_path, pending={"kind": "question", "stage": 2, "stage_name": "rtl-design-creation", "question": "SECRET QUESTION TEXT"})
    m = SM.stage_map(tmp_path / "runs", rd.name, now=NOW)
    last = m["frames"][-1]
    assert last["kind"] == "wait" and last["wait"]["kind"] == "question" and last["wait"]["why"] == "waiting for your answer to a question" and "SECRET" not in json.dumps(m)
    rd2 = trace_run(tmp_path / "p", pending={"kind": "permission", "stage": 2, "needs": ["board", "registers"]})
    assert "board, registers" in SM.stage_map(tmp_path / "p" / "runs", rd2.name, now=NOW)["frames"][-1]["wait"]["why"]


def test_an_idle_run_is_idle_with_its_age_and_a_finished_run_freezes_with_its_stop_reason(tmp_path):
    idle = SM.stage_map(tmp_path / "runs", trace_run(tmp_path, age=1200).name, now=NOW)
    assert idle["status"] == "idle" and idle["age_s"] == 1200 and idle["active_s"] == 180 and not idle["can_replay"]
    done = SM.stage_map(tmp_path / "x" / "runs", trace_run(tmp_path / "x", finished="stage 2 visited more than 6 times; last failing gate: lint").name, now=NOW)
    assert done["status"] == "finished" and done["frames"][-1]["kind"] == "end" and done["frames"][-1]["ok"] is False and done["can_replay"]
    assert done["frames"][-1]["open"] is False and done["frames"][-1]["wait"] is None


def test_a_design_request_rewind_is_labelled_as_the_request_and_not_as_a_gate(tmp_path):
    extra = [ev("stage_end", NOW - 430, "rtl-design-creation", n=2, visit=2, passed=True), ev("request", NOW - 429, "rtl-design-creation", request="r1", what="design", outcome="rewind", to_stage=1),
             ev("stage_start", NOW - 420, "board-and-device-planning", n=1, visit=3)]
    m = SM.stage_map(tmp_path / "runs", trace_run(tmp_path, extra).name, now=NOW)
    last = m["frames"][-1]
    assert last["back"] and last["route"] == "your request: back to stage 1"


def test_a_stage_added_to_the_machine_appears_in_the_map_by_itself(tmp_path, monkeypatch):
    import agent.graph.stages as ST
    from dataclasses import replace
    extra = replace(ST.MACHINE[-1], n=10, name="a-new-stage")
    monkeypatch.setattr(ST, "MACHINE", (*ST.MACHINE, extra))
    assert SM.machine()[-1]["name"] == "a-new-stage"


# --- read-only, redacted, served ----------------------------------------------------------------------------------------------------------

def test_the_map_writes_nothing_and_leaks_no_secret(tmp_path):
    rd = trace_run(tmp_path, [ev("slot_wait", NOW - 5, "rtl-design-creation", waited_s=1, reason="sk-or-v1-PLANTED0123456789abcdef")])
    before = tree_hash(rd)
    m = SM.stage_map(tmp_path / "runs", rd.name, now=NOW)
    assert tree_hash(rd) == before and "PLANTED" not in json.dumps(m)


def test_the_api_serves_the_map_only_for_a_listed_run_and_the_page_script_is_served_with_the_strict_policy(tmp_path):
    runs = fixture_runs(tmp_path)
    app, _ = make_app(tmp_path, runs=runs)
    s = Live(app)
    st, _, b = s.get(f"/api/live/map?id={PASS_RUN}")
    j = json.loads(b)
    assert st == 200 and j["source"]["mode"] == "role_usage" and j["frames"][-1]["kind"] == "end" and j["can_replay"]
    assert "line" in j["frames"][0] and all("text" not in f for f in j["frames"])               # key names the redaction would drop are not used
    assert s.get("/api/live/map?id=../x")[0] == 404 and s.get("/api/live/map?id=nope")[0] == 404
    assert s.req("GET", f"/api/live/map?id={PASS_RUN}")[0] == 401                                  # no token
    st, hd, body = s.get("/stagemap.js")
    assert st == 200 and b"FdaStageMap" in body and hd["Content-Security-Policy"].startswith("default-src 'none'; script-src 'self'")
    assert b"/stagemap.js" in s.get("/")[2]
