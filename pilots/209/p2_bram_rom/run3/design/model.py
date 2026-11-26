import os

_M = 0xFFFFFFFF


class Model:
    def __init__(self, ADDR_BITS=10, DEPTH_WORDS=1024, DATA_BITS=32,
                 DESIGN_ID=546439169, RAM_INIT_BASE=3235774464,
                 PASSES_MAX=65535, POR_CYCLES=8):
        self.depth = DEPTH_WORDS
        self.dbits = DATA_BITS
        self.mask = (1 << DATA_BITS) - 1
        self.id = DESIGN_ID
        self.base = RAM_INIT_BASE
        self.pmax = PASSES_MAX
        self.rom = [0] * self.depth
        for p in ("data/rom_init.hex",
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rom_init.hex")):
            if os.path.exists(p):
                try:
                    i = 0
                    for ln in open(p):
                        ln = ln.split("//")[0].strip()
                        for w in ln.split():
                            if i < self.depth:
                                self.rom[i] = int(w, 16) & self.mask
                                i += 1
                except Exception:
                    pass
                break
        self.ram = [(self.base + i) & self.mask for i in range(self.depth)]
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}
        self.reset()

    def reset(self):
        # RAM/ROM contents are not affected by reset
        self.scratch = 0
        self.addr = 0
        self.autoinc = 0
        self.inject = 0
        self.passes = 1
        self.busy = 0
        self.done = 0
        self.done_passes = 0
        self.errs = 0
        self.first = _M
        self.pos = 0
        self.bgi = 0
        self.rdata = 0
        self.inp = {"h_we": 0, "h_re": 0, "h_addr": 0, "h_wdata": 0}

    # ---- registers
    def _inc(self):
        if self.autoinc:
            self.addr = (self.addr + 1) % self.depth

    def read_reg(self, offset):
        o = offset & 0xFFC
        if o == 0:
            return self.id & _M
        if o == 4:
            return 0
        if o == 8:
            return self.scratch
        if o == 16:
            return self.addr
        if o == 20:
            v = self.rom[self.addr]
            self._inc()
            return v
        if o == 24:
            if self.busy:
                return 0
            v = self.ram[self.addr]
            self._inc()
            return v
        if o == 28:
            return self.autoinc
        if o == 32:
            return self.inject << 1
        if o == 36:
            return self.passes
        if o == 40:
            return self.busy | (self.done << 1) | (self.done_passes << 16)
        if o == 44:
            return self.errs
        if o == 48:
            return self.first
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFC
        value &= _M
        if o == 8:
            self.scratch = value
        elif o == 16:
            self.addr = value % self.depth
        elif o == 24:
            if not self.busy:
                self.ram[self.addr] = value & self.mask
                self._inc()
        elif o == 28:
            self.autoinc = value & 1
        elif o == 32:
            self.inject = (value >> 1) & 1
            if (value & 1) and not self.busy:
                self.errs = 0
                self.done_passes = 0
                self.done = 0
                self.first = _M
                self.busy = 1
                self.pos = 0
                self.bgi = 0
        elif o == 36:
            self.passes = value & 0xFFFF

    # ---- march engine, one operation per clock
    def _march(self):
        n = self.depth
        p = self.pos
        bg = 0 if self.bgi == 0 else self.mask
        nb = bg ^ self.mask
        ram = self.ram
        # element boundaries in ops
        b1 = n
        b2 = b1 + 2 * n
        b3 = b2 + 2 * n
        b4 = b3 + 2 * n
        b5 = b4 + 2 * n
        total = b5 + n
        if p < b1:
            ram[p] = bg
        else:
            if p < b2:
                q = p - b1; a = q >> 1; rd = (q & 1) == 0; exp = bg; wv = nb; first = True
            elif p < b3:
                q = p - b2; a = q >> 1; rd = (q & 1) == 0; exp = nb; wv = bg; first = False
            elif p < b4:
                q = p - b3; a = n - 1 - (q >> 1); rd = (q & 1) == 0; exp = bg; wv = nb; first = False
            elif p < b5:
                q = p - b4; a = n - 1 - (q >> 1); rd = (q & 1) == 0; exp = nb; wv = bg; first = False
            else:
                q = p - b5; a = n - 1 - q; rd = True; exp = bg; wv = None; first = False
            if rd:
                v = ram[a]
                if first and a == 0 and self.inject:
                    v ^= self.mask
                if v != exp:
                    self.errs = (self.errs + 1) & _M
                    if self.first == _M:
                        self.first = a
            else:
                ram[a] = wv
        p += 1
        if p >= total:
            p = 0
            if self.bgi == 0:
                self.bgi = 1
            else:
                self.bgi = 0
                self.done_passes += 1
                target = self.passes or 1
                if self.done_passes >= target:
                    self.busy = 0
                    self.done = 1
                    for i in range(n):
                        ram[i] = 0
        self.pos = p

    def step(self, inputs=None):
        if inputs:
            for k, v in inputs.items():
                self.inp[k] = v
        i = self.inp
        we = i["h_we"] & 1
        re = i["h_re"] & 1
        # engine runs on state before this edge's host write
        was_busy = self.busy
        if was_busy:
            self._march()
        if we:
            self.write_reg(i["h_addr"], i["h_wdata"])
        if re:
            self.rdata = self.read_reg(i["h_addr"])
        # pulses are one-cycle: consume
        self.inp["h_we"] = 0
        self.inp["h_re"] = 0
        return {"led": self.busy | (self.done << 1),
                "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
