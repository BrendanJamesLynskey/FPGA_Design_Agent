class Model:
    def __init__(self, DESIGN_ID=546701313, B_DIV=2,
                 GATE_LEN_DEFAULT_CYCLES=25000000, SYNC_STAGES=2):
        self.DESIGN_ID = DESIGN_ID
        self.B_DIV = B_DIV
        self.GATE_DEF = GATE_LEN_DEFAULT_CYCLES
        self.SYNC = SYNC_STAGES
        self.in_ = {}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.sel = 0
        self.active = 0
        self.hs = 0
        self.switch_count = 0
        self.gate_len = self.GATE_DEF
        self.busy = False
        self.done = False
        self.remaining = 0
        self.freq_count = 0
        self.counter = 0
        self.errs = 0
        self.mux_count = 0
        self.acc = 0
        self.rdata = 0

    def _switching(self):
        return 1 if self.sel != self.active else 0

    def read_reg(self, offset):
        o = offset
        if o == 0:
            return self.DESIGN_ID & 0xFFFFFFFF
        if o == 4:
            return 0
        if o == 8:
            return self.scratch
        if o == 16:
            return self.sel
        if o == 20:
            return self._switching() | (self.active << 1)
        if o == 24:
            return self.B_DIV
        if o == 28:
            return self.gate_len
        if o == 36:
            return (1 if self.busy else 0) | (2 if self.done else 0)
        if o == 40:
            return self.freq_count
        if o == 44:
            return self.errs
        if o == 48:
            return self.mux_count
        if o == 52:
            return self.switch_count
        return 0

    def write_reg(self, offset, value):
        v = value & 0xFFFFFFFF
        o = offset
        if o == 8:
            self.scratch = v
        elif o == 16:
            self.sel = v & 1
        elif o == 28:
            self.gate_len = v
        elif o == 32:
            if (v & 1) and not self.busy:
                self.busy = True
                self.done = False
                self.remaining = max(1, self.gate_len)
                self.freq_count = 0
        elif o == 56:
            self.mux_count = self.counter & 0xFFFFFFFF

    def _edges(self):
        if self.active == 0:
            return 1
        self.acc += 625
        d = 100 * self.B_DIV
        e = self.acc // d
        self.acc %= d
        return e

    def step(self, inputs=None):
        if inputs:
            self.in_.update(inputs)
        i = self.in_
        if i.get("h_we"):
            self.write_reg(i.get("h_addr", 0), i.get("h_wdata", 0))
        if i.get("h_re"):
            self.rdata = self.read_reg(i.get("h_addr", 0))
        e = self._edges()
        self.counter = (self.counter + e) & 0xFFFFFFFFFFFFFFFF
        if self.busy:
            self.freq_count += e
            self.remaining -= 1
            if self.remaining <= 0:
                self.busy = False
                self.done = True
        # clock switch handshake
        if self.sel != self.active:
            if self.hs == 0:
                self.hs = self.SYNC + 2
            self.hs -= 1
            if self.hs == 0:
                self.active = self.sel
                self.switch_count += 1
        else:
            self.hs = 0
        return {"sfp_tx_disable": 1,
                "led": self.active | (self._switching() << 1)}
