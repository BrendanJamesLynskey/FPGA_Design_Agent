from collections import deque

M32 = 0xFFFFFFFF


class Model:
    def __init__(self, FIFO_DEPTH=512, DATA_WIDTH=32, ADDR_WIDTH=9,
                 PRBS_SEED=2147483647, DESIGN_ID=546635777,
                 SLOW_READ_DIV_CYCLES=8, SYNC_STAGES=2):
        self.depth = FIFO_DEPTH
        self.seed = PRBS_SEED
        self.design_id = DESIGN_ID
        self.slow_div = SLOW_READ_DIV_CYCLES
        self.reset()

    def reset(self):
        self.scratch = 0
        self.run = 0
        self.slow = 0
        self.inject = 0
        self.pending = []
        self._clear_state()
        self.snap = [0] * 7
        self.err_sticky = 0
        self.rd_acc = 0
        self.slow_cnt = 0

    def _clear_state(self):
        self.wprbs = self.seed
        self.rprbs = self.seed
        self.fifo = deque()
        self.c = {k: 0 for k in ("ww", "wr", "de", "ov", "un", "st", "occ")}
        self.slow_cnt = 0

    @staticmethod
    def _word(s):
        w = 0
        for i in range(32):
            nb = ((s >> 30) ^ (s >> 27)) & 1
            s = ((s << 1) | nb) & 0x7FFFFFFF
            w |= nb << i
        return w, s

    def _rd_cycle(self):
        c = self.c
        if self.slow_cnt > 0:
            self.slow_cnt -= 1
            return
        if not self.fifo:
            return
        w = self.fifo.popleft()
        exp, self.rprbs = self._word(self.rprbs)
        if self.inject:
            w ^= 1
            self.inject = 0
        c["wr"] = (c["wr"] + 1) & M32
        if w != exp:
            c["de"] = (c["de"] + 1) & M32
            self.err_sticky = 1
        if self.slow:
            self.slow_cnt = self.slow_div - 1

    def step(self, inputs=None):
        pend, self.pending = self.pending, []
        for off, v in pend:
            self._apply(off, v)
        c = self.c
        if self.run:
            if len(self.fifo) < self.depth:
                w, self.wprbs = self._word(self.wprbs)
                self.fifo.append(w)
                c["ww"] = (c["ww"] + 1) & M32
                c["occ"] = max(c["occ"], len(self.fifo))
            else:
                c["st"] = (c["st"] + 1) & M32
        # 156.25/25 = 25/4 reader clocks per writer clock
        self.rd_acc += 25
        while self.rd_acc >= 4:
            self.rd_acc -= 4
            self._rd_cycle()
        return {"led": self.run | (self.err_sticky or
                                   (c["ov"] or c["un"] or c["de"]) and 1) << 1,
                "sfp_tx_disable": 1}

    def _apply(self, off, v):
        v &= M32
        if off == 8:
            self.scratch = v
        elif off == 16:
            clear = (v >> 2) & 1
            self.slow = (v >> 1) & 1
            if v & 8:
                self.inject = 1
            if clear and not self.run:
                self._clear_state()
                self.err_sticky = 0
            self.run = v & 1
        elif off == 48:
            c = self.c
            self.snap = [c["ww"], c["wr"], c["de"], c["ov"], c["un"],
                         c["st"], c["occ"]][:5] + [c["st"]]
            self.snap = [c["ww"], c["wr"], c["de"], c["ov"], c["un"], c["st"]]
            self.snap.append(c["occ"])

    def write_reg(self, offset, value):
        if offset == 8:
            self.scratch = value & M32
            return
        self.pending.append((offset, value))

    def read_reg(self, offset):
        if offset == 0:
            return self.design_id
        if offset == 4:
            return 0
        if offset == 8:
            return self.scratch
        if offset == 16:
            return self.run | self.slow << 1 | self.inject << 3
        if 20 <= offset <= 44 and offset % 4 == 0:
            i = (offset - 20) // 4
            return self.snap[i] if i < len(self.snap) else 0
        return 0
