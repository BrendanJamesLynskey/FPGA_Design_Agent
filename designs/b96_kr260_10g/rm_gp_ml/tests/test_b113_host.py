"""Brief 113: the ML build's board driver against a fake board: the lock prefix, the feature check, the sweeps against the twin's predictions, and the pre-registered verdict
(results/b113/preregistration.md). Nothing here touches a board or says anything about what the hardware does."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from designs.b96_kr260_10g.host import b96_bench as bb
from designs.b96_kr260_10g.host import b113_ml as m
from designs.b96_kr260_10g.host.b96f1_bypass import REF_D, REF_E, REF_L
from designs.b96_kr260_10g.tests.test_b96_bench import FakeBoard

REPO = Path(__file__).resolve().parents[4]


class MlBoard(FakeBoard):
    """FakeBoard plus the ML registers: FEATURES bit 8, ML_ID, ML_CTRL, and the status words the twin predicts for the frames the run sends (`wrong` perturbs one word)."""

    def __init__(self, wrong=None, **kw):
        super().__init__(**kw)
        self.r[0x008] = 0x12F; self.r[m.ML_ID] = m.ID_VALUE
        self.mlv = [0] * 14; self.wrong = wrong or {}

    def wr(self, a, v):
        super().wr(a, v)
        if a == 0x018 and v & 2 and (self.r.get(0x068, 0) & 1) and ((self.r.get(0x068, 0) >> 4) & 3) == 1:
            veto = bool(self.r.get(m.ML_CTRL, 0) & 1)
            want = m.predict(self.r.get(0x078, 0), veto)
            self.mlv = [want[k] for k in m.MLV_NAMES] + [0, 0, 0]
            for k, d in self.wrong.items():
                self.mlv[m.MLV_NAMES.index(k)] += d
            n = want["orders"]
            self.tx[bb.TX["n_order"]] = n; self.rx[bb.RX["fired"]] = n; self.rx[bb.RX["order_ok"]] = n     # a veto run sends fewer orders than frames

    def rd(self, a):
        if m.MLV_BASE <= a < m.MLV_BASE + 4 * 14:
            return self.mlv[(a - m.MLV_BASE) // 4]
        return super().rd(a)


def _stage3(e=REF_E, l=REF_L, ok=True, failed=0, link=True):
    return {"link_up": link, "restarts": {"restarts": 100, "failed_to_lock": failed, "E_min_per_link": {"median": e}, "L_min_per_link": {"median": l}},
            "safety": {"ok": ok, "failing_counters": [] if ok else ["late"]}}


FEAT = {"ml_stage": 1, "ml_id_ok": True}
SW = {"shadow": {"all_match": True}, "veto": {"all_match": True}}


def test_lock_prefix_113_accepted(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bb.Board, "module_info", lambda self: {"vendor": "fake"})
    monkeypatch.setattr(bb.Board, "ddm", lambda self: {"temp_c": 30.0})
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    assert bb.run_all(FakeBoard(), "113: ML test", tmp_path, cable_loop_m=1.0, n_restarts=2)["link_up"]
    with pytest.raises(RuntimeError):
        bb.run_all(FakeBoard(), "114: not a lock", tmp_path, cable_loop_m=1.0, n_restarts=2)


def test_features_and_id() -> None:
    f = m.ml_features(MlBoard())
    assert f["ml_stage"] == 1 and f["ml_id_ok"] and f["rm_own"] == 1
    assert m.ml_features(FakeBoard())["ml_stage"] == 0


def test_predictions_for_the_generator_stream() -> None:
    """The board's own stream (the same ADD ask 99.50 size 1 every time): the first frame sees the empty book and the model says up, every later frame says down."""
    p = m.predict(50, True)
    assert (p["n_cls_up"], p["n_cls_down"], p["n_cls_flat"]) == (1, 49, 0) and p["orders"] == 1 and p["n_veto"] == 49 and p["n_would_veto"] == 0
    s = m.predict(50, False)
    assert s["orders"] == 50 and s["n_veto"] == 0 and s["n_would_veto"] == 49


@pytest.mark.parametrize("veto", [False, True])
def test_sweep_matches_and_detects_a_wrong_counter(monkeypatch, veto) -> None:
    monkeypatch.setattr(bb.time, "sleep", lambda s: None)
    ok = m.sweep(bb.Board(MlBoard()), veto, repeats=3, frames=20)
    assert ok["all_match"] and all(r["match"] for r in ok["rows"])
    bad = m.sweep(bb.Board(MlBoard(wrong={"n_cls_up": 1})), veto, repeats=3, frames=20)
    assert not bad["all_match"] and bad["mismatches"]


def test_verdict_pass_warn_fail_abort() -> None:
    assert m.verdict(_stage3(), SW, True, FEAT)["result"] == "PASS"
    assert m.verdict(_stage3(l=REF_L + 1.0), SW, True, FEAT)["result"] == "PASS"                  # inside the band
    w = m.verdict(_stage3(l=REF_L + 1.5), SW, True, FEAT)
    assert w["result"] == "WARN" and "predicted within" in w["reasons"][0]
    f = m.verdict(_stage3(l=REF_L + 3.0), SW, True, FEAT)
    assert f["result"] == "FAIL" and "added or removed latency" in f["reasons"][0]
    assert m.verdict(_stage3(e=REF_E - 2.5), SW, True, FEAT)["result"] == "FAIL"
    assert m.verdict(_stage3(ok=False), SW, True, FEAT)["result"] == "FAIL"
    assert m.verdict(_stage3(failed=1), SW, True, FEAT)["result"] == "FAIL"
    assert m.verdict(_stage3(), SW, False, FEAT)["result"] == "FAIL"
    assert m.verdict(_stage3(), {"shadow": {"all_match": True}, "veto": {"all_match": False, "mismatches": [{"n_cls_up": (2, 1)}]}}, True, FEAT)["result"] == "FAIL"
    assert m.verdict(_stage3(), SW, True, {"ml_stage": 0, "ml_id_ok": False})["result"] == "ABORT"
    assert m.verdict(_stage3(link=False), SW, True, FEAT)["result"] == "ABORT"
    v = m.verdict(_stage3(e=REF_E + 0.5, l=REF_L + 0.5), SW, True, FEAT)
    assert v["dE"] == pytest.approx(0.5) and v["dL"] == pytest.approx(0.5) and v["D_from_medians"] == pytest.approx(REF_L + 0.5 - 2 * (REF_E + 0.5))
    assert REF_D == REF_L - 2 * REF_E


def test_the_preregistration_states_the_rule_the_driver_codes() -> None:
    doc = (REPO / "results" / "b113" / "preregistration.md").read_text()
    for must in (f"within {m.PASS_BAND:.1f} clock", f"{m.WARN_BAND:.1f} clock", "ABORT", "FAIL", "WARN", "PASS", "113:"):
        assert must in doc, must
    assert json.loads(json.dumps(m.predict(50, True)))["orders"] == 1
