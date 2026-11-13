class Model:
    def __init__(self, *, DEBOUNCE_CYCLES=1000000, PWM_PERIOD_CYCLES=4096, DISPLAY_DIGIT_CYCLES=100000, UART_BAUD_DIVIDER_CYCLES=868):
        self.DEBOUNCE_CYCLES = int(DEBOUNCE_CYCLES)
        self.PWM_PERIOD_CYCLES = int(PWM_PERIOD_CYCLES)
        self.DISPLAY_DIGIT_CYCLES = int(DISPLAY_DIGIT_CYCLES)
        self.UART_BAUD_DIVIDER_CYCLES = int(UART_BAUD_DIVIDER_CYCLES)
        self._inputs = {}
        self.reset()

    def reset(self):
        self._inputs = {
            "clk": 0,
            "cpu_resetn": 1,
            "btn_up": 0,
            "btn_down": 0,
            "btn_center": 0,
            "switches": 0,
            "uart_rxd": 1,
        }
        self._reset_state()

    def _reset_state(self):
        self._counter = 0
        self._brightness = 255
        self._control = 0
        self._press_counts = {"up": 0, "down": 0, "center": 0}
        self._sync_meta = {"up": 0, "down": 0, "center": 0}
        self._sync_value = {"up": 0, "down": 0, "center": 0}
        self._debounced = {"up": 0, "down": 0, "center": 0}
        self._debounce_candidate = {"up": 0, "down": 0, "center": 0}
        self._debounce_count = {"up": 0, "down": 0, "center": 0}
        self._pwm_phase = 0
        self._display_count = 0
        self._display_digit = 0
        self._counter_write_pending = False

    def _outputs(self):
        brightness = self._inputs["switches"] & 0xff if (self._control & 1) else self._brightness
        period = max(1, self.PWM_PERIOD_CYCLES)
        if brightness <= 0:
            pwm_on = False
        elif brightness >= 255:
            pwm_on = True
        else:
            on_cycles = (brightness * period + 254) // 255
            pwm_on = self._pwm_phase < on_cycles
        leds = (self._counter & 0xffff) if pwm_on else 0

        # Seven-segment codes are active-low and ordered abcdefg.
        glyphs = (0x01, 0x4f, 0x12, 0x06, 0x4c, 0x24, 0x20, 0x0f,
                  0x00, 0x04, 0x08, 0x60, 0x31, 0x42, 0x30, 0x38)
        digit = self._display_digit
        an = 0xff
        seg = 0x7f
        if not (self._control & 2) and digit not in (4, 5):
            an = 0xff ^ (1 << digit)
            if digit == 7:
                value = (brightness >> 4) & 0xf
            elif digit == 6:
                value = brightness & 0xf
            else:
                value = (self._counter >> (4 * digit)) & 0xf
            seg = glyphs[value]

        return {
            "leds": leds & 0xffff,
            "seg": seg & 0x7f,
            "dp": 1,
            "an": an & 0xff,
            "uart_txd": 1,
        }

    def step(self, inputs=None):
        if inputs is not None:
            for name, value in inputs.items():
                if name in self._inputs:
                    self._inputs[name] = int(value)

        if not self._inputs["cpu_resetn"]:
            self._reset_state()
            return self._outputs()

        old_meta = dict(self._sync_meta)
        old_sync = dict(self._sync_value)
        raw_buttons = {
            "up": 1 if self._inputs["btn_up"] else 0,
            "down": 1 if self._inputs["btn_down"] else 0,
            "center": 1 if self._inputs["btn_center"] else 0,
        }
        events = {"up": False, "down": False, "center": False}

        for name in ("up", "down", "center"):
            self._sync_meta[name] = raw_buttons[name]
            self._sync_value[name] = old_meta[name]
            sampled = old_sync[name]
            if sampled == self._debounced[name]:
                self._debounce_candidate[name] = sampled
                self._debounce_count[name] = 0
            else:
                if sampled != self._debounce_candidate[name]:
                    self._debounce_candidate[name] = sampled
                    self._debounce_count[name] = 1
                else:
                    self._debounce_count[name] += 1
                required = max(1, self.DEBOUNCE_CYCLES)
                if self._debounce_count[name] >= required:
                    self._debounced[name] = sampled
                    self._debounce_count[name] = 0
                    events[name] = bool(sampled)

        # A press is counted independently of counter-event arbitration.
        for name in ("up", "down", "center"):
            if events[name]:
                self._press_counts[name] = (self._press_counts[name] + 1) & 0xffffffff

        if self._counter_write_pending:
            self._counter_write_pending = False
        else:
            if events["center"]:
                self._counter = 0
            elif events["up"]:
                self._counter = (self._counter + 1) & 0xffff
            elif events["down"]:
                self._counter = (self._counter - 1) & 0xffff

        pwm_period = max(1, self.PWM_PERIOD_CYCLES)
        self._pwm_phase = (self._pwm_phase + 1) % pwm_period

        display_period = max(1, self.DISPLAY_DIGIT_CYCLES)
        self._display_count += 1
        if self._display_count >= display_period:
            self._display_count = 0
            self._display_digit = (self._display_digit + 1) & 7

        return self._outputs()

    def read_reg(self, offset):
        offset = int(offset)
        if offset == 0:
            return self._counter & 0xffff
        if offset == 4:
            return self._brightness & 0xff
        if offset == 8:
            return self._control & 0x3
        if offset == 12:
            status = self._inputs["switches"] & 0xff
            status |= (1 if self._inputs["btn_up"] else 0) << 8
            status |= (1 if self._inputs["btn_down"] else 0) << 9
            status |= (1 if self._inputs["btn_center"] else 0) << 10
            return status
        if offset == 16:
            return self._press_counts["up"]
        if offset == 20:
            return self._press_counts["down"]
        if offset == 24:
            return self._press_counts["center"]
        if offset == 28:
            return 0x54314443
        return 0

    def write_reg(self, offset, value):
        offset = int(offset)
        value = int(value)
        if offset == 0:
            self._counter = value & 0xffff
            self._counter_write_pending = True
        elif offset == 4:
            self._brightness = value & 0xff
        elif offset == 8:
            self._control = value & 0x3
