"""Seeded faults for ddr2_sched (brief 141): one deliberate bug each in a copy of the RTL (a timing constant short, the dependency check removed, the refresh disabled, a wrong bank on the command bus, ...)
must make the bench of tb/tb_ddr2.sv report it. The rtl/ files are never edited."""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
D = HERE.parent
sys.path.insert(0, str(HERE))
import m141_measure as measure  # noqa: E402
import m141_timing as timing  # noqa: E402

RTL = D / "rtl"



@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return tmp_path_factory.mktemp("m141f")


# one deliberate bug each: (name, regex on ddr2_sched.sv, replacement, traffic (pattern, gap, requests), policy)
FAULTS = [
    ("trcd_short", r"c_col\[d_bank\] <= ld\(c_col\[d_bank\], T_RCD\);", "c_col[d_bank] <= ld(c_col[d_bank], T_RCD - 1);", (0, 40, 200), 0),
    ("tras_short", r"c_pre\[d_bank\] <= ld\(c_pre\[d_bank\], T_RAS\);", "c_pre[d_bank] <= ld(c_pre[d_bank], T_RAS - 3);", (1, 5, 250), 1),
    ("trp_short", r"c_rp\[d_bank\] <= ld\(c_rp\[d_bank\], T_RP\);", "c_rp[d_bank] <= ld(c_rp[d_bank], T_RP - 1);", (0, 40, 200), 0),
    ("trrd_short", r"c_rrd <= ld\(c_rrd, T_RRD\);", "c_rrd <= ld(c_rrd, T_RRD - 2);", (0, 0, 300), 1),
    ("tfaw_short", r"c_faw\[faw_z\] <= CNW'\(T_FAW - 1\);", "c_faw[faw_z] <= CNW'(T_FAW - 8);", (0, 0, 300), 1),
    ("twr_short", r"c_pre\[d_bank\] <= ld\(c_pre\[d_bank\], W2P\);", "c_pre[d_bank] <= ld(c_pre[d_bank], W2P - 2);", (1, 0, 300), 0),
    ("trtp_short", r"c_pre\[d_bank\] <= ld\(c_pre\[d_bank\], R2P\);", "c_pre[d_bank] <= ld(c_pre[d_bank], R2P - 2);", (5, 0, 300), 1),
    ("twtr_short", r"c_rd <= ld\(c_rd, W2R\);", "c_rd <= ld(c_rd, W2R - 2);", (1, 0, 300), 0),
    ("rtw_short", r"c_wr <= ld\(c_wr, RTW\);", "c_wr <= ld(c_wr, RTW - 2);", (5, 0, 400), 1),
    ("ccd_short", r"c_rd <= ld\(c_rd, BL2\);", "c_rd <= ld(c_rd, BL2 - 2);", (2, 0, 200), 1),
    ("trfc_short", r"c_rfc <= CNW'\(T_RFC - 1\);", "c_rfc <= CNW'(T_RFC - 20);", (0, 30, 300), 0),
    ("refresh_with_open_bank", r"end else if \(!any_open && all_rp_ok && \(c_rfc == '0\)\) begin", "end else if (all_rp_ok && (c_rfc == '0)) begin", (0, 0, 1000), 1),
    ("refresh_never", r"ref_want = \(debt != '0\) && \(\(debt > 4'\(REF_POST\)\) \|\| \(!ref_defer && idle_ok\)\);", "ref_want = 1'b0;", (0, 40, 700), 0),
    ("dependency_dropped", r"dep\[free_i\] <= conf;", "dep[free_i] <= '0;", (5, 0, 400), 1),
    ("wrong_bank_on_column", r"cmd_bank <= d_bank;", "cmd_bank <= d_bank ^ BW'(1);", (0, 40, 100), 0),
    ("wrong_row_opened", r"orow\[d_bank\] <= d_row;", "orow[d_bank] <= d_row ^ RW'(1);", (0, 40, 100), 0),
]


@pytest.mark.parametrize("name,pat,rep,traffic,pol", FAULTS, ids=[f[0] for f in FAULTS])
def test_seeded_fault(tmp_path, name, pat, rep, traffic, pol):
    src = (RTL / "ddr2_sched.sv").read_text()
    new, n = re.subn(pat, rep, src)
    assert n >= 1 and new != src, f"the substitution for {name} matched nothing"
    rd = tmp_path / "rtl"
    rd.mkdir()
    (rd / "ddr2_sched.sv").write_text(new)
    shutil.copy(RTL / "ddr2_addrmap.sv", rd / "ddr2_addrmap.sv")
    pat_, gap, n_req = traffic
    r = measure.run(tmp_path, "nexys_650", pol, pat_, gap, n_req, rtl_dir=rd)
    assert not r["pass"] and (r.get("violations", 1) > 0 or r.get("hazards", 0) > 0 or r.get("badreq", 0) > 0 or "error" in r), r


