import os
from collections import deque


def _load_coeffs(n):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "data", "coeffs.hex"), "data/coeffs.hex"):
        try:
            with open(p) as f:
                v = [int(l.strip(), 16) for l in f if l.strip()]
            v = [x - 65536 if x & 0x8000 else x for x in v]
            if len(v) >= n:
                return v[:n]
        except Exception:
            pass
    # fallback: symmetric low-pass (windowed sinc), Q1.15
    import math
    out = []
    for k in range(n):
        d = k - (n - 1) / 2.0
        s = 0.4 if d == 0 else math.sin(0.4 * math.pi * d) / (math.pi * d)
        w = 0.54 - 0.46 * math.cos(2 * math.pi * k / (n - 1))
        out.append(int(round(s * w * 32768)))
    return out


class Model:
    SPEED = 10  # samples per clk cycle (clk_dsp = 10 x clk)

    def __init__(self, NUM_TAPS=32, UNIQUE_COEFFS=16, DATA_WIDTH=16, COEFF_WIDTH=16,
                 FIFO_DEPTH=1024, ACC_WIDTH=38, SHIFT=15, ROUND_CONST=16384,
                 DESIGN_ID=546570241, MMCM_MULT=10, MMCM_DIV=1):
        self.NUM_TAPS = NUM_TAPS
        self.DEPTH = FIFO_DEPTH
        self.SHIFT = SHIFT
        self.RC = ROUND_CONST
        self.ID = DESIGN_ID
        self.DW = DATA_WIDTH
        self.h = _load_coeffs(NUM_TAPS)
        self.SPEED = max(1, MMCM_MULT // max(1, MMCM_DIV))
        self.inp = {"rst": 0, "h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.scratch = 0
        self.rdata = 0
        self._clear()
        self.busy = 0

    def _clear(self):
        self.fin = deque()
        self.fout = deque()
        self.hist = [0] * self.NUM_TAPS
        self.sat = 0
        self.done = 0
        self.busy = 0

    def reset(self):
        self.scratch = 0
        self.rdata = 0
        self._clear()
        self.inp = {"rst": 0, "h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}

    def _status(self):
        return (self.busy & 1) | (len(self.fin) << 4) | (len(self.fout) << 20)

    def read_reg(self, offset, pop=True):
        o = offset & 0xFFF
        if o == 0:
            return self.ID & 0xFFFFFFFF
        if o == 4:
            return 0
        if o == 8:
            return self.scratch
        if o == 16:
            return 0
        if o == 24:
            if self.fout:
                v = self.fout.popleft() if pop else self.fout[0]
                return 0x80000000 | (v & 0xFFFF)
            return 0
        if o == 28:
            return self._status() & 0xFFFFFFFF
        if o == 32:
            return self.sat & 0xFFFFFFFF
        if o == 36:
            return self.done & 0xFFFFFFFF
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            if value & 1:
                self._clear()
            elif value & 2 and not self.busy:
                self.busy = 1
        elif o == 20:
            if len(self.fin) < self.DEPTH:
                self.fin.append(value & 0xFFFF)

    def _process(self):
        for _ in range(self.SPEED):
            if not self.fin or len(self.fout) >= self.DEPTH:
                break
            x = self.fin.popleft()
            if x & 0x8000:
                x -= 65536
            self.hist = [x] + self.hist[:-1]
            acc = sum(a * b for a, b in zip(self.h, self.hist))
            y = (acc + self.RC) >> self.SHIFT
            if y > 32767:
                y = 32767
                self.sat += 1
            elif y < -32768:
                y = -32768
                self.sat += 1
            self.fout.append(y & 0xFFFF)
            self.done += 1
        if self.busy and not self.fin:
            self.busy = 0

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                self.inp[k] = int(v)
        i = self.inp
        if i["rst"]:
            self.reset()
            self.inp["rst"] = 1
        else:
            if self.busy:
                self._process()
            if i["h_we"]:
                self.write_reg(i["h_addr"], i["h_wdata"])
            if i["h_re"]:
                self.rdata = self.read_reg(i["h_addr"])
        self.inp["h_we"] = 0
        self.inp["h_re"] = 0
        return {"led": (self.busy & 1) | 2, "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
