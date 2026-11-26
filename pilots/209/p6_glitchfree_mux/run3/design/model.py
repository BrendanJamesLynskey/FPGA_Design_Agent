class Model:
    SWITCH_DELAY = 3

    def __init__(self, DESIGN_ID=546701313, B_DIV_VALUE=1, GATE_LEN_DEFAULT=25000000,
                 SWITCH_TIMEOUT_CYCLES=4096, MUX_COUNT_WIDTH=32):
        self.p = dict(DESIGN_ID=DESIGN_ID, B_DIV_VALUE=B_DIV_VALUE,
                      GATE_LEN_DEFAULT=GATE_LEN_DEFAULT,
                      SWITCH_TIMEOUT_CYCLES=SWITCH_TIMEOUT_CYCLES,
                      MUX_COUNT_WIDTH=MUX_COUNT_WIDTH)
        self.inputs = {}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.sel = 0
        self.active = 0
        self.sdelay = 0
        self.gate_len = self.p['GATE_LEN_DEFAULT'] & 0xFFFFFFFF
        self.busy = 0
        self.done = 0
        self.gate_cnt = 0
        self.edges = 0
        self.freq_count = 0
        self.errs = 0
        self.mux_count = 0
        self.switch_count = 0
        self.counter = 0
        self.acc = 0  # fractional edge accumulator (units of 1/(25*div) of B edges)

    def _edges_this_cycle(self):
        if self.active == 0:
            return 1
        # B freq = 156.25/div MHz vs 25 MHz: 6.25/div edges per cycle = 25/(4*div)
        num = 25
        den = 4 * max(1, self.p['B_DIV_VALUE'])
        self.acc += num
        n = self.acc // den
        self.acc -= n * den
        return n

    def _outputs(self):
        sw = 1 if self.sel != self.active else 0
        return {'led': (self.active & 1) | (sw << 1), 'sfp_tx_disable': 1}

    def step(self, inputs=None):
        if inputs:
            self.inputs.update(inputs)
        n = self._edges_this_cycle()
        self.counter = (self.counter + n) & ((1 << self.p['MUX_COUNT_WIDTH']) - 1)
        if self.busy:
            self.edges = (self.edges + n) & 0xFFFFFFFF
            self.gate_cnt -= 1
            if self.gate_cnt <= 0:
                self.busy = 0
                self.done = 1
                self.freq_count = self.edges
        if self.sel != self.active:
            self.sdelay += 1
            if self.sdelay >= self.SWITCH_DELAY:
                self.active = self.sel
                self.sdelay = 0
                self.switch_count = (self.switch_count + 1) & 0xFFFFFFFF
        else:
            self.sdelay = 0
        return self._outputs()

    def read_reg(self, offset):
        o = offset & 0xFFF
        sw = 1 if self.sel != self.active else 0
        if o == 0: return self.p['DESIGN_ID'] & 0xFFFFFFFF
        if o == 4: return 0
        if o == 8: return self.scratch
        if o == 16: return self.sel
        if o == 20: return sw | (self.active << 1)
        if o == 24: return self.p['B_DIV_VALUE'] & 0xF
        if o == 28: return self.gate_len
        if o == 32: return 0
        if o == 36: return self.busy | (self.done << 1)
        if o == 40: return self.freq_count
        if o == 44: return self.errs
        if o == 48: return self.mux_count
        if o == 52: return self.switch_count
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        v = value & 0xFFFFFFFF
        if o == 8:
            self.scratch = v
        elif o == 16:
            self.sel = v & 1
        elif o == 28:
            self.gate_len = v
        elif o == 32:
            if (v & 1) and not self.busy:
                self.busy = 1
                self.done = 0
                self.gate_cnt = max(1, self.gate_len)
                self.edges = 0
        elif o == 56:
            self.mux_count = self.counter & 0xFFFFFFFF
