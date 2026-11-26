"""Behavioural models of the two custom Red Pitaya instruments, written from the register maps in ``hil/redpitaya_regs.py`` (brief 225).

They are the mock of the AXI window the dry run and the tests use: a model is what the spec says the block does, in arithmetic, without clocks (a one-second
gate is not simulated cycle by cycle). They are **not** the RTL and not evidence about it: the RTL is checked by its own simulation, and the board by the
owner's run. A reading through a model is marked ``mock`` everywhere it is recorded.

The models stay inside the map, like the real windows: a read or write of an unmapped offset raises :class:`BusError` (the shell answers such an access with
an error line; a write to a read-only register is ignored and also answers with an error).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from hil.redpitaya_regs import FREQCOUNT, PATGEN, RegMap, WindowError, sext14

F_CLK = 125_000_000.0


class BusError(WindowError):
    """The access the shell would answer with its error line."""


@dataclass
class SineSignal:
    """What IN1 sees: a sine of ``freq_hz`` with ``amp`` counts of amplitude around ``offset`` counts (14-bit counts, +-8192 is full scale). The phase at the
    start of a gate is ``phase0`` cycles (0 to 1); a model with no signal (``amp`` 0) sees a constant ``offset``."""
    freq_hz: float
    amp: float = 4000.0
    offset: float = 0.0
    phase0: float = 0.0


class _Base:
    MAP: RegMap

    def __init__(self) -> None:
        self.regs = {r.name: r.reset for r in self.MAP.regs}
        self._by_off = {r.offset: r for r in self.MAP.regs}
        self.writes: list[tuple[str, int]] = []

    def _reg(self, offset: int):
        r = self._by_off.get(offset)
        if r is None:
            raise BusError(f"offset {offset:#x} is not in the map of {self.MAP.block}")
        return r

    def read(self, offset: int) -> int:
        r = self._reg(offset)
        return self.on_read(r.name) & 0xFFFFFFFF

    def write(self, offset: int, value: int) -> None:
        r = self._reg(offset)
        if r.access == "RO":
            raise BusError(f"{r.name} is read-only (the block ignores the write and answers with an error)")
        self.writes.append((r.name, value))
        self.on_write(r.name, value & 0xFFFFFFFF)

    def on_read(self, name: str) -> int:
        return self.regs[name]

    def on_write(self, name: str, v: int) -> None:
        self.regs[name] = v


class FreqCountModel(_Base):
    """``rp_freqcount``: gated edge counting with a Schmitt trigger, and the first-to-last-edge span for the reciprocal method.

    A gate takes ``GATE_LEN`` cycles of simulated time; every read of STATUS while a gate is running advances simulated time by a quarter of the gate, so a
    polling script ends. ``signal`` is the :class:`SineSignal` on IN1 (None: a flat line at 0, no edges)."""
    MAP = FREQCOUNT

    def __init__(self, signal: SineSignal | None = None, clk_hz: float = F_CLK) -> None:
        super().__init__()
        self.signal, self.clk_hz = signal, clk_hz
        self._busy_left = 0.0                       # cycles of the running gate still to go
        self._pending: dict[str, int] | None = None
        self.regs["THR_LOW"] = 0xFFFFFF00           # -256 sign-extended, as the register reads back

    # -- the arithmetic of one gate ----------------------------------------------------------------------------------------------------
    def gate(self, gate_cycles: int) -> dict[str, int]:
        hi, lo = sext14(self.regs["THR_HIGH"]), sext14(self.regs["THR_LOW"])
        bad = hi <= lo
        s = self.signal
        status = 0
        if bad:
            status |= 8
        edges, span = 0, 0
        if s is not None and not bad and s.amp > 0 and s.freq_hz > 0:
            top, bottom = s.offset + s.amp, s.offset - s.amp
            if top >= hi and bottom <= lo:          # the swing reaches both thresholds: one counted edge per cycle
                period = self.clk_hz / s.freq_hz    # in adc_clk cycles (float)
                phi = math.asin(max(-1.0, min(1.0, (hi - s.offset) / s.amp))) / (2 * math.pi) % 1.0     # the rising crossing of THR_HIGH, in cycles of the signal
                first = ((phi - s.phase0) % 1.0) * period
                t = first
                times = []
                while t < gate_cycles:
                    times.append(t)
                    t += period
                edges = len(times)
                if edges >= 2:
                    span = int(round(times[-1] - times[0]))
        if edges < 2:
            status |= 4
        return {"EDGES": edges, "GATE_ACTUAL": gate_cycles, "SPAN": span, "status": status}

    # -- registers ---------------------------------------------------------------------------------------------------------------------
    def on_write(self, name: str, v: int) -> None:
        if name == "CTRL":
            if v & 1 and self._busy_left <= 0:
                glen = self.regs["GATE_LEN"]
                self._busy_left = float(glen)
                self._pending = self.gate(glen)
                self.regs["STATUS"] &= ~2
            self.regs["CTRL"] = v & 2                 # START reads back 0
        elif name == "GATE_LEN":
            self.regs["GATE_LEN"] = max(1000, v)
        elif name in ("THR_HIGH", "THR_LOW"):
            self.regs[name] = sext14(v) & 0xFFFFFFFF
        else:
            self.regs[name] = v

    def on_read(self, name: str) -> int:
        if name == "STATUS":
            if self._busy_left > 0:
                self._busy_left -= max(1.0, self.regs["GATE_LEN"] / 4.0)
                if self._busy_left <= 0:
                    self._finish()
            busy = 1 if self._busy_left > 0 else 0
            return (self.regs["STATUS"] & ~1) | busy
        return self.regs[name]

    def _finish(self) -> None:
        p = self._pending or {}
        self.regs.update(EDGES=p["EDGES"], GATE_ACTUAL=p["GATE_ACTUAL"], SPAN=p["SPAN"], MEAS_DONE=(self.regs["MEAS_DONE"] + 1) & 0xFFFFFFFF)
        self.regs["STATUS"] = (self.regs["STATUS"] & ~(4 | 8)) | p["status"] | 2
        self._pending = None
        if self.regs["CTRL"] & 2:                     # CONT: the next gate starts at once
            self._busy_left = float(self.regs["GATE_LEN"])
            self._pending = self.gate(self.regs["GATE_LEN"])


class PatGenModel(_Base):
    """``rp_patgen``: a pulse or pattern sequence on OUT1, every level cut to +-LIMIT. :meth:`output` gives the DAC count at a cycle after START, so a test can
    check the waveform and the clamp without clocks. A sequence is instantaneous in this model (STATUS shows DONE at once unless CONT is set)."""
    MAP = PATGEN
    HARD_LIMIT = 7372

    def __init__(self) -> None:
        super().__init__()
        self.running = False
        self.clamped = False
        self._start: dict | None = None

    def on_write(self, name: str, v: int) -> None:
        r = self.regs
        if name == "CTRL":
            if v & 2:
                self.running, self._start, r["STATUS"] = False, None, (r["STATUS"] & ~1) | 2
            else:
                r["CTRL"] = v & 4
                if v & 1 and not self.running:
                    self._begin()
            r["CTRL"] = v & 4
        elif name == "MODE":
            r["MODE"] = v if v in (0, 1) else 0
        elif name == "PERIOD":
            r["PERIOD"] = max(2, v)
        elif name in ("LEVEL_HI", "LEVEL_LO") or name.startswith("PAT") and name[3:].isdigit():
            r[name] = sext14(v) & 0xFFFFFFFF
        elif name == "COUNT":
            r["COUNT"] = max(1, min(65535, v))
        elif name == "LIMIT":
            r["LIMIT"] = min(v, self.HARD_LIMIT)
        elif name == "PAT_LEN":
            r["PAT_LEN"] = max(1, min(16, v))
        elif name == "SAMPLE_DIV":
            r["SAMPLE_DIV"] = max(1, min(65535, v))
        else:
            r[name] = v

    def _begin(self) -> None:
        r = self.regs
        period = r["PERIOD"]
        width = max(1, min(period - 1, r["WIDTH"]))
        self._start = {"mode": r["MODE"], "period": period, "width": width, "hi": sext14(r["LEVEL_HI"]), "lo": sext14(r["LEVEL_LO"]), "limit": r["LIMIT"],
                       "pat": [sext14(r[f"PAT{i}"]) for i in range(r["PAT_LEN"])], "div": r["SAMPLE_DIV"], "count": r["COUNT"], "cont": bool(r["CTRL"] & 4)}
        s = self._start
        raw = [s["hi"], s["lo"]] if s["mode"] == 0 else s["pat"]
        self.clamped = any(abs(x) > s["limit"] for x in raw)
        self.running = bool(s["cont"])
        r["STATUS"] = (r["STATUS"] & ~7) | (1 if self.running else 2) | (4 if self.clamped else 0)
        r["PERIODS_DONE"] = 0 if s["cont"] else s["count"]

    def on_read(self, name: str) -> int:
        return self.regs[name]

    def output(self, cycle: int) -> int:
        """The DAC count ``cycle`` adc_clk cycles after the START write (0 when idle, done or stopped), cut to +-LIMIT."""
        s = self._start
        if s is None or (not self.running and self.regs["STATUS"] & 2 == 0):
            return 0
        def cut(x: int) -> int:
            return max(-s["limit"], min(s["limit"], x))
        if s["mode"] == 0:
            span, per = s["period"] * (s["count"] if not s["cont"] else 1 << 60), s["period"]
            if cycle >= span:
                return 0
            return cut(s["hi"] if cycle % per < s["width"] else s["lo"])
        n = len(s["pat"])
        span = n * s["div"] * (s["count"] if not s["cont"] else 1 << 60)
        if cycle >= span:
            return 0
        return cut(s["pat"][(cycle // s["div"]) % n])
