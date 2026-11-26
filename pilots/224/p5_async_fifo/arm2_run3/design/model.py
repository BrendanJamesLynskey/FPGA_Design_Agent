from collections import deque

M32 = 0xFFFFFFFF


class Model:
    def __init__(self, DESIGN_ID=546635777, FIFO_DEPTH_WORDS=512, DATA_WIDTH=32,
                 PRBS_SEED=2147483647, SLOW_READ_DIV_CYCLES=8, PTR_WIDTH=9,
                 COUNTER_WIDTH=32):
        self.ID = DESIGN_ID
        self.depth = FIFO_DEPTH_WORDS
        self.dw = DATA_WIDTH
        self.seed = PRBS_SEED
        self.div = SLOW_READ_DIV_CYCLES
        self.cmask = (1 << COUNTER_WIDTH) - 1
        self.build = 0
        self.reset()

    @staticmethod
    def _prbs(s, n=32):
        w = 0
        for _ in range(n):
            fb = ((s >> 30) ^ (s >> 27)) & 1
            s = ((s << 1) | fb) & 0x7FFFFFFF
            w = (w << 1) | fb
        return s, w

    def reset(self):
        self.scratch = 0
        self.run = 0
        self.slow = 0
        self.inject = 0
        self.cnt = [0] * 7  # words_w, words_r, errs, ovf, unf, stall, occmax
        self.snap = [0] * 7
        self.pend = None
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.rdata = 0
        self._restart()
        self.run_sync = [0, 0]
        self.gacc = 0
        self.gcyc = 0

    def _restart(self):
        self.fifo = deque()
        self.wseed = self.seed
        self.rseed = self.seed
        self.wp = 0
        self.rp = 0
        self.wp_sync = [0, 0]  # seen by reader
        self.rp_sync = [0, 0]  # seen by writer
        self.slowcnt = 0

    def _c(self, i, d=1):
        self.cnt[i] = (self.cnt[i] + d) & self.cmask

    def read_reg(self, off):
        if off == 0:
            return self.ID & M32
        if off == 4:
            return self.build & M32
        if off == 8:
            return self.scratch
        if off == 16:
            return self.run | (self.slow << 1)
        if 20 <= off <= 44 and off % 4 == 0:
            return self.snap[(off - 20) // 4]
        return 0

    def write_reg(self, off, value):
        value &= M32
        if off == 8:
            self.scratch = value
        elif off == 16:
            self.slow = (value >> 1) & 1
            if (value >> 3) & 1:
                self.inject = 1
            if (value >> 2) & 1 and not self.run:
                self.cnt = [0] * 7
                self._restart()
            self.run = value & 1
        elif off == 48:
            self.snap = list(self.cnt)

    def step(self, inputs=None):
        if inputs:
            self.inp.update(inputs)
        i = self.inp
        if self.pend is not None:
            self.write_reg(*self.pend)
            self.pend = None
        if i.get("h_we"):
            self.pend = (i["h_addr"] & 0xFFF, i["h_wdata"])
            i["h_we"] = 0
        if i.get("h_re"):
            self.rdata = self.read_reg(i["h_addr"] & 0xFFF)
            i["h_re"] = 0

        # writer (clk_25)
        self.rp_sync = [self.rp, self.rp_sync[0]]
        if self.run:
            fill = (self.wp - self.rp_sync[1]) & 0xFFFFFFFF
            if fill >= self.depth:
                self._c(5)
            else:
                self.wseed, w = self._prbs(self.wseed)
                self.fifo.append(w)
                self.wp += 1
                self._c(0)
                fill += 1
                if fill > self.cnt[6]:
                    self.cnt[6] = fill

        # reader: 6.25 gt cycles per clk_25 cycle
        self.gacc += 25
        while self.gacc >= 4:
            self.gacc -= 4
            self._gt()

        return {"led": self.run | (1 << 1 if (self.cnt[2] or self.cnt[3] or self.cnt[4]) else 0),
                "sfp_tx_disable": 1}

    def _gt(self):
        self.run_sync = [self.run, self.run_sync[0]]
        seen = self.wp_sync[1]
        self.wp_sync = [self.wp, self.wp_sync[0]]
        if self.slowcnt > 0:
            self.slowcnt -= 1
            return
        if not (self.run_sync[1] or self.fifo):
            return
        if self.rp == seen or not self.fifo:
            return
        w = self.fifo.popleft()
        self.rp += 1
        if self.slow:
            self.slowcnt = self.div - 1
        if self.inject:
            w ^= 1
            self.inject = 0
        self.rseed, exp = self._prbs(self.rseed)
        self._c(1)
        if w != exp:
            self._c(2)
