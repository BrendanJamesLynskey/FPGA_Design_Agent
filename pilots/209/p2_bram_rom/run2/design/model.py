import os

_M = 0xFFFFFFFF


class Model:
    def __init__(self, ROM_DEPTH=1024, RAM_DEPTH=1024, DATA_WIDTH=32, ADDR_WIDTH=10,
                 RESET_CYCLES=8, DESIGN_ID=546439169, RAM_INIT_BASE=3235774464,
                 MAX_PASSES=65535, FAULT_ADDR=0, READ_LATENCY_CYCLES=2):
        self.ROM_DEPTH = ROM_DEPTH
        self.RAM_DEPTH = RAM_DEPTH
        self.DW = DATA_WIDTH
        self.AW = ADDR_WIDTH
        self.ID = DESIGN_ID
        self.base = RAM_INIT_BASE
        self.FAULT_ADDR = FAULT_ADDR
        self.mask = (1 << DATA_WIDTH) - 1
        self.rom = [0] * ROM_DEPTH
        here = os.path.dirname(os.path.abspath(__file__))
        for p in (os.path.join(here, "data", "rom_init.hex"), "data/rom_init.hex"):
            if os.path.exists(p):
                try:
                    i = 0
                    for ln in open(p):
                        ln = ln.split("//")[0].strip()
                        for w in ln.split():
                            if w.startswith("@"):
                                i = int(w[1:], 16)
                                continue
                            if i < ROM_DEPTH:
                                self.rom[i] = int(w.replace("_", ""), 16) & self.mask
                            i += 1
                except Exception:
                    pass
                break
        self.ram = [(self.base + i) & self.mask for i in range(RAM_DEPTH)]
        self.reset()

    def reset(self):
        self.scratch = 0
        self.addr = 0
        self.autoinc = 0
        self.inject = 0
        self.passes_cfg = 1
        self.busy = 0
        self.done = 0
        self.completed = 0
        self.errs = 0
        self.first = _M
        self.gen = None
        self.rdata = 0

    def _march(self):
        n = self.RAM_DEPTH
        total = self.passes_cfg or 1
        for _ in range(total):
            fault_used = False
            for bg in (self.mask, 0):
                inv = bg ^ self.mask
                up = range(n)
                dn = range(n - 1, -1, -1)
                elems = [(up, None, inv and bg), (up, bg, inv), (up, inv, bg),
                         (dn, bg, inv), (dn, inv, bg), (dn, bg, None)]
                # element 0: w0 only
                for a in up:
                    self.ram[a] = bg
                    yield
                for order, exp, wr in elems[1:]:
                    for a in order:
                        v = self.ram[a]
                        if (self.inject and not fault_used and a == self.FAULT_ADDR):
                            v ^= 1
                            fault_used = True
                        yield_err = v != exp
                        if yield_err:
                            self.errs = (self.errs + 1) & _M
                            if self.first == _M:
                                self.first = a
                        yield
                        if wr is not None:
                            self.ram[a] = wr
                            yield
            self.completed += 1
        self.busy = 0
        self.done = 1

    def step(self, inputs=None):
        if self.gen is not None:
            try:
                next(self.gen)
            except StopIteration:
                self.gen = None
        return {"led": (self.busy & 1) | ((self.done & 1) << 1), "sfp_tx_disable": 1}

    def _inc(self):
        if self.autoinc:
            self.addr = (self.addr + 1) % self.RAM_DEPTH

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            v = self.ID
        elif o == 4:
            v = 0
        elif o == 8:
            v = self.scratch
        elif o == 16:
            v = self.addr
        elif o == 20:
            v = self.rom[self.addr % self.ROM_DEPTH]
            self._inc()
        elif o == 24:
            if self.busy:
                v = 0
            else:
                v = self.ram[self.addr % self.RAM_DEPTH]
                self._inc()
        elif o == 28:
            v = self.autoinc
        elif o == 32:
            v = self.inject << 1
        elif o == 36:
            v = self.passes_cfg
        elif o == 40:
            v = self.busy | (self.done << 1) | ((self.completed & 0xFFFF) << 16)
        elif o == 44:
            v = self.errs
        elif o == 48:
            v = self.first
        else:
            v = 0
        self.rdata = v & _M
        return self.rdata

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= _M
        if o == 8:
            self.scratch = value
        elif o == 16:
            self.addr = value % self.RAM_DEPTH if False else value & ((1 << self.AW) - 1)
        elif o == 24:
            if not self.busy:
                self.ram[self.addr % self.RAM_DEPTH] = value & self.mask
                self._inc()
        elif o == 28:
            self.autoinc = value & 1
        elif o == 32:
            self.inject = (value >> 1) & 1
            if value & 1 and not self.busy:
                self.errs = 0
                self.completed = 0
                self.done = 0
                self.first = _M
                self.busy = 1
                self.gen = self._march()
        elif o == 36:
            self.passes_cfg = value & 0xFFFF
