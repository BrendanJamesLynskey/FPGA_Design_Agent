class Model:
    def __init__(self, DESIGN_ID=546504705, CRC_POLY=79764919, CRC_INIT=4294967295,
                 CRC_XOROUT=4294967295, DATA_BYTES_PER_CLK=4, TAIL_LEN_MAX=3,
                 READ_LATENCY_CYCLES=1, CLK_FREQ_CYCLES=1):
        self.DESIGN_ID = DESIGN_ID & 0xFFFFFFFF
        self.poly = CRC_POLY & 0xFFFFFFFF
        self.rpoly = int(format(self.poly, '032b')[::-1], 2)
        self.init = CRC_INIT & 0xFFFFFFFF
        self.xorout = CRC_XOROUT & 0xFFFFFFFF
        self.tail_max = TAIL_LEN_MAX
        self.reset()

    def reset(self):
        self.crc = self.init
        self.bytes = 0
        self.busy = 0
        self.scratch = 0
        self.tail = 0
        self.build = 0
        self.rdata = 0
        self.inp = {'h_we': 0, 'h_re': 0, 'h_addr': 0, 'h_wdata': 0}
        self.cnt = 0

    def _push(self, word, n):
        c = self.crc
        for i in range(n):
            c ^= (word >> (8 * i)) & 0xFF
            for _ in range(8):
                c = (c >> 1) ^ self.rpoly if c & 1 else c >> 1
        self.crc = c & 0xFFFFFFFF
        if n:
            self.bytes = (self.bytes + n) & 0xFFFFFFFF
            self.busy = (self.busy + 1) & 0xFFFFFFFF

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.DESIGN_ID
        if o == 4:
            return self.build
        if o == 8:
            return self.scratch
        if o == 28:
            return self.tail
        if o == 32:
            return (self.crc ^ self.xorout) & 0xFFFFFFFF if self.bytes else 0
        if o == 36:
            return self.bytes
        if o == 40:
            return self.busy
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        v = value & 0xFFFFFFFF
        if o == 8:
            self.scratch = v
        elif o == 16:
            if v & 1:
                self.crc = self.init
                self.bytes = 0
                self.busy = 0
        elif o == 20:
            self._push(v, 4)
        elif o == 24:
            self._push(v, self.tail)
        elif o == 28:
            self.tail = v & 3

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                if k in self.inp:
                    self.inp[k] = v
        i = self.inp
        # read samples pre-edge state
        if i['h_re']:
            self.rdata = self.read_reg(i['h_addr'])
        if i['h_we']:
            self.write_reg(i['h_addr'], i['h_wdata'])
        self.cnt += 1
        return {'h_rdata': self.rdata,
                'led': 1 | (((self.cnt >> 24) & 1) << 1),
                'sfp_tx_disable': 1}
