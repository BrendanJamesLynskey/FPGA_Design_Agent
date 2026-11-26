import math
import os


def _load_coeffs(n, w):
    for p in ("data/coeffs.hex", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coeffs.hex")):
        try:
            vals = []
            for tok in open(p).read().split():
                v = int(tok, 16) & ((1 << w) - 1)
                vals.append(v - (1 << w) if v >> (w - 1) else v)
            if len(vals) >= n:
                return vals[:n]
        except Exception:
            pass
    # fallback: windowed-sinc low-pass, symmetric
    h = []
    for k in range(n):
        t = k - (n - 1) / 2.0
        s = 0.5 if t == 0 else math.sin(2 * math.pi * 0.1 * t) / (2 * math.pi * 0.1 * t) * 0.2 * 2.5 / 2.5
        s = 0.2 * (1.0 if t == 0 else math.sin(0.2 * math.pi * t) / (0.2 * math.pi * t))
        win = 0.54 - 0.46 * math.cos(2 * math.pi * k / (n - 1))
        h.append(int(round(s * win * (1 << (w - 1)))))
    for k in range(n // 2):
        h[n - 1 - k] = h[k]
    return h


class Model:
    def __init__(self, NUM_TAPS=32, UNIQUE_COEFFS=16, DATA_WIDTH=16, COEFF_WIDTH=16,
                 ACC_WIDTH=37, FIFO_DEPTH=1024, ROUND_CONST=16384, SHIFT=15,
                 DESIGN_ID=546570241, MMCM_MULT=10, MMCM_DIV=1):
        self.taps = NUM_TAPS
        self.dw = DATA_WIDTH
        self.depth = FIFO_DEPTH
        self.rc = ROUND_CONST
        self.shift = SHIFT
        self.design_id = DESIGN_ID
        self.per_clk = max(1, MMCM_MULT // MMCM_DIV)
        self.h = _load_coeffs(NUM_TAPS, COEFF_WIDTH)
        self.reset()

    def reset(self):
        self.scratch = 0
        self._clear()
        self.rdata = 0
        self.inputs = {}

    def _clear(self):
        self.inf = []
        self.outf = []
        self.hist = [0] * self.taps
        self.sat = 0
        self.done = 0
        self.busy = False
        self.todo = 0

    def _sample(self, x):
        self.hist = [x] + self.hist[:-1]
        acc = sum(c * v for c, v in zip(self.h, self.hist)) + self.rc
        y = acc >> self.shift
        hi = (1 << (self.dw - 1)) - 1
        lo = -(1 << (self.dw - 1))
        if y > hi:
            y = hi
            self.sat += 1
        elif y < lo:
            y = lo
            self.sat += 1
        self.outf.append(y & ((1 << self.dw) - 1))
        self.done = (self.done + 1) & 0xFFFFFFFF
        self.sat &= 0xFFFFFFFF

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            v = self.design_id
        elif o == 4:
            v = 0
        elif o == 8:
            v = self.scratch
        elif o == 16:
            v = 0
        elif o == 24:
            if self.outf:
                v = 0x80000000 | self.outf.pop(0)
            else:
                v = 0
        elif o == 28:
            v = (int(self.busy) | (len(self.inf) << 4) | (len(self.outf) << 20)) & 0xFFFFFFFF
        elif o == 32:
            v = self.sat
        elif o == 36:
            v = self.done
        else:
            v = 0
        self.rdata = v
        return v

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            if value & 1:
                self._clear()
            elif value & 2 and not self.busy:
                n = min(len(self.inf), self.depth - len(self.outf))
                if n > 0:
                    self.busy = True
                    self.todo = n
        elif o == 20:
            if len(self.inf) < self.depth:
                self.inf.append(value & 0xFFFF)

    def step(self, inputs=None):
        if inputs:
            self.inputs.update(inputs)
        i = self.inputs
        # datapath work for this clk25 period
        if self.busy:
            for _ in range(self.per_clk):
                if self.todo > 0:
                    self._sample(self.inf.pop(0))
                    self.todo -= 1
            if self.todo == 0:
                self.busy = False
        if inputs and inputs.get("h_we"):
            self.write_reg(i.get("h_addr", 0), i.get("h_wdata", 0))
        if inputs and inputs.get("h_re"):
            self.read_reg(i.get("h_addr", 0))
        return {"led": int(self.busy) | 2, "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
