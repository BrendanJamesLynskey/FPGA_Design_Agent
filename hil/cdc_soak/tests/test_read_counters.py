"""Unit tests for host/read_counters.py (no simulator): CRC, each record type, bad lines, the stop rules.
The parser is also run on real simulated UART output by test_cdc_rig_rtl.py."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
import read_counters as rc  # noqa: E402


def line(body: str) -> str:
    return f"{body}*{rc.crc8(body.encode()):02X}\r\n"


def test_crc8_known_value() -> None:
    # CRC-8 (poly 0x07, init 0): the standard check value for "123456789" is 0xF4
    assert rc.crc8(b"123456789") == 0xF4


def test_records_decode() -> None:
    h = rc.parse_line(line("H,CDCRIG,218,1A2B3C4D"))
    assert h == {"kind": "H", "copies": 0x218, "build": "1A2B3C4D"}
    e = rc.parse_line(line("E,0003,000000B4,9A0,555,0FDE8,1"))
    assert e["epoch"] == 3 and e["uptime_s"] == 180 and e["cfgmclk_khz"] == 65000 and e["storm_mode"] == 1
    assert 29 < e["tj_c"] < 31 and 999 < e["vccint_mv"] < 1001
    c = rc.parse_line(line("C,011,10,0,2,000005,0000ABCD,01,02,0"))
    assert c["variant"] == "M2" and c["cls"] == "far" and c["dir"] == "a->c"
    assert (c["errors"], c["events"], c["lockups"], c["relocks"], c["sat"]) == (5, 0xABCD, 1, 2, 0)
    s = rc.parse_line(line("S,TJ,B40,0000012C"))
    assert s["reason"] == "TJ" and s["tj_c"] >= 80 and s["uptime_s"] == 300


@pytest.mark.parametrize("bad", ["C,011,11,0,2,000005,0000ABCD,01,02,0*00", "no star", "X,1*" + "%02X" % rc.crc8(b"X,1"),
                                 line("C,011,1F,0,2,000005,0000ABCD,01,02,0").strip()])
def test_bad_lines(bad: str) -> None:
    with pytest.raises(rc.LineError):
        rc.parse_line(bad)
    assert list(rc.parse_stream([bad]))[0]["kind"] == "bad"


def test_run_summary_and_complete_epochs() -> None:
    text = line("H,CDCRIG,002,00000000") + line("E,0000,0000003C,9A0,555,0FDE8,0") + \
        line("C,001,0E,1,0,000000,00000010,00,00,0") + line("C,000,00,0,0,000000,00000020,00,00,0")
    run = rc.Run()
    for r in rc.parse_stream(text.splitlines()):
        run.add(r)
    assert run.complete_epochs() == [0]
    pv = run.per_variant()
    assert pv["C1"]["events"] == 0x20 and pv["M1"]["events"] == 0x10


def test_follow_stops_on_temperature(tmp_path: Path) -> None:
    src = io.StringIO(line("H,CDCRIG,001,00000000") + line("E,0000,0000003C,B40,555,0FDE8,0"))
    assert rc.follow(src, tmp_path / "r.csv", 60, 80.0) == 2
    assert (tmp_path / "r.csv").read_text().count("\n") == 3          # header + 2 records


def test_follow_stops_on_rig_stop_line() -> None:
    src = io.StringIO(line("S,TJ,B40,0000012C"))
    assert rc.follow(src, None, 60, 80.0) == 2


def test_follow_stops_when_epochs_are_missed() -> None:
    t = iter([0.0, 0.0, 200.0, 200.0])
    src = io.StringIO(line("H,CDCRIG,001,00000000") + line("C,000,00,0,0,000000,00000020,00,00,0"))
    assert rc.follow(src, None, 60, 80.0, clock=lambda: next(t)) == 2


def test_follow_ends_cleanly() -> None:
    src = io.StringIO(line("H,CDCRIG,001,00000000") + line("E,0000,0000003C,9A0,555,0FDE8,0"))
    assert rc.follow(src, None, 60, 80.0) == 0
