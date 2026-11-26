from collections import deque

_M32 = 0xFFFFFFFF


class Model:
    def __init__(self, DEPTH=512, DATA_WIDTH=32, ADDR_WIDTH=9,
                 PRBS_SEED=2147483647, DESIGN_ID=546635777,
                 SLOW_READ_DIV_CLOCKS=8, SYNC_STAGES=2):
        self.DEPTH = DEPTH
        self.DW = DATA_WIDTH
        self.SEED = PRBS_SEED
        self.ID = DESIGN_ID
        self.DIV = SLOW_READ_DIV_CLOCKS
        self.SS = SYNC_STAGES
        self.reset()

    def _next(self, s):
        for _ in range(32):
            s = ((s << 1) | (((s >> 30) ^ (s >> 27)) & 1)) & 0x7FFFFFFF
        return s

    def _clear(self):
        self.fifo = deque()
        self.wp = 0
        self.rp = 0
        self.wsync = deque([0] * (self.SS + 1), maxlen=self.SS + 1)  # rp seen by writer
        self.rsync = deque([0] * (self.SS + 1), maxlen=self.SS + 1)  # wp seen by reader
        self.wstate = self.SEED
        self.rstate = self.SEED
        self.wword = self._next(self.wstate)
        self.cool = 0
        self.err_seen = 0
        self.words_w = self.words_r = self.data_errs = 0
        self.overflows = self.underflows = self.stall = self.occ_max = 0

    def reset(self):
        self.run = 0
        self.slow = 0
        self.scratch = 0
        self.snap = [0] * 7
        self.acc = 0
        self.inject = 0
        self._clear()

    def _wclk(self):
        rp_seen = self.wsync[0]
        full = (self.wp - rp_seen) >= self.DEPTH
        if self.run:
            if full:
                self.stall += 1
            else:
                self.fifo.append(self.wword)
                self.wstate = self._next(self.wstate)
                self.wword = self._next(self.wstate)
                self.wp += 1
                self.words_w = (self.words_w + 1) & _M32
        occ = self.wp - rp_seen
        if occ > self.occ_max:
            self.occ_max = min(occ, self.DEPTH)
        self.wsync.append(self.rp)

    def _rclk(self):
        wp_seen = self.rsync[0]
        if self.cool > 0:
            self.cool -= 1
        elif wp_seen - self.rp > 0 and self.fifo:
            w = self.fifo.popleft()
            self.rp += 1
            if self.slow:
                self.cool = self.DIV - 1
            self.rstate = self._next(self.rstate)
            if self.inject:
                w ^= 1
                self.inject = 0
            if w != self.rstate:
                self.data_errs = (self.data_errs + 1) & _M32
                self.err_seen = 1
            self.words_r = (self.words_r + 1) & _M32
        self.rsync.append(self.wp)

    def step(self, inputs=None):
        # 25 reader cycles per 4 writer cycles (156.25 / 25 MHz)
        self._wclk()
        self.acc += 25
        while self.acc >= 4:
            self.acc -= 4
            self._rclk()
        if self.overflows or self.underflows:
            self.err_seen = 1
        return {"sfp_tx_disable": 1,
                "led": (self.run & 1) | (self.err_seen << 1)}

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.ID & _M32
        if o == 8:
            return self.scratch
        if o == 16:
            return self.run | (self.slow << 1) | (self.inject << 3)
        if 20 <= o <= 44 and o % 4 == 0:
            return self.snap[(o - 20) // 4]
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= _M32
        if o == 8:
            self.scratch = value
        elif o == 16:
            self.run = value & 1
            self.slow = (value >> 1) & 1
            if value & 8:
                self.inject = 1
            if (value & 4) and not self.run:
                self._clear()
        elif o == 48:
            self.snap = [self.words_w, self.words_r, self.data_errs,
                         self.overflows, self.underflows, self.stall,
                         self.occ_max]
