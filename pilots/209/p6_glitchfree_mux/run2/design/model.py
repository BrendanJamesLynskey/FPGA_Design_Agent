class Model:
    def __init__(self, ID_VALUE=546701313, B_DIV=1, GATE_LEN_DEFAULT=25000000,
                 SYNC_STAGES=2):
        self.ID_VALUE = ID_VALUE
        self.B_DIV = B_DIV
        self.GATE_LEN_DEFAULT = GATE_LEN_DEFAULT
        self.SYNC_STAGES = SYNC_STAGES
        self.reset()

    def reset(self):
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.scratch = 0
        self.sel = 0
        self.active = 0
        self.cnt = 0
        self.gate_len = self.GATE_LEN_DEFAULT
        self.busy = 0
        self.done = 0
        self.remaining = 0
        self.fcount = 0
        self.fcur = 0
        self.facc = 0
        self.macc = 0
        self.errs = 0
        self.mux_count = 0
        self.snap = 0
        self.switches = 0
        self.counter = 0
        self.rdata = 0

    def _edges(self, acc_name):
        if self.active == 0:
            return 1
        acc = getattr(self, acc_name) + 25
        d = 4 * self.B_DIV
        setattr(self, acc_name, acc % d)
        return acc // d

    def write_reg(self, offset, value):
        value &= 0xFFFFFFFF
        o = offset & 0xFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            v = value & 1
            if v != self.sel:
                self.sel = v
                self.cnt = self.SYNC_STAGES + 2
            elif v != self.active:
                self.cnt = self.SYNC_STAGES + 2
            self.sel = v
        elif o == 28:
            self.gate_len = value
        elif o == 32:
            if (value & 1) and not self.busy:
                self.done = 0
                self.fcur = 0
                if self.gate_len == 0:
                    self.done = 1
                    self.fcount = 0
                else:
                    self.busy = 1
                    self.remaining = self.gate_len
        elif o == 56:
            self.mux_count = self.counter & 0xFFFFFFFF

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.ID_VALUE & 0xFFFFFFFF
        if o == 8:
            return self.scratch
        if o == 16:
            return self.sel
        if o == 20:
            return (self.sel != self.active) | (self.active << 1)
        if o == 24:
            return self.B_DIV
        if o == 28:
            return self.gate_len
        if o == 36:
            return self.busy | (self.done << 1)
        if o == 40:
            return self.fcount
        if o == 44:
            return self.errs
        if o == 48:
            return self.mux_count
        if o == 52:
            return self.switches
        return 0

    def step(self, inputs=None):
        if inputs:
            for k in self.inp:
                if k in inputs:
                    self.inp[k] = int(inputs[k])
        # free-running domain / measurement (pre-edge state)
        self.counter = (self.counter + self._edges("macc")) & (2**64 - 1)
        if self.busy:
            self.fcur += self._edges("facc")
            self.remaining -= 1
            if self.remaining <= 0:
                self.busy = 0
                self.done = 1
                self.fcount = self.fcur & 0xFFFFFFFF
        # switch handshake
        if self.sel != self.active:
            self.cnt -= 1
            if self.cnt <= 0:
                self.active = self.sel
                self.switches = (self.switches + 1) & 0xFFFFFFFF
        i = self.inp
        if i["h_we"]:
            self.write_reg(i["h_addr"], i["h_wdata"])
        if i["h_re"]:
            self.rdata = self.read_reg(i["h_addr"])
        sw = 1 if self.sel != self.active else 0
        return {"led": self.active | (sw << 1), "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
