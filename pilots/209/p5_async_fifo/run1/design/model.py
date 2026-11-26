from collections import deque

M32 = 0xFFFFFFFF


class Model:
    def __init__(self, FIFO_DEPTH_WORDS=512, DATA_WIDTH=32, PRBS_SEED=2147483647,
                 SLOW_READ_DIV_CYCLES=8, DESIGN_ID=546635777, ADDR_BITS=12):
        self.depth = FIFO_DEPTH_WORDS
        self.width = DATA_WIDTH
        self.seed = PRBS_SEED
        self.div = SLOW_READ_DIV_CYCLES
        self.design_id = DESIGN_ID
        self.addr_mask = (1 << ADDR_BITS) - 1
        self.build = 0
        self.inp = {"rst": 0, "h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.reset()

    def _word(self, s):
        w = 0
        for i in range(self.width):
            b = ((s >> 30) ^ (s >> 27)) & 1
            s = ((s << 1) | b) & 0x7FFFFFFF
            w |= b << i
        return w, s

    def _clear_counters(self):
        self.c = {k: 0 for k in ("ww", "wr", "err", "ovf", "unf", "stall", "occ")}
        self.wsd = self.seed
        self.rsd = self.seed

    def reset(self):
        self.scratch = 0
        self.run = 0
        self.slow = 0
        self.inject = 0
        self.fifo = deque()
        self.wptr = 0
        self.rptr = 0
        self.rptr_sync = [0, 0]   # seen by writer
        self.wptr_sync = [0, 0]   # seen by reader
        self.slow_cnt = 0
        self.phase = 0
        self.snap = [0] * 7
        self.rdata = 0
        self._clear_counters()

    def _regs(self):
        return ("ww", "wr", "err", "ovf", "unf", "stall", "occ")

    def read_reg(self, offset):
        offset &= self.addr_mask
        if offset == 0:
            return self.design_id & M32
        if offset == 4:
            return self.build
        if offset == 8:
            return self.scratch
        if offset == 16:
            return self.run | (self.slow << 1) | (self.inject << 3)
        if 20 <= offset <= 44 and offset % 4 == 0:
            return self.snap[(offset - 20) // 4]
        return 0

    def write_reg(self, offset, value):
        offset &= self.addr_mask
        value &= M32
        if offset == 8:
            self.scratch = value
        elif offset == 16:
            if (value & 4) and not self.run and not (value & 1):
                self._clear_counters()
            self.run = value & 1
            self.slow = (value >> 1) & 1
            if value & 8:
                self.inject = 1
        elif offset == 48:
            self.snap = [self.c[k] for k in self._regs()]

    def _gt_cycle(self):
        # synchroniser update
        self.wptr_sync = [self.wptr, self.wptr_sync[0]]
        seen_w = self.wptr_sync[1]
        if self.slow_cnt > 0:
            self.slow_cnt -= 1
        if self.slow_cnt == 0 or not self.slow:
            if seen_w != self.rptr and self.fifo:
                w = self.fifo.popleft()
                self.rptr += 1
                if self.run:
                    exp, self.rsd = self._word(self.rsd)
                    if self.inject:
                        w ^= 1
                        self.inject = 0
                    if w != exp:
                        self.c["err"] = (self.c["err"] + 1) & M32
                    self.c["wr"] = (self.c["wr"] + 1) & M32
                if self.slow:
                    self.slow_cnt = self.div - 1 + 1
            elif self.run and seen_w == self.rptr and False:
                pass

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                if k in self.inp:
                    self.inp[k] = v
        i = self.inp
        if i["rst"]:
            self.reset()
            return self._out()
        we, re = i["h_we"], i["h_re"]
        # keep pulses from repeating: treat as per-step pulses
        self.inp["h_we"] = 0
        self.inp["h_re"] = 0
        if we:
            self.write_reg(i["h_addr"], i["h_wdata"])
        if re:
            self.rdata = self.read_reg(i["h_addr"])
        # reader domain
        self.phase = (self.phase + 1) % 4
        n = 7 if self.phase == 0 else 6
        for _ in range(n):
            self._gt_cycle()
        # writer domain
        self.rptr_sync = [self.rptr, self.rptr_sync[0]]
        if self.run:
            if self.wptr - self.rptr_sync[1] >= self.depth:
                self.c["stall"] = (self.c["stall"] + 1) & M32
            else:
                w, self.wsd = self._word(self.wsd)
                self.fifo.append(w)
                self.wptr += 1
                self.c["ww"] = (self.c["ww"] + 1) & M32
                occ = len(self.fifo)
                if occ > self.c["occ"]:
                    self.c["occ"] = occ
        return self._out()

    def _out(self):
        return {
            "led": self.run | ((1 if self.c["err"] else 0) << 1),
            "sfp_tx_disable": 1,
            "h_rdata": self.rdata,
        }
