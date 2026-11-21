"""Brief 131: the dbg_xvc board test's verdict logic (pure Python; the board test itself has not run), the debug build's source set, and the rule that the default and latency builds are unchanged."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import yaml

from designs.b96_kr260_10g.dbg_xvc.model.xvc_verdict import ILA_SAMPLES, N_CAPTURES, verdict

D = Path(__file__).resolve().parents[1]
GOOD = {
    "jtag_cable_used": False,
    "heartbeat_gaps_s": [1.0, 1.1, 1.0],
    "dmesg_new_errors": [],
    "xvc": {"connected": True, "ila_count": 1, "probe_width": 38, "connect_s": 12.0},
    "held_trigger_s": 30.5,
    "captures": [{"ok": True, "samples": ILA_SAMPLES} for _ in range(N_CAPTURES)],
    "static_bits": {"rx_los": 1, "mod_abs": 0, "tx_fault": 0, "pgood": 1},
}


def test_verdict_passes_a_good_record():
    assert verdict(GOOD)[0] == "PASS"


def test_verdict_fails_each_pre_registered_criterion():
    def mut(f):
        r = copy.deepcopy(GOOD)
        f(r)
        return verdict(r)[0]
    assert mut(lambda r: r.update(jtag_cable_used=True)) == "FAIL"
    assert mut(lambda r: r["heartbeat_gaps_s"].append(5.0)) == "FAIL"
    assert mut(lambda r: r["dmesg_new_errors"].append("x")) == "FAIL"
    assert mut(lambda r: r["xvc"].update(connected=False)) == "FAIL"
    assert mut(lambda r: r["xvc"].update(ila_count=2)) == "FAIL"
    assert mut(lambda r: r["xvc"].update(connect_s=90.0)) == "FAIL"
    assert mut(lambda r: r.update(held_trigger_s=3.0)) == "FAIL"
    assert mut(lambda r: r["captures"].pop()) == "FAIL"
    assert mut(lambda r: r["captures"][3].update(samples=100)) == "FAIL"
    assert mut(lambda r: r["static_bits"].update(rx_los=0)) == "FAIL"


def test_verdict_missing_key_is_a_fail_not_a_pass():
    for k in GOOD:
        r = copy.deepcopy(GOOD)
        del r[k]
        assert verdict(r)[0] == "FAIL", k


def test_dbg_xvc_build_differs_from_eyescan_only_in_the_debug_files():
    a = yaml.safe_load((D / "eyescan" / "build.yaml").read_text())
    b = yaml.safe_load((D / "dbg_xvc" / "build.yaml").read_text())
    assert a["generics"] == b["generics"] and a["constraints"] == b["constraints"]
    sa, sb = set(a["sources"]), set(b["sources"])
    assert sa - sb == {"designs/b96_kr260_10g/rtl/b96_core.sv", "designs/b96_kr260_10g/rtl/kr260_10g_top.sv"}
    assert sb - sa == {"designs/b96_kr260_10g/dbg_xvc/rtl/b96_core.sv", "designs/b96_kr260_10g/dbg_xvc/rtl/kr260_10g_top.sv",
                       "designs/b96_kr260_10g/dbg_xvc/rtl/xvc_debug.sv"}
    assert b["ip_tcl"] == a["ip_tcl"] + ["designs/b96_kr260_10g/ip/amd_ip_xvc.tcl"]


def test_dbg_xvc_core_is_the_base_core_plus_read_only_taps():
    base = (D / "rtl" / "b96_core.sv").read_text().splitlines()
    dbg = (D / "dbg_xvc" / "rtl" / "b96_core.sv").read_text().splitlines()
    added = [ln for ln in dbg if ln not in base]
    assert all("dbg_" in ln or "brief 131" in ln or ln.strip().startswith("rxpmadone") or ln.strip().startswith("output logic [1:0]  led") for ln in added), added
    assert [ln for ln in base if ln not in dbg] == ["    output logic [1:0]  led"]


def test_no_build_of_record_uses_the_debug_files():
    for name in ("rm_gp", "rm_gp_bypass", "lat_all3", "lat_all3_bypass", "rm_gp_ml", "eyescan"):
        p = D / name / "build.yaml"
        if p.exists():
            assert not re.search(r"dbg_xvc|xvc_debug|amd_ip_xvc", p.read_text()), name
    assert not re.search(r"dbg_xvc|xvc", (D / "build.yaml").read_text())
