import math, os


def _load_coeffs(n, w):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coeffs.hex")
    try:
        with open(p) as f:
            v = []
            for t in f.read().split():
                t = t.strip()
                if not t or t.startswith("//") or t.startswith("#"):
                    continue
                x = int(t, 16) & ((1 << w) - 1)
                if x >= 1 << (w - 1):
                    x -= 1 << w
                v.append(x)
        if len(v) >= n:
            return v[:n]
    except Exception:
        pass
    c = (n - 1) / 2.0
    out = []
    for k in range(n):
        d = k - c
        s = 0.25 if d == 0 else math.sin(0.25 * math.pi * d) / (math.pi * d)
        wn = 0.54 - 0.46 * math.cos(2 * math.pi * k / (n - 1))
        out.append(int(round(s * wn * (1 << (w - 1)))))
    return out


class Model:
    PIPE = 10

    def __init__(self, NUM_TAPS=32, DATA_WIDTH=16, COEFF_WIDTH=16, ACC_WIDTH=40,
                 FIFO_DEPTH=1024, ROUND_CONST=16384, SHIFT=15, DESIGN_ID=546570241):
        self.NT = NUM_TAPS
        self.DW = DATA_WIDTH
        self.depth = FIFO_DEPTH
        self.rc = ROUND_CONST
        self.sh = SHIFT
        self.design_id = DESIGN_ID
        self.h = _load_coeffs(NUM_TAPS, COEFF_WIDTH)
        self.build = 0
        self.reset()

    def reset(self):
        self.inp = []
        self.out = []
        self.hist = [0] * self.NT
        self.sat = 0
        self.done = 0
        self.scratch = 0
        self.busy = False
        self.remaining = 0
        self.pending = []  # [countdown, value, sat]
        self.rdata = 0
        self.cyc = 0
        self.ins = {}

    def _clear(self):
        self.inp = []
        self.out = []
        self.hist = [0] * self.NT
        self.sat = 0
        self.done = 0
        self.busy = False
        self.remaining = 0
        self.pending = []

    def _compute(self, x):
        self.hist = [x] + self.hist[:-1]
        acc = sum(a * b for a, b in zip(self.h, self.hist))
        y = (acc + self.rc) >> self.sh
        s = 0
        if y > 32767:
            y, s = 32767, 1
        elif y < -32768:
            y, s = -32768, 1
        return y & 0xFFFF, s

    def read_reg(self, off):
        if off == 0:
            return self.design_id & 0xFFFFFFFF
        if off == 4:
            return self.build
        if off == 8:
            return self.scratch
        if off == 24:
            if self.out:
                return 0x80000000 | self.out.pop(0)
            return 0
        if off == 28:
            return (int(self.busy) | (len(self.inp) << 4) | (len(self.out) << 20)) & 0xFFFFFFFF
        if off == 32:
            return self.sat & 0xFFFFFFFF
        if off == 36:
            return self.done & 0xFFFFFFFF
        return 0

    def write_reg(self, off, v):
        v &= 0xFFFFFFFF
        if off == 8:
            self.scratch = v
        elif off == 16:
            if v & 1:
                self._clear()
            elif v & 2 and not self.busy:
                n = min(len(self.inp), self.depth - len(self.out))
                if n > 0:
                    self.busy = True
                    self.remaining = n
        elif off == 20:
            if len(self.inp) < self.depth:
                self.inp.append(v & 0xFFFF)

    def step(self, inputs=None):
        if inputs:
            self.ins.update(inputs)
        i = self.ins
        # datapath
        for p in self.pending:
            p[0] -= 1
        while self.pending and self.pending[0][0] <= 0:
            _, y, s = self.pending.pop(0)
            self.out.append(y)
            self.sat += s
            self.done += 1
        if self.remaining > 0:
            y, s = self._compute(self.inp.pop(0))
            self.remaining -= 1
            self.pending.append([self.PIPE, y, s])
        if self.busy and self.remaining == 0 and not self.pending:
            self.busy = False
        # bus
        if i.get("h_we"):
            self.write_reg(i.get("h_addr", 0), i.get("h_wdata", 0))
            # a run started this cycle becomes busy immediately
        if i.get("h_re"):
            self.rdata = self.read_reg(i.get("h_addr", 0))
        return {"led": int(self.busy) | (int(bool(self.out)) << 1),
                "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
