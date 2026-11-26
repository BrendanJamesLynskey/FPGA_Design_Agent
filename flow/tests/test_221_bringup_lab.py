"""Brief 221: the bring-up runs a design's instrument steps (lab_steps.yaml) as its own step, with mock instruments and a mock bus: no board, no instrument."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from flow import bringup
from flow.tests.test_209a_jtag_bringup import design as toy_design, H
from hil import lab as L
from hil import lab_bringup as B
from hil import lab_drivers as D
from hil.tests.test_221_lab import WIRED, counter, lab_of


def run_bringup(tmp_path, monkeypatch, d, lab_runner):
    mod = H.load_hw_checks(d)
    monkeypatch.setattr(bringup.hw, "ROOT", tmp_path)
    monkeypatch.setattr(bringup.program, "program", lambda *a, **k: {"pass": True, "build_stamp": "ab12", "build_id": "1234abcd"})

    class FakeServer:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
    monkeypatch.setattr(bringup.hw, "HwServer", FakeServer)
    monkeypatch.setattr(bringup.hw, "git_commit", lambda: ("0" * 40, False))
    shared = mod.make_mock()
    shared.BUILD = 0x1234ABCD
    run = bringup.Run(d, "kr260", False, tmp_path / "res", cable_serial="SERIAL123456", bus_factory=lambda s: shared, lab_runner=lab_runner)
    rc = run.run()
    return rc, json.loads((tmp_path / "res" / "toy_bringup.json").read_text())


def write_steps(d, expected=25e6):
    lab = lab_of(counter(), conns=WIRED)
    steps = [{"id": "wire", "kind": "confirm", "method": "manual", "instrument": "counter", "channel": "A", "prompt": "wired?"},
             {"id": "req_13_counter", "kind": "measure", "method": "scripted", "instrument": "counter", "channel": "A", "quantity": "frequency",
              "expected": expected, "tolerance_ppm": 100.0, "requirement": "REQ-13"}]
    (d / "lab_steps.yaml").write_text(yaml.safe_dump({"steps": steps}))
    return lab


def mock_runner(lab, value):
    def run(design):
        return B.run_for_design(design, dry_run=False, lab=lab, confirm=lambda p: True,
                                open_fn=lambda e, l, **kw: D.MockInstrument(e, l, {("frequency", "A"): value}))
    return run


def test_a_design_without_instrument_steps_has_the_same_step_list_as_before(tmp_path, monkeypatch):
    d = toy_design(tmp_path)
    rc, rec = run_bringup(tmp_path, monkeypatch, d, None)
    assert rc == 0 and list(rec["steps"]) == ["discover", "program_base", "bus_checks", "still_alive"]


def test_the_instrument_step_runs_between_the_bus_checks_and_still_alive_and_records_each_reading(tmp_path, monkeypatch):
    d = toy_design(tmp_path)
    lab = write_steps(d)
    rc, rec = run_bringup(tmp_path, monkeypatch, d, mock_runner(lab, 25.0004e6))
    assert rc == 0 and list(rec["steps"]) == ["discover", "program_base", "bus_checks", "lab_instruments", "still_alive"]
    rows = rec["steps"]["lab_instruments"]["rows"]
    assert [r["result"] for r in rows] == ["confirmed", "pass"] and rows[1]["value"] == 25.0004e6 and rows[1]["requirement"] == "REQ-13"
    assert json.loads((d / "build" / "lab" / "results.json").read_text())["evidence"] is False                  # the readings came from a mock instrument


def test_a_failed_instrument_reading_fails_the_bringup_and_names_the_step(tmp_path, monkeypatch):
    d = toy_design(tmp_path)
    lab = write_steps(d)
    rc, rec = run_bringup(tmp_path, monkeypatch, d, mock_runner(lab, 26e6))
    assert rc == 1 and rec["failed_step"] == "lab_instruments" and "req_13_counter: fail" in rec["steps"]["lab_instruments"]["why"]
    assert "still_alive" not in rec["steps"]
