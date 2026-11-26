from collections import deque

M32 = 0xFFFFFFFF


def _prbs_word(s):
    w = 0
    for i in range(32):
        n = ((s >> 30) ^ (s >> 27)) & 1
        s = ((s << 1) | n) & 0x7FFFFFFF
        w |= n << i
    return s, w


class Model:
    def __init__(self, FIFO_DEPTH=512, DATA_WIDTH=32, PRBS_SEED=2147483647,
                 DESIGN_ID=546635777, SLOW_READ_DIV_CYCLES=8, ADDR_WIDTH=9,
                 RESET_CYCLES=16):
        self.depth = FIFO_DEPTH
        self.dw = DATA_WIDTH
        self.seed = PRBS_SEED
        self.id = DESIGN_ID
        self.div = SLOW_READ_DIV_CYCLES
        self.inputs = {}
        self.reset()

    def reset(self):
        self.run = 0
        self.slow = 0
        self.scratch = 0
        self.fifo = deque()
        self.wprbs = self.seed
        self.rprbs = self.seed
        self.cnt = [0] * 7  # WORDS_W, WORDS_R, ERRS, OVF, UNF, STALL, OCC
        self.shadow = [0] * 7
        self.inject = 0
        self.acc = 0
        self.slow_cnt = 0
        self.rdata = 0

    def _read(self, off):
        if off == 0:
            return self.id & M32
        if off == 4:
            return 0
        if off == 8:
            return self.scratch
        if off == 16:
            return self.run | (self.slow << 1)
        if 20 <= off <= 44 and off % 4 == 0:
            return self.shadow[(off - 20) // 4]
        return 0

    def read_reg(self, offset):
        return self._read(offset)

    def write_reg(self, offset, value):
        value &= M32
        if offset == 8:
            self.scratch = value
        elif offset == 16:
            old_run = self.run
            self.run = value & 1
            self.slow = (value >> 1) & 1
            if (value & 4) and not old_run:
                self.fifo.clear()
                self.wprbs = self.seed
                self.rprbs = self.seed
                self.cnt = [0] * 7
                self.inject = 0
                self.slow_cnt = 0
            if (value & 8) and self.run:
                self.inject = 1
        elif offset == 48:
            self.shadow = list(self.cnt)

    def step(self, inputs=None):
        if inputs:
            self.inputs.update(inputs)
        i = self.inputs
        was_full = len(self.fifo) >= self.depth
        # reader: 25 gt_refclk cycles per 4 clk25 cycles
        self.acc += 25
        n = self.acc // 4
        self.acc %= 4
        avail = len(self.fifo)
        for _ in range(n):
            if self.slow_cnt > 0:
                self.slow_cnt -= 1
                continue
            if avail > 0 and self.fifo:
                avail -= 1
                w = self.fifo.popleft()
                self.rprbs, exp = _prbs_word(self.rprbs)
                if self.inject:
                    w ^= 1
                    self.inject = 0
                if w != exp:
                    self.cnt[2] = (self.cnt[2] + 1) & M32
                self.cnt[1] = (self.cnt[1] + 1) & M32
                if self.slow:
                    self.slow_cnt = self.div - 1
        # writer
        if self.run:
            if was_full:
                self.cnt[5] = (self.cnt[5] + 1) & M32
            else:
                self.wprbs, w = _prbs_word(self.wprbs)
                self.fifo.append(w)
                self.cnt[0] = (self.cnt[0] + 1) & M32
                self.cnt[6] = max(self.cnt[6], len(self.fifo))
        # host bus
        if i.get("h_we"):
            self.write_reg(i.get("h_addr", 0) & 0xFFF, i.get("h_wdata", 0))
        if i.get("h_re"):
            self.rdata = self._read(i.get("h_addr", 0) & 0xFFF)
        i["h_we"] = 0
        i["h_re"] = 0
        err = 1 if (self.cnt[2] or self.cnt[3] or self.cnt[4]) else 0
        return {"led": self.run | (err << 1), "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
