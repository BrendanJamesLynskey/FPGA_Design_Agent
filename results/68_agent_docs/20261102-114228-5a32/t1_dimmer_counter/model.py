class Model:
    def __init__(self, *, DEBOUNCE_CYCLES=1000000, PWM_PERIOD_CYCLES=256, DISPLAY_SCAN_CYCLES=100000, UART_BAUD_DIVIDER=868):
        self.DEBOUNCE_CYCLES = max(1, int(DEBOUNCE_CYCLES))
        self.PWM_PERIOD_CYCLES = max(1, int(PWM_PERIOD_CYCLES))
        self.DISPLAY_SCAN_CYCLES = max(1, int(DISPLAY_SCAN_CYCLES))
        self.UART_BAUD_DIVIDER = int(UART_BAUD_DIVIDER)
        self._inputs = {
            "clk": 0,
            "cpu_reset_n": 1,
            "button_up": 0,
            "button_down": 0,
            "button_center": 0,
            "switches": 0,
            "uart_rx": 1,
        }
        self.reset()

    def reset(self):
        self.counter = 0
        self.brightness = 0
        self.control = 0
        self.press_counts = [0, 0, 0]
        self._switches = 0
        self._sync1 = [0, 0, 0]
        self._sync2 = [0, 0, 0]
        self._button_levels = [0, 0, 0]
        self._debounce_candidate = [0, 0, 0]
        self._debounce_count = [0, 0, 0]
        self._pwm_phase = 0
        self._scan_digit = 0
        self._scan_elapsed = 0

    def read_reg(self, offset):
        offset = int(offset)
        if offset == 0:
            return 0x54314443
        if offset == 4:
            return self.counter & 0xFFFF
        if offset == 8:
            return self.brightness & 0xFF
        if offset == 12:
            return self.control & 0xFFFFFFFF
        if offset == 16:
            return sum((level & 1) << bit for bit, level in enumerate(self._button_levels))
        if offset == 20:
            return self._switches & 0xFF
        if offset == 24:
            return self.press_counts[0] & 0xFFFFFFFF
        if offset == 28:
            return self.press_counts[1] & 0xFFFFFFFF
        if offset == 32:
            return self.press_counts[2] & 0xFFFFFFFF
        return 0

    def write_reg(self, offset, value):
        offset = int(offset)
        value = int(value)
        if offset == 4:
            self.counter = value & 0xFFFF
        elif offset == 8:
            self.brightness = value & 0xFF
        elif offset == 12:
            self.control = value & 0xFFFFFFFF

    def _active_brightness(self):
        if self.control & 1:
            return self._switches & 0xFF
        return self.brightness & 0xFF

    def _segments(self, nibble):
        # Bit order is CA, CB, CC, CD, CE, CF, CG, DP; zero lights a segment.
        patterns = (0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
                    0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71)
        return ((~patterns[nibble & 0xF]) & 0x7F) | 0x80

    def _display_outputs(self):
        if self.control & 2:
            return 0xFF, 0xFF
        digit = self._scan_digit
        if digit <= 3:
            nibble = (self.counter >> (digit * 4)) & 0xF
            segments = self._segments(nibble)
        elif digit == 4 or digit == 5:
            segments = 0xFF
        elif digit == 6:
            segments = self._segments(self._active_brightness() & 0xF)
        else:
            segments = self._segments((self._active_brightness() >> 4) & 0xF)
        return segments, (0xFF ^ (1 << digit)) & 0xFF

    def _outputs(self):
        brightness = self._active_brightness()
        # Brightness zero is off and 255 is exactly full duty.
        threshold = (brightness * self.PWM_PERIOD_CYCLES + 254) // 255
        led_value = self.counter if self._pwm_phase < threshold else 0
        segments, digit_enable = self._display_outputs()
        return {
            "uart_tx": 1,
            "leds": led_value & 0xFFFF,
            "segments_n": segments & 0xFF,
            "digit_enable_n": digit_enable & 0xFF,
        }

    def step(self, inputs=None):
        if inputs:
            for name, value in inputs.items():
                if name in self._inputs:
                    self._inputs[name] = int(value)
        if not (self._inputs["cpu_reset_n"] & 1):
            self.reset()
            return self._outputs()

        self._switches = self._inputs["switches"] & 0xFF
        raw_buttons = [self._inputs["button_up"] & 1,
                       self._inputs["button_down"] & 1,
                       self._inputs["button_center"] & 1]
        old_sync1 = self._sync1[:]
        old_sync2 = self._sync2[:]
        self._sync1 = raw_buttons
        self._sync2 = old_sync1

        rising = [False, False, False]
        for i, sample in enumerate(old_sync2):
            if sample == self._button_levels[i]:
                self._debounce_candidate[i] = sample
                self._debounce_count[i] = 0
            else:
                if sample != self._debounce_candidate[i]:
                    self._debounce_candidate[i] = sample
                    self._debounce_count[i] = 1
                else:
                    self._debounce_count[i] += 1
                if self._debounce_count[i] >= self.DEBOUNCE_CYCLES:
                    previous = self._button_levels[i]
                    self._button_levels[i] = sample
                    self._debounce_count[i] = 0
                    rising[i] = bool(sample and not previous)

        for i, event in enumerate(rising):
            if event:
                self.press_counts[i] = (self.press_counts[i] + 1) & 0xFFFFFFFF
        if rising[2]:
            self.counter = 0
        elif rising[0] and not rising[1]:
            self.counter = (self.counter + 1) & 0xFFFF
        elif rising[1] and not rising[0]:
            self.counter = (self.counter - 1) & 0xFFFF

        self._pwm_phase = (self._pwm_phase + 1) % self.PWM_PERIOD_CYCLES
        self._scan_elapsed += 1
        if self._scan_elapsed >= self.DISPLAY_SCAN_CYCLES:
            self._scan_elapsed = 0
            self._scan_digit = (self._scan_digit + 1) & 7
        return self._outputs()
