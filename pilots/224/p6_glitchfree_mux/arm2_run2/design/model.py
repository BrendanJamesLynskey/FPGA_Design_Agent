class Model:
    SW_LAT = 4
    SYNC = 2

    def __init__(self, DESIGN_ID=546701313, B_DIV=1, GATE_LEN_DEFAULT=25000000,
                 GATE_LEN_BITS=32, RST_HOLD_CYCLES=8, ADDR_WIDTH=12):
        self.DESIGN_ID = DESIGN_ID
        self.B_DIV = B_DIV
        self.GATE_LEN_DEFAULT = GATE_LEN_DEFAULT
        self.GATE_LEN_BITS = GATE_LEN_BITS
        self.RST_HOLD_CYCLES = RST_HOLD_CYCLES
        self.ADDR_WIDTH = ADDR_WIDTH
        self.build = 0
        self.reset()

    def reset(self):
        self.scratch = 0
        self.sel = 0
        self.mux_active = 0
        self.active_sync = [0] * self.SYNC
        self.active_sel = 0
        self.sw_timer = 0
        self.switching = 0
        self.switch_count = 0
        self.gate_len = self.GATE_LEN_DEFAULT
        self.busy = 0
        self.done = 0
        self.remaining = 0
        self.freq_count = 0
        self.errs = 0
        self.counter = 0
        self.mux_count = 0
        self.acc = 0

    def _mask(self):
        return (1 << self.GATE_LEN_BITS) - 1

    def _edges(self):
        if self.mux_active == 0:
            return 1
        d = 4 * max(1, self.B_DIV)
        self.acc += 25
        e, self.acc = divmod(self.acc, d)
        return e

    def _start_switch_if_needed(self):
        if not self.switching and self.sel != self.mux_active:
            self.switching = 1
            self.sw_timer = self.SW_LAT

    def step(self, inputs=None):
        e = self._edges()
        self.counter = (self.counter + e) & 0xFFFFFFFF
        if self.busy:
            self.freq_count = (self.freq_count + e) & 0xFFFFFFFF
            self.remaining -= 1
            if self.remaining <= 0:
                self.busy = 0
                self.done = 1
        self._start_switch_if_needed()
        if self.switching:
            self.sw_timer -= 1
            if self.sw_timer <= 0:
                self.mux_active = self.sel
                self.switch_count = (self.switch_count + 1) & 0xFFFFFFFF
                self.switching = 0
                self._start_switch_if_needed()
        self.active_sel = self.active_sync[-1]
        self.active_sync = [self.mux_active] + self.active_sync[:-1]
        return {"sfp_tx_disable": 1,
                "led": (self.active_sel & 1) | ((1 if self.errs else 0) << 1)}

    def read_reg(self, offset):
        o = offset
        if o == 0:
            return self.DESIGN_ID & 0xFFFFFFFF
        if o == 4:
            return self.build
        if o == 8:
            return self.scratch
        if o == 16:
            return self.sel
        if o == 20:
            return self.switching | (self.active_sel << 1)
        if o == 24:
            return self.B_DIV & 0xF
        if o == 28:
            return self.gate_len
        if o == 32:
            return 0
        if o == 36:
            return self.busy | (self.done << 1)
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
            self._start_switch_if_needed()
        elif o == 28:
            self.gate_len = v & self._mask()
        elif o == 32:
            if (v & 1) and not self.busy:
                self.busy = 1
                self.done = 0
                self.freq_count = 0
                self.remaining = max(1, self.gate_len)
        elif o == 56:
            self.mux_count = self.counter
