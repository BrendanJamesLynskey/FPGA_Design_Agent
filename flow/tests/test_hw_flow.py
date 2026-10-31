"""The F0B hardware flow without hardware: flash refusal, the power gate, board
discovery's refusals, serial redaction, and the ILA capture reader and checks on the
committed captures (results/f0b/captures/), unchanged and deliberately corrupted."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from designs.t1_dimmer_counter import hw_checks
from flow import hw, hw_discover, ila, program

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data"
CAPS = ROOT / "results" / "f0b" / "captures"
NAME = "t1_dimmer_counter"


# --- programming never writes flash -------------------------------------------------

@pytest.mark.skipif(shutil.which("tclsh") is None, reason="needs tclsh")
@pytest.mark.parametrize("args", [
    ["SERIAL", "t1.bit", "--flash"], ["SERIAL", "t1.mcs"], ["SERIAL", "t1.bit", "-cfgmem"],
    ["SERIAL", "t1.bin"], ["SERIAL", "t1.bit", "t1.ltx", "-write_qspi"], ["SERIAL", "t1.prm"],
])
def test_program_tcl_refuses_flash_before_touching_hardware(args: list[str]) -> None:
    r = subprocess.run(["tclsh", str(ROOT / "flow" / "program.tcl"), *args], capture_output=True, text=True)
    assert r.returncode != 0
    assert "REFUSED" in r.stdout and "volatile SRAM only" in r.stdout


@pytest.mark.skipif(shutil.which("tclsh") is None, reason="needs tclsh")
@pytest.mark.parametrize("args", [["SERIAL"], ["SERIAL", "t1.dcp"], ["SERIAL", "t1.bit", "t1.txt"]])
def test_program_tcl_refuses_bad_arguments(args: list[str]) -> None:
    r = subprocess.run(["tclsh", str(ROOT / "flow" / "program.tcl"), *args], capture_output=True, text=True)
    assert r.returncode != 0 and "REFUSED" in r.stdout


def test_program_py_refuses_flash(capsys: pytest.CaptureFixture[str]) -> None:
    assert program.main(["designs/t1_dimmer_counter", "base", "--flash"]) == 2
    assert "volatile SRAM only" in capsys.readouterr().err


# --- power gate (power_ok, brief 04c) ------------------------------------------------

STILL_AIR = (DATA / "still_air_power.rpt").read_text()   # b2_tmp_adt7420: 0.116 W, Tj 42.1 C, 0 LFM, no heat sink


def _report(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "power.rpt").write_text(text)
    return d


def _total(text: str, watts: str) -> str:
    return text.replace("| Total On-Chip Power (W)  | 0.116        |", f"| Total On-Chip Power (W)  | {watts:<12} |")


def test_power_gate_usb_and_wall(tmp_path: Path) -> None:
    good = _report(tmp_path, "good", STILL_AIR)
    g = hw.power_ok(good, source="usb")
    assert g["pass"] and g["total_w"] == 0.116 and g["limit_w"] == 0.5 and g["junction_c"] == 42.1
    assert g["environment"]["airflow_lfm"] == 0 and g["environment"]["heatsink"] == "none"
    assert g["supplies_a"]["vccint"] == 0.031
    mid = _report(tmp_path, "mid", _total(STILL_AIR, "0.612"))
    u = hw.power_ok(mid, source="usb")
    assert not u["pass"] and "above the usb-power limit 0.5 W" in u["why"]
    w = hw.power_ok(mid, source="wall")
    assert w["pass"] and w["limit_w"] == 2.0
    hot = _report(tmp_path, "hot", _total(STILL_AIR, "2.100"))
    assert "above the wall-power limit 2.0 W" in hw.power_ok(hot, source="wall")["why"]
    assert not hw.power_ok(tmp_path / "missing", source="wall")["pass"]


def test_power_gate_junction_temperature(tmp_path: Path) -> None:
    tj = STILL_AIR.replace("| Junction Temperature (C) | 42.1         |", "| Junction Temperature (C) | 85.4         |")
    r = hw.power_ok(_report(tmp_path, "tj", tj), source="wall")
    assert not r["pass"] and "junction temperature 85.4 C is above 85.0 C" in r["why"]


def test_power_gate_rail_limits(tmp_path: Path) -> None:
    hot = STILL_AIR.replace("| Vccint    |       1.000 |     0.031 |", "| Vccint    |       1.000 |     2.500 |")
    r = hw.power_ok(_report(tmp_path, "vccint", hot), source="wall")
    assert not r["pass"] and "vccint current 2.5 A is above 2.4 A" in r["why"]
    aux = STILL_AIR.replace("| Vccaux    |       1.800 |     0.019 |", "| Vccaux    |       1.800 |     0.370 |")
    r = hw.power_ok(_report(tmp_path, "aux", aux), source="wall")
    assert not r["pass"] and "rail_1v8 current 0.39 A is above 0.38 A" in r["why"]   # 0.370 + 0.020 VCCADC
    assert hw.power_ok(_report(tmp_path, "ok", STILL_AIR), source="wall")["rails"]["rail_1v8"]["a"] == 0.039


def test_power_gate_refuses_vivado_default_environment(tmp_path: Path) -> None:
    # F0B's T1 report: 0.133 W, but computed for 250 LFM airflow and a medium heat sink
    r = hw.power_ok(_report(tmp_path, "f0b", (DATA / "good_power.rpt").read_text()), source="usb")
    assert not r["pass"] and "airflow 250.0 LFM and heat sink medium" in r["why"]


def test_power_source_from_board_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "boards.yaml"
    monkeypatch.setattr(hw, "BOARDS_FILE", f)
    assert hw.power_source("nexys_a7_100t")[0] == "usb"                        # no file: usb
    f.write_text("boards:\n  nexys_a7_100t:\n    cable_serial: X\npower_source: wall\n")
    assert hw.power_source("nexys_a7_100t")[0] == "usb"                        # top-level key is not the board's
    f.write_text("boards:\n  nexys_a7_100t:\n    cable_serial: X\n    power_source: battery\n")
    assert hw.power_source("nexys_a7_100t")[0] == "usb"                        # unknown value: usb
    f.write_text("boards:\n  nexys_a7_100t:\n    cable_serial: X\n    power_source: wall\n")
    assert hw.power_source("nexys_a7_100t") == ("wall", f"{f} boards.nexys_a7_100t.power_source")
    mid = _report(tmp_path, "mid", _total(STILL_AIR, "0.612"))
    assert hw.power_ok(mid, "nexys_a7_100t")["pass"]                          # wall, from the file
    hw.save_board("nexys_a7_100t", {"cable_serial": "Y", "uart": "/dev/x"})  # rediscovery keeps the source
    assert hw.power_source("nexys_a7_100t")[0] == "wall"
    assert hw.load_board("nexys_a7_100t")["cable_serial"] == "Y"


# --- discovery refuses to guess -------------------------------------------------------

LIST_ONE = """FDA-TARGET Digilent/123456ABCDEFA localhost:3121/xilinx_tcf/Digilent/123456ABCDEFA
FDA-DEVICE Digilent/123456ABCDEFA xc7a100t_0 xc7a100t 13631093
FDA-LIST-DONE
"""


def test_discover_accepts_one_board() -> None:
    uid, t = hw_discover.decide(hw_discover.parse_list(LIST_ONE), "xc7a100t")
    assert uid == "Digilent/123456ABCDEFA" and t["devices"][0]["part"] == "xc7a100t"
    assert hw_discover.usb_serial(hw_discover.cable_serial(uid)) == "123456ABCDEF"


def test_discover_refuses_two_boards_none_or_wrong_part() -> None:
    two = LIST_ONE.replace("FDA-LIST-DONE\n", LIST_ONE.replace("123456ABCDEF", "99999999FFFF"))
    with pytest.raises(hw.HwError, match="exactly one Digilent JTAG target, found 2"):
        hw_discover.decide(hw_discover.parse_list(two), "xc7a100t")
    with pytest.raises(hw.HwError, match="found 0"):
        hw_discover.decide(hw_discover.parse_list("FDA-LIST-DONE\n"), "xc7a100t")
    with pytest.raises(hw.HwError, match="expected exactly"):
        hw_discover.decide(hw_discover.parse_list(LIST_ONE), "xc7a35t")
    with pytest.raises(hw.HwError, match="did not finish"):
        hw_discover.parse_list(LIST_ONE.replace("FDA-LIST-DONE\n", ""))


def test_uart_is_interface_1_of_the_same_cable() -> None:
    def port(dev: str, loc: str, ser: str) -> SimpleNamespace:
        return SimpleNamespace(device=dev, location=loc, serial_number=ser, vid=0x0403, pid=0x6010)
    ports = [port("/dev/ttyUSB0", "1-2:1.0", "123456ABCDEF"), port("/dev/ttyUSB1", "1-2:1.1", "123456ABCDEF"),
             port("/dev/ttyUSB3", "1-3:1.1", "99999999FFFF")]
    hits = hw_discover.find_uart("123456ABCDEF", ports)
    assert len(hits) == 1 and (hits[0] == "/dev/ttyUSB1" or hits[0].endswith("123456ABCDEF-if01-port0"))


def test_redact_keeps_last_four() -> None:
    assert hw.redact("123456ABCDEFA") == "...DEFA" and hw.redact(None) is None


# --- ILA captures: reader and checks --------------------------------------------------

needs_caps = pytest.mark.skipif(not (CAPS / f"{NAME}_count_write.csv").is_file(), reason="no committed captures")


def load(name: str) -> dict[str, list[int]]:
    return ila.load_capture(CAPS / f"{NAME}_{name}.csv", CAPS / f"{NAME}_probe_map.txt",
                            CAPS / f"{NAME}_hw_probes.txt")


def test_map_bits() -> None:
    assert ila.map_bits("probe8[6:3]") == [6, 5, 4, 3]
    assert ila.map_bits("probe0[13]") == [13]
    assert ila.map_bits("probe0[15:14],probe0[1]") == [15, 14, 1]


@needs_caps
@pytest.mark.parametrize("cap", hw_checks.CAPTURES, ids=lambda c: c.name)
def test_committed_captures_pass_their_checks(cap: hw_checks.Capture) -> None:
    s = load(cap.name)
    assert len(s["count"]) == 1024 and len(s["led"]) == 1024
    r = cap.check(s)
    assert r["pass"], r["errors"]


@needs_caps
def test_count_write_check_catches_an_early_update() -> None:
    s = load("count_write")
    t = hw_checks.check_count_write(s)["write_at_sample"]
    s["count"][t] = hw_checks.COUNT_WRITTEN            # the write taking effect one clock early
    assert not hw_checks.check_count_write(s)["pass"]


@needs_caps
@pytest.mark.parametrize("cap", [c for c in hw_checks.CAPTURES if c.name.startswith("pwm_")], ids=lambda c: c.name)
def test_pwm_check_catches_one_wrong_led_sample_and_a_wrong_duty(cap: hw_checks.Capture) -> None:
    s = load(cap.name)
    k = next(i for i in range(1, 1024) if s["led"][i])
    s["led"][k - 1] = s["led"][k]                       # one LED clock too many
    assert not cap.check(s)["pass"]
    duty = int(cap.name.split("_")[1], 16)
    assert not hw_checks.make_pwm_check(duty + 1)(load(cap.name))["pass"]
