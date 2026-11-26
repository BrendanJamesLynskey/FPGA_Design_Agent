"""Bring-up checks for p2_rom_ram_march over the JTAG register bus."""
from flow.host_transport import MockBus
from model import Model

DESIGN_ID = 0x20920001

MEM_ADDR, ROM_DATA, RAM_DATA, MEM_CTRL = 0x10, 0x14, 0x18, 0x1C
MARCH_CTRL, MARCH_PASSES, MARCH_STATUS = 0x20, 0x24, 0x28
MARCH_ERRS, MARCH_FIRST_ERR = 0x2C, 0x30
M32 = 0xFFFFFFFF


class _Mock(MockBus):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for name in ("id", "ID", "design_id", "DESIGN_ID"):
            try:
                setattr(self, name, DESIGN_ID)
            except Exception:
                pass
        self.m = Model()

    def _finish(self):
        n = 0
        while self.m.busy and n < 5_000_000:
            self.m.step()
            n += 1

    def read(self, addr):
        a = addr & 0xFFF
        if a == 0:
            return DESIGN_ID
        if a < 0x10 or a > 0x30:
            return super().read(addr)
        return self.m.read_reg(a) & M32

    def write(self, addr, value):
        a = addr & 0xFFF
        if a < 0x10 or a > 0x30:
            return super().write(addr, value)
        self.m.write_reg(a, value)
        if a == MARCH_CTRL:
            self._finish()


CAPTURES = []


def restore(sh):
    """Leave the design at reset values."""
    for a, v in ((MARCH_CTRL, 0), (MARCH_PASSES, 1), (MEM_ADDR, 0), (MEM_CTRL, 0), (0x08, 0)):
        sh.wr(a, v) if hasattr(sh, "wr") else sh.write(a, v)


def make_mock():
    return _Mock()


def _rom_words():
    return Model().rom


def run(bus):
    res = []
    rom = _rom_words()

    # ROM reads with autoinc
    bus.wr(MEM_ADDR, 0)
    bus.wr(MEM_CTRL, 1)
    got = [bus.rd(ROM_DATA) for _ in range(16)]
    res.append(("rom_first16", got == rom[:16], "got %s" % [hex(x) for x in got[:4]]))
    res.append(("autoinc_rom", bus.rd(MEM_ADDR) == 16, "MEM_ADDR=%d" % bus.rd(MEM_ADDR)))
    bus.wr(MEM_ADDR, 1020)
    got = [bus.rd(ROM_DATA) for _ in range(6)]
    exp = [rom[(1020 + i) % 1024] for i in range(6)]
    res.append(("rom_wrap", got == exp and bus.rd(MEM_ADDR) == 2, "wrap"))
    bus.wr(MEM_CTRL, 0)
    bus.wr(MEM_ADDR, 5)
    bus.rd(ROM_DATA)
    res.append(("autoinc_off", bus.rd(MEM_ADDR) == 5, "MEM_ADDR unchanged"))

    # RAM initial contents
    bus.wr(MEM_ADDR, 0)
    bus.wr(MEM_CTRL, 1)
    got = [bus.rd(RAM_DATA) for _ in range(8)]
    exp = [0xC0DE0000 + i for i in range(8)]
    res.append(("ram_init", got == exp, "got %s" % [hex(x) for x in got[:3]]))

    # RAM write/read back, then restore
    bus.wr(MEM_ADDR, 100)
    bus.wr(RAM_DATA, 0xA5A55A5A)
    bus.wr(RAM_DATA, 0x12345678)
    bus.wr(MEM_ADDR, 100)
    a, b = bus.rd(RAM_DATA), bus.rd(RAM_DATA)
    res.append(("ram_rw", (a, b) == (0xA5A55A5A, 0x12345678), "%x %x" % (a, b)))
    bus.wr(MEM_CTRL, 0)

    # March, 2 passes, no fault
    bus.wr(MARCH_PASSES, 2)
    bus.wr(MARCH_CTRL, 1)
    st = 0
    for _ in range(2000):
        st = bus.rd(MARCH_STATUS)
        if st & 2:
            break
    res.append(("march_done", bool(st & 2) and not (st & 1) and (st >> 16) == 2,
                "status=0x%x" % st))
    res.append(("march_errs0", bus.rd(MARCH_ERRS) == 0, "errs"))
    res.append(("march_first_none", bus.rd(MARCH_FIRST_ERR) == M32, "first_err"))
    bus.wr(MEM_ADDR, 0)
    bus.wr(MEM_CTRL, 1)
    z = [bus.rd(RAM_DATA) for _ in range(4)]
    bus.wr(MEM_ADDR, 1023)
    z.append(bus.rd(RAM_DATA))
    res.append(("ram_zero_after", all(v == 0 for v in z), "ram zeros"))
    bus.wr(MEM_CTRL, 0)

    # March with injected fault, 2 passes
    bus.wr(MARCH_CTRL, 3)
    for _ in range(2000):
        st = bus.rd(MARCH_STATUS)
        if st & 2:
            break
    errs = bus.rd(MARCH_ERRS)
    first = bus.rd(MARCH_FIRST_ERR)
    res.append(("march_fault", bool(st & 2) and errs == 2 and first == 0x155,
                "errs=%d first=0x%x" % (errs, first)))

    # restore reset values
    bus.wr(MARCH_CTRL, 0)
    bus.wr(MARCH_PASSES, 1)
    bus.wr(MEM_ADDR, 0)
    bus.wr(MEM_CTRL, 0)
    return res
