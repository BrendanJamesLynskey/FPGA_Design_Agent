import os
from collections import deque

_DEFAULT = [-30, 0, 62, 0, -120, 0, 210, 0, -340, 0, 520, 0, -780, 0, 1250, 0]


def _load_coeffs(n):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "data", "coeffs.hex"), os.path.join("data", "coeffs.hex")):
        try:
            vals = []
            for line in open(p):
                line = line.split("//")[0].strip()
                for tok in line.split():
                    v = int(tok, 16) & 0xFFFF
                    vals.append(v - 65536 if v & 0x8000 else v)
            if len(vals) >= n:
                return vals[:n]
            if len(vals) == n // 2:
                return vals + vals[::-1]
        except Exception:
            pass
    half = (_DEFAULT * 2)[:n // 2]
    return half + half[::-1]


class Model:
    SAMPLES_PER_STEP = 10  # clk_dp / clk_25

    def __init__(self, NUM_TAPS=32, UNIQUE_COEFFS=16, DATA_WIDTH=16, COEFF_WIDTH=16,
                 FIFO_DEPTH=1024, ROUND_CONST=16384, SHIFT=15, RESET_CYCLES=16,
                 DESIGN_ID=546570241):
        self.NUM_TAPS = NUM_TAPS
        self.DW = DATA_WIDTH
        self.depth = FIFO_DEPTH
        self.rc = ROUND_CONST
        self.shift = SHIFT
        self.design_id = DESIGN_ID
        self.h = _load_coeffs(NUM_TAPS)
        self.reset()

    def reset(self):
        self.scratch = 0
        self.infifo = deque()
        self.outfifo = deque()
        self.hist = [0] * self.NUM_TAPS
        self.busy = False
        self.pending = 0
        self.sat = 0
        self.done = 0
        self.sticky = False
        self.rdata = 0

    def _sample(self, x):
        self.hist = [x] + self.hist[:-1]
        s = sum(c * v for c, v in zip(self.h, self.hist)) + self.rc
        y = s >> self.shift
        if y > 32767:
            y = 32767
            self.sat += 1
            self.sticky = True
        elif y < -32768:
            y = -32768
            self.sat += 1
            self.sticky = True
        self.sat &= 0xFFFFFFFF
        self.outfifo.append(y & 0xFFFF)
        self.done = (self.done + 1) & 0xFFFFFFFF

    def step(self, inputs=None):
        if self.busy:
            for _ in range(self.SAMPLES_PER_STEP):
                if self.pending <= 0:
                    break
                x = self.infifo.popleft()
                x = x - 65536 if x & 0x8000 else x
                self._sample(x)
                self.pending -= 1
            if self.pending <= 0:
                self.busy = False
        return {"led": (1 if self.busy else 0) | (2 if self.sticky else 0),
                "sfp_tx_disable": 1}

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            v = self.design_id
        elif o == 8:
            v = self.scratch
        elif o == 16:
            v = 0
        elif o == 24:
            if self.outfifo:
                v = 0x80000000 | self.outfifo.popleft()
            else:
                v = 0
        elif o == 28:
            v = (int(self.busy) | (len(self.infifo) << 4) | (len(self.outfifo) << 20))
        elif o == 32:
            v = self.sat
        elif o == 36:
            v = self.done
        else:
            v = 0
        self.rdata = v & 0xFFFFFFFF
        return self.rdata

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            if value & 1:
                self.infifo.clear()
                self.outfifo.clear()
                self.hist = [0] * self.NUM_TAPS
                self.sat = 0
                self.done = 0
                self.sticky = False
                self.busy = False
                self.pending = 0
            elif (value & 2) and not self.busy:
                n = min(len(self.infifo), self.depth - len(self.outfifo))
                if n > 0:
                    self.busy = True
                    self.pending = n
        elif o == 20:
            if len(self.infifo) < self.depth:
                self.infifo.append(value & 0xFFFF)
