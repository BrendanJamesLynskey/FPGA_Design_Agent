"""A SYNTHETIC board for offline work: a register-level stand-in for the EYESCAN = 1 bitstream (raw DRP, the point sequencer, the status and drive registers) whose
error counts come from a statistical eye MODEL with Poisson counting noise. It exists to test the host code, the derived numbers and the displays end to end without a
board. Every capture it produces is marked `synthetic: true`, `instrument.mock: true` and the plots say SYNTHETIC. It is NOT a measurement, and no number from it goes
into a result.

The model: BER(h, v) = 0.5 x erfc((m(h) - |v|) / (sqrt(2) sigma)) with the vertical margin m(h) = M0 x (1 - (|h| x 2)^p) (h in UI) and Gaussian noise sigma, floored at
0.5. DFE gets slightly more margin than LPM so the comparison has something to show. TX swing scales the margin. All of it is invented for the test.
"""

from __future__ import annotations

import math
import random
from typing import Any

from designs.b96_kr260_10g.model import eyescan as tw
from flow.eyescan import hw as H


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 60:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


class FakeBoard:
    """Transport (rd/wr) with the register behaviour of the EYESCAN build, and a synthetic eye."""

    def __init__(self, seed: int = 1, m0_mv: float = 150.0, sigma_mv: float = 14.0, exponent: float = 2.4, lpm: bool = True, drive_diff: int = 0b11000, link: bool = True, phase_trap: bool = False) -> None:
        self.rng = random.Random(seed)
        self.m0, self.sigma, self.exp = m0_mv, sigma_mv, exponent
        self.reg = {H.R_FEATURES: 0x11, H.R_GT_CTRL: 0x08 | (0x40 if lpm else 0), H.R_TMO: 500_000_000, H.R_DRIVE: drive_diff}
        self.drp = {a: 0 for a in range(1024)}
        self.drp[tw.A_ES_CONTROL] = 0x0300 | (0x3 << 5)
        self.drp[tw.A_ES_HORZ] = 0x0005
        self.drp[tw.A_VS] = 0x1800
        self.drp[tw.A_RXOUT_DIV] = 0x0000
        self.drp[H.A_RX_INT] = 0x0001
        self.stat = 0
        self.drp_last = 0
        self.points = 0
        self.link = link
        self.phase_trap = phase_trap          # True: model the KR260's 2026-11-20 behaviour (an eye only with USE_PCS_CLK_PHASE_SEL = 1, ES_CLK_PHASE_SEL = 1)
        self.drp_log: list[tuple[str, int, int | None]] = []

    # ---- the eye
    def ber(self, h_counts: int, v_code: int, rng_sel: int) -> float:
        div = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}[self.drp[tw.A_RXOUT_DIV] & 7]
        h_ui = h_counts * 0.5 / (32 * div)
        diff = self.reg[H.R_DRIVE] & 31
        scale = 0.35 + 0.65 * (diff / 24.0)
        lpm = bool(self.reg[H.R_GT_CTRL] & 0x40)
        m = self.m0 * scale * (1.0 if lpm else 1.08) * max(0.0, 1.0 - (abs(h_ui) * 2) ** self.exp)
        mv = abs(v_code) * (1.5, 1.8, 2.2, 2.8)[rng_sel]
        z = (m - mv) / (math.sqrt(2) * self.sigma)
        return min(0.5, 0.5 * math.erfc(z))

    def _qual_all_masked(self) -> bool:
        """UG576 (Table 4-20, GTHE4): the sample counter advances only on cycles whose Rdata matches ES_QUALIFIER where ES_QUAL_MASK is 0, so for a statistical eye ALL ten words of
        ES_QUAL_MASK must be 1s. Real data never matches 80 bits of an unmasked, all-zero qualifier, so one zero bit anywhere means no sample is ever counted."""
        return all(self.drp[a] == 0xFFFF for a in tw.QUAL_MASK_ADDRS)

    def _run_point(self) -> None:
        p = self.reg.get(H.R_POINT, 0)
        if not self._qual_all_masked():           # the GT stays in COUNT (0b0110), the sequencer's poll times out: result registers 0, tmo flag, as on the board 2026-11-19
            self.reg[H.R_RES] = 0
            self.points += 1
            self.stat = 0x2 | 0x4 | (0b0110 << 8)
            return
        if self.phase_trap and (self.drp[0x094] >> 10) & 3 != 3:     # wrong 4T phase: Sdata is about half ones, the error counter saturates first
            pre0 = (p >> 23) & 31
            self.reg[H.R_RES] = (max(1, 65535 // 32) << 16) | 65535 if pre0 == 0 else (64 << 16) | 65535
            self.points += 1
            self.stat = 0x2 | (0b0101 << 8)
            return
        horz, code, neg, rng_sel, pre = p & 0xFFF, (p >> 12) & 0x7F, (p >> 19) & 1, (p >> 21) & 3, (p >> 23) & 31
        h = horz & 0x7FF
        if horz & 0x800:
            h -= 0x800
        v = -code if neg else code
        ber = self.ber(h, v, rng_sel)
        bits_full = 65535 * (1 << (1 + pre)) * 32
        lam = bits_full * ber
        if lam >= 65535:
            err = 65535
            samp = max(1, min(65535, int(math.ceil(65535 / ber / ((1 << (1 + pre)) * 32)))))
        else:
            err, samp = poisson(self.rng, lam), 65535
        self.reg[H.R_RES] = (samp << 16) | err
        self.points += 1
        self.stat = 0x2 | (0b0101 << 8)

    # ---- Transport
    def rd(self, a: int) -> int:
        if a == H.R_STAT:
            return self.stat | (self.points << 16)
        if a == H.R_DRP_DATA:
            return self.drp_last
        if a == 0x014:                                              # GT_STAT
            return 0x20B if self.link else 0x0
        if a == 0x094:
            return 1 << 16 | (int((50.0 + 273.6777) * 1024 / 501.3743) << 6)
        return self.reg.get(a, 0)

    def wr(self, a: int, v: int) -> None:
        if a == H.R_CMD:
            if v & 8:
                self.stat &= ~0x1F
            if v & 1:
                self.drp_last = self.drp[self.reg.get(H.R_DRP_ADDR, 0)]
                self.drp_log.append(("R", self.reg.get(H.R_DRP_ADDR, 0), None))
            if v & 2:
                self.drp[self.reg.get(H.R_DRP_ADDR, 0)] = self.reg.get(H.R_DRP_DATA, 0) & 0xFFFF
                self.drp_log.append(("W", self.reg.get(H.R_DRP_ADDR, 0), self.reg.get(H.R_DRP_DATA, 0)))
            if v & 4:
                self._run_point()
            return
        if a == H.R_DRP_DATA:
            self.reg[a] = v & 0xFFFF
            return
        self.reg[a] = v & 0xFFFFFFFF


def design_info() -> dict[str, Any]:
    return {"name": "b96_kr260_10g", "variant": "eyescan", "board": "kr260 (SYNTHETIC: no board)"}
