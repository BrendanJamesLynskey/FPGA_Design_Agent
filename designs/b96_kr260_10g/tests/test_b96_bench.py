"""The stage-3 bench driver against a fake board (brief 96): the sequence runs, refuses without the lock, stops on the wrong polarity."""

from __future__ import annotations

import json

import pytest

from designs.b96_kr260_10g.host import b96_bench as bb


class FakeBoard:
    """Registers of the design as far as the driver reads them; the module behind the I2C pins is not modelled (module_info is stubbed)."""

    def __init__(self, polarity_ok=True):
        self.r = {0x000: 0x96A00001, 0x00C: 0x8, 0x014: 0x3 | (1 << 9) | (1 << 11)}
        self.polarity_ok = polarity_ok
        self.rx = [0] * 16; self.tx = [0] * 26
        self.snap_n = 0
        self.rx[bb.RX["lock_clk"]] = 70

    def rd(self, a):
        if 0x100 <= a < 0x140: return self.rx[(a - 0x100) // 4]
        if 0x200 <= a < 0x268: return self.tx[(a - 0x200) // 4]
        if a == 0x014:
            off = self.r[0x00C] & 8
            s = 0x3 | (1 << 9) | (0 if off or not self.polarity_ok else 0) | (0 if (not off and self.polarity_ok) else (1 << 11))
            return s
        return self.r.get(a, 0)

    def wr(self, a, v):
        self.r[a] = v
        if a == 0x018 and v & 4:
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
