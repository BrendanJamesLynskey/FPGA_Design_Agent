import os


def _load_coeffs(n):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "data", "coeffs.hex"), os.path.join("data", "coeffs.hex")):
        if os.path.exists(p):
            vals = []
            for ln in open(p):
                ln = ln.split("//")[0].strip()
                if ln:
                    v = int(ln, 16) & 0xFFFF
                    vals.append(v - 65536 if v & 0x8000 else v)
            if len(vals) >= n:
                return vals[:n]
    half = [-30, -60, -40, 90, 250, 100, -420, -700, 150, 1500, 1400,
            -1200, -4000, -1500, 9000, 21000]
    return (half + half[::-1])[:n] if n == 32 else [0] * n


class Model:
    DSP_PER_CLK = 10
    LATENCY = 11

    def __init__(self, N_TAPS=32, N_MULT=16, DATA_WIDTH=16, COEF_WIDTH=16,
                 ACC_WIDTH=38, FIFO_DEPTH=1024, SHIFT=15, ROUND_CONST=16384,
                 DESIGN_ID=546570241, SFP_TX_DISABLE_VALUE=1):
        self.n_taps = N_TAPS
        self.depth = FIFO_DEPTH
        self.shift = SHIFT
        self.rc = ROUND_CONST
        self.dw = DATA_WIDTH
        self.design_id = DESIGN_ID
        self.sfp = SFP_TX_DISABLE_VALUE
        self.h = _load_coeffs(N_TAPS)
        self.reset()

    def reset(self):
        self.scratch = 0
        self.infifo = []
        self.outfifo = []
        self.hist = [0] * self.n_taps
        self.sat = 0
        self.done = 0
        self.busy = False
        self.todo = []      # samples issued for current run
        self.pipe = []      # [countdown, result, sat]
        self.rdata = 0
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}

    def _filter(self, x):
        self.hist = [x] + self.hist[:-1]
        acc = sum(c * s for c, s in zip(self.h, self.hist)) + self.rc
        y = acc >> self.shift
        lo, hi = -(1 << (self.dw - 1)), (1 << (self.dw - 1)) - 1
        s = 0
        if y > hi:
            y, s = hi, 1
        elif y < lo:
            y, s = lo, 1
        return y & ((1 << self.dw) - 1), s

    def _status(self):
        return (int(self.busy) | (len(self.infifo) << 4) | (len(self.outfifo) << 20)) & 0xFFFFFFFF

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.design_id & 0xFFFFFFFF
        if o == 4:
            return 0
        if o == 8:
            return self.scratch
        if o == 16:
            return 0
        if o == 24:
            if self.outfifo:
                return 0x80000000 | self.outfifo.pop(0)
            return 0
        if o == 28:
            return self._status()
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
                self.infifo = []
                self.outfifo = []
                self.hist = [0] * self.n_taps
                self.sat = 0
                self.done = 0
                self.todo = []
                self.pipe = []
                self.busy = False
            elif (value & 2) and not self.busy:
                self.todo = self.infifo
                self.infifo = []
                self.busy = True
                if not self.todo:
                    self.busy = False
        elif o == 20:
            if len(self.infifo) < self.depth:
                self.infifo.append(value & ((1 << self.dw) - 1))

    def _dsp_tick(self):
        for p in self.pipe:
            p[0] -= 1
        while self.pipe and self.pipe[0][0] <= 0:
            if len(self.outfifo) >= self.depth:
                break
            _, y, s = self.pipe.pop(0)
            self.outfifo.append(y)
            self.sat += s
            self.done += 1
        if self.todo:
            x = self.todo.pop(0)
            if x & 0x8000:
                x -= 0x10000
            y, s = self._filter(x)
            self.pipe.append([self.LATENCY, y, s])
        if self.busy and not self.todo and not self.pipe:
            self.busy = False

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                self.inp[k] = v
        i = self.inp
        we, re = i["h_we"], i["h_re"]
        if we:
            self.write_reg(i["h_addr"], i["h_wdata"])
        if re:
            self.rdata = self.read_reg(i["h_addr"])
        for _ in range(self.DSP_PER_CLK):
            self._dsp_tick()
        return {"led": int(self.busy) | 2, "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
