import math
import os


def _default_coeffs(n, w):
    c = []
    fc = 0.25
    m = (n - 1) / 2.0
    for k in range(n):
        d = k - m
        s = 2 * fc if d == 0 else math.sin(2 * math.pi * fc * d) / (math.pi * d)
        win = 0.54 - 0.46 * math.cos(2 * math.pi * k / (n - 1))
        c.append(s * win)
    tot = sum(c)
    sc = (1 << (w - 1)) - 1
    return [int(round(v / tot * 0.9 * sc)) for v in c]


class Model:
    def __init__(self, NUM_TAPS=32, NUM_UNIQUE_COEFFS=16, DATA_WIDTH=16,
                 COEFF_WIDTH=16, FIFO_DEPTH=1024, SHIFT=15, ROUND_CONST=16384,
                 DESIGN_ID=546570241, RST_HOLD_CYCLES=16):
        self.NT = NUM_TAPS
        self.DW = DATA_WIDTH
        self.CW = COEFF_WIDTH
        self.DEPTH = FIFO_DEPTH
        self.SHIFT = SHIFT
        self.RC = ROUND_CONST
        self.ID = DESIGN_ID
        self.coeffs = self._load()
        self.dsp_per_cycle = 10
        self.reset()

    def _load(self):
        n = self.NT
        for p in ("data/coeffs.hex", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coeffs.hex")):
            try:
                vals = []
                with open(p) as f:
                    for line in f:
                        line = line.split("//")[0].split("#")[0].strip()
                        for t in line.split():
                            v = int(t, 16) & ((1 << self.CW) - 1)
                            if v >= 1 << (self.CW - 1):
                                v -= 1 << self.CW
                            vals.append(v)
                if len(vals) >= n:
                    return vals[:n]
            except Exception:
                pass
        h = _default_coeffs(n, self.CW)
        for k in range(n // 2):
            h[n - 1 - k] = h[k]
        return h

    def reset(self):
        self.scratch = 0
        self.inq = []
        self.outq = []
        self.hist = [0] * self.NT
        self.busy = 0
        self.sat = 0
        self.done = 0
        self.rdata = 0

    def _clear(self):
        self.inq = []
        self.outq = []
        self.hist = [0] * self.NT
        self.sat = 0
        self.done = 0
        self.busy = 0

    def _sample(self, x):
        self.hist = [x] + self.hist[:-1]
        s = sum(h * v for h, v in zip(self.coeffs, self.hist))
        y = (s + self.RC) >> self.SHIFT
        lo, hi = -(1 << (self.DW - 1)), (1 << (self.DW - 1)) - 1
        if y > hi:
            y = hi
            self.sat = (self.sat + 1) & 0xFFFFFFFF
        elif y < lo:
            y = lo
            self.sat = (self.sat + 1) & 0xFFFFFFFF
        self.done = (self.done + 1) & 0xFFFFFFFF
        return y & ((1 << self.DW) - 1)

    def step(self, inputs=None):
        if self.busy:
            n = 0
            while n < self.dsp_per_cycle and self.inq and len(self.outq) < self.DEPTH:
                x = self.inq.pop(0)
                if x >= 1 << (self.DW - 1):
                    x -= 1 << self.DW
                self.outq.append(self._sample(x))
                n += 1
            if not self.inq:
                self.busy = 0
        return {"led": self.busy & 1, "sfp_tx_disable": 1}

    def read_reg(self, offset):
        o = offset & ~3
        if o == 0:
            v = self.ID
        elif o == 8:
            v = self.scratch
        elif o == 24:
            if self.outq:
                v = 0x80000000 | self.outq.pop(0)
            else:
                v = 0
        elif o == 28:
            v = (self.busy & 1) | ((len(self.inq) & 0xFFF) << 4) | ((len(self.outq) & 0xFFF) << 20)
        elif o == 32:
            v = self.sat
        elif o == 36:
            v = self.done
        else:
            v = 0
        self.rdata = v
        return v

    def write_reg(self, offset, value):
        o = offset & ~3
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            if value & 1:
                self._clear()
            elif value & 2 and not self.busy:
                if self.inq:
                    self.busy = 1
        elif o == 20:
            if len(self.inq) < self.DEPTH:
                self.inq.append(value & ((1 << self.DW) - 1))
