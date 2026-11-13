class Model:
    LATENCY = 3

    def __init__(self, CLKS_PER_BIT=868, TIMEOUT_CYCLES=100000000,
                 BUILD_STAMP=0, DESIGN_ID="DOTQ"):
        self.CLKS_PER_BIT = CLKS_PER_BIT
        self.TIMEOUT_CYCLES = TIMEOUT_CYCLES
        self.BUILD_STAMP = BUILD_STAMP
        self.DESIGN_ID = DESIGN_ID
        self.inp = {"CPU_RESETN": 1, "UART_TXD_IN": 1}
        self.reset()

    def reset(self):
        self.regs = [0] * 7
        self.regs[6] = 1
        self.ready = 0
        self.y = 0
        self.acc = 0
        self.pend = 0
        self.snap = None

    @staticmethod
    def _s8(v):
        v &= 0xFF
        return v - 256 if v & 0x80 else v

    def _compute(self):
        r = self.snap
        a = [self._s8(r[0] >> (8 * i)) for i in range(4)] + \
            [self._s8(r[1] >> (8 * i)) for i in range(4)]
        w = [self._s8(r[2] >> (8 * i)) for i in range(4)] + \
            [self._s8(r[3] >> (8 * i)) for i in range(4)]
        bias = r[4] & 0xFFFFFFFF
        if bias & 0x80000000:
            bias -= 1 << 32
        acc = sum(x * z for x, z in zip(a, w)) + bias
        mult = r[5] & 0xFFFF
        shift = r[6] & 0x1F
        relu = (r[6] >> 8) & 1
        if shift == 0:
            sc = acc * mult
        else:
            sc = (acc * mult + (1 << (shift - 1))) >> shift
        lo = 0 if relu else -128
        y = max(lo, min(127, sc))
        a32 = acc & 0xFFFFFFFF
        self.acc = a32
        self.y = y & 0xFF

    def write_reg(self, offset, value):
        value &= 0xFFFFFFFF
        if offset in (0, 1, 2, 3, 4):
            self.regs[offset] = value
        elif offset == 5:
            self.regs[5] = value & 0xFFFF
        elif offset == 6:
            self.regs[6] = value & 0x11F
        elif offset == 7:
            self.ready = 0
            self.y = 0
            self.acc = 0
            self.snap = list(self.regs)
            self.pend = self.LATENCY

    def read_reg(self, offset):
        if 0 <= offset <= 6:
            return self.regs[offset]
        if offset == 8:
            return self.y if self.ready else 0
        if offset == 9:
            return self.acc if self.ready else 0
        if offset == 10:
            return self.ready
        return 0

    def step(self, inputs=None):
        if inputs:
            self.inp.update(inputs)
        if not self.inp.get("CPU_RESETN", 1):
            self.reset()
        elif self.pend:
            self.pend -= 1
            if self.pend == 0:
                self._compute()
                self.ready = 1
        return {"UART_RXD_OUT": 1, "LED0": self.ready}
