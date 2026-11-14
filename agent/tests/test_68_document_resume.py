"""Brief 68 parts C and D: the DOC step and its gate (agent.graph.document), and resume from a handover
(agent.graph.pickup). No model call: the DOC step replays the Designer replies recorded in results/68_agent_docs."""

from __future__ import annotations

import copy
import json
import shutil
import uuid
from pathlib import Path

import pytest
import yaml

from agent.graph import document as D
from agent.graph import pickup as P
from flow import handover as H

ROOT = H.ROOT
REC = ROOT / "results" / "68_agent_docs"
C14 = "20261107-005621-8deb"


@pytest.fixture
def run_copy():
    """A recorded run copied under runs/ (gitignored), without its renderings: the DOC step writes them afresh."""
    dst = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    shutil.copytree(REC / C14, dst)
    d = dst / "c14_int8_dot_requant"
    for n in ("handover.yaml", "README.md", "AGENT.md"):
        (d / n).unlink(missing_ok=True)
    shutil.rmtree(d / "docs", ignore_errors=True)
    yield dst
    shutil.rmtree(dst, ignore_errors=True)


def _doc(run: Path, llm) -> dict:
    s = json.loads((run / "summary.json").read_text())
    return D.document(run / s["design"], run, llm, run_id=s["run_id"], board="nexys_a7_100t", gates_last=s["gates_last"],
                      stop=s["stop"])


# --- the DOC step ---------------------------------------------------------------------------------------------------

def test_recorded_designer_reply_passes_the_doc_gate(run_copy) -> None:
    res = _doc(run_copy, D.replay_llm(REC / C14 / "doc_calls.jsonl"))
    assert res["ok"], res["problems"]
    d = run_copy / "c14_int8_dot_requant"
    assert (d / "README.md").is_file() and (d / "AGENT.md").is_file()
    assert D.doc_gate(d, res["required_gaps"]) == []
    assert D.recheck(d) == []
    h = H.load(d)
    assert h["produced_by"] == "agent" and h["agent_run"]["run_id"] == C14
    gaps = {g["about"] for g in h["gaps"]}
    # every stage that did not pass, every non-pass evidence entry and requirement is a gap (the brief's rule)
    for s, r in h["state"]["gates"].items():
        assert r == "pass" or s in gaps
    assert all(e["result"] == "pass" or e["id"] in gaps for e in h["evidence"])


def test_unusable_replies_fail_the_gate_after_the_passes(run_copy) -> None:
    res = _doc(run_copy, lambda s, u: "not yaml: [")
    assert not res["ok"] and res["passes"] == D.DOC_PASSES and res["problems"]


def test_invented_number_in_prose_fails_then_repair_passes(run_copy) -> None:
    good = json.loads((REC / C14 / "doc_calls.jsonl").read_text().splitlines()[-1])["reply"]   # the reply that passed the gate
    y = D.parse_reply(good)
    y["summary"] = y["summary"] + " It closes timing at 731.25 MHz."
    bad = "```yaml\n" + yaml.safe_dump(y) + "```"
    seen = []

    def llm(system, user):
        seen.append(user)
        return bad if len(seen) == 1 else good
    res = _doc(run_copy, llm)
    assert res["ok"] and res["passes"] == 2
    assert "731.25" in seen[1]                     # the gate's problem went back to the Designer


def test_merge_keeps_code_owned_facts_and_required_gaps(run_copy) -> None:
    s = json.loads((run_copy / "summary.json").read_text())
    d = run_copy / "c14_int8_dot_requant"
    h0, req = D.draft(d, run_copy, run_id=C14, board="nexys_a7_100t", gates_last=s["gates_last"], stop=s["stop"])
    evil = copy.deepcopy(h0)
    evil["state"]["gates"] = {k: "pass" for k in evil["state"]["gates"]}
    evil["evidence"][1]["result"] = "pass"
    evil["measurements"][0]["field"] = "killed"
    evil["gaps"] = [{"about": "x", "text": "all good, nothing missing here"}]
    evil["summary"] = "a written summary of the design for the next engineer"
    m = D.merge(h0, evil, req)
    assert m["state"] == h0["state"] and m["evidence"] == h0["evidence"] and m["measurements"] == h0["measurements"]
    assert [g for g in m["gaps"] if g["about"] in req] == [g for g in h0["gaps"] if g["about"] in req]
    assert m["summary"].startswith("a written summary") and any(g["about"] == "x" for g in m["gaps"])


