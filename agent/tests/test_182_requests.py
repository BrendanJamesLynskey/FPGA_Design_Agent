"""Brief 182: mid-run requests are applied at a safe point of the real stage machine (scripted model, fake runner: no spend, no Vivado).

A request waits in ``requests.jsonl`` until the end of a stage (after its gate and review); then the agent acknowledges it, applies it and records why. Control: pause, stop-after, abort.
Design: the owner's note to the next stage's writer, or a rewind when its words name an earlier stage."""

import json
import shutil
import uuid

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("deepagents")

from langgraph.types import Command  # noqa: E402

from agent.core.session import ROOT  # noqa: E402
from agent.graph import ownership  # noqa: E402
from agent.graph import requests as rq  # noqa: E402
from agent.graph import run as gr  # noqa: E402
from agent.tests.test_episode import FakeRunner, T1, scripted_client  # noqa: E402


@pytest.fixture
def world(monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    from flow import hw
    monkeypatch.setattr(hw, "load_board", lambda b: {"cable_serial": "TEST0000"})
    monkeypatch.setattr(hw, "power_ok", lambda d, b: {"pass": True, "total_w": 0.15, "junction_c": 42.7, "source": "wall"})
    yield runs
    shutil.rmtree(runs, ignore_errors=True)


def start(runs, stop_after=None, hidden=None):
    seen, where = [], {}
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off", review="on", stop_after=stop_after, hidden_spec=hidden)
    rt = gr.new_runtime(cfg, scripted_client(seen, where), run_id="r182", runner=FakeRunner())
    (rt.design / "spec.md").write_text("A PWM dimmer counter for the board.\n")
    where["design"] = str(rt.design.relative_to(ROOT))
    graph = gr.build_graph(gr.checkpointer_for(rt.run_dir))
    return rt, graph, {"configurable": {"thread_id": "r182"}}, seen


def pending(graph, lg):
    st = graph.get_state(lg)
    return st, [i.value for t in st.tasks for i in (t.interrupts or [])]


def drive(rt, graph, lg, hook, limit=40):
    """Approve every review; ``hook(interrupt value)`` runs first (it queues requests) and may return a different reply. Returns the final state and every interrupt seen."""
    inp, seen = {"run_id": "r182", "stage": 0, "visits": {}, "history": []}, []
    for _ in range(limit):
        graph.invoke(inp, lg)
        st, pend = pending(graph, lg)
        if not pend:
            return st, seen
        seen.append(pend[0])
        inp = Command(resume=hook(pend[0]) or {"decision": "approve", "by": "planner"})
    raise AssertionError("the run did not end")


def test_a_design_request_and_a_stop_after_are_applied_at_the_stage_boundary(world):
    rt, graph, lg, seen = start(world)
    done = {}

    def hook(p):
        if p["kind"] == "review" and p["stage"] == 0 and not done:
            done["a"] = rq.submit(rt.run_dir, design="use block RAM for the FIFO")
            done["b"] = rq.submit(rt.run_dir, control="stop-after", stage=2)
            assert [r["status"] for r in rq.load(rt.run_dir)] == ["queued", "queued"]
            assert not (rt.design / "build" / "who_did_what.json").exists() or all(r["what"] != "mid-run request" for r in ownership.load(rt.design))
    st, ints = drive(rt, graph, lg, hook)
    hist = [h["n"] for h in st.values["history"]]
    assert hist == [0, 1, 2] and st.values["stop"] == "done"                                       # stop-after 2: the run ended once stage 2 passed
    by = {r["id"]: r for r in rq.load(rt.run_dir)}
    assert by["r001"]["status"] == "done" and "stage 1" in by["r001"]["history"][-1]["reason"] and "owner's note" in by["r001"]["history"][-1]["reason"]
    assert [h["event"] for h in by["r002"]["history"]] == ["queued", "accepted", "done"] and "stage 2" in by["r002"]["history"][1]["reason"]
    rows = [r for r in ownership.load(rt.design) if r["what"] == "mid-run request"]
    assert len(rows) == 2 and all(r["who"] == "owner" for r in rows)                                 # each is a user intervention in who_did_what.json
    s = gr.summary(rt, st.values)
    assert s["user_requests"]["control"] == 1 and s["user_requests"]["design"] == 1 and s["user_requests"]["user_interventions"] == 2
    ev = [json.loads(ln) for ln in (rt.run_dir / "trace.jsonl").read_text().splitlines() if '"kind": "event"' in ln]
    names = [e["event"] for e in ev]
    assert names.count("stage_start") == 3 and names.count("stage_end") == 3 and "request" in names and "console" not in {e["event"] for e in ev if e["event"] == "x"}


def test_a_design_request_reaches_the_next_stages_writer_as_the_owners_note(world):
    rt, graph, lg, seen = start(world, stop_after=1)
    sent = {}

    def hook(p):
        if p["kind"] == "review" and p["stage"] == 0 and not sent:
            sent["r"] = rq.submit(rt.run_dir, design="use block RAM for the FIFO")
    st, _ = drive(rt, graph, lg, hook)
    assert "use block RAM for the FIFO" in "\n".join(x["user"] for x in seen if x["role"] == "rtl")      # the stage-1 Designer's prompt carried the note


def test_a_pause_waits_for_the_safe_point_stops_the_run_and_resumes_where_it_was(world):
    rt, graph, lg, seen = start(world, stop_after=2)
    inp, queued = {"run_id": "r182", "stage": 0, "visits": {}, "history": []}, None
    for _ in range(40):
        graph.invoke(inp, lg)
        st, pend = pending(graph, lg)
        assert pend
        p = pend[0]
        if p["kind"] == "paused":
            break
        if p["kind"] == "review" and p["stage"] == 1 and queued is None:
            queued = rq.submit(rt.run_dir, control="pause")
        inp = Command(resume={"decision": "approve", "by": "planner"})
    assert p["kind"] == "paused" and p["stage"] == 1 and "resume" in p and queued["id"] == "r001"
    assert [h["n"] for h in st.values["history"]] == [0, 1]                                         # stage 2 has not started
    r = rq.load(rt.run_dir)[0]
    assert r["status"] == "applied" and "paused at the end of stage 1" in r["history"][-1]["reason"]
    assert not (rt.run_dir / "summary.json").exists()                                               # paused, not ended
    graph.invoke(Command(resume={"resumed": True}), lg)                                             # the user resumes it
    st, pend = pending(graph, lg)
    while pend:                                                                                     # then it runs on to its stop-after
        graph.invoke(Command(resume={"decision": "approve", "by": "planner"}), lg)
        st, pend = pending(graph, lg)
    assert [h["n"] for h in st.values["history"]] == [0, 1, 2] and st.values["stop"] == "done"
    r = rq.load(rt.run_dir)[0]
    assert r["status"] == "done" and r["history"][-1]["reason"] == "resumed"


def test_an_abort_ends_the_run_at_the_safe_point(world):
    rt, graph, lg, seen = start(world)
    sent = {}

    def hook(p):
        if p["kind"] == "review" and p["stage"] == 1 and not sent:
            sent["r"] = rq.submit(rt.run_dir, control="abort")
    st, _ = drive(rt, graph, lg, hook)
    assert st.values["stop"] == "aborted: user request" and [h["n"] for h in st.values["history"]] == [0, 1]
    assert rq.load(rt.run_dir)[0]["status"] == "done" and "ended at the end of stage 1" in rq.load(rt.run_dir)[0]["history"][-1]["reason"]


def test_a_design_request_that_names_an_earlier_stage_rewinds_through_the_snapshots(world):
    rt, graph, lg, seen = start(world, stop_after=3)
    sent = {}

    def hook(p):
        if p["kind"] == "review" and p["stage"] == 2 and not sent:
            sent["r"] = rq.submit(rt.run_dir, design="change the architecture: add a block for the debounce")
    st, _ = drive(rt, graph, lg, hook)
    r = rq.load(rt.run_dir)[0]
    assert r["status"] == "done" and "rewound to stage 1" in r["history"][-1]["reason"]
    assert [h["n"] for h in st.values["history"]][:4] == [0, 1, 2, 1]                                  # went back to stage 1 after stage 2
    assert any(x["what"].startswith("rewound to stage 1 (request r001)") for x in ownership.load(rt.design))


def test_a_design_request_in_a_scored_run_is_declined_at_the_safe_point_and_a_late_request_is_declined_when_the_run_ended(world, tmp_path):
    hidden = tmp_path / "hidden.yaml"
    hidden.write_text((T1 / "spec.yaml").read_text())
    rt, graph, lg, seen = start(world, stop_after=1, hidden=hidden)
    with pytest.raises(rq.RequestError, match="scored"):
        rq.submit(rt.run_dir, design="use block RAM")
    rq._append(rt.run_dir, {"event": "queued", "id": "r001", "kind": "design", "text": "use block RAM", "source": "hand-written"})      # a row somebody wrote by hand
    st, _ = drive(rt, graph, lg, lambda p: None)
    r = rq.load(rt.run_dir)[0]
    assert r["status"] == "declined" and "scored" in r["history"][-1]["reason"]
    assert "use block RAM" not in "\n".join(x["user"] for x in seen)


def test_a_design_request_that_arrives_when_the_run_is_about_to_end_is_declined_with_the_reason(world):
    rt, graph, lg, seen = start(world, stop_after=1)
    sent = {}

    def hook(p):
        if p["kind"] == "review" and p["stage"] == 1 and not sent:
            sent["r"] = rq.submit(rt.run_dir, design="use block RAM for the FIFO")
    st, _ = drive(rt, graph, lg, hook)
    r = rq.load(rt.run_dir)[0]
    assert st.values["stop"] == "done" and r["status"] == "declined" and "ended" in r["history"][-1]["reason"]
