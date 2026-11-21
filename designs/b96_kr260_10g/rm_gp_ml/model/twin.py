"""Brief 113: the Python twin of the ML decision stage of build rm_gp_ml (rtl/ml_stage.sv and the veto in rtl/trade64.sv).

Written from the stage's documented behaviour (the header of ml_stage.sv, docs/ml_stage.md), over the brief 87 reference model (`lobsim.FeatureState`, `arms.gbt_predict_int`) and the
58A book semantics (b58a_trigger/rtl/book.sv, written out here). One call per frame the rule path accepts (the first message of a frame addressed to us on the feed port, header good, IPv4 length
at most 60). The features and the class are those of the state BEFORE the frame's message; the state moves only when the frame ends good.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

import numpy as np

from designs.b58a_trigger.model import benchfeed as bf
from designs.b87_ml_trading.model import arms as A
from designs.b87_ml_trading.model import lobsim as L
from designs.b87_ml_trading.model.gen_rtl import MODELS

UP = 2


def load_gbt() -> dict:
    return json.loads((MODELS / "gbt.json").read_text())


@dataclass
class Obs:
    """What the fabric shows at the price word of one frame (the MSG line of tb_ml_core.sv)."""
    trk: bool
    feat: int          # the 38 bits packed as ml_feat.sv documents (dir[37:36] ofi[35:28] trades[27:23] imb[22:20] spread[19:16] ask[15:8] bid[7:0])
    cls: int
    hit: bool          # the rule's price test (ask ADD or MODIFY, 0 < price <= thr), before arm/kill/trade_en
    dec: bool          # a decision on the tracked instrument that the rule wants to act on (armed)
    veto: bool         # the model stops it (veto mode only)
    order: bool        # an order leaves
    applied: bool      # the frame ended good, so the state moved


class Twin:
    def __init__(self, inst: int = 1, thr: int = 9975, veto_mode: bool = False) -> None:
        self.inst, self.thr, self.veto_mode = inst, thr, veto_mode
        self.model = load_gbt()
        self.book = [0, 0, 0, 0]          # bid px, bid sz, ask px, ask sz
        self.fs = L.FeatureState(0, 0, 0, 0)
        self.pend = 0
        self.n = dict(obs=0, cls=[0, 0, 0], dec=0, veto=0, would=0, apply=0, drop=0, orders=0)

    @staticmethod
    def pack(f: list[int]) -> int:
        b, a, spr, imb, tr, ofi, d = f
        return b | (a << 8) | (spr << 16) | (imb << 20) | (tr << 23) | (ofi << 28) | (d << 36)

    def _classify(self, f: list[int]) -> int:
        return int(A.gbt_predict_int(self.model, np.array([f], dtype=np.int64))[0])

    def _apply_book(self, m: bf.Msg) -> None:
        bk = self.book
        i = 2 if m.side == bf.ASK else 0
        if m.type in (bf.ADD, bf.MODIFY):
            bk[i], bk[i + 1] = m.price, m.size
        elif m.type == bf.CANCEL:
            bk[i], bk[i + 1] = 0, 0
        elif m.type == bf.TRADE:
            if bk[i] == m.price and bk[i + 1] != 0:
                bk[i + 1] = max(0, bk[i + 1] - m.size)
                if bk[i + 1] == 0:
                    bk[i] = 0

    def frame(self, m: bf.Msg, good: bool) -> Obs:
        trk = m.inst == self.inst
        hit = m.type in (bf.ADD, bf.MODIFY) and m.side == bf.ASK and 0 < m.price <= self.thr
        trial = copy.deepcopy(self.fs)
        f = trial.update(*self.book, self.pend)           # features of the state before this message (state moves only on apply)
        cls = self._classify(f)
        feat = self.pack(f)
        dec = hit and trk
        veto = dec and self.veto_mode and cls != UP
        would = dec and (not self.veto_mode) and cls != UP
        order = hit and not veto
        if trk:
            self.n["obs"] += 1
            self.n["cls"][cls] += 1
            if dec:
                self.n["dec"] += 1
                self.n["veto"] += int(veto)
                self.n["would"] += int(would)
        if order:
            self.n["orders"] += 1
        applied = good and trk
        if trk and not good:
            self.n["drop"] += 1
        if applied:
            self.fs = trial
            self.pend = (1 if m.side == bf.ASK else -1) if m.type == bf.TRADE else 0
            self._apply_book(m)
            self.n["apply"] += 1
        return Obs(trk, feat, cls, hit, dec, veto, order, applied)
