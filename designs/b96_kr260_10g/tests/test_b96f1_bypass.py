"""Brief 96F1: the bypass build's board driver against a fake board: the lock prefix, the controllers' status bits, the full GT restarts, and the pre-registered verdict
(results/b96f1/preregistration.md). Nothing here touches a board or says anything about what the GT does."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from designs.b96_kr260_10g.host import b96_bench as bb
from designs.b96_kr260_10g.host import b96f1_bypass as f1
from designs.b96_kr260_10g.tests.test_b96_bench import FakeBoard

DESIGN = Path(__file__).resolve().parents[1]


class BypassBoard(FakeBoard):
    """FakeBoard plus the build's GT_BUF bits 15:10 and FEATURES bit 6; each full GT reset takes `lag` status polls to come back."""

    def __init__(self, err_at=None, lag=2, retry_at=None, gave_up_at=None, **kw):
        super().__init__(**kw)
        self.err_at = err_at; self.lag = lag; self.resets = 0; self.polls = 0; self.up_after = 0
        self.retry_at = retry_at; self.gave_up_at = gave_up_at
        self.r[0x008] = 0x6F

    def wr(self, a, v):
        super().wr(a, v)
        if a == 0x010 and v & 1:
            self.resets += 1; self.up_after = self.lag

    def rd(self, a):
        if a == 0x014 and self.up_after > 0:
            self.up_after -= 1
            return 0x0 | (1 << 11)
        if a == 0x020:
            err = 1 if self.err_at == self.resets else 0
            v = 0xC00 if not err else 0xC00 | (1 << 12) | (1 << 14)
            if self.retry_at == self.resets:
                v |= (1 << 16) | (2 << 20) | (1 << 28) | (1 << 29)                   # TX retried once, RX twice, both recovered
            if self.gave_up_at == self.resets:
                v = (3 << 16) | (3 << 20) | (1 << 24) | (1 << 26) | (1 << 28) | (1 << 29)   # TX gave up (3 retries), RX 3 retries, neither done
            return v
        return super().rd(a)


def _stage3(e=17.0, l=46.0, ok=True, failed=0, link=True):
    return {"link_up": link, "restarts": {"restarts": 100, "failed_to_lock": failed, "E_min_per_link": {"median": e}, "L_min_per_link": {"median": l}},
            "safety": {"ok": ok, "failing_counters": [] if ok else ["late"]}}


GOOD = {"n": 20, "failed_to_lock": 0, "controllers_done_at_link_up": True, "controller_error_seen": False, "gave_up_seen": False}


def test_lock_prefix_96f_accepted_and_others_refused(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bb.Board, "module_info", lambda self: {"vendor": "fake"})
    monkeypatch.setattr(bb.Board, "ddm", lambda self: {"temp_c": 30.0})
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    res = bb.run_all(FakeBoard(), "96F: bypass test", tmp_path, cable_loop_m=1.0, n_restarts=2)
    assert res["link_up"]
    with pytest.raises(RuntimeError):
        bb.run_all(FakeBoard(), "96G: not a lock", tmp_path, cable_loop_m=1.0, n_restarts=2)


def test_status_bits_and_features() -> None:
    b = BypassBoard()
    assert f1.bp_status(b) == {"tx_bp_done": 1, "rx_bp_done": 1, "tx_bp_err_seen": 0, "rx_bp_err_seen": 0, "tx_bp_err": 0, "rx_bp_err": 0,
                               "tx_gave_up": 0, "rx_gave_up": 0, "tx_gave_up_seen": 0, "rx_gave_up_seen": 0, "tx_retried_seen": 0, "rx_retried_seen": 0, "tx_retries": 0, "rx_retries": 0}
    assert not f1.gave_up(f1.bp_status(b))
    assert f1.features(b)["gt_bypass"] == 1
    assert f1.features(FakeBoard())["gt_bypass"] == 0


def test_full_restarts_ok_and_error(monkeypatch) -> None:
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    monkeypatch.setattr(f1.pp, "safe_conditions", lambda t: {"inside_roc": True})
    b = bb.Board(BypassBoard(lag=2))
    r = f1.full_restarts(b, n=6)
    assert r["failed_to_lock"] == 0 and r["controllers_done_at_link_up"] is True and r["controller_error_seen"] is False
    assert sum("conditions" in row for row in r["rows"]) == 2
    r2 = f1.full_restarts(bb.Board(BypassBoard(err_at=3)), n=6)
    assert r2["controller_error_seen"] is True


