"""Host drivers for the library instruments, over the test shell (brief 30).

Each class takes an object with read(addr) -> int and write(addr, value) (shell.host.fpga_shell.FpgaShell, or any
stand-in) and the absolute shell address of the instrument's first register (window base 0x80 + the design's offset).
The register maps are in the RTL headers (ip_lib/<block>/rtl) and in designs/b30_hil_audio/rtl.
"""
from __future__ import annotations

import time
from typing import Protocol

from hil.instruments import models

WINDOW = 0x80


class Shell(Protocol):
    def read(self, addr: int) -> int: ...
    def write(self, addr: int, value: int) -> None: ...


# ---------------------------------------------------------------------------------------------------- XADC (UG480)
def xadc_temp_c(code: int) -> float:
    return code * 503.975 / 4096 - 273.15


def xadc_volts(code: int) -> float:
    """Supply channels: 3 V full scale (UG480 table for the on-chip supply sensors)."""
    return code * 3.0 / 4096


class XadcHost:
    """Tj, VCCINT, VCCAUX and VCCBRAM from the four code registers b30_hil_audio polls from the XADC."""
    def __init__(self, sh: Shell, base: int = WINDOW + 0x40) -> None:
        self.sh, self.base = sh, base

    def read(self) -> dict[str, float]:
        c = [self.sh.read(self.base + i) & 0xFFF for i in range(4)]
        return {"tj_c": xadc_temp_c(c[0]), "vccint_v": xadc_volts(c[1]), "vccaux_v": xadc_volts(c[2]),
                "vccbram_v": xadc_volts(c[3]), "codes": c}


# ---------------------------------------------------------------------------------------------------- logic analyser
class LogicAnalyserHost:
    """ip_lib/logic_analyser over the shell: set a trigger, arm, wait, read the buffer back in capture order."""
    CTRL, STATUS, MASK, VALUE, PRE, DEPTH, RD_ADDR, RD_DATA, RAWCOUNT = range(9)

    def __init__(self, sh: Shell, base: int = WINDOW + 0x20) -> None:
        self.sh, self.base = sh, base

    def _r(self, reg: int) -> int:
        return self.sh.read(self.base + reg)

    def _w(self, reg: int, v: int) -> None:
        self.sh.write(self.base + reg, v)

    def depth(self) -> int:
        return self._r(self.DEPTH)

    def capture(self, mask: int, value: int, pre: int = 0, edge: bool = False, timeout_s: float = 5.0) -> list[int]:
        self._w(self.MASK, mask)
        self._w(self.VALUE, value)
        self._w(self.PRE, pre)
        self._w(self.CTRL, 1 | (2 if edge else 0))
        t0 = time.time()
        while not (self._r(self.STATUS) & 4):
            if time.time() - t0 > timeout_s:
                self._w(self.CTRL, 4)                     # abort
                raise TimeoutError("logic analyser never triggered")
        out = []
        for k in range(self.depth()):
            self._w(self.RD_ADDR, k)
            out.append(self._r(self.RD_DATA))
        return out


# ---------------------------------------------------------------------------------------------------- freq / duty
class FreqDutyHost:
    def __init__(self, sh: Shell, f_clk: float = 100e6, base: int = WINDOW + 0x10) -> None:
        self.sh, self.base, self.f_clk = sh, base, f_clk

    def read(self) -> dict[str, float]:
        edges, high, gates, gate_clks = (self.sh.read(self.base + i) for i in range(4))
        f, d = models.freq_duty(edges, high, gate_clks, self.f_clk)
        return {"edges": edges, "high_clks": high, "gates": gates, "gate_clks": gate_clks, "freq_hz": f, "duty": d}


# ---------------------------------------------------------------------------------------------------- frame CRC
class FrameCrcHost:
    def __init__(self, sh: Shell, base: int = WINDOW + 0x50) -> None:
        self.sh, self.base = sh, base

    def set_expect(self, crc: int) -> None:
        self.sh.write(self.base + 4, crc)

    def read(self) -> dict[str, int]:
        names = ("crc", "frames", "pix", "sum", "expect", "mismatches")
        return {n: self.sh.read(self.base + i) for i, n in enumerate(names)}


def lfsr_frame(n: int = 128, seed: int = 0xACE1) -> list[int]:
    """The 24-bit LFSR pixel words b30_hil_audio sends each frame: s <= {s[22:0], s23^s22^s21^s16}."""
    s, out = seed, []
    for _ in range(n):
        out.append(s)
        s = ((s << 1) & 0xFFFFFF) | (((s >> 23) ^ (s >> 22) ^ (s >> 21) ^ (s >> 16)) & 1)
    return out
