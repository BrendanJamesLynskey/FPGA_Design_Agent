"""Brief 219 (agent side): fix 6, the Designer's lint applies lint/waivers.yaml (209 pilot p3 run 1), and fix 7, a run paused at the
programming approval leaves summary.json and the DOC step, marked paused (209 pilot, every run that reached stage 9)."""

from __future__ import annotations

import json
import shutil
import uuid

import yaml

from agent.core import dispatch
from agent.core.runner import RunResult
from agent.core.session import ROOT
from agent.tests.conftest import FakeRunner

# what Verilator printed for the supplied jtag_bus.sv in the pilot (two UNUSEDSIGNAL warnings; the file must stay unchanged)
VL = ("%Warning-UNUSEDSIGNAL: {p}:20:5: Signal is not used: 'tdo'\n"
      "                       20 |     input wire tdo,\n                          |                ^~~\n"
      "%Warning-UNUSEDSIGNAL: {p}:41:20: Bits of signal are not used: 'cmd_s'[45]\n"
      "%Error: Exiting due to 2 warning(s)\n")


def _waiver(rel: str, line: int) -> dict:
    return {"rule": "HDL-SIG-01", "match": f"verilator:UNUSEDSIGNAL {rel}:{line}", "owner": "designer", "date": "2026-11-25",
            "reason": "supplied jtag_bus.sv is used unchanged; the signal is unused inside it by design."}


def _setup(session, waive: list[int]) -> str:
    rel = (session.design / "data" / "jtag_bus.sv").relative_to(session.root).as_posix()
    (session.design / "data").mkdir(exist_ok=True)
    (session.design / "data" / "jtag_bus.sv").write_text("module jtag_bus; endmodule\n")
    (session.design / "lint").mkdir(exist_ok=True)
    (session.design / "lint" / "waivers.yaml").write_text(yaml.safe_dump({"waivers": [_waiver(rel, n) for n in waive]}))
    session.runner = FakeRunner({"lint": RunResult(1, "", VL.format(p=rel), 0.1)})
    return rel


def test_lint_applies_the_design_waivers(session) -> None:
    _setup(session, [20, 41])
    r = dispatch(session, "lint", {})
    assert r["ok"] is True and r["returncode"] == 0
    assert "lint/waivers.yaml applied: 2 finding(s) waived, 0 open" in r["output"] and "the run is clean" in r["output"]


def test_a_finding_no_waiver_covers_still_fails_and_is_named(session) -> None:
    _setup(session, [20])
    r = dispatch(session, "lint", {})
    assert r["ok"] is False and r["returncode"] != 0
    assert "1 finding(s) waived, 1 open" in r["output"] and "OPEN verilator:UNUSEDSIGNAL" in r["output"] and ":41" in r["output"]


def test_without_a_waiver_file_lint_is_unchanged(session) -> None:
    session.runner = FakeRunner({"lint": RunResult(1, "", VL.format(p="x/data/jtag_bus.sv"), 0.1)})
    r = dispatch(session, "lint", {})
    assert r["ok"] is False and "waivers.yaml applied" not in r["output"]


def test_a_real_error_is_never_waived(session) -> None:
    rel = _setup(session, [20, 41])
    session.runner = FakeRunner({"lint": RunResult(1, "", VL.format(p=rel) + "%Error: Cannot find file containing module: 'foo'\n", 0.1)})
    r = dispatch(session, "lint", {})
    assert r["ok"] is False and "not waivable" in r["output"]


def test_waiver_with_a_wrong_rule_does_not_hide_the_warning(session) -> None:
    rel = _setup(session, [20, 41])
    w = yaml.safe_load((session.design / "lint" / "waivers.yaml").read_text())
    for x in w["waivers"]:
        x["rule"] = "HDL-RST-01"
    (session.design / "lint" / "waivers.yaml").write_text(yaml.safe_dump(w))
    assert dispatch(session, "lint", {})["ok"] is False


def test_a_paused_run_leaves_a_summary_and_a_doc_marked_paused(monkeypatch) -> None:
    from agent.graph import run as gr
    from agent.tests.request_golden import T1, _Ok
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    try:
        cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", docs="on")
        rt = gr.new_runtime(cfg, lambda *a, **k: None, runner=_Ok())
        rt.doc_llm = lambda s, u: "no yaml"
        pending = {"kind": "review", "stage": 9, "stage_name": "configuration-and-debug", "hardware": True,
                   "fails": ["hardware: awaiting approval before programming"]}
        from agent.graph import requests as rq
        assert not rq.has_ended(rt.run_dir)
        paused = gr.write_paused_record(rt, {"run_id": rt.run_id, "history": []}, pending)
        s = json.loads((rt.run_dir / "summary.json").read_text())
        assert s["paused"] == paused and s["clean_stop"] is False and s["stop"] == gr.PAUSE_STOP
        assert paused["kind"] == "hardware approval" and paused["stage"] == 9 and f"resume {rt.run_id}" in paused["resume"]
        doc = json.loads((rt.run_dir / "doc.json").read_text())
        assert doc["paused"] == paused and doc["signed_off"] is False                 # a pause is never a sign-off
        assert not rq.has_ended(rt.run_dir)                                           # the run can still take a request at its next safe point
        (rt.run_dir / "summary.json").write_text(json.dumps({**s, "paused": None}))   # the final record (no pause) ends the run
        assert rq.has_ended(rt.run_dir)
        cfg.docs = "off"                                                              # docs off: the summary alone
        (rt.run_dir / "summary.json").unlink()
        (rt.run_dir / "doc.json").unlink()
        gr.write_paused_record(rt, {"run_id": rt.run_id, "history": []}, pending)
        assert json.loads((rt.run_dir / "summary.json").read_text())["paused"] and not (rt.run_dir / "doc.json").exists()
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_the_driver_writes_the_record_at_a_hardware_pause_only() -> None:
    import inspect
    from agent import __main__ as m
    src = inspect.getsource(m._drive)
    assert 'pending[0].get("kind") == "review" and pending[0].get("hardware")' in src and "write_paused_record" in src

