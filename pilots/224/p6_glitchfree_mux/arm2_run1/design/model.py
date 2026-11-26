class Model:
    SWITCH_DELAY = 3

    def __init__(self, ID_VALUE=546701313, B_DIV=1, GATE_LEN_DEFAULT=25000000,
                 RST_HOLD_CYCLES=16):
        self.ID_VALUE = ID_VALUE
        self.B_DIV = B_DIV
        self.GATE_LEN_DEFAULT = GATE_LEN_DEFAULT
        self.RST_HOLD_CYCLES = RST_HOLD_CYCLES
        self.reset()

    def reset(self):
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.scratch = 0
        self.sel = 0
        self.active = 0
        self.delay = 0
        self.switch_count = 0
        self.gate_len = self.GATE_LEN_DEFAULT
        self.busy = 0
        self.done = 0
        self.gate_left = 0
        self.freq_count = 0
        self.errs = 0
        self.mux_cnt = 0
        self.mux_snap = 0
        self.frac = 0.0
        self.h_rdata = 0

    @property
    def switching(self):
        return 1 if self.sel != self.active else 0

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.ID_VALUE & 0xFFFFFFFF
        if o == 4:
            return 0
        if o == 8:
            return self.scratch
        if o == 16:
            return self.sel
        if o == 20:
            return self.switching | (self.active << 1)
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
            return self.mux_snap
        if o == 52:
            return self.switch_count
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            self.sel = value & 1
            if self.sel != self.active and self.delay == 0:
                self.delay = self.SWITCH_DELAY
        elif o == 28:
            self.gate_len = value
        elif o == 32:
            if value & 1 and not self.busy:
                self.busy = 1
                self.done = 0
                self.freq_count = 0
                self.gate_left = max(self.gate_len, 1)
        elif o == 48 or o == 56:
            if o == 56:
                self.mux_snap = self.mux_cnt & 0xFFFFFFFF

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                self.inp[k] = v
        we = self.inp["h_we"]
        re = self.inp["h_re"]
        if we:
            self.write_reg(self.inp["h_addr"], self.inp["h_wdata"])
        # mux domain
        if self.active == 0:
            edges = 1
        else:
            self.frac += 6.25 / max(self.B_DIV, 1)
            edges = int(self.frac)
            self.frac -= edges
        self.mux_cnt = (self.mux_cnt + edges) & 0xFFFFFFFFFFFFFFFF
        if self.busy:
            self.freq_count = (self.freq_count + edges) & 0xFFFFFFFF
            self.gate_left -= 1
            if self.gate_left <= 0:
                self.busy = 0
                self.done = 1
        # switching
        if self.delay > 0:
            self.delay -= 1
            if self.delay == 0:
                if self.active != self.sel:
                    self.active = self.sel
                    self.switch_count = (self.switch_count + 1) & 0xFFFFFFFF
        elif self.sel != self.active:
            self.delay = self.SWITCH_DELAY
        if re:
            self.h_rdata = self.read_reg(self.inp["h_addr"])
        return {"led": self.active | (self.switching << 1),
                "sfp_tx_disable": 1,
                "h_rdata": self.h_rdata}
