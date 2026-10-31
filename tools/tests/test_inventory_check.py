"""tools/inventory_check.py: the real Nexys A7 inventory passes; each kind of mistake is caught."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from tools import inventory_check as ic

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "boards" / "nexys_a7_100t"


def test_real_inventory_passes() -> None:
    assert ic.check(BOARD, ROOT / "designs") == []
    assert ic.main([str(BOARD)]) == 0


@pytest.fixture
def board(tmp_path: Path) -> Path:
    d = tmp_path / "nexys_a7_100t"
    shutil.copytree(BOARD, d)
    return d


def edit(board: Path, fn) -> list[str]:
    f = board / "inventory.yaml"
    inv = yaml.safe_load(f.read_text())
    fn(inv)
    f.write_text(yaml.safe_dump(inv, sort_keys=False))
    return ic.check(board)


def periph(inv: dict, pid: str) -> dict:
    return next(p for p in inv["peripherals"] if p["id"] == pid)


def test_wrong_pin_is_caught(board: Path) -> None:
    probs = edit(board, lambda inv: periph(inv, "temperature_sensor")["pins"]["TMP_SCL"].update(pin="C15"))
    assert "temperature_sensor: TMP_SCL pin C15 but the master XDC says C14" in probs
    assert "temperature_sensor: pin C15 (TMP_SDA) also belongs to temperature_sensor (TMP_SCL)" in probs


def test_wrong_iostandard_and_unknown_port(board: Path) -> None:
    def f(inv: dict) -> None:
        periph(inv, "accelerometer")["pins"]["ACL_MISO"]["iostandard"] = "LVCMOS18"
        periph(inv, "accelerometer")["pins"]["ACL_FOO"] = {"pin": "A2", "iostandard": "LVCMOS33", "dir": "in"}
    probs = edit(board, f)
    assert "accelerometer: ACL_MISO iostandard LVCMOS18 but the master XDC says LVCMOS33" in probs
    assert any("port ACL_FOO is not in" in p for p in probs)


def test_pin_shared_by_two_peripherals(board: Path) -> None:
    def f(inv: dict) -> None:
        periph(inv, "pdm_microphone")["pins"]["TMP_SCL"] = {"pin": "C14", "iostandard": "LVCMOS33", "dir": "in"}
    assert "pdm_microphone: pin C14 (TMP_SCL) also belongs to temperature_sensor (TMP_SCL)" in edit(board, f)


def test_missing_field_source_and_unknown_document(board: Path) -> None:
    def f(inv: dict) -> None:
        p = periph(inv, "ethernet_phy")
        del p["clocking"]
        del p["sources"]["pullups"]
        p["sources"]["current"] = ["NOSUCHDOC p.3"]
    probs = edit(board, f)
    assert "ethernet_phy: missing field 'clocking'" in probs
    assert "ethernet_phy: field 'pullups' has no source" in probs
    assert "ethernet_phy: source 'NOSUCHDOC p.3' of 'current' names no document in documents" in probs


def test_bad_verdict_and_empty_pins(board: Path) -> None:
    def f(inv: dict) -> None:
        periph(inv, "qspi_flash")["usb_power_safe"] = {"verdict": "probably", "reason": ""}
        del periph(inv, "ddr2")["pins_note"]
    probs = edit(board, f)
    assert any(p.startswith("qspi_flash: usb_power_safe.verdict 'probably'") for p in probs)
    assert "qspi_flash: usb_power_safe has no reason" in probs
    assert "ddr2: no pins and no pins_note" in probs


def test_uncovered_xdc_port_and_wrong_section_count(board: Path) -> None:
    def f(inv: dict) -> None:
        del periph(inv, "usb_hid_host")["pins"]["PS2_DATA"]
        next(c for c in inv["core_io"] if c["id"] == "switches")["pin_count"] = 15
    probs = edit(board, f)
    assert "master XDC port PS2_DATA (B2) is in no peripheral and no core_io section" in probs
    assert "core_io switches: section 'Switches' has 16 ports, pin_count says 15" in probs


def test_design_xdc_with_wrong_iostandard(tmp_path: Path) -> None:
    designs = tmp_path / "designs"
    (designs / "bad").mkdir(parents=True)
    (designs / "bad" / "design.xdc").write_text(
        "set_property -dict { PACKAGE_PIN C14   IOSTANDARD LVCMOS18 } [get_ports { scl }];\n"
        "set_property -dict { PACKAGE_PIN Z99   IOSTANDARD LVCMOS33 } [get_ports { nowhere }];\n")
    probs = ic.check(BOARD, designs)
    assert "designs/bad/design.xdc: scl on C14 uses LVCMOS18, the master XDC LVCMOS33 (TMP_SCL)" in probs
    assert any("nowhere on Z99" in p for p in probs)
