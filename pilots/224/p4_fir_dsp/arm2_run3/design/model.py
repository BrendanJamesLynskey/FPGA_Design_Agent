import math
from collections import deque


def _default_coeffs(n=32):
    fc = 0.2
    h = []
    for k in range(n):
        m = k - (n - 1) / 2.0
        s = 2 * fc if m == 0 else math.sin(2 * math.pi * fc * m) / (math.pi * m)
        w = 0.54 - 0.46 * math.cos(2 * math.pi * k / (n - 1))
        h.append(s * w)
    tot = sum(h)
    q = [int(round(v / tot * 0.95 * 32768)) for v in h]
    for k in range(n // 2):
        q[n - 1 - k] = q[k]
    return q


class Model:
    def __init__(self, TAPS=32, UNIQUE_COEFFS=16, DATA_WIDTH=16, COEFF_WIDTH=16,
                 FIFO_DEPTH=1024, SHIFT=15, ROUND_CONST=16384,
                 ID_VALUE=546570241, READ_LATENCY_CYCLES=2):
        self.TAPS = TAPS
        self.DW = DATA_WIDTH
        self.depth = FIFO_DEPTH
        self.shift = SHIFT
        self.rnd = ROUND_CONST
        self.id = ID_VALUE
        self.h = _default_coeffs(TAPS)
        self.build = 0
        self.inputs = {}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.infifo = deque()
        self.outfifo = deque()
        self.hist = [0] * self.TAPS
        self.sat = 0
        self.done = 0
        self.busy = 0
        self.pending = 0
        self.hb = 0
        self.rdata = 0

    def _clear(self):
        self.infifo.clear()
        self.outfifo.clear()
        self.hist = [0] * self.TAPS
        self.sat = 0
        self.done = 0
        self.busy = 0
        self.pending = 0

    def _process(self):
        x = self.infifo.popleft()
        if x & (1 << (self.DW - 1)):
            x -= 1 << self.DW
        self.hist = [x] + self.hist[:-1]
        acc = sum(c * v for c, v in zip(self.h, self.hist)) + self.rnd
        y = acc >> self.shift
        lo, hi = -(1 << (self.DW - 1)), (1 << (self.DW - 1)) - 1
        if y > hi:
            y = hi
            self.sat += 1
        elif y < lo:
            y = lo
            self.sat += 1
        self.done = (self.done + 1) & 0xFFFFFFFF
        if len(self.outfifo) < self.depth:
            self.outfifo.append(y & 0xFFFF)
        self.pending -= 1
        if self.pending == 0:
            self.busy = 0

    def step(self, inputs=None):
        if inputs:
            self.inputs.update(inputs)
            i = self.inputs
            if i.get("h_we"):
                self.write_reg(i.get("h_addr", 0), i.get("h_wdata", 0))
            if i.get("h_re"):
                self.rdata = self.read_reg(i.get("h_addr", 0))
        if self.busy:
            self._process()
        self.hb = (self.hb + 1) & 0xFFFFFF
        return {"led": (self.busy & 1) | (((self.hb >> 23) & 1) << 1),
                "sfp_tx_disable": 1}

    def read_reg(self, offset):
        o = offset & ~3
        if o == 0:
            return self.id & 0xFFFFFFFF
        if o == 4:
            return self.build
        if o == 8:
            return self.scratch
        if o == 24:
            if self.outfifo:
                return 0x80000000 | self.outfifo.popleft()
            return 0
        if o == 28:
            return (self.busy | (len(self.infifo) << 4) | (len(self.outfifo) << 20)) & 0xFFFFFFFF
        if o == 32:
            return self.sat
        if o == 36:
            return self.done
        return 0

    def write_reg(self, offset, value):
        o = offset & ~3
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            if value & 1:
                self._clear()
            elif value & 2:
                if not self.busy and self.infifo:
                    self.busy = 1
                    self.pending = len(self.infifo)
        elif o == 20:
            if len(self.infifo) < self.depth:
                self.infifo.append(value & 0xFFFF)