def test_recheck_catches_hand_edits_of_a_committed_agent_handover(run_copy) -> None:
    res = _doc(run_copy, D.replay_llm(REC / C14 / "doc_calls.jsonl"))
    assert res["ok"]
    d = run_copy / "c14_int8_dot_requant"
    h = H.load(d)
    h["state"]["gates"]["rtl-design-creation"] = "pass"
    h["gaps"] = [g for g in h["gaps"] if g["about"] != "rtl-design-creation"]
    (d / "handover.yaml").write_text(H.dump(h))
    H.write(d, build_id=False)
    errs = D.recheck(d)
    assert any("state.gates" in e for e in errs) and any("rtl-design-creation" in e for e in errs)


def test_old_vivado_builds_publish_no_build_numbers(run_copy) -> None:
    s = json.loads((run_copy / "summary.json").read_text())
    d = run_copy / "c14_int8_dot_requant"
    h, req = D.draft(d, run_copy, run_id=C14, board="nexys_a7_100t", gates_last=s["gates_last"], stop=s["stop"])
    assert D.build_release(d) != H.VIVADO
    assert not {m["category"] for m in h["measurements"]} & {"timing", "resources", "power"}
    assert h["state"]["evidence_vivado"] == "earlier"
    assert {"timing", "resources", "power"} <= set(req)
    assert next(e for e in h["evidence"] if e["activity"] == "build")["result"] == "partial"


def test_measurement_records_of_an_agent_run_are_its_own(run_copy) -> None:
    res = _doc(run_copy, D.replay_llm(REC / C14 / "doc_calls.jsonl"))
    assert res["ok"]
    d = run_copy / "c14_int8_dot_requant"
    h = H.load(d)
    rd = H.agent_run_dir(h, d)
    assert rd == run_copy.resolve()
    assert H.in_run_records(d / "build" / "verif" / "mutation.json", rd, d)
    assert not H.in_run_records(d / "rtl" / "dotq_core.sv", rd, d)          # a role-written file is never a record
    assert not H.in_run_records(ROOT / "README.md", rd, d)
    h["measurements"][0]["record"] = H.rel(d / "spec.yaml")
    h["measurements"][0]["field"] = "name"
    errs, _ = H.problems(d, h)
    assert any("own directory" in e for e in errs)


def test_committed_agent_runs_pass_doccheck() -> None:
    from flow import doccheck
    ds = doccheck.agent_designs()
    assert len(ds) >= 3
    for d in ds:
        e, s = doccheck.check_design(d)
        assert e == [] and s == [], (d, e, s)


def test_document_node_writes_doc_json_and_freezes_the_summary(tmp_path, monkeypatch) -> None:
    from agent.graph import run as gr
    from agent.tests.request_golden import T1, _Ok
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    try:
        cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", docs="on")
        rt = gr.new_runtime(cfg, lambda *a, **k: None, runner=_Ok())
        rt.doc_llm = lambda s, u: "no yaml"
        out = gr.node_document({"run_id": rt.run_id, "stop": "done", "history": []})
        assert out["doc"]["ok"] is False and out["doc"]["signed_off"] is False
        assert json.loads((rt.run_dir / "doc.json").read_text())["passes"] == D.DOC_PASSES
        assert (rt.run_dir / "summary.json").is_file()
        cfg.docs = "off"
        assert gr.node_document({"run_id": rt.run_id, "stop": "done"}) == {}
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_graph_ends_through_the_document_node() -> None:
    from langgraph.checkpoint.memory import MemorySaver
    from agent.graph.run import build_graph
    g = build_graph(MemorySaver())
    assert "document" in g.get_graph().nodes


# --- resume ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind,stage", [
    ("Add a register that counts button presses", "spec", 0),
    ("Rename the internal tick counter signal", "rtl", 2),
    ("In rtl/debounce.sv, rename the register cnt to stable_count", "rtl", 2),   # a register named in the RTL is not a map change
    ("Add a register for the press count to the register map", "spec", 0),
    ("Specify the input delays of the buttons", "constraints", 3),               # "specify" is not "spec"
    ("Move LED pins and fix the XDC", "rtl", 2),                # 'fix' (rtl) is earlier than 'pin' (constraints)
    ("Move the LED pins in the XDC", "constraints", 3),
    ("Improve the setup slack", "timing", 6),
    ("Timing fails: add a pipeline stage to the multiplier", "rtl", 2),          # a change verb under a late class
    ("Update the README wording", "spec", 0),                                    # docs-only is never guessed (--kind docs)
    ("Make it better", "spec", 0),                              # nothing matched: re-read the request
    (None, None, None),
])
def test_change_classifier(text, kind, stage) -> None:
    k, s, _ = P.classify_change(text)
    assert (k, s) == (kind, stage)


