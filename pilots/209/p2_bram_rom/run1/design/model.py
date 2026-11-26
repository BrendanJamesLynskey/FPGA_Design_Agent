import os

M32 = 0xFFFFFFFF


def _load_rom(path, depth):
    rom = [0] * depth
    cands = [path, os.path.join(os.path.dirname(os.path.abspath(__file__)), path)]
    for p in cands:
        if os.path.exists(p):
            i = 0
            with open(p) as f:
                for line in f:
                    line = line.strip().split('//')[0].strip()
                    if not line or line.startswith('@'):
                        continue
                    if i < depth:
                        rom[i] = int(line, 16) & M32
                        i += 1
            break
    return rom


class Model:
    def __init__(self, ROM_DEPTH=1024, RAM_DEPTH=1024, DATA_WIDTH=32,
                 ADDR_WIDTH=10, RAM_INIT_BASE=3235774464, DESIGN_ID=546439169,
                 POR_CYCLES=8, MAX_PASSES=65535,
                 ROM_INIT_FILE="data/rom_init.hex"):
        self.ROM_DEPTH = ROM_DEPTH
        self.RAM_DEPTH = RAM_DEPTH
        self.DW = DATA_WIDTH
        self.mask = (1 << DATA_WIDTH) - 1
        self.AW = ADDR_WIDTH
        self.RAM_INIT_BASE = RAM_INIT_BASE
        self.DESIGN_ID = DESIGN_ID
        self.MAX_PASSES = MAX_PASSES
        self.rom = _load_rom(ROM_INIT_FILE, ROM_DEPTH)
        self.inputs = {}
        self.fault_addr = 0x155
        self.reset()
        # reset() keeps memory contents only on explicit full init
        
    def reset(self):
        self.ram = [(self.RAM_INIT_BASE + i) & self.mask for i in range(self.RAM_DEPTH)]
        self.scratch = 0
        self.mem_addr = 0
        self.autoinc = 0
        self.inject = 0
        self.passes = 1
        self.busy = 0
        self.done = 0
        self.completed = 0
        self.errs = 0
        self.first_err = M32
        self.h_rdata = 0
        self.gen = None
        self.inputs = {}

    # ---- march engine ----
    def _ops(self):
        n = self.RAM_DEPTH
        up = range(n)
        dn = range(n - 1, -1, -1)
        total = self.passes or 1
        for _ in range(total):
            for bi, bg in enumerate((self.mask, 0)):
                c = bg ^ self.mask
                first = bi == 0
                for a in up:
                    yield ('w', a, bg, False)
                for rng, e, w in ((up, bg, c), (up, c, bg), (dn, bg, c), (dn, c, bg)):
                    for a in rng:
                        yield ('r', a, e, first and e == bg and rng is up and a == self.fault_addr)
                        yield ('w', a, w, False)
                for a in up:
                    yield ('r', a, bg, False)
            yield ('p', 0, 0, False)

    def _engine(self):
        if not self.busy:
            return
        try:
            k, a, v, inj = next(self.gen)
        except StopIteration:
            self.busy = 0
            self.done = 1
            self.gen = None
            return
        if k == 'w':
            self.ram[a] = v
        elif k == 'r':
            d = self.ram[a]
            if inj and self.inject:
                d ^= 1
            if d != v:
                self.errs = (self.errs + 1) & M32
                if self.first_err == M32:
                    self.first_err = a
        else:
            self.completed = (self.completed + 1) & 0xFFFF

    # ---- registers ----
    def _inc(self):
        if self.autoinc:
            self.mem_addr = (self.mem_addr + 1) % self.RAM_DEPTH

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.DESIGN_ID & M32
        if o == 4:
            return 0
        if o == 8:
            return self.scratch
        if o == 16:
            return self.mem_addr
        if o == 20:
            v = self.rom[self.mem_addr % self.ROM_DEPTH]
            self._inc()
            return v
        if o == 24:
            if self.busy:
                return 0
            v = self.ram[self.mem_addr % self.RAM_DEPTH]
            self._inc()
            return v
        if o == 28:
            return self.autoinc
        if o == 32:
            return self.inject << 1
        if o == 36:
            return self.passes
        if o == 40:
            return self.busy | (self.done << 1) | (self.completed << 16)
        if o == 44:
            return self.errs
        if o == 48:
            return self.first_err
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= M32
        if o == 8:
            self.scratch = value
        elif o == 16:
            self.mem_addr = value & ((1 << self.AW) - 1)
        elif o == 24:
            if not self.busy:
                self.ram[self.mem_addr % self.RAM_DEPTH] = value & self.mask
                self._inc()
        elif o == 28:
            self.autoinc = value & 1
        elif o == 32:
            self.inject = (value >> 1) & 1
            if (value & 1) and not self.busy:
                self.errs = 0
                self.completed = 0
                self.done = 0
                self.first_err = M32
                self.busy = 1
                self.gen = self._ops()
        elif o == 36:
            p = value & 0xFFFF
            self.passes = p
        # others ignored

    def step(self, inputs=None):
        if inputs:
            self.inputs.update(inputs)
        i = self.inputs
        we = i.get('h_we', 0)
        re = i.get('h_re', 0)
        # pulses: consumed once
        self.inputs['h_we'] = 0
        self.inputs['h_re'] = 0
        addr = i.get('h_addr', 0)
        if we:
            self.write_reg(addr, i.get('h_wdata', 0))
        elif re:
            self.h_rdata = self.read_reg(addr)
        self._engine()
        return {
            'led': self.busy | (self.done << 1),
            'sfp_tx_disable': 1,
            'h_rdata': self.h_rdata,
        }
