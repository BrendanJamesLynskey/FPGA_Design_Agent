class Model:
    SWITCH_CYCLES = 4

    def __init__(self, DESIGN_ID=546701313, B_DIV_VALUE=2, GATE_LEN_DEFAULT=25000000,
                 MUX_COUNTER_WIDTH=32, RESET_SYNC_STAGES=3):
        self.design_id = DESIGN_ID
        self.b_div = B_DIV_VALUE
        self.gate_default = GATE_LEN_DEFAULT
        self.width = MUX_COUNTER_WIDTH
        self.sync = RESET_SYNC_STAGES
        self.inputs = {}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.sel = 0
        self.active = 0
        self.switching = 0
        self.sw_timer = 0
        self.switch_count = 0
        self.gate_len = self.gate_default
        self.busy = 0
        self.done = 0
        self.remaining = 0
        self.gcnt = 0
        self.freq_count = 0
        self.errs = 0
        self.counter = 0
        self.mux_count = 0
        self.acc = 0

    def _edges(self):
        if self.active == 0:
            return 1
        self.acc += 625
        d = 100 * self.b_div
        e = self.acc // d
        self.acc -= e * d
        return e

    def step(self, inputs=None):
        if inputs:
            self.inputs.update(inputs)
        e = self._edges()
        self.counter = (self.counter + e) & ((1 << self.width) - 1)
        if self.busy:
            self.gcnt += e
            self.remaining -= 1
            if self.remaining <= 0:
                self.busy = 0
                self.done = 1
                self.freq_count = self.gcnt & 0xFFFFFFFF
        if self.switching:
            self.sw_timer -= 1
            if self.sw_timer <= 0:
                if self.active != self.sel:
                    self.active = self.sel
                    self.switch_count = (self.switch_count + 1) & 0xFFFFFFFF
                    self.acc = 0
                self.switching = 0
        return {"led": self.active | (self.switching << 1), "sfp_tx_disable": 1}

    def read_reg(self, offset):
        o = offset
        if o == 0: return self.design_id & 0xFFFFFFFF
        if o == 4: return 0
        if o == 8: return self.scratch
        if o == 16: return self.sel
        if o == 20: return self.switching | (self.active << 1)
        if o == 24: return self.b_div
        if o == 28: return self.gate_len
        if o == 32: return 0
        if o == 36: return self.busy | (self.done << 1)
        if o == 40: return self.freq_count
        if o == 44: return self.errs
        if o == 48: return self.mux_count
        if o == 52: return self.switch_count
        return 0

    def write_reg(self, offset, value):
        o = offset
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            v = value & 1
            if v != self.sel:
                self.sel = v
                self.switching = 1
                self.sw_timer = self.SWITCH_CYCLES
        elif o == 28:
            self.gate_len = value
        elif o == 32:
            if value & 1 and not self.busy:
                self.busy = 1
                self.done = 0
                self.remaining = max(self.gate_len, 1)
                self.gcnt = 0
        elif o == 56:
            self.mux_count = self.counter & 0xFFFFFFFF
