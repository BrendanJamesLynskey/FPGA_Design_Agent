class Model:
    def __init__(self, DESIGN_ID=546504705, CRC_POLY=79764919, CRC_INIT=4294967295,
                 CRC_XOROUT=4294967295, DATA_BYTES_PER_CLK=4, MMCM_MULT=40,
                 MMCM_DIVIDE=10, RDATA_LATENCY_CYCLES=1):
        self.DESIGN_ID = DESIGN_ID
        self.CRC_INIT = CRC_INIT & 0xFFFFFFFF
        self.CRC_XOROUT = CRC_XOROUT & 0xFFFFFFFF
        self.rpoly = int(format(CRC_POLY & 0xFFFFFFFF, '032b')[::-1], 2)
        self.in_ = {'h_we': 0, 'h_re': 0, 'h_addr': 0, 'h_wdata': 0}
        self.reset()

    def reset(self):
        self.scratch = 0
        self.tail = 0
        self.state = self.CRC_INIT
        self.bytes = 0
        self.busy = 0
        self.rdata = 0
        self.in_ = {'h_we': 0, 'h_re': 0, 'h_addr': 0, 'h_wdata': 0}

    def _feed(self, data, n):
        s = self.state
        for i in range(n):
            s ^= (data >> (8 * i)) & 0xFF
            for _ in range(8):
                s = (s >> 1) ^ self.rpoly if s & 1 else s >> 1
        self.state = s & 0xFFFFFFFF

    def read_reg(self, offset):
        o = offset
        if o == 0:
            return self.DESIGN_ID & 0xFFFFFFFF
        if o == 8:
            return self.scratch
        if o == 28:
            return self.tail
        if o == 32:
            return (self.state ^ self.CRC_XOROUT) & 0xFFFFFFFF
        if o == 36:
            return self.bytes & 0xFFFFFFFF
        if o == 40:
            return self.busy & 0xFFFFFFFF
        return 0  # BUILD, CTRL, WO, unmapped

    def write_reg(self, offset, value):
        v = value & 0xFFFFFFFF
        if offset == 8:
            self.scratch = v
        elif offset == 28:
            self.tail = v & 3
        elif offset == 16:
            if v & 1:
                self.state = self.CRC_INIT
                self.bytes = 0
                self.busy = 0
        elif offset == 20:
            self._feed(v, 4)
            self.bytes += 4
            self.busy += 1
        elif offset == 24:
            n = self.tail
            if n:
                self._feed(v, n)
                self.bytes += n
                self.busy += 1

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                if k in self.in_:
                    self.in_[k] = v
        i = self.in_
        # read samples pre-edge state
        if i['h_re']:
            self.rdata = self.read_reg(i['h_addr'] & 0xFFF)
        if i['h_we']:
            self.write_reg(i['h_addr'] & 0xFFF, i['h_wdata'])
        # pulses
        self.in_['h_we'] = 0
        self.in_['h_re'] = 0
        return {'led': 1, 'sfp_tx_disable': 1, 'h_rdata': self.rdata}
