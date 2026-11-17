"""The stage-3 bench driver against a fake board (brief 96): the sequence runs, refuses without the lock, stops on the wrong polarity."""

from __future__ import annotations

import json

import pytest

from designs.b96_kr260_10g.host import b96_bench as bb


class FakeBoard:
    """Registers of the design as far as the driver reads them; the module behind the I2C pins is not modelled (module_info is stubbed)."""

    def __init__(self, polarity_ok=True, inject=None, drop_orders=None, late_orders=0):
        # inject: {restart index: {"stale": 1, "bad": 2, ...}} counters set non-zero at that restart's snapshot (restart = number of clears - 1);
        # drop_orders: {restart index: orders actually fired and sent}; late_orders: snapshots that still show no orders (the tail has not arrived)
        self.inject = inject or {}; self.drop_orders = drop_orders or {}; self.late_orders = late_orders
        self.clears = 0; self.late_left = 0
        self.r = {0x000: 0x96A00001, 0x00C: 0x8, 0x014: 0x3 | (1 << 9) | (1 << 11)}
        self.polarity_ok = polarity_ok
        self.rx = [0] * 16; self.tx = [0] * 26
        self.snap_n = 0
        self.rx[bb.RX["lock_clk"]] = 70

    def rd(self, a):
        if 0x100 <= a < 0x140: return 0 if getattr(self, "mask", False) and a == 0x100 + 4 * bb.RX["fired"] else self.rx[(a - 0x100) // 4]
        if 0x200 <= a < 0x268: return 0 if getattr(self, "mask", False) and a == 0x200 + 4 * bb.TX["n_order"] else self.tx[(a - 0x200) // 4]
        if a == 0x014:
            off = self.r[0x00C] & 8
            s = 0x3 | (1 << 9) | (0 if off or not self.polarity_ok else 0) | (0 if (not off and self.polarity_ok) else (1 << 11))
            return s
        return self.r.get(a, 0)

    def wr(self, a, v):
        self.r[a] = v
        if a == 0x018 and v & 1:
            self.clears += 1; self.late_left = self.late_orders
            self.tx = [0] * 26; self.rx = [0] * 16; self.rx[bb.RX["lock_clk"]] = 70
        if a == 0x018 and v & 2 and (self.r.get(0x068, 0) & 1) and ((self.r.get(0x068, 0) >> 4) & 3) == 1:      # armed feed frames fire one order each
            n = self.drop_orders.get(self.clears - 1, self.r.get(0x078, 0))
            self.tx[bb.TX["n_order"]] += n; self.rx[bb.RX["fired"]] += n
        if a == 0x018 and v & 4:
            i = self.clears - 1
            for k, c in self.inject.get(i, {}).items():
                (self.tx if k in bb.TX else self.rx)[(bb.TX if k in bb.TX else bb.RX)[k]] = c
            self.mask = self.late_left > 0
            self.late_left = max(0, self.late_left - 1)
            self.snap_n += 1
            self.tx[bb.TX["e_cnt"]] = 5; self.tx[bb.TX["e_min"]] = 70 + self.snap_n % 3; self.tx[bb.TX["e_max"]] = 72
            self.tx[bb.TX["l_cnt"]] = 5; self.tx[bb.TX["l_min"]] = 160; self.tx[bb.TX["l_max"]] = 163


def test_sequence_runs(tmp_path, monkeypatch) -> None:
    f = FakeBoard()
    monkeypatch.setattr(bb.Board, "module_info", lambda self: {"vendor": "fake"})
    monkeypatch.setattr(bb.Board, "ddm", lambda self: {"temp_c": 30.0})
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    res = bb.run_all(f, "96: stage 3 test", tmp_path, cable_loop_m=1.0, n_restarts=7)
    assert res["polarity_ok"] and res["link_up"] and res["restarts"]["failed_to_lock"] == 0
    assert res["restarts"]["lock_clocks"]["min"] == 70
    assert res["D_clocks_from_medians_of_minima"] == pytest.approx(160 - 2 * res["restarts"]["E_min_per_link"]["median"])
    assert res["safety"]["ok"] and res["safety"]["orders"] == {"expected_total": 35, "sent_total": 35, "fired_total": 35}
    assert len(res["restarts"]["snapshots"]) == 7
    assert json.loads((tmp_path / "stage3.json").read_text())["id"] == "96a00001"
    assert f.r[0x00C] & 8, "the laser must be left off"


def test_refuses_without_lock(tmp_path) -> None:
    with pytest.raises(RuntimeError):
        bb.run_all(FakeBoard(), "", tmp_path, cable_loop_m=1.0)


def test_stops_on_wrong_polarity(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bb.Board, "module_info", lambda self: {})
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    res = bb.run_all(FakeBoard(polarity_ok=False), "96: x", tmp_path, cable_loop_m=1.0)
    assert not res["polarity_ok"] and "stopped" in res and "restarts" not in res


def test_arithmetic() -> None:
    assert bb.decision_latency(70, 160) == 20
    assert bb.fibre_delay_ns(1.0) == pytest.approx(4.896, abs=0.01)
    assert bb.summarise([3, 3, 4])["histogram"] == {3: 2, 4: 1}


def _run(tmp_path, monkeypatch, n=6, **kw):
    f = FakeBoard(**kw)
    monkeypatch.setattr(bb.Board, "module_info", lambda self: {})
    monkeypatch.setattr(bb.Board, "ddm", lambda self: {})
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    return bb.run_all(f, "97: safety test", tmp_path, cable_loop_m=1.0, n_restarts=n)


def test_clean_run_is_ok(tmp_path, monkeypatch) -> None:
    sf = _run(tmp_path, monkeypatch)["safety"]
    assert sf["ok"] is True and sf["failing_counters"] == [] and sf["reasons"] == [] and sf["bad_restarts"] == []
    assert sf["sums"]["stale"] == 0 and sf["restarts_checked"] == 6
    saved = json.loads((tmp_path / "stage3.json").read_text())["restarts"]["snapshots"]
    assert saved[0]["tx"]["n_order"] == 5 and saved[0]["rx"]["fired"] == 5


def test_one_stale_in_one_restart_fails_and_names_it(tmp_path, monkeypatch) -> None:
    sf = _run(tmp_path, monkeypatch, inject={3: {"stale": 1}})["safety"]
    assert sf["ok"] is False and sf["failing_counters"] == ["stale"]
    assert [r["restart"] for r in sf["bad_restarts"]] == [3] and sf["bad_restarts"][0]["nonzero"] == {"stale": 1}
    assert sf["sums"]["stale"] == 1 and sf["orders"]["fired_total"] == 30      # orders are right: only stale failed


@pytest.mark.parametrize("name", ["poisoned", "dropped", "underrun", "late", "stale", "bad", "err", "toolong"])
def test_every_safety_counter_is_judged(tmp_path, monkeypatch, name) -> None:
    sf = _run(tmp_path, monkeypatch, n=2, inject={1: {name: 2}})["safety"]
    assert sf["ok"] is False and sf["failing_counters"] == [name]


def test_order_shortfall_fails(tmp_path, monkeypatch) -> None:
    sf = _run(tmp_path, monkeypatch, drop_orders={2: 4})["safety"]
    assert sf["ok"] is False and sorted(sf["failing_counters"]) == ["fired", "n_order"]
    assert sf["bad_restarts"][0]["order_count_wrong"] == {"n_order": 4, "fired": 4}
    assert sf["orders"]["expected_total"] == 30 and sf["orders"]["fired_total"] == 29


def test_tail_that_arrives_late_is_waited_for(tmp_path, monkeypatch) -> None:
    sf = _run(tmp_path, monkeypatch, late_orders=2)["safety"]
    assert sf["ok"] is True


def test_unlocked_restart_is_not_ok() -> None:
    clean = {"tx": {k: 0 for k in bb.SAFETY_TX} | {"n_order": 5}, "rx": {k: 0 for k in bb.SAFETY_RX} | {"blocked": 0, "fired": 5}}
    assert bb.safety_verdict([clean, clean], 5, 2)["ok"] is True
    sf = bb.safety_verdict([clean, None], 5, 2)
    assert sf["ok"] is False and sf["restarts_unreadable"] == [1]
    assert bb.safety_verdict([clean], 5, 2)["ok"] is False            # a missing snapshot is not a pass


def test_unread_counter_is_not_ok() -> None:
    sn = {"tx": {k: 0 for k in bb.SAFETY_TX} | {"n_order": 5}, "rx": {"bad": 0, "err": 0, "blocked": 0, "fired": 5}}      # toolong missing
    sf = bb.safety_verdict([sn], 5, 1)
    assert sf["ok"] is False and "toolong" in sf["failing_counters"]


def test_link_never_up_has_no_ok(tmp_path, monkeypatch) -> None:
    f = FakeBoard()
    monkeypatch.setattr(bb.Board, "module_info", lambda self: {}); monkeypatch.setattr(bb.Board, "ddm", lambda self: {})
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    monkeypatch.setattr(bb.Board, "wait", lambda self, pred, t, poll_s=0.05: False)
    res = bb.run_all(f, "97: x", tmp_path, cable_loop_m=1.0, n_restarts=3)
    assert res["safety"]["ok"] is False
