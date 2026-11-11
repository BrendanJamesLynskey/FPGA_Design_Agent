"""Brief 21: every build's gates.json says which Vivado ran it and whether that is the version the knowledge bank was measured on."""

from __future__ import annotations

import json
from pathlib import Path

from flow import gates, version_pin

DATA = Path(__file__).parent / "data"


def test_build_version_from_run_json_and_from_a_report(tmp_path):
    assert version_pin.build_version(tmp_path, {"vivado_version": "2025.2"}) == "2025.2"
    assert version_pin.build_version(tmp_path, {"vivado_version": "2026.1.1"}) == "2026.1"
    (tmp_path / "x.rpt").write_text("| Tool Version : Vivado v.2026.1 (lin64) Build 1\n")
    assert version_pin.build_version(tmp_path, None) == "2026.1"
    assert version_pin.build_version(tmp_path / "none", None) is None


def test_record_and_note():
    same = version_pin.record(Path("."), {"vivado_version": version_pin.KB_MEASURED_VERSION})
    assert same["kb_version_match"] is True and version_pin.note(same) is None
    other = version_pin.record(Path("."), {"vivado_version": "2025.2"})
    assert other["kb_version_match"] is False and "2025.2" in version_pin.note(other)
    unknown = version_pin.record(Path("/nonexistent"), None)
    assert unknown["kb_version_match"] is None and version_pin.note(unknown) is None


def test_gates_json_carries_the_version(tmp_path):
    for f in DATA.glob("good_*.rpt"):
        (tmp_path / f.name.replace("good_", "").replace("_synth", "")).write_text(f.read_text())
    (tmp_path / "run.json").write_text(json.dumps({"vivado_version": "2025.2"}))
    r = gates.evaluate(tmp_path)
    assert r["vivado_version"] == "2025.2" and r["kb_measured_version"] == "2026.1" and r["kb_version_match"] is False


def test_vivado_path_has_one_source():
    """Brief 48: $VIVADO wins, then $FDA_VIVADO_VERSION, then the default; the flow's three entry points all read it."""
    assert version_pin.vivado_path({}) == f"/opt/Xilinx/{version_pin.DEFAULT_VIVADO_VERSION}/Vivado/bin/vivado"
    assert version_pin.vivado_path({"FDA_VIVADO_VERSION": "2025.2"}) == "/opt/Xilinx/2025.2/Vivado/bin/vivado"
    assert version_pin.vivado_path({"VIVADO": "/x/vivado", "FDA_VIVADO_VERSION": "2025.2"}) == "/x/vivado"
    root = Path(__file__).resolve().parents[2]
    for f in ("flow/run_vivado.sh", "flow/hw.py", "hil/cdc_soak/run_build.sh"):
        assert "Xilinx/20" not in (root / f).read_text(), f
