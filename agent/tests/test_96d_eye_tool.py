"""Brief 96D: the eye_scan tool through the registry: reads a capture inside the design directory, never runs the board, never passes a synthetic capture."""

from __future__ import annotations

from pathlib import Path

from agent.core import registry
from agent.core import tools as _t  # noqa: F401
from agent.core.session import ROOT, Session
from flow.eyescan import capture as C
from flow.eyescan import fake, hw, scan

DESIGN = ROOT / "designs" / "b96_kr260_10g"


def _cap(tmp: Path) -> Path:
    cap = scan.run_scan(hw.EyeHW(fake.FakeBoard(seed=1)), scan.ScanConfig(target_ber=1e-6, hstep=4, vstep=16, vmax=112), synthetic=True, design={})
    return C.save(cap, tmp / "eye.json")


def test_eye_scan_is_registered_and_not_a_hardware_tool() -> None:
    assert "eye_scan" in registry.TOOLS and registry.TOOLS["eye_scan"].hardware is False


def test_reads_a_capture_and_refuses_to_pass_a_synthetic_one(tmp_path: Path) -> None:
    d = tmp_path / "designs" / "x"
    d.mkdir(parents=True)
    _cap(d)
    s = Session(design=d, root=tmp_path)
    r = registry.dispatch(s, "eye_scan", {"capture": "eye.json", "depth": 1e-6, "min_width_ui": 0.3, "min_height_mv": 30})
    assert r["ok"] and r["eye_scan"]["synthetic"] and r["eye_scan"]["pass"] is False
    assert "SYNTHETIC" in r["output"] and "AFTER the equaliser" in r["output"] and "NOT PASSED" in r["output"]
    assert r["eye_scan"]["width_ui"] > 0.3 and r["eye_scan"]["width_margin_ui"] > 0


def test_measure_returns_the_owner_plan_and_does_not_touch_the_board() -> None:
    r = registry.dispatch(Session(design=DESIGN, board="kr260"), "eye_scan", {"measure": True})
    assert r["ok"] and r.get("plan") and "owner" in r["output"] and "run_96d_stage3.sh" in r["output"]


def test_path_outside_the_design_and_bad_arguments_are_refused(tmp_path: Path) -> None:
    d = tmp_path / "designs" / "x"
    d.mkdir(parents=True)
    s = Session(design=d, root=tmp_path)
    r = registry.dispatch(s, "eye_scan", {"capture": "../../../etc/passwd"})
    assert not r["ok"]
    assert not registry.dispatch(s, "eye_scan", {"capture": "eye.json", "depth": 5})["ok"]
    assert not registry.dispatch(s, "eye_scan", {"capture": "nothing.json"})["ok"]
    assert not registry.dispatch(s, "eye_scan", {"capture": "eye.json", "bogus": 1})["ok"]
