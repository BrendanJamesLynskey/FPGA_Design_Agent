from collections import deque


class Model:
    def __init__(self, FIFO_DEPTH_WORDS=512, DATA_WIDTH=32, PRBS_SEED=2147483647,
                 DESIGN_ID=546635777, SLOW_READ_PERIOD_CYCLES=8, COUNTER_WIDTH=32,
                 RESET_HOLD_CYCLES=8):
        self.depth = FIFO_DEPTH_WORDS
        self.dw = DATA_WIDTH
        self.seed = PRBS_SEED
        self.id = DESIGN_ID
        self.slow_n = SLOW_READ_PERIOD_CYCLES
        self.cmask = (1 << COUNTER_WIDTH) - 1
        self.dmask = (1 << DATA_WIDTH) - 1
        self.reset()

    def reset(self):
        self.scratch = 0
        self.run = 0
        self.slow = 0
        self.inject = 0
        self.build = 0
        self.snap = [0] * 7
        self.h_rdata = 0
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.acc = 0
        self.slow_cnt = 0
        self._clear()

    def _clear(self):
        self.c = {"w": 0, "r": 0, "err": 0, "ovf": 0, "unf": 0, "stall": 0, "occ": 0}
        self.wp = self.seed & 0x7FFFFFFF
        self.rp = self.seed & 0x7FFFFFFF
        self.fifo = deque()
        self.inject = 0

    def _word(self, s):
        w = 0
        for i in range(32):
            fb = ((s >> 30) ^ (s >> 27)) & 1
            s = ((s << 1) | fb) & 0x7FFFFFFF
            w |= fb << i
        return s, w & self.dmask

    def _cnt(self, k, n=1):
        self.c[k] = (self.c[k] + n) & self.cmask

    def write_reg(self, offset, value):
        value &= 0xFFFFFFFF
        offset &= 0xFFF
        if offset == 8:
            self.scratch = value
        elif offset == 16:
            was_run = self.run
            self.run = value & 1
            self.slow = (value >> 1) & 1
            if (value & 4) and not was_run:
                self._clear()
            if value & 8:
                self.inject = 1
        elif offset == 48:
            c = self.c
            self.snap = [c["w"], c["r"], c["err"], c["ovf"], c["unf"], c["stall"], c["occ"]]

    def read_reg(self, offset):
        offset &= 0xFFF
        if offset == 0:
            return self.id
        if offset == 4:
            return self.build
        if offset == 8:
            return self.scratch
        if offset == 16:
            return self.run | (self.slow << 1)
        if 20 <= offset <= 44 and offset % 4 == 0:
            return self.snap[(offset - 20) // 4]
        return 0

    def _reader_tick(self):
        if self.slow:
            self.slow_cnt += 1
            if self.slow_cnt < self.slow_n:
                return
            self.slow_cnt = 0
        else:
            self.slow_cnt = 0
        if not self.fifo:
            return
        w = self.fifo.popleft()
        self.rp, exp = self._word(self.rp)
        if self.inject:
            w ^= 1
            self.inject = 0
        if self.run:
            self._cnt("r")
            if w != exp:
                self._cnt("err")

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                self.inp[k] = v
        i = self.inp
        if i["h_we"]:
            self.write_reg(i["h_addr"], i["h_wdata"])
        if i["h_re"]:
            self.h_rdata = self.read_reg(i["h_addr"])
        i["h_we"] = 0
        i["h_re"] = 0

        if self.run:
            if len(self.fifo) >= self.depth:
                self._cnt("stall")
            else:
                self.wp, w = self._word(self.wp)
                self.fifo.append(w)
                self._cnt("w")
                if len(self.fifo) > self.c["occ"]:
                    self.c["occ"] = len(self.fifo)

        self.acc += 25
        ticks, self.acc = divmod(self.acc, 4)
        for _ in range(ticks):
            self._reader_tick()

        c = self.c
        err = 1 if (c["err"] or c["ovf"] or c["unf"]) else 0
        return {"led": self.run | (err << 1), "sfp_tx_disable": 1,
                "h_rdata": self.h_rdata}
