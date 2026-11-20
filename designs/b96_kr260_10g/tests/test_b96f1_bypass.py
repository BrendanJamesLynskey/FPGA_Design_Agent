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

    def __init__(self, err_at=None, lag=2, **kw):
        super().__init__(**kw)
        self.err_at = err_at; self.lag = lag; self.resets = 0; self.polls = 0; self.up_after = 0
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
            return (0xC00 if not err else 0xC00 | (1 << 12) | (1 << 14))
        return super().rd(a)


def _stage3(e=17.0, l=46.0, ok=True, failed=0, link=True):
    return {"link_up": link, "restarts": {"restarts": 100, "failed_to_lock": failed, "E_min_per_link": {"median": e}, "L_min_per_link": {"median": l}},
            "safety": {"ok": ok, "failing_counters": [] if ok else ["late"]}}


GOOD = {"n": 20, "failed_to_lock": 0, "controllers_done_at_link_up": True, "controller_error_seen": False}


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
    assert f1.bp_status(b) == {"tx_bp_done": 1, "rx_bp_done": 1, "tx_bp_err_seen": 0, "rx_bp_err_seen": 0, "tx_bp_err": 0, "rx_bp_err": 0}
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
    """The copy of b96_core.sv must stay the base file plus the 96F1 lines: every removed base line is one of the few that change."""
    base = (DESIGN / "rtl" / "b96_core.sv").read_text().splitlines(); var = (DESIGN / "rm_gp_bypass" / "rtl" / "b96_core.sv").read_text().splitlines()
    import difflib
    removed = [l[2:].strip() for l in difflib.ndiff(base, var) if l.startswith("- ")]
    allowed = re.compile(r"module b96_core #\(|\.txbufstatus_out\(txbuf_c\)|\.src_clk\(txusr2\), \.src_in\(tx_done_t\)|\.src_clk\(rxusr2\), \.src_in\(rx_done_r\)|12'h008: rd|12'h020: rd|"
                         r"txb_seen <= txb_seen \| txbuf|ppm_step <= '0; ppm_en|p_clr <= h_wdata\[0\]|\.rst\(!(rx_done_r|tx_done_t)\)|\.rst_c\(!tx_done_t\)|rx_path #|tx_path #|assign _unused|xpm_cdc_single .*u_s_(tx|rx) ")
    bad = [l for l in removed if not allowed.search(l)]
    assert not bad, bad
