class Model:
    """Cycle model. One step() = one clk_c3 (register port) cycle; clk_ref
    advances 6.25 cycles per step (156.25/25) via a phase accumulator."""

    def __init__(self, GATE_LEN_DEFAULT=156250000, GATE_LEN_MIN=1000,
                 LED_C3_HALF_PERIOD_CYCLES=12500000,
                 LED_REF_HALF_PERIOD_CYCLES=78125000,
                 DESIGN_ID=546373633, REG_READ_LATENCY_CYCLES=1):
        self.GATE_LEN_DEFAULT = GATE_LEN_DEFAULT
        self.GATE_LEN_MIN = GATE_LEN_MIN
        self.LC = LED_C3_HALF_PERIOD_CYCLES
        self.LR = LED_REF_HALF_PERIOD_CYCLES
        self.DESIGN_ID = DESIGN_ID
        self.RL = max(1, REG_READ_LATENCY_CYCLES)
        self.reset()

    def reset(self):
        self.scratch = 0
        self.gate_len = self.GATE_LEN_DEFAULT
        self.led_en = 0
        self.busy = 0
        self.done = 0
        self.count = 0
        self.gate_actual = 0
        self.meas_done = 0
        self.gate_latched = 0
        self.remaining = 0
        self.edges = 0
        self.phase = 0
        self.c3_cnt = 0
        self.ref_cnt = 0
        self.led0 = 0
        self.led1 = 0
        self.rdata = 0
        self.pipe = []
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0, "rst": 0}

    def read_reg(self, offset):
        o = offset & 0xFFFFFFFF
        m = 0xFFFFFFFF
        if o == 0: return self.DESIGN_ID & m
        if o == 4: return 0
        if o == 8: return self.scratch
        if o == 16: return self.gate_len
        if o == 20: return self.led_en << 1
        if o == 24: return self.busy | (self.done << 1)
        if o == 28: return self.count
        if o == 32: return self.gate_actual
        if o == 36: return self.meas_done
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFFFFFFF
        v = value & 0xFFFFFFFF
        if o == 8:
            self.scratch = v
        elif o == 16:
            self.gate_len = v
        elif o == 20:
            self.led_en = (v >> 1) & 1
            if (v & 1) and not self.busy:
                self.gate_latched = max(self.gate_len, self.GATE_LEN_MIN)
                self.remaining = self.gate_latched
                self.edges = 0
                self.done = 0
                self.busy = 1

    def _out(self):
        return {"led": ((self.led1 << 1) | self.led0) if self.led_en else 0,
                "sfp_tx_disable": 1, "h_rdata": self.rdata}

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                self.inp[k] = v
        i = self.inp
        if i.get("rst"):
            keep = dict(i)
            self.reset()
            self.inp.update(keep)
            self.inp["h_we"] = 0
            self.inp["h_re"] = 0
            return self._out()
        # register port
        if i["h_we"]:
            self.write_reg(i["h_addr"], i["h_wdata"])
        # read pipeline
        if i["h_re"]:
            self.pipe.append([self.RL - 1, self.read_reg(i["h_addr"])])
        nxt = []
        for p in self.pipe:
            if p[0] <= 0:
                self.rdata = p[1]
            else:
                p[0] -= 1
                nxt.append(p)
        self.pipe = nxt
        # ref ticks this step
        total = self.phase + 25
        k = total // 4
        self.phase = total % 4
        # gate (a gate started this step begins counting next step)
        if self.busy and not (i["h_we"] and i["h_addr"] == 20 and (i["h_wdata"] & 1)
                              and self.remaining == self.gate_latched
                              and self.edges == 0 and False):
            self.edges += 1
            if k >= self.remaining:
                self.remaining = 0
                self.count = self.edges
                self.gate_actual = self.gate_latched
                self.meas_done = (self.meas_done + 1) & 0xFFFFFFFF
                self.busy = 0
                self.done = 1
            else:
                self.remaining -= k
        # LEDs
        self.c3_cnt += 1
        if self.c3_cnt >= self.LC:
            self.c3_cnt = 0
            self.led0 ^= 1
        self.ref_cnt += k
        while self.ref_cnt >= self.LR:
            self.ref_cnt -= self.LR
            self.led1 ^= 1
        return self._out()