def test_verdict_pass_warn_fail_abort() -> None:
    feat = {"gt_bypass": 1}
    assert f1.verdict(_stage3(e=17.0), GOOD, True, feat)["result"] == "PASS"            # fall 4.0, inside 2.9 to 4.5
    w = f1.verdict(_stage3(e=19.0), GOOD, True, feat)                                   # fall 2.0: real but short of the prediction
    assert w["result"] == "WARN" and "outside the predicted" in w["reasons"][0]
    f = f1.verdict(_stage3(e=20.0), GOOD, True, feat)                                   # fall 1.0 < 1.5
    assert f["result"] == "FAIL" and "less than" in f["reasons"][0]
    assert f1.verdict(_stage3(e=17.0, ok=False), GOOD, True, feat)["result"] == "FAIL"
    assert f1.verdict(_stage3(e=17.0, failed=1), GOOD, True, feat)["result"] == "FAIL"
    assert f1.verdict(_stage3(e=17.0), GOOD, False, feat)["result"] == "FAIL"
    assert f1.verdict(_stage3(e=17.0), dict(GOOD, controller_error_seen=True), True, feat)["result"] == "FAIL"
    assert f1.verdict(_stage3(e=17.0), dict(GOOD, failed_to_lock=2), True, feat)["result"] == "FAIL"
    assert f1.verdict(_stage3(e=17.0), dict(GOOD, controllers_done_at_link_up=False), True, feat)["result"] == "FAIL"
    assert f1.verdict(_stage3(e=17.0), GOOD, True, {"gt_bypass": 0})["result"] == "ABORT"
    assert f1.verdict(_stage3(link=False), GOOD, True, feat)["result"] == "ABORT"
    v = f1.verdict(_stage3(e=17.0, l=46.0), GOOD, True, feat)
    assert v["E_drop_clocks"] == pytest.approx(4.0) and v["L_drop_clocks"] == pytest.approx(8.0) and v["D_from_medians"] == pytest.approx(12.0)


def test_reference_numbers_are_the_96e_board_run() -> None:
    import json
    d = json.loads((DESIGN.parents[1] / "results" / "b96e" / "hw" / "20261119_231251" / "rm_gp" / "stage3.json").read_text())
    r = d["restarts"]
    assert (f1.REF_E, f1.REF_L) == (r["E_min_per_link"]["median"], r["L_min_per_link"]["median"])
    assert f1.REF_D == d["D_clocks_from_medians_of_minima"]


def test_variant_is_rm_gp_with_only_the_bypass_differences() -> None:
    a = yaml.safe_load((DESIGN / "rm_gp" / "build.yaml").read_text()); b = yaml.safe_load((DESIGN / "rm_gp_bypass" / "build.yaml").read_text())
    assert a["generics"] == b["generics"] and a["part"] == b["part"] and a["constraints"] == b["constraints"] and a["top"] == b["top"]
    assert b["ip_tcl"] == ["designs/b96_kr260_10g/ip/amd_ip_bypass.tcl"]
    sa = [s for s in a["sources"] if not s.endswith("/b96_core.sv")]
    sb = [s for s in b["sources"] if "rm_gp_bypass/rtl/" not in s]
    assert sa == sb and any(s.endswith("rm_gp_bypass/rtl/b96_core.sv") for s in b["sources"]) and any(s.endswith("rm_gp_bypass/rtl/gt_bp_gate.sv") for s in b["sources"])


def test_bypass_core_differs_from_base_only_where_documented() -> None:
    """The copy of b96_core.sv must stay the base file plus the 96F1 and 96F1b lines: every removed base line is one of the few that change (96F1b: the RM_OWN parameter line gets a comma, three parameters follow it)."""
    base = (DESIGN / "rtl" / "b96_core.sv").read_text().splitlines(); var = (DESIGN / "rm_gp_bypass" / "rtl" / "b96_core.sv").read_text().splitlines()
    import difflib
    removed = [l[2:].strip() for l in difflib.ndiff(base, var) if l.startswith("- ")]
    allowed = re.compile(r"module b96_core #\(|parameter bit\s+RM_OWN|\.txbufstatus_out\(txbuf_c\)|\.src_clk\(txusr2\), \.src_in\(tx_done_t\)|\.src_clk\(rxusr2\), \.src_in\(rx_done_r\)|12'h008: rd|12'h020: rd|"
                         r"txb_seen <= txb_seen \| txbuf|ppm_step <= '0; ppm_en|p_clr <= h_wdata\[0\]|\.rst\(!(rx_done_r|tx_done_t)\)|\.rst_c\(!tx_done_t\)|rx_path #|tx_path #|assign _unused|xpm_cdc_single .*u_s_(tx|rx) ")
    bad = [l for l in removed if not allowed.search(l)]
    assert not bad, bad