def _h(gates=None, stage="board-verified", ev_vivado=None):
    st = {"stage": stage, "gates": gates or {}, "vivado": H.VIVADO}
    if ev_vivado:
        st["evidence_vivado"] = ev_vivado
    return {"state": st, "evidence": [{"id": "E1", "activity": "simulation", "record": "r1"},
                                      {"id": "E2", "activity": "build", "record": "r2"}],
            "measurements": [{"id": "M1", "category": "timing", "record": "r2"}]}


def _fresh(**kw):
    f = {"design": "designs/x", "stale": [], "changed_files": [], "vivado": {"handover": H.VIVADO, "now": H.VIVADO},
         "kb_pin": {"handover": "a", "now": "a"}}
    f.update(kw)
    return f


def test_entry_stage_rule() -> None:
    e = P.entry_stage
    assert e(_h(), _fresh())["stage"] == P.DOC_ONLY                               # current, finished: nothing to re-run
    assert e(_h(), _fresh(), "rename a signal")["stage"] == 2
    assert e(_h(), _fresh(changed_files=["designs/x/rtl/a.sv"]))["stage"] == 2
    assert e(_h(), _fresh(changed_files=["designs/x/design.xdc"]))["stage"] == 3
    assert e(_h(), _fresh(changed_files=["designs/x/spec.yaml"]), "move the pins in the xdc")["stage"] == 0
    assert e(_h(), _fresh(stale=["E2: r2 changed since the handover (sha256)"]))["stage"] == 3
    assert e(_h(), _fresh(stale=["M1: r2 changed"]))["stage"] == 3
    assert e(_h(), _fresh(stale=["E1: r1 changed"]))["stage"] == 2
    assert e(_h(ev_vivado="earlier"), _fresh())["stage"] == 3
    assert e(_h(), _fresh(vivado={"handover": "2025.9", "now": H.VIVADO}))["stage"] == 3
    assert e(_h(), _fresh(build_id={"handover": "aa", "now": "bb"}))["stage"] == 3
    r = e(_h(), _fresh(kb_pin={"handover": "a", "now": "b"}))
    assert r["stage"] == P.DOC_ONLY and r["notes"]                               # a KB pin change is reported only
    gates = {n: "pass" for n in D.STAGE_NAMES}
    gates["timing-closure"] = "fail"
    assert e(_h(gates=gates, stage="built"), _fresh())["stage"] == 6              # agent gates: continue at the first non-pass
    assert e(_h(stage="simulated"), _fresh())["stage"] == 3                       # human handover: continue from its state
    assert e(_h(), _fresh(), "rename a signal", kind="constraints")["stage"] == 3
    assert e(_h(), _fresh(changed_files=["designs/x/rtl/a.sv"]), from_stage=5)["stage"] == 5


