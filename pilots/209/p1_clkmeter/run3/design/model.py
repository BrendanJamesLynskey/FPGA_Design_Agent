class Model:
    def __init__(self, DESIGN_ID=546373633, GATE_DEFAULT_CYCLES=156250000,
                 GATE_MIN_CYCLES=1000, LED_C3_HALF_PERIOD_CYCLES=12500000,
                 LED_REF_HALF_PERIOD_CYCLES=78125000, REG_WIDTH=32, COUNT_WIDTH=32):
        self.p = dict(DESIGN_ID=DESIGN_ID, GATE_DEFAULT_CYCLES=GATE_DEFAULT_CYCLES,
                      GATE_MIN_CYCLES=GATE_MIN_CYCLES,
                      LED_C3_HALF_PERIOD_CYCLES=LED_C3_HALF_PERIOD_CYCLES,
                      LED_REF_HALF_PERIOD_CYCLES=LED_REF_HALF_PERIOD_CYCLES)
        self.M = (1 << REG_WIDTH) - 1
        self.CM = (1 << COUNT_WIDTH) - 1
        self.inp = {}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.gate_len = self.p['GATE_DEFAULT_CYCLES']
        self.led_en = 0
        self.busy = 0
        self.done = 0
        self.count = 0
        self.actual = 0
        self.meas = 0
        self.phase = 0      # 0 idle, 1 sync delay, 2 gate open
        self.latched = 0
        self.ref_left_q = 0
        self.cnt = 0
        self.c3_cnt = 0
        self.ref_q = 0      # led ref counter in quarter cycles
        self.led0 = 0
        self.led1 = 0
        self.rdata = 0

    def read_reg(self, offset):
        o = offset
        if o == 0: return self.p['DESIGN_ID'] & self.M
        if o == 4: return 0
        if o == 8: return self.scratch
        if o == 16: return self.gate_len
        if o == 20: return self.led_en << 1
        if o == 24: return self.busy | (self.done << 1)
        if o == 28: return self.count
        if o == 32: return self.actual
        if o == 36: return self.meas
        return 0

    def write_reg(self, offset, value):
        v = value & self.M
        if offset == 8:
            self.scratch = v
        elif offset == 16:
            self.gate_len = v
        elif offset == 20:
            self.led_en = (v >> 1) & 1
            if (v & 1) and not self.busy:
                self.busy = 1
                self.done = 0
                self.latched = max(self.gate_len, self.p['GATE_MIN_CYCLES'])
                self.phase = 1

    def step(self, inputs=None):
        if inputs:
            self.inp.update(inputs)
        i = self.inp
        if i.get('h_we'):
            self.write_reg(i.get('h_addr', 0), i.get('h_wdata', 0))
        if i.get('h_re'):
            self.rdata = self.read_reg(i.get('h_addr', 0))
        # measurement
        if self.phase == 2:
            self.cnt += 1
            self.ref_left_q -= 25
            if self.ref_left_q <= 0:
                self.count = self.cnt & self.CM
                self.actual = self.latched
                self.meas = (self.meas + 1) & self.M
                self.busy = 0
                self.done = 1
                self.phase = 0
        elif self.phase == 1:
            self.phase = 2
            self.cnt = 0
            self.ref_left_q = self.latched * 4
        # leds
        if self.led_en:
            self.c3_cnt += 1
            if self.c3_cnt >= self.p['LED_C3_HALF_PERIOD_CYCLES']:
                self.c3_cnt = 0
                self.led0 ^= 1
            self.ref_q += 25
            h4 = self.p['LED_REF_HALF_PERIOD_CYCLES'] * 4
            if self.ref_q >= h4:
                self.ref_q -= h4
                self.led1 ^= 1
        else:
            self.c3_cnt = 0
            self.ref_q = 0
            self.led0 = 0
            self.led1 = 0
        return {'led': self.led0 | (self.led1 << 1), 'sfp_tx_disable': 1,
                'h_rdata': self.rdata}
