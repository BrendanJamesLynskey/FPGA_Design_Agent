"""The brief 96C board driver against a fake board: ppm arithmetic, the choice of settings, the acceptance of a point, and a whole short session."""

from __future__ import annotations

import pytest

from designs.b96_kr260_10g.host import b96_bench as bb
from designs.b96_kr260_10g.host import b96c_ppm as pp


class FakeBoard:
    """Registers as far as the 96C driver reads them. The offset is a linear function of the step code (a made-up law: the real one is what the board
    run measures); sel 0 does nothing; code 31 drops the link."""

    def __init__(self, ppm_per_step=12.0, hot=False):
        self.ppm_per_step = ppm_per_step; self.reg = {0x000: 0x96A00001, 0x00C: 0x8, 0x01C: 0}; self.hot = hot
        self.rx = [0] * 29; self.tx = [0] * 26; self.reads = 0; self.snap = False; self.n_clears = 0; self.link = True; self.sm_addr = 0; self.dwelling = False; self.extra = 0

    def ppm(self):
        v = self.reg[0x01C]
        step = v & 0x1F; en = (v >> 5) & 1; sel = (v >> 6) & 1
        if not (en and sel):
            return 0.0
        return (step if step < 16 else step - 32) * self.ppm_per_step

    def rd(self, a):
        if a == 0x014:
            return (0x3 | (1 << 9)) if self.link else 0
        if a == 0x020:
            return 0
        if a == 0x094:
            code = {0x00: int((55 + 273.6777) * 1024 / 501.3743) if not self.hot else int((95 + 273.6777) * 1024 / 501.3743), 0x01: int(0.72 / 3 * 1024), 0x02: int(1.8 / 3 * 1024), 0x06: int(0.85 / 3 * 1024)}[self.sm_addr]
            return (1 << 16) | (code << 6)
        if 0x100 <= a < 0x174:
            i = (a - 0x100) // 4
            if i == bb.RX["f_win"]:
                if not self.dwelling:
                    self.reads += 1
                self.rx[i] = self.reads // 3 + self.extra
            if i == bb.RX["f_delta"]:
                self.rx[i] = round((1 << 24) * (1 + self.ppm() * 1e-6))
            return self.rx[i]
        if 0x200 <= a < 0x268:
            return self.tx[(a - 0x200) // 4]
        return self.reg.get(a, 0)

    def wr(self, a, v):
        self.reg[a] = v
        if a == 0x090:
            self.sm_addr = v
        if a == 0x01C:
            self.dwelling = False           # the fake's windows run again once the ppm register is written
        if a == 0x01C and (v & 0x1F) == 31 and (v >> 5) & 1:
            self.link = False
        if a == 0x010:
            self.link = True
        if a == 0x018 and v & 1:
            self.n_clears += 1; self.dwelling = False
            self.tx = [0] * 26
            self.rx = [0] * 29
        if a == 0x018 and v & 2 and (self.reg.get(0x068, 0) & 1) and ((self.reg.get(0x068, 0) >> 4) & 3) == 1:
            n = self.reg.get(0x078, 0)
            self.tx[bb.TX["n_order"]] = n; self.rx[bb.RX["fired"]] = n; self.rx[bb.RX["order_ok"]] = n
            p = self.ppm()
            secs = n * self.reg.get(0x074, 1) / pp.F_CORE_HZ
            self.extra += int(secs / (pp.WINDOW_CLOCKS / pp.F_CORE_HZ)); self.dwelling = True
            self.rx[bb.RX["rm_del"]] = int(max(p, 0) * 1e-6 * pp.BLOCK_RATE * secs); self.rx[bb.RX["rm_ins"]] = int(max(-p, 0) * 1e-6 * pp.BLOCK_RATE * secs)
        if a == 0x018 and v & 4:
            self.tx[bb.TX["e_cnt"]] = 5; self.tx[bb.TX["e_min"]] = 21; self.tx[bb.TX["e_max"]] = 22
            self.tx[bb.TX["l_cnt"]] = 5; self.tx[bb.TX["l_min"]] = 55; self.tx[bb.TX["l_max"]] = 57
            n = 5
            if not ((self.reg.get(0x068, 0) & 1) and ((self.reg.get(0x068, 0) >> 4) & 3) == 1):
                pass


def test_ppm_arithmetic() -> None:
    assert pp.ppm_from_delta((1 << 24) + 1678) == pytest.approx(100.0, abs=0.05)
    assert pp.ppm_from_delta((1 << 24) - 839) == pytest.approx(-50.0, abs=0.05)
    assert pp.expected_rates(100)["deletes_per_s"] == pytest.approx(100e-6 * pp.F_CORE_HZ * 32 / 33)
    assert pp.expected_rates(-100)["inserts_per_s"] > 0 and pp.expected_rates(-100)["deletes_per_s"] == 0


def test_sysmon_units() -> None:
    assert pp.sysmon_to_units("vccint_v", 0x2E00 << 0) == pytest.approx(((0x2E00 >> 6) & 0x3FF) / 1024 * 3)
    assert pp.sysmon_to_units("temp_c", 700 << 6) == pytest.approx(700 * 501.3743 / 1024 - 273.6777)


def test_choose_points_and_unreachable() -> None:
    rows = [{"link": True, "stable": True, "ppm": p, "txbuf_seen": 0, "rxbuf_seen": 0, "en": 1, "sel": 1, "step": s} for s, p in ((1, 12.0), (2, 24.0), (3, 36.0), (4, 48.0), (5, 60.0))]
    pts = {p["target_ppm"]: p for p in pp.choose_points(rows, targets=(50.0, 150.0, 0.0))}
    assert pts[50.0]["reachable"] and pts[50.0]["step"] == 4
    assert not pts[150.0]["reachable"] and pts[150.0]["nearest"]["step"] == 5


def test_conditions_flag_a_hot_die() -> None:
    assert pp.read_conditions(FakeBoard())["inside_roc"] is True
    assert pp.read_conditions(FakeBoard(hot=True))["inside_roc"] is False


def test_session_on_a_fake_board(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pp.time, "sleep", lambda s: None)
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    f = FakeBoard()
    res = pp.run_ppm_session(f, "96C: test", tmp_path, dwell_s=1.0, restarts=3, targets=(0.0, 48.0, -48.0, 400.0), steps=range(0, 32))
    pts = {p["target_ppm"]: p for p in res["points"]}
    assert pts[48.0]["reachable"] and pts[48.0]["verdict"]["ok"], pts[48.0].get("verdict")
    assert pts[48.0]["ppm_now"]["ppm"] == pytest.approx(48.0, abs=0.1)
    assert pts[-48.0]["verdict"]["ok"] and pts[0.0]["verdict"]["ok"]
    assert not pts[400.0]["reachable"] and pts[400.0]["nearest"] is not None
    assert pp.summary(res)["points"][1]["ok"]
    assert f.reg[0x01C] == 0, "the offset must be put back to zero"


def test_a_failed_counter_fails_the_point() -> None:
    d = {"orders_expected": 10, "tx": {k: 0 for k in pp.SAFE_TX} | {"n_order": 10}, "rx": {k: 0 for k in pp.SAFE_RX} | {"fired": 10, "order_ok": 10, "rm_del": 0, "rm_ins": 0, "rm_wr": 0, "rm_out": 0, "rm_drain": 0},
         "elapsed_s_by_windows": 1.0, "conditions": [{"inside_roc": True}], "gt_buffers": {"txbuf_seen": 0, "rxbuf_seen": 0}}
    assert pp.judge_point(d, 0.0)["ok"]
    d["rx"]["rm_ovf"] = 1
    v = pp.judge_point(d, 0.0)
    assert not v["ok"] and "rm_ovf=1" in v["failing"]
    d["rx"]["rm_ovf"] = 0; d["gt_buffers"]["txbuf_seen"] = 2
    assert not pp.judge_point(d, 0.0)["ok"]


def test_refuses_without_96c_lock(tmp_path) -> None:
    with pytest.raises(RuntimeError):
        pp.run_ppm_session(FakeBoard(), "97: x", tmp_path)
