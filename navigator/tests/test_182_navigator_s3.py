"""Brief 182, navigator stage 3: the plain-words status, the live console, questions about a run, mid-run requests, and the guards on the new routes.

No model is called (a fake stands in for the review purpose), no process is started, nothing outside the tmp directory is read or written."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from agent.graph import requests as rq
from navigator import ask as NA
from navigator import console as NC
from navigator import redact
from navigator import summary as NS
from navigator.tests.test_103_navigator import TOKEN, make_app
from navigator.tests.test_103s2_navigator import Live

ROOT = Path(__file__).resolve().parents[2]
KEY = "sk-or-v1-PLANTED0123456789abcdef"
NOW = 1_800_000_000.0


def jl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def ev(name: str, t: float, stage: str | None = None, **f) -> dict:
    return {"v": 1, "kind": "event", "event": name, "stage": stage, "t": t, **f}


def fake_run(runs: Path, rid: str = "20261122-000000-aaaa", hidden: str | None = None, events: list[dict] | None = None, finished: bool = False) -> Path:
    rd = runs / rid
    rd.mkdir(parents=True)
    (rd / "config.json").write_text(json.dumps({"name": "t1", "run_limits": {"usd": 3.0}, "harness": "claude_code", "hidden_spec": hidden or "None"}))
    jl(rd / "role_usage.jsonl", [{"stage": "rtl-design-creation", "visit": 1, "role": "rtl", "tokens": 1000, "plan_cost_estimate_usd": 0.12}])
    jl(rd / "trace.jsonl", events or [])
    (rd / "snapshots.json").write_text(json.dumps([{"n": 0, "stage": "clarify"}, {"n": 1, "stage": "board-and-device-planning"}]))
    (rd / "t1" / "build").mkdir(parents=True)
    (rd / "t1" / "build" / "audit.jsonl").write_text("")
    if finished:
        (rd / "summary.json").write_text(json.dumps({"stop": "done"}))
    import os
    for f in rd.rglob("*"):                                   # the run counts as working: files written "now"
        os.utime(f, (NOW, NOW))
    return rd


STD = [ev("stage_start", NOW - 900, "clarify", n=0, visit=1), ev("stage_end", NOW - 700, "clarify", n=0, visit=1, passed=True),
       ev("stage_start", NOW - 690, "board-and-device-planning", n=1, visit=1), ev("stage_end", NOW - 400, "board-and-device-planning", n=1, visit=1, passed=True),
       ev("stage_start", NOW - 390, "rtl-design-creation", n=2, visit=1),
       ev("console", NOW - 150, "rtl-design-creation", step="004_rtl_rtl-design-creation", label="model: rtl", stream="claude_stream", source="console/004_rtl_rtl-design-creation.log", started=NOW - 150)]


# --- the plain-words status ----------------------------------------------------------------------------------------------------------

def test_the_status_is_plain_words_from_the_records_and_makes_no_model_call(tmp_path, monkeypatch):
    import agent.models.resolver as RS
    monkeypatch.setattr(RS, "resolver_for", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the status must not call a model")))
    fake_run(tmp_path / "runs", events=STD)
    s = NS.summarise(tmp_path / "runs", "20261122-000000-aaaa", now=NOW)
    assert s["done"].startswith("2 of 10 stages passed") and "0 clarify" in s["done"]
    assert "stage 2 (rtl-design-creation)" in s["doing"] and "model: rtl for 2 min" in s["doing"] and s["step"]["since_s"] == 150
    assert "stage 3 (constraints) if the gate passes" in s["next"]
    assert s["blocked"] == [] and "$0.00 provider-reported of a $3.00 cap" in s["cost_line"] and "plan estimate" in s["cost_line"]
    assert "Nothing is blocked" in s["sentence"] and s["mode"]["scored"] is False


def test_what_is_blocked_or_waiting_is_said(tmp_path):
    rd = fake_run(tmp_path / "runs", events=STD + [ev("build_step", NOW - 60, "rtl-design-creation", state="start", until="route", variant="base"), ev("slot_wait", NOW - 10, "rtl-design-creation", waited_s=45, reason="another Vivado holds the PC's slot")])
    rq.submit(rd, design="use block RAM for the FIFO", stages=())
    (rd / "pending.json").write_text(json.dumps({"paused": {"kind": "question", "id": "q1", "question": "Reset polarity?", "default": "active low", "reason": "the spec is silent"}}))
    s = NS.summarise(tmp_path / "runs", rd.name, now=NOW)
    b = " | ".join(s["blocked"])
    assert "waiting for a Vivado slot" in b and "45 s" in b and "1 request queued" in b and "waiting for your answer" in b
    assert s["pending"]["ask"] == "Reset polarity?" and s["pending"]["default"] == "active low"
    pend = redact.scrub(s)                                           # the page gets the scrubbed form: the question text must survive it
    assert pend["pending"]["ask"] == "Reset polarity?" and pend["requests"][0]["what"].startswith("use block RAM")


def test_a_finished_run_says_so_and_the_sentence_is_rebuilt_only_at_a_stage_end_or_after_n_minutes(tmp_path):
    rd = fake_run(tmp_path / "runs", events=STD)
    a = NS.summarise(tmp_path / "runs", rd.name, now=NOW)
    b = NS.summarise(tmp_path / "runs", rd.name, now=NOW + 120)
    assert a["sentence"] == b["sentence"] and b["built_at"] == a["built_at"] and b["step"]["since_s"] == 270      # the live field moves, the sentence does not
    jl(rd / "trace.jsonl", [ev("stage_end", NOW + 130, "rtl-design-creation", n=2, visit=1, passed=True)])
    assert NS.summarise(tmp_path / "runs", rd.name, now=NOW + 140)["built_at"] == NOW + 140                      # a stage ended: rebuilt
    c = NS.summarise(tmp_path / "runs", rd.name, now=NOW + 140 + NS.REFRESH_MIN * 60 + 1)
    assert c["built_at"] == NOW + 140 + NS.REFRESH_MIN * 60 + 1                                                   # the interval passed: rebuilt
    (rd / "summary.json").write_text(json.dumps({"stop": "done"}))
    f = NS.summarise(tmp_path / "runs", rd.name, now=NOW + 999)
    assert f["status"] == "finished" and f["doing"].startswith("finished: done") and f["step"] is None


# --- the live console ----------------------------------------------------------------------------------------------------------------------

def stream(*events: dict) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


MODEL = [{"type": "system", "subtype": "init", "cwd": "/tmp/x"},
         {"type": "assistant", "message": {"content": [{"type": "text", "text": f"I will write the FIFO. key={KEY}"}, {"type": "tool_use", "name": "mcp__fda__write_file", "input": {"path": "/rtl/fifo.sv", "content": "module fifo; endmodule\n" * 20}}]}},
         {"type": "user", "message": {"content": [{"type": "tool_result", "content": [{"type": "text", "text": "wrote 440 bytes"}]}]}},
         {"type": "result", "subtype": "success", "num_turns": 2}]
VIV = "Starting synth_design\nINFO: [Common 17-1] user secret = " + KEY + "\nHELD-OUT-TESTBENCH-LINE a == 5\nPhase 1 Placer Initialization\nelapsed 12 s\n"


def touch(rd: Path) -> None:
    import os
    for f in rd.rglob("*"):
        if not f.is_symlink():
            os.utime(f, (NOW, NOW))


def console_run(tmp_path, hidden=None, finished=False):
    rd = fake_run(tmp_path / "runs", hidden=hidden, finished=finished, events=STD + [ev("console", NOW - 500, "synthesis", step="005_build", label="build", stream="tool_output", source="console/005_build.log", started=NOW - 500),
                                                                                     ev("console_end", NOW - 440, None, step="005_build", seconds=60.0, returncode=0)])
    (rd / "console").mkdir()
    (rd / "console" / "004_rtl_rtl-design-creation.log").write_text(stream(*MODEL))
    (rd / "console" / "005_build.log").write_text(VIV)
    touch(rd)
    return rd


def test_the_console_lists_steps_and_reads_incrementally_with_every_chunk_redacted(tmp_path):
    rd = console_run(tmp_path)
    lst = NC.steps(tmp_path / "runs", rd.name, now=NOW)
    ids = {s["id"]: s for s in lst["steps"]}
    assert ids["004_rtl_rtl-design-creation"]["active"] and not ids["005_build"]["active"] and ids["005_build"]["seconds"] == 60.0 and lst["restricted"] is False
    r = NC.read(tmp_path / "runs", rd.name, "004_rtl_rtl-design-creation", now=NOW)
    text = "\n".join(r["lines"])
    assert "assistant: I will write the FIFO." in text and "tool call: write_file(path=/rtl/fifo.sv" in text and "tool result: wrote 440 bytes" in text and "finished: success, 2 turns" in text
    assert KEY not in text and "[redacted]" in text                                                       # the planted key in model output
    v = NC.read(tmp_path / "runs", rd.name, "005_build", now=NOW)
    assert KEY not in "\n".join(v["lines"]) and "Phase 1 Placer Initialization" in v["lines"]              # and in a Vivado log
    # incremental: append a line, read from the returned offset, get only the new line
    f = rd / "console" / "005_build.log"
    f.write_text(f.read_text() + "route_design done\n")
    n = NC.read(tmp_path / "runs", rd.name, "005_build", offset=v["next_offset"], now=NOW)
    assert n["lines"] == ["route_design done"] and n["next_offset"] == f.stat().st_size


def test_a_running_step_holds_back_the_line_still_being_written_and_a_large_file_is_read_from_its_last_256kb(tmp_path):
    rd = console_run(tmp_path)
    f = rd / "console" / "004_rtl_rtl-design-creation.log"
    f.write_text(f.read_text() + '{"type":"assistant","mess')                                              # half a line: the step is still running
    touch(rd)
    r = NC.read(tmp_path / "runs", rd.name, "004_rtl_rtl-design-creation", now=NOW)
    assert r["next_offset"] == len(stream(*MODEL).encode()) and "mess" not in "\n".join(r["lines"])
    big = rd / "console" / "005_build.log"
    big.write_text("Starting x\n" * 100_000)                                                              # 1.1 MB
    touch(rd)
    r = NC.read(tmp_path / "runs", rd.name, "005_build", now=NOW)
    assert r["tail_only"] and r["size"] - r["offset"] <= NC.MAX_BYTES and r["next_offset"] == r["size"] and len(r["lines"]) < 30_000
    r2 = NC.read(tmp_path / "runs", rd.name, "005_build", offset=0, now=NOW)                               # a request for everything is still capped
    assert r2["size"] - r2["offset"] <= NC.MAX_BYTES


def test_the_console_takes_a_step_id_from_the_list_never_a_path(tmp_path):
    rd = console_run(tmp_path)
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    for bad in ("../../secret.txt", "/etc/passwd", "console/005_build.log", "..", "005_build/../../x", "nope", "", "005_build\x00"):
        assert NC.read(tmp_path / "runs", rd.name, bad, now=NOW) is None
    jl(rd / "trace.jsonl", [ev("console", NOW, None, step="evil", label="x", stream="tool_output", source="../secret.txt", started=NOW),
                            ev("console", NOW, None, step="evil2", label="x", stream="tool_output", source="/etc/passwd", started=NOW)])
    assert {s["id"] for s in NC.steps(tmp_path / "runs", rd.name, now=NOW)["steps"]} == {"004_rtl_rtl-design-creation", "005_build"}      # a trace row cannot name a file outside console/
    (rd / "console" / "link.log").symlink_to(tmp_path / "secret.txt")
    jl(rd / "trace.jsonl", [ev("console", NOW, None, step="link", label="x", stream="tool_output", source="console/link.log", started=NOW)])
    assert NC.read(tmp_path / "runs", rd.name, "link", now=NOW) is None                                   # a link is refused
    assert NC.steps(tmp_path / "runs", "../runs", now=NOW) is None and NC.read(tmp_path / "runs", "..", "005_build") is None


def test_a_scored_run_shows_tool_names_and_progress_lines_only(tmp_path):
    rd = console_run(tmp_path, hidden="benchmark_private/v2/task/hidden/spec.yaml")
    lst = NC.steps(tmp_path / "runs", rd.name, now=NOW)
    assert lst["restricted"] and lst["held_out"] and "no model text" in lst["restriction"]
    m = "\n".join(NC.read(tmp_path / "runs", rd.name, "004_rtl_rtl-design-creation", now=NOW)["lines"])
    assert "tool call: write_file" in m and "fifo" not in m and "I will write" not in m and "path=" not in m and "tool result" not in m
    v = NC.read(tmp_path / "runs", rd.name, "005_build", now=NOW)
    assert "HELD-OUT-TESTBENCH-LINE a == 5" not in "\n".join(v["lines"]) and v["withheld"] >= 1 and "Phase 1 Placer Initialization" in v["lines"]


def test_runs_from_before_the_console_show_their_finished_model_streams(tmp_path):
    rd = fake_run(tmp_path / "runs", events=STD)
    (rd / "claude_code").mkdir()
    (rd / "claude_code" / "001_rtl_rtl-design-creation.jsonl").write_text(stream(*MODEL))
    lst = NC.steps(tmp_path / "runs", rd.name, now=NOW)
    sid = lst["steps"][-1]["id"]
    assert sid == "cc-001_rtl_rtl-design-creation" and not lst["steps"][-1]["active"] and "write_file" in "\n".join(NC.read(tmp_path / "runs", rd.name, sid)["lines"])
    (rd / "claude_code" / "001_rtl_rtl-design-creation.user.txt").write_text("PROMPT TEXT")        # a prompt file is never listed
    assert all("user" not in s["id"] and "system" not in s["id"] for s in NC.steps(tmp_path / "runs", rd.name)["steps"])


# --- ask a question -------------------------------------------------------------------------------------------------------------------------

class FakeLlm:
    def __init__(self, text="Stage 2 is running [R1], and the gate has not been called yet [R3]. See also [R9].", cost=0.05):
        self.calls, self.text, self.cost = [], text, cost

    def __call__(self, system, user):
        self.calls.append((system, user))
        return {"text": self.text, "plan_estimate_usd": self.cost, "cost_usd": None, "tokens": 321, "model": "claude-sonnet-5-5"}


def test_the_answer_cites_the_records_it_read_and_is_logged_with_its_cost(tmp_path):
    rd = fake_run(tmp_path / "runs", events=STD)
    jl(rd / "t1" / "build" / "audit.jsonl", [{"t": NOW, "tool": "write_file", "stage": "rtl-design-creation", "ok": True, "result_summary": f"wrote the file with {KEY}"}])
    llm = FakeLlm()
    r = NA.ask(tmp_path / "runs", rd.name, "What is the run doing?", llm=llm)
    assert r["cited"] == ["R1", "R3"] and r["cites_unknown"] == ["R9"] and r["records_read"] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    system, user = llm.calls[0]
    assert "[R1] status" in user and "QUESTION\nWhat is the run doing?" in user and KEY not in user and "no tools" in system        # only redacted records reach the model
    row = json.loads((rd / "qa.jsonl").read_text().splitlines()[0])
    assert row["q"] == "What is the run doing?" and row["plan_estimate_usd"] == 0.05 and row["cited"] == ["R1", "R3"] and row["model"] == "claude-sonnet-5-5"
    assert r["qa_spent_usd"] == 0.05 and "plan estimate" in r["cost_note"]
    assert not (rd / "t1" / "rtl").exists() and sorted(p.name for p in rd.iterdir()) == sorted(["config.json", "role_usage.jsonl", "trace.jsonl", "snapshots.json", "t1", "qa.jsonl"])  # nothing but qa.jsonl was written


def test_a_question_is_refused_for_a_scored_run_a_bad_text_or_past_its_own_cap(tmp_path):
    rd = fake_run(tmp_path / "runs", events=STD)
    llm = FakeLlm()
    for bad in ("", "   ", "-rf /", "x" * 501, 7):
        with pytest.raises(NA.AskError):
            NA.ask(tmp_path / "runs", rd.name, bad, llm=llm)
    with pytest.raises(NA.AskError):
        NA.ask(tmp_path / "runs", "../etc", "hello", llm=llm)
    assert llm.calls == [] and not (rd / "qa.jsonl").exists()                                              # refusals make no call and log nothing
    NA.ask(tmp_path / "runs", rd.name, "one", llm=FakeLlm(cost=0.45))
    NA.ask(tmp_path / "runs", rd.name, "two", llm=FakeLlm(cost=0.1))                                       # 0.45 is under the $0.50 cap: allowed, and takes it to 0.55
    with pytest.raises(NA.AskError, match="cap"):
        NA.ask(tmp_path / "runs", rd.name, "three", llm=llm)
    sc = fake_run(tmp_path / "runs", "20261122-000000-bbbb", hidden="benchmark/tasks/x/hidden/spec.yaml")
    with pytest.raises(NA.AskError, match="scored"):
        NA.ask(tmp_path / "runs", sc.name, "why?", llm=llm)


def test_the_default_model_call_refuses_forbidden_models(tmp_path, monkeypatch):
    import agent.models.resolver as RS

    class E:
        model, kind, options, purpose = "anthropic/claude-opus-5-5", "openrouter", {}, "review"

    class R:
        def entry(self, p):
            return E
    monkeypatch.setattr(RS, "resolver_for", lambda *a, **k: R())
    with pytest.raises(NA.AskError, match="Fable, Opus"):
        NA.default_llm()("s", "u")


# --- requests -------------------------------------------------------------------------------------------------------------------------------

def test_requests_are_queued_with_when_and_what_they_affect_and_refused_when_unsafe(tmp_path):
    rd = fake_run(tmp_path / "runs", events=STD)
    a = rq.submit(rd, control="stop-after", stage=3)
    b = rq.submit(rd, design="use block RAM for the FIFO")
    c = rq.submit(rd, control="pause")
    assert [a["id"], b["id"], c["id"]] == ["r001", "r002", "r003"] and a["status"] == "queued" and "safe point" in a["applies"] and "stage 3" in a["affects"]
    for kw in ({"control": "reboot"}, {"control": "stop_after"}, {"control": "stop_after", "stage": 12}, {"control": "pause", "stage": 2}, {"control": "abort", "design": "x"},
               {"design": ""}, {"design": "-rf"}, {"design": "x" * 501}, {}):
        with pytest.raises(rq.RequestError):
            rq.submit(rd, **kw)
    assert len(rq.load(rd)) == 3
    (rd / "summary.json").write_text("{}")
    with pytest.raises(rq.RequestError, match="has ended"):
        rq.submit(rd, control="pause")


def test_a_scored_run_refuses_design_requests_and_allows_control_requests(tmp_path):
    for hidden, marker in (("benchmark/tasks/x/hidden/spec.yaml", False), (None, True)):
        rd = fake_run(tmp_path / ("runs" + str(marker)), hidden=hidden, events=STD)
        if marker:
            (rd / "SCORED").write_text("")
        assert rq.eval_mode(rd)["scored"]
        with pytest.raises(rq.RequestError, match="scored"):
            rq.submit(rd, design="use block RAM")
        assert rq.submit(rd, control="pause")["status"] == "queued" and rq.submit(rd, control="abort")["status"] == "queued"


# --- the new routes -------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def srv(tmp_path):
    app, _ = make_app(tmp_path)
    rd = fake_run(tmp_path / "runs", events=STD)
    app.ask_llm = FakeLlm()
    s = Live(app)
    s.rd, s.rid, s.tmp = rd, rd.name, tmp_path
    yield s
    s.close()


def j(b):
    return json.loads(b)


def test_the_new_get_routes_serve_scrubbed_records_for_listed_runs_only(srv):
    st, _, b = srv.get(f"/api/live/summary?id={srv.rid}")
    assert st == 200 and "stage 2 (rtl-design-creation)" in j(b)["doing"]
    st, _, b = srv.get(f"/api/live/requests?id={srv.rid}")
    assert st == 200 and j(b)["requests"] == [] and j(b)["qa_max"] == NA.QA_MAX
    assert srv.get(f"/api/console/steps?id={srv.rid}")[0] == 200
    for bad in ("..", "../runs", "/etc", "nope", ""):
        for route in ("live/summary", "live/requests", "console/steps"):
            assert srv.get(f"/api/{route}?id={bad}")[0] == 404
    assert srv.get(f"/api/console/read?id={srv.rid}&step=../../x")[0] == 404
    assert srv.get("/api/live/summary?id=" + srv.rid, )[0] == 200
    assert srv.req("GET", f"/api/live/summary?id={srv.rid}")[0] == 401                  # no token


def test_the_new_post_routes_follow_the_guards_of_every_action(srv):
    ask = {"id": srv.rid, "question": "What is it doing?", "confirm": "ask"}
    # token in the header (the cookie alone is refused), Origin, Content-Type
    for path, body in (("/api/run/ask", ask), ("/api/run/request", {"id": srv.rid, "kind": "control", "action": "pause", "confirm": "request"})):
        assert srv.req("POST", path, {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{srv.port}", "Cookie": "fda_nav=" + TOKEN}, json.dumps(body))[0] == 403
        assert srv.req("POST", path, {"X-Navigator-Token": TOKEN, "Content-Type": "application/json", "Origin": "http://evil.example"}, json.dumps(body))[0] == 403
        assert srv.req("POST", path, {"X-Navigator-Token": TOKEN, "Content-Type": "text/plain", "Origin": f"http://127.0.0.1:{srv.port}"}, json.dumps(body))[0] == 403
        assert srv.req("POST", path, {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{srv.port}"}, json.dumps(body))[0] == 401
    st, r = srv.post("/api/run/ask", ask)
    assert st == 200 and r["ok"] and r["cited"] == ["R1", "R3"] and (srv.rd / "qa.jsonl").is_file()
    # a confirmation the page sends, or nothing happens
    st, r = srv.post("/api/run/ask", {**ask, "confirm": "yes"})
    assert not r["ok"] and "confirmation" in r["refused"]
    st, r = srv.post("/api/run/request", {"id": srv.rid, "kind": "design", "text": "use block RAM", "confirm": "ask"})
    assert not r["ok"] and rq.load(srv.rd) == []
    st, r = srv.post("/api/run/request", {"id": srv.rid, "kind": "design", "text": "use block RAM for the FIFO", "confirm": "request"})
    assert r["ok"] and r["request"]["id"] == "r001" and "next stage" in r["request"]["affects"]
    st, r = srv.post("/api/run/request", {"id": srv.rid, "kind": "control", "action": "stop_after", "stage": 4, "confirm": "request"})
    assert r["ok"] and r["request"]["stage"] == 4
    assert [x["id"] for x in rq.load(srv.rd)] == ["r001", "r002"]


def test_a_question_or_request_cannot_name_a_file_inject_a_flag_or_reach_a_run_that_is_not_listed(srv):
    base = {"confirm": "request", "kind": "design", "text": "use block RAM"}
    for extra in ({"file": "/etc/passwd"}, {"path": "../x"}, {"argv": ["--allow-fable"]}, {"flags": "--max-usd 99"}, {"cmd": "rm"}, {"run_dir": "/tmp"}):
        st, r = srv.post("/api/run/request", {"id": srv.rid, **base, **extra})
        assert not r["ok"] and "fields this action does not take" in r["refused"]
        st, r = srv.post("/api/run/ask", {"id": srv.rid, "question": "hi", "confirm": "ask", **extra})
        assert not r["ok"] and "fields this action does not take" in r["refused"]
    for rid in ("../runs/" + srv.rid, "/tmp", "..", "nope", None, 5, ["x"]):
        for path, body in (("/api/run/request", base), ("/api/run/ask", {"question": "hi", "confirm": "ask"})):
            st, r = srv.post(path, {"id": rid, **body})
            assert not r["ok"] and "pick a run from the list" in r["refused"]
    for text in ("--allow-fable", "-x", "x" * 501):                                        # text is data: a flag-looking text is refused, and it never reaches a command line
        st, r = srv.post("/api/run/request", {"id": srv.rid, "kind": "design", "text": text, "confirm": "request"})
        assert not r["ok"]
        st, r = srv.post("/api/run/ask", {"id": srv.rid, "question": text, "confirm": "ask"})
        assert not r["ok"]
    st, r = srv.post("/api/run/request", {"id": srv.rid, "kind": "control", "action": "pause", "text": "x", "confirm": "request"})
    assert not r["ok"] and rq.load(srv.rd) == []
    st, r = srv.post("/api/run/request", {"id": srv.rid, "kind": "control", "action": "; rm -rf /", "confirm": "request"})
    assert not r["ok"]


def test_a_scored_run_is_refused_over_http_for_ask_and_design_but_not_control(tmp_path):
    app, _ = make_app(tmp_path)
    rd = fake_run(tmp_path / "runs", hidden="benchmark_private/v2/t/hidden/spec.yaml", events=STD)
    app.ask_llm = FakeLlm()
    s = Live(app)
    try:
        assert not s.post("/api/run/ask", {"id": rd.name, "question": "why?", "confirm": "ask"})[1]["ok"]
        assert not s.post("/api/run/request", {"id": rd.name, "kind": "design", "text": "use block RAM", "confirm": "request"})[1]["ok"]
        assert s.post("/api/run/request", {"id": rd.name, "kind": "control", "action": "pause", "confirm": "request"})[1]["ok"]
        assert s.app.ask_llm.calls == [] and not (rd / "qa.jsonl").exists()
        assert j(s.get(f"/api/live/requests?id={rd.name}")[2])["mode"]["scored"] is True
        assert j(s.get(f"/api/console/steps?id={rd.name}")[2])["restricted"] is True
    finally:
        s.close()


def test_a_run_paused_on_its_own_question_is_resumed_with_the_stage_2_guards_and_the_answer_is_one_argv_element(tmp_path):
    from navigator.tests.test_103s2_navigator import FakeSpawner, env as _e, make_rc    # noqa: F401  (the Stage 2 fakes)
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "usage_log.txt").write_text("")
    rd = fake_run(tmp_path / "runs", events=STD)
    (rd / "pending.json").write_text(json.dumps({"paused": {"kind": "question", "id": "q1", "question": "Reset polarity?", "default": "active low"}}))
    rc, runner, sp = make_rc({"handoff": handoff, "runs": tmp_path / "runs", "state": tmp_path / "state", "tmp": tmp_path, "cfg": tmp_path / "cfg"})
    r = rc.start({"kind": "answer", "run": rd.name, "answer": "--allow-fable; active high", "confirm": "start"})
    assert r["started"], r
    argv = sp.calls[0]["argv"]
    assert argv[1:6] == ["-m", "agent", "resume", rd.name, "--reply"] and json.loads(argv[6]) == {"answer": "--allow-fable; active high"} and len(argv) == 7
    assert any("usage_check.sh" in c[1] for c in runner.calls if c[0] == "bash") and (handoff / "heavy_slot.lock").is_file()          # usage guard and a heavy slot
    for bad in ({"run": "../x"}, {"run": "nope"}, {"run": rd.name, "answer": ""}, {"run": rd.name, "answer": "x" * 401}):
        assert not rc.start({"kind": "answer", "answer": "ok", "confirm": "start", **bad}).get("started")
    (rd / "pending.json").unlink()
    assert "not waiting" in rc.start({"kind": "answer", "run": rd.name, "answer": "x", "confirm": "start"})["refused"]


def test_the_shipped_files_name_no_host_and_the_new_routes_are_the_only_new_posts():
    assert not re.search(r"https?://", (ROOT / "navigator" / "static" / "app.css").read_text())
    src = (ROOT / "navigator" / "server.py").read_text()
    new = set(re.findall(r'"(/api/run/(?:ask|request|answer))"', src[src.index("def live_post"):src.index("    def action")]))
    assert new == {"/api/run/ask", "/api/run/request", "/api/run/answer"}
    js = (ROOT / "navigator" / "static" / "app.js").read_text()
    assert "innerHTML" not in js and "/api/run/ask" in js and "/api/run/request" in js and "/api/run/answer" in js
