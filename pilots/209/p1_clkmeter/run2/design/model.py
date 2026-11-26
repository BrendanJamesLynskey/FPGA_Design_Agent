class Model:
    def __init__(self, GATE_LEN_DEFAULT=156250000, GATE_LEN_MIN=1000,
                 LED_HALF_PERIOD_C3_CYCLES=12500000,
                 LED_HALF_PERIOD_REF_CYCLES=78125000,
                 DESIGN_ID=546373633, REG_READ_LATENCY_CYCLES=1):
        self.p_gate_def = GATE_LEN_DEFAULT
        self.p_gate_min = GATE_LEN_MIN
        self.p_led_c3 = LED_HALF_PERIOD_C3_CYCLES
        self.p_led_ref = LED_HALF_PERIOD_REF_CYCLES
        self.p_id = DESIGN_ID
        self.build = 0  # settable constant (USR_ACCESSE2 not simulated)
        self.reset()

    def reset(self):
        self.scratch = 0
        self.gate_len = self.p_gate_def
        self.led_en = 0
        self.busy = 0
        self.done = 0
        self.count = 0
        self.gate_actual = 0
        self.meas_done = 0
        self.latched = 0
        self.gcnt = 0
        self.c3cnt = 0
        self.phase = 0
        self.led0_cnt = 0
        self.led0 = 0
        self.led1_cnt = 0
        self.led1 = 0
        self.h_rdata = 0
        self.inp = {}

    def read_reg(self, offset):
        m = 0xFFFFFFFF
        if offset == 0:
            return self.p_id & m
        if offset == 4:
            return self.build & m
        if offset == 8:
            return self.scratch
        if offset == 16:
            return self.gate_len
        if offset == 20:
            return self.led_en << 1
        if offset == 24:
            return self.busy | (self.done << 1)
        if offset == 28:
            return self.count
        if offset == 32:
            return self.gate_actual
        if offset == 36:
            return self.meas_done
        return 0

    def write_reg(self, offset, value):
        value &= 0xFFFFFFFF
        if offset == 8:
            self.scratch = value
        elif offset == 16:
            self.gate_len = value
        elif offset == 20:
            self.led_en = (value >> 1) & 1
            if (value & 1) and not self.busy:
                self.done = 0
                self.busy = 1
                self.latched = max(self.gate_len, self.p_gate_min)
                self.gcnt = 0
                self.c3cnt = 0

    def step(self, inputs=None):
        if inputs:
            self.inp.update(inputs)
        i = self.inp
        we = i.get("h_we", 0)
        re = i.get("h_re", 0)
        addr = i.get("h_addr", 0)
        # one-shot strobes: consumed each step
        if inputs is not None:
            self.inp["h_we"] = 0
            self.inp["h_re"] = 0
        # clock-domain evolution (c3 = 25/156.25 edges per ref cycle)
        self.phase += 4
        edge = 0
        if self.phase >= 25:
            self.phase -= 25
            edge = 1
        if self.busy:
            self.c3cnt += edge
            self.gcnt += 1
            if self.gcnt >= self.latched:
                self.busy = 0
                self.done = 1
                self.count = self.c3cnt
                self.gate_actual = self.latched
                self.meas_done = (self.meas_done + 1) & 0xFFFFFFFF
        if self.led_en:
            if edge:
                self.led0_cnt += 1
                if self.led0_cnt >= self.p_led_c3:
                    self.led0_cnt = 0
                    self.led0 ^= 1
            self.led1_cnt += 1
            if self.led1_cnt >= self.p_led_ref:
                self.led1_cnt = 0
                self.led1 ^= 1
        else:
            self.led0 = self.led1 = 0
            self.led0_cnt = self.led1_cnt = 0
        if we:
            self.write_reg(addr, i.get("h_wdata", 0))
        if re:
            self.h_rdata = self.read_reg(addr)
        return {"led": self.led0 | (self.led1 << 1),
                "sfp_tx_disable": 1,
                "h_rdata": self.h_rdata}
