M32 = 0xFFFFFFFF


class Model:
    def __init__(self, DESIGN_ID=546504705, CLK_MULT_NUM_X1000=40000,
                 RST_HOLD_CYCLES=8, MAX_TAIL_LEN=3, DATA_BYTES_PER_CLK=4,
                 CRC_POLY=79764919, CRC_INIT=4294967295,
                 CRC_XOROUT=4294967295):
        self.design_id = DESIGN_ID & M32
        self.max_tail = MAX_TAIL_LEN
        self.poly = CRC_POLY & M32
        self.init = CRC_INIT & M32
        self.xorout = CRC_XOROUT & M32
        self.rpoly = int(format(self.poly, '032b')[::-1], 2)
        self.hb_half = 50_000_000
        self.reset()

    def reset(self):
        self.crc = self.init
        self.bytes = 0
        self.busy = 0
        self.scratch = 0
        self.tail = 0
        self.rdata = 0
        self.hb = 0
        self.led0 = 0
        self.inp = {'h_we': 0, 'h_re': 0, 'h_addr': 0, 'h_wdata': 0}

    def _feed(self, word, n):
        c = self.crc
        for i in range(n):
            c ^= (word >> (8 * i)) & 0xFF
            for _ in range(8):
                c = (c >> 1) ^ self.rpoly if c & 1 else c >> 1
        self.crc = c & M32

    def _read(self, off):
        off &= 0xFFF
        if off == 0:
            return self.design_id
        if off == 8:
            return self.scratch
        if off == 28:
            return self.tail
        if off == 32:
            return (self.crc ^ self.xorout) & M32
        if off == 36:
            return self.bytes
        if off == 40:
            return self.busy
        return 0

    def read_reg(self, offset):
        return self._read(offset)

    def write_reg(self, offset, value):
        off = offset & 0xFFF
        v = value & M32
        if off == 8:
            self.scratch = v
        elif off == 16:
            if v & 1:
                self.crc = self.init
                self.bytes = 0
                self.busy = 0
        elif off == 20:
            self._feed(v, 4)
            self.bytes = (self.bytes + 4) & M32
            self.busy = (self.busy + 1) & M32
        elif off == 24:
            if self.tail > 0:
                self._feed(v, self.tail)
                self.bytes = (self.bytes + self.tail) & M32
                self.busy = (self.busy + 1) & M32
        elif off == 28:
            if v <= self.max_tail and v <= 3:
                self.tail = v

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                self.inp[k] = v
        i = self.inp
        # read samples pre-edge state
        if i['h_re']:
            self.rdata = self._read(i['h_addr'])
        if i['h_we']:
            self.write_reg(i['h_addr'], i['h_wdata'])
        self.hb += 1
        if self.hb >= self.hb_half:
            self.hb = 0
            self.led0 ^= 1
        return {'led': (1 << 1) | self.led0, 'sfp_tx_disable': 1,
                'h_rdata': self.rdata}
