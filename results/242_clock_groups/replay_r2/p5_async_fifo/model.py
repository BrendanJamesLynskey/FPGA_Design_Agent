M32 = 0xFFFFFFFF


def _prbs_word(s):
    w = 0
    for _ in range(32):
        n = ((s >> 30) ^ (s >> 27)) & 1
        s = ((s << 1) | n) & 0x7FFFFFFF
        w = (w << 1) | n
    return s, w


class Model:
    def __init__(self, DATA_WIDTH=32, FIFO_DEPTH=512, PRBS_SEED=2147483647,
                 DESIGN_ID=546635777, SLOW_READ_DIV_CYCLES=8,
                 RST_HOLD_CYCLES=8):
        self.DATA_WIDTH = DATA_WIDTH
        self.FIFO_DEPTH = FIFO_DEPTH
        self.SEED = PRBS_SEED
        self.DESIGN_ID = DESIGN_ID
        self.DIV = SLOW_READ_DIV_CYCLES
        self.RST_HOLD = RST_HOLD_CYCLES
        self.reset()

    def reset(self):
        self.run = 0
        self.slow = 0
        self.scratch = 0
        self.inject_pend = 0
        self._clear_state()
        self.snap = [0] * 7
        self.rdata = 0
        self.acc = 0
        self.slow_cnt = 0
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}

    def _clear_state(self):
        self.fifo = []
        self.wstate = self.SEED
        self.rstate = self.SEED
        self.words_w = self.words_r = self.errs = 0
        self.ovf = self.unf = self.stall = self.occ_max = 0

    def _live(self):
        return [self.words_w, self.words_r, self.errs, self.ovf, self.unf,
                self.stall, self.occ_max]

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.DESIGN_ID & M32
        if o == 8:
            return self.scratch
        if o == 16:
            return self.run | (self.slow << 1)
        if 20 <= o <= 44 and o % 4 == 0:
            return self.snap[(o - 20) // 4] & M32
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= M32
        if o == 8:
            self.scratch = value
        elif o == 16:
            clr = (value >> 2) & 1
            inj = (value >> 3) & 1
            if clr and not self.run:
                self._clear_state()
            if inj:
                self.inject_pend = 1
            self.run = value & 1
            self.slow = (value >> 1) & 1
        elif o == 48:
            self.snap = self._live()

    def _gt_cycle(self):
        if self.slow:
            self.slow_cnt += 1
            if self.slow_cnt < self.DIV:
                return
            if not self.fifo:
                self.slow_cnt = self.DIV  # ready, wait for data
                return
            self.slow_cnt = 0
        if not self.fifo:
            return
        w = self.fifo.pop(0)
        if self.inject_pend:
            w ^= 1
            self.inject_pend = 0
        self.rstate, exp = _prbs_word(self.rstate)
        self.words_r = (self.words_r + 1) & M32
        if w != exp:
            self.errs = (self.errs + 1) & M32

    def step(self, inputs=None):
        if inputs:
            for k in ("h_we", "h_re", "h_addr", "h_wdata"):
                if k in inputs:
                    self.inp[k] = inputs[k]
        i = self.inp
        we, re = i["h_we"], i["h_re"]
        if inputs is not None:
            # strobes are single-cycle unless re-supplied
            self.inp["h_we"] = 0
            self.inp["h_re"] = 0
        if we:
            self.write_reg(i["h_addr"], i["h_wdata"])
        if re:
            self.rdata = self.read_reg(i["h_addr"])
        # writer
        if self.run:
            if len(self.fifo) >= self.FIFO_DEPTH:
                self.stall = (self.stall + 1) & M32
            else:
                self.wstate, w = _prbs_word(self.wstate)
                self.fifo.append(w)
                self.words_w = (self.words_w + 1) & M32
                self.occ_max = max(self.occ_max, len(self.fifo))
        # reader: 6.25 gt cycles per clk_c3 cycle
        self.acc += 25
        n = self.acc // 4
        self.acc %= 4
        for _ in range(n):
            self._gt_cycle()
        return {"led": self.run | ((1 if self.errs else 0) << 1),
                "sfp_tx_disable": 1, "h_rdata": self.rdata}
