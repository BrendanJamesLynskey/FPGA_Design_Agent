import os


def _load_coeffs(n, w):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "data", "coeffs.hex"), os.path.join("data", "coeffs.hex")):
        if os.path.exists(p):
            vals = []
            for tok in open(p).read().split():
                if tok.startswith("//"):
                    continue
                try:
                    v = int(tok, 16) & ((1 << w) - 1)
                except ValueError:
                    continue
                vals.append(v - (1 << w) if v >> (w - 1) else v)
            if len(vals) >= n:
                return vals[:n]
    half = n // 2
    h = [1000 + 500 * min(i, half - 1 - i) for i in range(half)]
    return h + h[::-1]


class Model:
    LAT = 8

    def __init__(self, NUM_TAPS=32, UNIQUE_COEFFS=16, DATA_WIDTH=16, COEFF_WIDTH=16,
                 FIFO_DEPTH=1024, SHIFT=15, ROUND_CONST=16384, ID_VALUE=546570241,
                 SFP_TX_DISABLE_VALUE=1):
        self.NT = NUM_TAPS
        self.DW = DATA_WIDTH
        self.depth = FIFO_DEPTH
        self.shift = SHIFT
        self.rc = ROUND_CONST
        self.id = ID_VALUE
        self.sfp = SFP_TX_DISABLE_VALUE
        self.h = _load_coeffs(NUM_TAPS, COEFF_WIDTH)
        self.inputs = {}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.infifo = []
        self.outfifo = []
        self.hist = [0] * self.NT
        self.sat = 0
        self.done = 0
        self.pending = []  # [release_cycle_remaining, value]
        self.busy_cnt = 0
        self.rdata = 0
        self.inputs = {}

    @property
    def busy(self):
        return 1 if self.busy_cnt > 0 else 0

    def _filter(self, x):
        self.hist = [x] + self.hist[:-1]
        s = sum(c * v for c, v in zip(self.h, self.hist)) + self.rc
        y = s >> self.shift
        if y > 32767:
            y = 32767
            self.sat += 1
        elif y < -32768:
            y = -32768
            self.sat += 1
        self.sat &= 0xFFFFFFFF
        return y & 0xFFFF

    def _tick(self):
        if self.busy_cnt > 0:
            self.busy_cnt -= 1
        rem = []
        for p in self.pending:
            p[0] -= 1
            if p[0] <= 0:
                self.outfifo.append(p[1])
            else:
                rem.append(p)
        self.pending = rem

    def write_reg(self, offset, value):
        value &= 0xFFFFFFFF
        if offset == 8:
            self.scratch = value
        elif offset == 16:
            if self.busy:
                return
            if value & 1:
                self.infifo = []
                self.outfifo = []
                self.hist = [0] * self.NT
                self.sat = 0
                self.done = 0
            elif value & 2:
                n = min(len(self.infifo), self.depth - len(self.outfifo))
                if n > 0:
                    for i in range(n):
                        x = self.infifo.pop(0)
                        if x >> 15:
                            x -= 1 << 16
                        y = self._filter(x)
                        self.pending.append([i + self.LAT + 1, y])
                    self.done = (self.done + n) & 0xFFFFFFFF
                    self.busy_cnt = n + self.LAT
        elif offset == 20:
            if not self.busy and len(self.infifo) < self.depth:
                self.infifo.append(value & 0xFFFF)

    def read_reg(self, offset):
        if offset == 0:
            return self.id
        if offset == 4:
            return 0
        if offset == 8:
            return self.scratch
        if offset == 24:
            if self.outfifo:
                return 0x80000000 | self.outfifo.pop(0)
            return 0
        if offset == 28:
            return (self.busy | (len(self.infifo) << 4) | (len(self.outfifo) << 20)) & 0xFFFFFFFF
        if offset == 32:
            return self.sat
        if offset == 36:
            return self.done
        return 0

    def step(self, inputs=None):
        if inputs:
            self.inputs.update(inputs)
        i = self.inputs
        self._tick()
        we = i.get("h_we", 0)
        re = i.get("h_re", 0)
        addr = i.get("h_addr", 0)
        if we:
            self.write_reg(addr, i.get("h_wdata", 0))
        if re:
            self.rdata = self.read_reg(addr)
        # strobes are one-cycle pulses
        self.inputs["h_we"] = 0
        self.inputs["h_re"] = 0
        return {"led": self.busy | 2, "sfp_tx_disable": self.sfp & 1,
                "h_rdata": self.rdata}
