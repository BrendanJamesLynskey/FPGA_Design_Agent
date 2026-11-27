import os


def _load_coeffs(n, w):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coeffs.hex")
    h = []
    try:
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("//"):
                v = int(line, 16) & ((1 << w) - 1)
                h.append(v - (1 << w) if v >> (w - 1) else v)
    except Exception:
        h = []
    if len(h) < n:
        half = n // 2
        u = [(-1) ** k * 0 + 1000 + 500 * (half - k) for k in range(half)]
        h = u + u[::-1]
    return h[:n]


class Model:
    def __init__(self, NUM_TAPS=32, UNIQUE_COEFFS=16, DATA_WIDTH=16, COEFF_WIDTH=16,
                 FIFO_DEPTH=1024, ACC_WIDTH=38, ROUND_CONST=16384, SHIFT=15,
                 DESIGN_ID=546570241, MMCM_MULT=40, MMCM_OUT_DIVIDE=4):
        self.N = NUM_TAPS
        self.DW = DATA_WIDTH
        self.depth = FIFO_DEPTH
        self.rc = ROUND_CONST
        self.sh = SHIFT
        self.id = DESIGN_ID & 0xFFFFFFFF
        self.h = _load_coeffs(NUM_TAPS, COEFF_WIDTH)
        self.build = 0
        self.inp = {}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.infifo = []
        self.outfifo = []
        self.hist = [0] * self.N
        self.sat = 0
        self.done = 0
        self.busy = 0
        self.rdata = 0

    def _clear(self):
        self.infifo = []
        self.outfifo = []
        self.hist = [0] * self.N
        self.sat = 0
        self.done = 0
        self.busy = 0

    def write_reg(self, offset, value):
        value &= 0xFFFFFFFF
        if offset == 8:
            self.scratch = value
        elif offset == 16:
            if value & 1:
                self._clear()
            elif value & 2 and not self.busy:
                if self.infifo:
                    self.busy = 1
        elif offset == 20:
            if len(self.infifo) < self.depth:
                self.infifo.append(value & ((1 << self.DW) - 1))

    def read_reg(self, offset):
        if offset == 0:
            return self.id
        if offset == 4:
            return self.build
        if offset == 8:
            return self.scratch
        if offset == 28:
            return (self.busy | ((len(self.infifo) & 0xFFF) << 4)
                    | ((len(self.outfifo) & 0xFFF) << 20))
        if offset == 24:
            if not self.outfifo:
                return 0
            return 0x80000000 | self.outfifo.pop(0)
        if offset == 32:
            return self.sat & 0xFFFFFFFF
        if offset == 36:
            return self.done & 0xFFFFFFFF
        return 0

    def _sample(self):
        x = self.infifo.pop(0)
        if x >> (self.DW - 1):
            x -= 1 << self.DW
        self.hist = [x] + self.hist[:-1]
        acc = sum(c * s for c, s in zip(self.h, self.hist))
        y = (acc + self.rc) >> self.sh
        hi, lo = (1 << (self.DW - 1)) - 1, -(1 << (self.DW - 1))
        if y > hi:
            y = hi
            self.sat += 1
        elif y < lo:
            y = lo
            self.sat += 1
        self.outfifo.append(y & ((1 << self.DW) - 1))
        self.done += 1

    def step(self, inputs=None):
        if inputs:
            self.inp.update(inputs)
        i = self.inp
        if i.get("h_we"):
            self.write_reg(i.get("h_addr", 0), i.get("h_wdata", 0))
            i["h_we"] = 0
        if i.get("h_re"):
            self.rdata = self.read_reg(i.get("h_addr", 0))
            i["h_re"] = 0
        if self.busy:
            if self.infifo and len(self.outfifo) < self.depth:
                self._sample()
            if not self.infifo:
                self.busy = 0
        return {"led": self.busy | 2, "sfp_tx_disable": 1, "h_rdata": self.rdata}
