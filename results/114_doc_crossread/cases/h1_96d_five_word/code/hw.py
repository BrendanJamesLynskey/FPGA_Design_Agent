"""Host side of the eye-scan registers of designs/b96_kr260_10g (EYESCAN = 1 builds; register map docs/register_map.md): raw DRP access, the static eye-scan
attributes, one measurement point, and the save/restore of every DRP word the scan touches.

`t` is any object with rd(addr) -> int and wr(addr, value) (designs/b96_kr260_10g/host/b96_bench.py `Transport`; the real one is `VivadoTcl`, tests use
flow/eyescan/fake.py). Nothing here touches the laser, the reset or the line configuration; the equaliser mode and the TX drive are separate, explicit calls.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from designs.b96_kr260_10g.model import eyescan as tw

R_FEATURES, R_GT_CTRL = 0x008, 0x00C
R_DRP_ADDR, R_DRP_DATA, R_CMD, R_STAT, R_POINT, R_TMO, R_RES, R_DRIVE = 0x024, 0x028, 0x02C, 0x030, 0x034, 0x038, 0x03C, 0x084
FEATURE_EYESCAN = 0x10
SHIPPED_TXDIFF = 0b11000      # the design's TXDIFFCTRL (873 mVppd): never exceeded, the optical module's input is protected by it
MAX_CURSOR = 12              # 3.10 dB, UG576 Table 3-35
CLK_HZ = 100e6                       # the free-running clock the sequencer and its timeout run in
#: DRP words that the scan reads-modifies-writes or overwrites; all are saved first and written back at the end.
A_RX_INT = 0x066                     # [1:0] RX_INT_DATAWIDTH (read only, to check the width the masks assume)
SAVE_ADDRS = ([tw.A_ES_CONTROL, tw.A_ES_HORZ, tw.A_VS]
              + [tw.A_ES_QUALIFIER0 + i for i in range(5)] + [tw.A_ES_QUAL_MASK0 + i for i in range(5)] + [tw.A_ES_SDATA_MASK0 + i for i in range(5)])
#: Statistical-eye masks for a 32-bit valid data width (UG576 v1.7.1 Table 4-20, GTH: 80-bit ES_SDATA_MASK = {40'b1, 32'b0, 8'b1}; ES_QUAL_MASK all ones so every cycle counts;
#: ES_QUALIFIER 0). Word i holds bits [16 i + 15 : 16 i].
QUALIFIER = [0x0000] * 5
QUAL_MASK = [0xFFFF] * 5
SDATA_MASK_32 = [0x00FF, 0x0000, 0xFF00, 0xFFFF, 0xFFFF]
RXOUT_DIV_DECODE = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}     # DRP 0x63 [2:0] (UG576 appendix C)
COUNTS_PER_HALF_UI_AT_DIV1 = 32                       # Table 4-20: full rate, -32 .. +32 counts is -0.5 .. +0.5 UI


class Transport(Protocol):
    def rd(self, addr: int) -> int: ...
    def wr(self, addr: int, value: int) -> None: ...


class EyeScanError(RuntimeError):
    pass


def horz_field(counts: int) -> int:
    """ES_HORZ_OFFSET[11:0]: [10:0] two's complement, [11] phase unification = 1 for negative counts (UG576 Table 4-20)."""
    if not -1024 <= counts <= 1023:
        raise ValueError(f"horizontal offset {counts} does not fit 11 bits")
    return (counts & 0x7FF) | (0x800 if counts < 0 else 0)


def point_word(h: int, v: int, ut: int, rng: int, pre: int) -> int:
    """The ES_POINT register: [11:0] horizontal field, [18:12] vertical code magnitude, [19] NEG_DIR, [20] UT_SIGN, [22:21] RANGE, [27:23] prescale."""
    if not -127 <= v <= 127:
        raise ValueError(f"vertical code {v} outside -127..127")
    return horz_field(h) | (abs(v) << 12) | ((1 if v < 0 else 0) << 19) | ((ut & 1) << 20) | ((rng & 3) << 21) | ((pre & 31) << 23)


