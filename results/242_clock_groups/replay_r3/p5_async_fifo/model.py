from collections import deque

M32 = 0xFFFFFFFF


class Model:
    def __init__(self, DESIGN_ID=546635777, FIFO_DEPTH_WORDS=512, DATA_WIDTH=32,
                 PRBS_SEED=2147483647, PRBS_TAP_A=31, PRBS_TAP_B=28,
                 SLOW_READ_DIV_CYCLES=8, COUNTER_WIDTH=32, RESET_HOLD_CYCLES=16,
                 READ_LATENCY_MAX_CYCLES=2):
        self.p = dict(DESIGN_ID=DESIGN_ID, DEPTH=FIFO_DEPTH_WORDS, W=DATA_WIDTH,
                      SEED=PRBS_SEED, A=PRBS_TAP_A, B=PRBS_TAP_B,
                      DIV=SLOW_READ_DIV_CYCLES, CW=COUNTER_WIDTH)
        self.cmask = (1 << COUNTER_WIDTH) - 1
        self.reset()

    def reset(self):
        self.run = 0
        self.slow = 0
        self.inject = 0
        self.scratch = 0
        self.fifo = deque()
        self.ws = self.p['SEED']
        self.rs = self.p['SEED']
        self.c = dict(ww=0, wr=0, de=0, of=0, uf=0, st=0, occ=0)
        self.snap = dict(self.c)
        self.err = 0
        self.phase = 0
        self.rdiv = 0

    def _prbs(self, s):
        a, b, w = self.p['A'], self.p['B'], self.p['W']
        word = 0
        for i in range(w):
            bit = ((s >> (a - 1)) ^ (s >> (b - 1))) & 1
            s = ((s << 1) | bit) & ((1 << a) - 1)
            word |= bit << i
        return s, word

    def _inc(self, k):
        self.c[k] = (self.c[k] + 1) & self.cmask

    def _reader_clk(self):
        if self.slow:
            ok = self.rdiv == 0
            self.rdiv = (self.rdiv + 1) % self.p['DIV']
            if not ok:
                return
        else:
            self.rdiv = 0
        if self.fifo:
            w = self.fifo.popleft()
            self.rs, exp = self._prbs(self.rs)
            if self.inject:
                w ^= 1
                self.inject = 0
            if w != exp:
                self._inc('de')
                self.err = 1
            self._inc('wr')

    def step(self, inputs=None):
        # one writer clock; reader gets 6.25 clocks per writer clock
        n = 6 + (1 if self.phase == 3 else 0)
        self.phase = (self.phase + 1) % 4
        if self.run:
            if len(self.fifo) >= self.p['DEPTH']:
                self._inc('st')
            else:
                self.ws, w = self._prbs(self.ws)
                self.fifo.append(w)
                self._inc('ww')
                if len(self.fifo) > self.c['occ']:
                    self.c['occ'] = len(self.fifo)
        for _ in range(n):
            self._reader_clk()
        return {'led': self.run | (self.err << 1), 'sfp_tx_disable': 1}

    _CK = {0x14: 'ww', 0x18: 'wr', 0x1C: 'de', 0x20: 'of', 0x24: 'uf',
           0x28: 'st', 0x2C: 'occ'}

    def read_reg(self, offset):
        if offset == 0:
            return self.p['DESIGN_ID'] & M32
        if offset == 8:
            return self.scratch
        if offset == 0x10:
            return self.run | (self.slow << 1)
        if offset in self._CK:
            return self.snap[self._CK[offset]] & M32
        return 0

    def write_reg(self, offset, value):
        value &= M32
        if offset == 8:
            self.scratch = value
        elif offset == 0x10:
            old_run = self.run
            if (value & 4) and not old_run:
                for k in self.c:
                    self.c[k] = 0
                self.ws = self.rs = self.p['SEED']
                self.fifo.clear()
                self.err = 0
                self.rdiv = 0
            self.run = value & 1
            self.slow = (value >> 1) & 1
            if value & 8:
                self.inject = 1
        elif offset == 0x30:
            self.snap = dict(self.c)
