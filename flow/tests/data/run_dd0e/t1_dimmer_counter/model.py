class Model:
    _SEG = [0x40, 0x79, 0x24, 0x30, 0x19, 0x12, 0x02, 0x78,
            0x00, 0x10, 0x08, 0x03, 0x46, 0x21, 0x06, 0x0E]

    def __init__(self, CLK_FREQ_CYCLES_PER_SEC=100000000, BAUD_DIV_CYCLES=868,
                 DEBOUNCE_CYCLES=2000000, PWM_PERIOD_CYCLES=65536,
                 SCAN_DIGIT_CYCLES=100000, COUNTER_WIDTH=16, BRIGHT_WIDTH=8,
                 DESIGN_ID=1412514883):
        self.p_deb = DEBOUNCE_CYCLES
        self.p_pwm = PWM_PERIOD_CYCLES
        self.p_scan = SCAN_DIGIT_CYCLES
        self.cw = COUNTER_WIDTH
        self.bw = BRIGHT_WIDTH
        self.id = DESIGN_ID
        self.inp = {'BTNU': 0, 'BTND': 0, 'BTNC': 0, 'SW': 0, 'UART_RXD': 1}
        self.reset()

    def reset(self):
        self.counter = 0
        self.bright = 1 << (self.bw - 1)
        self.ctrl = 0
        self.s1 = [0, 0, 0]
        self.s2 = [0, 0, 0]
        self.deb = [0, 0, 0]
        self.dcnt = [0, 0, 0]
        self.press = [0, 0, 0]
        self.sw1 = 0
        self.sw2 = 0
        self.phase = 0
        self.samp = self.bright
        self.scan = 0
        self.digit = 0

    def _eff(self):
        return (self.sw2 & ((1 << self.bw) - 1)) if self.ctrl & 1 else self.bright

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                if k in self.inp:
                    self.inp[k] = int(v)
        i = self.inp
        btn = [i['BTNU'] & 1, i['BTND'] & 1, i['BTNC'] & 1]
        pulse = [0, 0, 0]
        for n in range(3):
            s2 = self.s2[n]
            if s2 != self.deb[n]:
                self.dcnt[n] += 1
                if self.dcnt[n] >= self.p_deb:
                    self.deb[n] = s2
                    self.dcnt[n] = 0
                    if s2:
                        pulse[n] = 1
            else:
                self.dcnt[n] = 0
            self.s2[n] = self.s1[n]
            self.s1[n] = btn[n]
        m = (1 << self.cw) - 1
        if pulse[2]:
            self.counter = 0
        elif pulse[0]:
            self.counter = (self.counter + 1) & m
        elif pulse[1]:
            self.counter = (self.counter - 1) & m
        for n in range(3):
            if pulse[n]:
                self.press[n] = (self.press[n] + 1) & 0xFFFFFFFF
        self.sw2 = self.sw1
        self.sw1 = i['SW'] & 0xFFFF
        # pwm
        self.phase += 1
        if self.phase >= self.p_pwm:
            self.phase = 0
            self.samp = self._eff()
        # scan
        self.scan += 1
        if self.scan >= self.p_scan:
            self.scan = 0
            self.digit = (self.digit + 1) & 7
        return self._outputs()

    def _outputs(self):
        lvl = (self.phase << self.bw) // self.p_pwm
        led = self.counter if lvl < self.samp else 0
        d = self.digit
        eff = self._eff()
        if self.ctrl & 2 or d in (4, 5):
            an = 0xFF
            seg = 0x7F
        else:
            if d < 4:
                nib = (self.counter >> (4 * d)) & 0xF
            else:
                nib = (eff >> (4 * (d - 6))) & 0xF
            an = 0xFF & ~(1 << d)
            seg = self._SEG[nib]
        return {'LED': led & 0xFFFF, 'SEG': seg, 'DP': 1, 'AN': an, 'UART_TXD': 1}

    def read_reg(self, offset):
        o = offset
        if o == 0: return self.id
        if o == 4: return self.counter
        if o == 8: return self.bright
        if o == 12: return self.ctrl
        if o == 16: return self.deb[0] | (self.deb[1] << 1) | (self.deb[2] << 2)
        if o == 20: return self.sw2
        if o == 24: return self.press[0]
        if o == 28: return self.press[1]
        if o == 32: return self.press[2]
        return 0

    def write_reg(self, offset, value):
        if offset == 4:
            self.counter = value & ((1 << self.cw) - 1)
        elif offset == 8:
            self.bright = value & ((1 << self.bw) - 1)
        elif offset == 12:
            self.ctrl = value & 3
