from collections import deque

M32 = 0xFFFFFFFF


class Model:
    def __init__(self, FIFO_DEPTH=512, DATA_WIDTH=32, PRBS_SEED=2147483647,
                 DESIGN_ID=546635777, SLOW_READ_DIV_CYCLES=8, POR_CYCLES=16,
                 SYNC_STAGES=2, SNAP_SYNC_STAGES=2):
        self.depth = FIFO_DEPTH
        self.dw = DATA_WIDTH
        self.seed = PRBS_SEED
        self.did = DESIGN_ID
        self.div = SLOW_READ_DIV_CYCLES
        self.inp = {}
        self.reset()

    def reset(self):
        self.run = 0
        self.slow = 0
        self.scratch = 0
        self.inject = 0
        self.err_flag = 0
        self.rdata = 0
        self.acc = 0
        self.snap = [0] * 7
        self._clear()

    def _clear(self):
        self.c = [0] * 7  # WORDS_W, WORDS_R, DATA_ERRS, OVF, UNF, STALL, OCC_MAX
        self.wprbs = self.seed
        self.rprbs = self.seed
        self.fifo = deque()
        self.wptr = 0
        self.rptr = 0
        self.w_seen = 0   # write ptr as seen by reader
        self.r_seen = 0   # read ptr as seen by writer
        self.slowcnt = 0
        self.err_flag = 0

    def _next(self, s):
        w = 0
        for i in range(self.dw):
            b = ((s >> 30) ^ (s >> 27)) & 1
            s = ((s << 1) | b) & 0x7FFFFFFF
            w |= b << i
        return s, w

    def write_reg(self, offset, value):
        value &= M32
        if offset == 8:
            self.scratch = value
        elif offset == 16:
            newrun = value & 1
            if (value & 4) and not self.run and not newrun:
                self._clear()
            if value & 8:
                self.inject = 1
            self.run = newrun
            self.slow = (value >> 1) & 1
        elif offset == 48:
            self.snap = list(self.c)

    def read_reg(self, offset):
        if offset == 0:
            return self.did & M32
        if offset == 8:
            return self.scratch
        if offset == 16:
            return self.run | (self.slow << 1) | (self.inject << 3)
        if 20 <= offset <= 44 and offset % 4 == 0:
            return self.snap[(offset - 20) // 4]
        return 0

    def step(self, inputs=None):
        if inputs:
            self.inp.update(inputs)
        i = self.inp
        if i.get("h_we", 0):
            self.write_reg(i.get("h_addr", 0) & 0xFFF, i.get("h_wdata", 0))
        if i.get("h_re", 0):
            self.rdata = self.read_reg(i.get("h_addr", 0) & 0xFFF)
        # writer (clk_25)
        occ = self.wptr - self.r_seen
        if self.run:
            if occ >= self.depth:
                self.c[5] = (self.c[5] + 1) & M32
            else:
                self.wprbs, w = self._next(self.wprbs)
                self.fifo.append(w)
                self.wptr += 1
                self.c[0] = (self.c[0] + 1) & M32
                occ += 1
                if occ > self.c[6]:
                    self.c[6] = occ
        self.r_seen = self.rptr
        # reader (clk_gt156), 6.25 ticks per clk_25 cycle
        self.acc += 25
        ticks = self.acc // 4
        self.acc %= 4
        wseen = self.w_seen
        for _ in range(ticks):
            self.slowcnt += 1
            if not self.run:
                continue
            if self.slow and self.slowcnt < self.div:
                continue
            if self.rptr < wseen and self.fifo:
                w = self.fifo.popleft()
                self.rptr += 1
                self.slowcnt = 0
                if self.inject:
                    w ^= 1
                    self.inject = 0
                self.rprbs, exp = self._next(self.rprbs)
                self.c[1] = (self.c[1] + 1) & M32
                if w != exp:
                    self.c[2] = (self.c[2] + 1) & M32
                    self.err_flag = 1
        self.w_seen = self.wptr
        if self.c[3] or self.c[4]:
            self.err_flag = 1
        return {"led": self.run | (self.err_flag << 1),
                "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
