"""The ITCH registers of build rm_gp_itch: the generated datasheet is current, the RTL decodes what the map lists and nothing else, and the two host vectors' layouts agree between
rtl/itch_pkg2.sv, regmap_itch.py and the host driver (brief 127; house rule: document wherever a user could be unsure, generate the text and test it)."""
from __future__ import annotations

import re
from pathlib import Path

from designs.b96_kr260_10g import regmap as base
from designs.b96_kr260_10g.rm_gp_itch import regmap_itch as R
from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B

DESIGN = Path(__file__).parent.parent
CORE = (DESIGN / "rtl" / "b96_core.sv").read_text()
PKG2 = (DESIGN / "rtl" / "itch_pkg2.sv").read_text()


def test_datasheet_is_current() -> None:
    assert (DESIGN / "docs" / "register_map.md").read_text() == R.render(), "run: python3 designs/b96_kr260_10g/rm_gp_itch/regmap_itch.py --write"


def test_rtl_decodes_what_the_map_lists() -> None:
    listed = {a for a, *_ in base.REGS} | {a for a, *_ in base.RANGES}
    in_rtl = {int(m, 16) for m in re.findall(r"12'h([0-9A-Fa-f]{3})", CORE)}
    extra_ok = {0x300, 0x380, 0x400}                  # the bounds of the two windows (the words inside are decoded by index)
    assert in_rtl - listed <= extra_ok, sorted(map(hex, in_rtl - listed - extra_ok))
    assert {0x300, 0x380, 0x400} <= in_rtl
    # the eye-scan registers of the base map are in this build too (they read 0), so every base address stays decoded
    assert listed - in_rtl == set(), sorted(map(hex, listed - in_rtl))


def test_pkg2_agrees_with_regmap() -> None:
    names = {"CTRL": "IT_CTRL", "THR": "IT_THR", "QTY": "IT_QTY", "MAXQTY": "IT_MAXQTY", "MAXPOS": "IT_MAXPOS", "BAND": "IT_BAND", "PXOFF": "IT_PXOFF", "MINQTY": "IT_MINQTY",
             "ORDF0": "IT_ORDF0", "ORDF1": "IT_ORDF1", "WATCH": "IT_WATCH0_LO", "FEEDIP": "IT_FEED_IP", "FEEDPORT": "IT_FEED_PORT", "TCPSEQ": "IT_TCP_SEQ", "TCPACK": "IT_TCP_ACK",
             "CMD": "IT_CMD", "RPW": "RP_WADDR", "RPWLO": "RP_WLO", "RPWHI": "RP_WHI", "CAPADDR": "CAP_ADDR", "TCPFA": "TCPF_ADDR", "TCPFD": "TCPF_WDATA", "RPCFG": "RP_CFG"}
    idx = {n: i for i, n, *_ in R.CFG}
    for k, n in names.items():
        m = re.search(rf"\bC_{k} = (\d+)", PKG2)
        assert m and int(m.group(1)) == idx[n], (k, n)
    assert f"NSW = {len(R.STAT_NAMES)};" in PKG2 and "NCW = 32;" in PKG2
    for n, k in (("S_O_SENT", "ord.sent"), ("S_RP_FRAMES", "rp.frames"), ("S_RP_STAT", "rp.stat"), ("S_LAT_LAST", "lat.last"), ("S_HIST", "lat.hist0_1"), ("S_TS_EOF", "ts.eof"), ("S_TS_SOP", "ts.sop"),
                 ("S_FLAGS", "flags"), ("S_CAP_LO", "cap.lo"), ("S_CAP_HI", "cap.hi"), ("S_CAP_ECHO", "cap.echo"), ("S_TCPF_RD", "tcpf.rdata"), ("S_CMD_ECHO", "cmd.echo"), ("S_US", "us.frames"),
                 ("S_O_PZ_ABORT", "ord.pz_abort"), ("S_O_LATE", "ord.late"), ("S_TS_RXSOP", "ts.rxsop"), ("S_O_UNRES", "ord.pz_unres")):
        m = re.search(rf"\b{n} = (\d+)", PKG2)
        assert m and int(m.group(1)) == R.STAT_NAMES.index(k), (n, k)
    # the 45 counters of brief 110 come first, in the order of its package
    pkg110 = (DESIGN.parents[1] / "b110_itch_ouch" / "rtl" / "itch_pkg.sv").read_text()
    from designs.b110_itch_ouch.model.ref import COUNTERS
    assert [n.split(".", 1)[1] for n in R.STAT_NAMES[:45]] == list(COUNTERS)
    assert "NC = 45" in pkg110


def test_each_vector_is_at_most_the_handshake_width() -> None:
    assert 32 * 32 <= 1024            # CFG2: one xpm_cdc_handshake carries at most 1024 bits
    assert 32 * len(R.STAT_NAMES) == 3 * 1024


def test_every_register_has_text() -> None:
    for i, n, acc, rst, d in R.CFG:
        assert n and acc in ("RW", "W", "RO") and d.strip() and rst
    assert B.ADDR["IT_CMD"] == 0x358 and B.STAT["ord.sent"] == 0x400 + 4 * 60