def rung_seconds(pre: int, width: int, rate_gbps: float) -> float:
    """Time for one rung whose sample counter saturates: 65535 x 2^(1+pre) cycles of `width` bits."""
    return 65535 * (1 << (1 + pre)) * width / (rate_gbps * 1e9)


class EyeHW:
    def __init__(self, t: Transport, poll_s: float = 0.0) -> None:
        self.t = t
        self.poll_s = poll_s
        self.saved: dict[int, int] = {}
        self.n_ops = 0

    # ---- registers
    def rd(self, a: int) -> int:
        self.n_ops += 1
        return self.t.rd(a)

    def wr(self, a: int, v: int) -> None:
        self.n_ops += 1
        self.t.wr(a, v)

    def features(self) -> int:
        return self.rd(R_FEATURES)

    def require_eyescan_build(self) -> None:
        f = self.features()
        if not f & FEATURE_EYESCAN:
            raise EyeScanError(f"FEATURES = {f:#x}: this bitstream has no eye-scan registers (EYESCAN = 0); program the eyescan build")

    def wait_idle(self, timeout_s: float) -> int:
        t0 = time.time()
        while True:
            st = self.rd(R_STAT)
            if not st & 1:
                return st
            if time.time() - t0 > timeout_s:
                raise EyeScanError(f"sequencer still busy after {timeout_s:.1f} s (ES_STAT {st:#x})")
            if self.poll_s:
                time.sleep(self.poll_s)

    def clear_flags(self) -> None:
        self.wr(R_CMD, 8)

    # ---- raw DRP
    def drp_read(self, addr: int) -> int:
        self.wr(R_DRP_ADDR, addr)
        self.wr(R_CMD, 1)
        st = self.wait_idle(1.0)
        if st & 0x18:
            raise EyeScanError(f"DRP read of {addr:#x} got no DRDY or was rejected (ES_STAT {st:#x})")
        return self.rd(R_DRP_DATA) & 0xFFFF

    def drp_write(self, addr: int, val: int) -> None:
        self.wr(R_DRP_ADDR, addr)
        self.wr(R_DRP_DATA, val & 0xFFFF)
        self.wr(R_CMD, 2)
        st = self.wait_idle(1.0)
        if st & 0x18:
            raise EyeScanError(f"DRP write of {addr:#x} got no DRDY or was rejected (ES_STAT {st:#x})")

    # ---- scan set-up and restore
    def geometry(self) -> dict[str, Any]:
        """RXOUT_DIV from the DRP and what follows from it: counts for half a UI and UI per count (Table 4-20)."""
        enc = self.drp_read(tw.A_RXOUT_DIV) & 7
        if enc not in RXOUT_DIV_DECODE:
            raise EyeScanError(f"RXOUT_DIV DRP encoding {enc} is not a legal value")
        div = RXOUT_DIV_DECODE[enc]
        half = COUNTS_PER_HALF_UI_AT_DIV1 * div
        return {"rxout_div": div, "counts_half_ui": half, "ui_per_count": 0.5 / half}

    def setup(self) -> dict[int, int]:
        """Save every DRP word the scan will touch, check that the build powered the eye-scan circuit up (ES_EYE_SCAN_EN and ES_ERRDET_EN, es.xdc), check the data width the
        masks assume, and write the static attributes. Returns the saved words."""
        self.require_eyescan_build()
        self.clear_flags()
        self.saved = {a: self.drp_read(a) for a in SAVE_ADDRS}
        c = self.saved[tw.A_ES_CONTROL]
        if (c >> 8) & 3 != 3:
            raise EyeScanError(f"ES_CONTROL word {c:#06x}: ES_EYE_SCAN_EN/ES_ERRDET_EN [9:8] are not both 1; this bitstream was built without es.xdc "
                               "(re-enabling eye scan through the DRP needs a PMA reset, UG576 Table 4-20, and is not done here)")
        if (c >> 10) & 0x3F:
            raise EyeScanError(f"ES_CONTROL = {c >> 10:#x} (run or arm already set): another user of the eye scan is active; not touching it")
        w = self.drp_read(A_RX_INT) & 3
        if w != 1:
            raise EyeScanError(f"RX_INT_DATAWIDTH = {w}: the statistical-eye masks written here assume the 32-bit internal width (value 1)")
        for i in range(5):
            self.drp_write(tw.A_ES_QUALIFIER0 + i, QUALIFIER[i])
            self.drp_write(tw.A_ES_QUAL_MASK0 + i, QUAL_MASK[i])
            self.drp_write(tw.A_ES_SDATA_MASK0 + i, SDATA_MASK_32[i])
        return dict(self.saved)

    def restore(self) -> dict[str, Any]:
        """Write the saved words back and read them again; `ok` only if every word reads as saved."""
        if not self.saved:
            return {"ok": False, "reason": "nothing was saved"}
        for a, v in self.saved.items():
            self.drp_write(a, v)
        after = {a: self.drp_read(a) for a in self.saved}
        bad = {f"{a:#05x}": {"saved": self.saved[a], "now": after[a]} for a in self.saved if after[a] != self.saved[a]}
        return {"ok": not bad, "mismatch": bad, "words": len(self.saved)}

    # ---- one point
    def point(self, h: int, v: int, ut: int, rng: int, pre: int, timeout_s: float) -> dict[str, Any]:
        self.wr(R_TMO, min(int(timeout_s * CLK_HZ), 0xFFFFFFFF))          # the register is 32 bits: 42.9 s at 100 MHz
        self.wr(R_POINT, point_word(h, v, ut, rng, pre))
        n0 = self.rd(R_STAT) >> 16
        self.wr(R_CMD, 4)
        st = self.wait_idle(timeout_s + 2.0)
        if st & 0x10 or ((st >> 16) - n0) & 0xFFFF != 1:
            raise EyeScanError(f"the point command did not run (ES_STAT {st:#x}, points completed {n0} -> {st >> 16}): its results would be the previous point's")
        res = self.rd(R_RES)
        return {"pre": pre, "err": res & 0xFFFF, "samp": res >> 16, "tmo": bool(st & 0x4), "drp_tmo": bool(st & 0x8), "status": (st >> 8) & 0xF}

    # ---- TX drive and equaliser (explicit, separate)
    def set_tx_drive(self, diff: int, pre: int, post: int, dfelpm_reset: bool = False) -> None:
        if not (0 <= diff <= SHIPPED_TXDIFF and 0 <= pre <= MAX_CURSOR and 0 <= post <= MAX_CURSOR):
            raise ValueError(f"TX drive {diff}/{pre}/{post} outside the allowed range (swing <= {SHIPPED_TXDIFF} = 873 mVppd, cursors <= {MAX_CURSOR} = 3.1 dB)")
        self.wr(R_DRIVE, (diff & 31) | ((pre & 31) << 5) | ((post & 31) << 10) | (0x10000 if dfelpm_reset else 0))

    def get_tx_drive(self) -> dict[str, int]:
        v = self.rd(R_DRIVE)
        return {"diff": v & 31, "pre": (v >> 5) & 31, "post": (v >> 10) & 31}

    def set_equaliser(self, lpm: bool, settle_s: float = 0.5) -> None:
        """RXLPMEN through GT_CTRL bit 6, then a pulse of RXDFELPMRESET (DRIVE bit 16) so the equaliser re-adapts, then a wait. The caller checks the link afterwards."""
        c = self.rd(R_GT_CTRL)
        self.wr(R_GT_CTRL, (c & ~0x40) | (0x40 if lpm else 0))
        d = self.get_tx_drive()
        self.set_tx_drive(d["diff"], d["pre"], d["post"], dfelpm_reset=True)
        try:
            time.sleep(0.01)
        finally:
            self.set_tx_drive(d["diff"], d["pre"], d["post"], dfelpm_reset=False)
        time.sleep(settle_s)

    def equaliser(self) -> str:
        return "LPM" if self.rd(R_GT_CTRL) & 0x40 else "DFE"
