M32 = 0xFFFFFFFF


def _prbs_word(s):
    w = 0
    for _ in range(32):
        b = ((s >> 30) ^ (s >> 27)) & 1
        s = ((s << 1) | b) & 0x7FFFFFFF
        w = ((w << 1) | b) & M32
    return w, s


class Model:
    def __init__(self, FIFO_DEPTH_WORDS=512, DATA_WIDTH_BITS=32,
                 PRBS_SEED=2147483647, SLOW_READ_PERIOD_CYCLES=8,
                 DESIGN_ID=546635777, COUNTER_WIDTH_BITS=32):
        self.depth = FIFO_DEPTH_WORDS
        self.dw = DATA_WIDTH_BITS
        self.seed = PRBS_SEED
        self.slow = SLOW_READ_PERIOD_CYCLES
        self.did = DESIGN_ID
        self.cmask = (1 << COUNTER_WIDTH_BITS) - 1
        self.reset()

    def reset(self):
        self.scratch = 0
        self.run = 0
        self.slow_read = 0
        self.inject = 0
        self.snap = [0] * 7
        self._clear_core()
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.pend_w = None
        self.pend_r = None
        self.rdata = 0
        self.acc = 0
        self.rd_div = 0

    def _clear_core(self):
        self.fifo = []
        self.wprbs = self.seed
        self.rprbs = self.seed
        # words_w, words_r, errs, ovf, unf, stall, occ_max
        self.cnt = [0] * 7

    def _live(self):
        return list(self.cnt)

    def _read(self, off):
        off &= 0xFFF
        if off == 0:
            return self.did & M32
        if off == 8:
            return self.scratch
        if off == 16:
            return self.run | (self.slow_read << 1) | (self.inject << 3)
        if 20 <= off <= 44 and off % 4 == 0:
            return self.snap[(off - 20) // 4]
        return 0

    def read_reg(self, offset):
        return self._read(offset)

    def write_reg(self, offset, value):
        off = offset & 0xFFF
        value &= M32
        if off == 8:
            self.scratch = value
        elif off == 16:
            if value & 4 and not self.run:
                self._clear_core()
                self.snap = [0] * 7 if False else self.snap
            self.run = value & 1
            self.slow_read = (value >> 1) & 1
            if value & 8:
                self.inject = 1
        elif off == 48:
            self.snap = self._live()

    def _rd_clock(self):
        if self.slow_read:
            self.rd_div += 1
            if self.rd_div < self.slow:
                return
            self.rd_div = 0
        if self.fifo:
            w = self.fifo.pop(0)
            exp, self.rprbs = _prbs_word(self.rprbs)
            if self.inject:
                w ^= 1
                self.inject = 0
            self.cnt[1] = (self.cnt[1] + 1) & self.cmask
            if w != exp:
                self.cnt[2] = (self.cnt[2] + 1) & self.cmask
        elif self.run:
            pass

    def _wr_clock(self):
        if self.run:
            if len(self.fifo) >= self.depth:
                self.cnt[5] = (self.cnt[5] + 1) & self.cmask
            else:
                w, self.wprbs = _prbs_word(self.wprbs)
                self.fifo.append(w)
                self.cnt[0] = (self.cnt[0] + 1) & self.cmask
        if len(self.fifo) > self.cnt[6]:
            self.cnt[6] = len(self.fifo)

    def step(self, inputs=None):
        if inputs:
            for k in self.inp:
                if k in inputs:
                    self.inp[k] = inputs[k]
        # apply write requested on previous clock
        if self.pend_w is not None:
            self.write_reg(*self.pend_w)
            self.pend_w = None
        if self.pend_r is not None:
            self.rdata = self._read(self.pend_r)
            self.pend_r = None
        if self.inp["h_we"]:
            self.pend_w = (self.inp["h_addr"], self.inp["h_wdata"])
        if self.inp["h_re"]:
            self.pend_r = self.inp["h_addr"]
        # one clk_wr cycle = 6.25 clk_rd cycles
        self._wr_clock()
        self.acc += 25
        while self.acc >= 4:
            self.acc -= 4
            self._rd_clock()
        # inputs are pulses
        self.inp["h_we"] = 0
        self.inp["h_re"] = 0
        err = 1 if (self.cnt[2] or self.cnt[3] or self.cnt[4]) else 0
        return {"led": (self.run & 1) | (err << 1),
                "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