def test_resume_dry_run_on_t1(capsys) -> None:
    from agent.__main__ import main
    rc = main(["resume", str(ROOT / "designs" / "t1_dimmer_counter"), "Rename the internal tick counter signal", "--dry-run"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["entry"]["stage"] == 2 and out["errors"] == []
    assert out["agent_md_tokens"] < out["design_files_tokens"]


def test_resume_refuses_a_design_without_the_agent_layout(capsys) -> None:
    from agent.__main__ import main
    from agent.graph import run as gr
    from agent.tests.request_golden import _Ok
    d = ROOT / "designs" / "b2_mic_pdm"
    ld = P.load(d, deep=False)
    entry = P.entry_stage(ld["handover"], ld["fresh"], "fix a bug")
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    old, gr.RUNS = gr.RUNS, runs
    try:
        rt = gr.new_runtime(gr.Config(spec_md=ROOT / "designs" / "t1_dimmer_counter" / "spec.md", name="b2_mic_pdm"),
                            lambda *a, **k: None, runner=_Ok())
        with pytest.raises(P.PickupError):
            P.prepare(d, rt, entry, "fix a bug")
    finally:
        gr.RUNS = old
        shutil.rmtree(runs, ignore_errors=True)


def test_prepare_rebuilds_the_run_state() -> None:
    from agent.graph import run as gr
    from agent.tests.request_golden import _Ok
    from flow import architecture as arch
    d = ROOT / "designs" / "t1_dimmer_counter"
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    old, gr.RUNS = gr.RUNS, runs
    try:
        rt = gr.new_runtime(gr.Config(spec_md=d / "spec.md", name=d.name), lambda *a, **k: None, runner=_Ok())
        entry = {"stage": 2, "kind": "rtl", "reasons": [], "notes": []}
        st = P.prepare(d, rt, entry, "Rename the tick counter")
        assert st["stage"] == 2 and st["owners"] == {"rtl": [st["owners"]["rtl"][0]]} and st["note_role"] == "rtl"
        assert st["resumed_from"] == "designs/t1_dimmer_counter"
        assert not (rt.design / "handover.yaml").exists() and not (rt.design / "README.md").exists()
        assert (rt.design / "rtl").is_dir() and arch.approval_status(rt.design)[0]
        assert "designs/t1_dimmer_counter" not in (rt.design / "build.yaml").read_text()
    finally:
        gr.RUNS = old
        shutil.rmtree(runs, ignore_errors=True)


def test_review_round_defeats_are_closed(run_copy) -> None:
    """Fix round of the adversarial review: laundering numbers through model-written names, success claims against failed
    gates, a non-dict target, rewording a required gap after the fact."""
    good = json.loads((REC / C14 / "doc_calls.jsonl").read_text().splitlines()[-1])["reply"]   # the reply that passed the gate
    y = D.parse_reply(good)
    for bad in ({"interfaces": (y.get("interfaces") or []) + [{"name": "clk 731.25 MHz", "type": "clock", "note": "a clock pin"}]},
                {"summary": y["summary"] + " The design was signed off and meets timing."},
                {"target": 5}):
        z = {**y, **bad}
        res = _doc(run_copy, lambda s, u, z=z: "```yaml\n" + yaml.safe_dump(z) + "```")
        if "target" in bad:
            assert res["problems"] != [] or res["ok"]          # never an uncaught crash
        else:
            assert not res["ok"], bad
    res = _doc(run_copy, D.replay_llm(REC / C14 / "doc_calls.jsonl"))
    assert res["ok"]
    d = run_copy / "c14_int8_dot_requant"
    h = H.load(d)
    g = next(x for x in h["gaps"] if x["about"] in res["required_gaps"])
    g["text"] = "this is fine really, nothing to see"
    (d / "handover.yaml").write_text(H.dump(h))
    H.write(d, build_id=False)
    assert any("reworded" in e for e in D.recheck(d))
    h["produced_by"] = "human"
    (d / "handover.yaml").write_text(H.dump(h))
    assert any("produced_by" in e for e in D.recheck(d))


def test_resumed_run_with_carried_stages_can_sign_off(run_copy) -> None:
    s = json.loads((run_copy / "summary.json").read_text())
    d = run_copy / "c14_int8_dot_requant"
    late = {n: True for n in D.STAGE_NAMES[3:]}
    h, req = D.draft(d, run_copy, run_id=C14, board="nexys_a7_100t", gates_last=late, stop="done",
                     resumed_from="designs/x", carried=list(D.STAGE_NAMES[:3]))
    assert all(r == "pass" for r in h["state"]["gates"].values()) and h["state"]["stage"] == "signed-off"
    h2, _ = D.draft(d, run_copy, run_id=C14, board="nexys_a7_100t", gates_last=late, stop="done", resumed_from="designs/x")
    assert h2["state"]["stage"] != "signed-off"               # not-run stages never make a signed-off handover


def test_from_stage_is_clamped_and_added_files_count() -> None:
    with pytest.raises(P.PickupError):
        P.entry_stage(_h(), _fresh(), from_stage=11)
    r = P.entry_stage(_h(), _fresh(changed_files=["designs/x/rtl/a.sv"]), from_stage=5)
    assert r["stage"] == 5 and r["notes"]
    assert P.entry_stage(_h(), _fresh(added_files=["designs/x/rtl/extra.sv"]))["stage"] == 2
