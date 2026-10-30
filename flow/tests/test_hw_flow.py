"""The F0B hardware flow without hardware: flash refusal, the USB-power gate, board
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


# --- USB power gate ------------------------------------------------------------------

def test_power_gate(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.mkdir()
    shutil.copy(DATA / "good_power.rpt", good / "power.rpt")
    g = hw.power_ok_usb(good)
    assert g["pass"] and g["total_w"] == 0.133 and g["limit_w"] == 0.5
    hot = tmp_path / "hot"
    hot.mkdir()
    text = (DATA / "good_power.rpt").read_text().replace("| Total On-Chip Power (W)  | 0.133        |",
                                                         "| Total On-Chip Power (W)  | 0.612        |")
    (hot / "power.rpt").write_text(text)
    h = hw.power_ok_usb(hot)
    assert not h["pass"] and h["total_w"] == 0.612 and "above the USB-power limit" in h["why"]
    assert not hw.power_ok_usb(tmp_path / "missing")["pass"]


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