def test_timeout_retry_fields_recorded_and_gave_up_is_a_fail(monkeypatch) -> None:
    """Brief 96F1b (amendment 2026-11-20, before any board time): GT_BUF bits 29:16 are read per restart; a retry that recovers is recorded, not judged; any gave-up flag is a FAIL, ahead of ABORT."""
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    monkeypatch.setattr(f1.pp, "safe_conditions", lambda t: {"inside_roc": True})
    assert f1.bp_status(BypassBoard(retry_at=1))["tx_retries"] == 0       # retry_at fires only on the matching reset count
    b = BypassBoard(retry_at=2)
    b.resets = 2
    st = f1.bp_status(b)
    assert (st["tx_retries"], st["rx_retries"], st["tx_retried_seen"], st["rx_retried_seen"]) == (1, 2, 1, 1) and not f1.gave_up(st)
    r = f1.full_restarts(bb.Board(BypassBoard(retry_at=3)), n=6)
    assert r["restarts_with_retries"] >= 1 and r["max_rx_retries"] == 2 and r["max_tx_retries"] == 1 and r["retried_seen"] is True and r["gave_up_seen"] is False
    feat = {"gt_bypass": 1}
    assert f1.verdict(_stage3(e=17.0), dict(GOOD, restarts_with_retries=1, retried_seen=True), True, feat)["result"] == "PASS"            # recovered retries: recorded, not judged
    r2 = f1.full_restarts(bb.Board(BypassBoard(gave_up_at=3)), n=6)
    assert r2["gave_up_seen"] is True
    v = f1.verdict(_stage3(e=17.0), r2, True, feat)
    assert v["result"] == "FAIL" and any("gave up" in x for x in v["reasons"])
    assert f1.verdict(_stage3(e=17.0), dict(GOOD, gave_up_seen=True), True, feat)["result"] == "FAIL"
    gu = {"tx_gave_up": 1, "rx_gave_up": 0, "tx_gave_up_seen": 1, "rx_gave_up_seen": 0}
    assert f1.verdict(_stage3(e=17.0), GOOD, True, feat, gu)["result"] == "FAIL"
    v = f1.verdict(_stage3(link=False), None, True, feat, gu)                                       # gave up is why the link did not come up: FAIL, not ABORT
    assert v["result"] == "FAIL" and "gave up" in v["reasons"][0]
    assert f1.verdict(_stage3(link=False), None, True, feat, {"tx_gave_up": 0, "rx_gave_up": 0})["result"] == "ABORT"


def test_alignment_timeouts_are_30_and_130_ms_at_the_user_clock() -> None:
    """Brief 96F1b: the core's defaults are AMD's example design's 30 ms (TX) and 130 ms (RX) at the 161.1328125 MHz user clock, rounded up to a whole clock; the retry bound is 3 and fits the 4-bit field."""
    src = (DESIGN / "rm_gp_bypass" / "rtl" / "b96_core.sv").read_text()
    tx = int(re.search(r"parameter int\s+BP_TX_TO\s*=\s*([\d_]+)", src).group(1).replace("_", ""))
    rx = int(re.search(r"parameter int\s+BP_RX_TO\s*=\s*([\d_]+)", src).group(1).replace("_", ""))
    rt = int(re.search(r"parameter int\s+BP_RETRIES\s*=\s*(\d+)", src).group(1))
    f = 10.3125e9 / 64
    assert f == 161_132_812.5
    assert tx == pytest.approx(0.030 * f, abs=1) and rx == pytest.approx(0.130 * f, abs=1)
    assert tx == 4_833_984 and rx == 20_947_266 and 1 <= rt <= 3
    ctl = (DESIGN / "rm_gp_bypass" / "rtl" / "gt_bp_ctl.sv").read_text()
    assert "xpm_cdc_async_rst" in ctl and "RST_ACTIVE_HIGH(0)" in ctl            # the reset synchroniser (asynchronous assert, synchronous release), no logic in front of it
