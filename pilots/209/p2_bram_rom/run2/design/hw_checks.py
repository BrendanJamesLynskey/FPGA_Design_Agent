"""Bring-up checks for p2_rom_ram_march over the JTAG register bus."""
from flow.host_transport import MockBus
from model import Model

DESIGN_ID = 0x20920001

MEM_ADDR, ROM_DATA, RAM_DATA, MEM_CTRL = 0x10, 0x14, 0x18, 0x1C
MARCH_CTRL, MARCH_PASSES, MARCH_STATUS, MARCH_ERRS, MARCH_FIRST = 0x20, 0x24, 0x28, 0x2C, 0x30


class _Mock(MockBus):
    def __init__(self):
        super().__init__()
        self.ID = DESIGN_ID
        self.m = Model()

    def read(self, addr):
        if addr in (0x0, 0x4, 0x8):
            return super().read(addr)
        if addr == MARCH_STATUS:
            # the model's march runs only per step; finish it on a status read
            while self.m.busy:
                self.m.step()
        return self.m.read_reg(addr)

    def write(self, addr, value):
        if addr in (0x0, 0x4, 0x8):
            return super().write(addr, value)
        return self.m.write_reg(addr, value)


def make_mock():
    return _Mock()


def run(bus):
    res = []
    m = Model()

    def chk(name, got, exp):
        res.append((name, got == exp, "got 0x%08X expected 0x%08X" % (got, exp)))

    # ROM words, autoincrement
    bus.wr(MEM_ADDR, 0)
    bus.wr(MEM_CTRL, 1)
    ok = True
    first_bad = None
    for i in range(16):
        v = bus.rd(ROM_DATA)
        if v != m.rom[i]:
            ok = False
            first_bad = (i, v)
            break
    res.append(("rom_first_16", ok, "ok" if ok else "bad word %s" % (first_bad,)))
    chk("autoinc_addr", bus.rd(MEM_ADDR), 16)
    bus.wr(MEM_ADDR, 1023)
    bus.rd(ROM_DATA)
    chk("rom_wrap", bus.rd(MEM_ADDR), 0)
    bus.wr(MEM_CTRL, 0)

    # RAM init values
    for a in (0, 1, 500, 1023):
        bus.wr(MEM_ADDR, a)
        chk("ram_init_%d" % a, bus.rd(RAM_DATA), (0xC0DE0000 + a) & 0xFFFFFFFF)
    # RAM write/read
    bus.wr(MEM_ADDR, 7)
    bus.wr(RAM_DATA, 0xA5A5F00D)
    chk("ram_wr_rd", bus.rd(RAM_DATA), 0xA5A5F00D)
    chk("mem_addr_unchanged", bus.rd(MEM_ADDR), 7)

    # March, no fault
    bus.wr(MARCH_PASSES, 2)
    bus.wr(MARCH_CTRL, 1)
    for _ in range(2000):
        if bus.rd(MARCH_STATUS) & 1 == 0:
            break
    st = bus.rd(MARCH_STATUS)
    chk("march_status", st, (2 << 16) | 2)
    chk("march_errs", bus.rd(MARCH_ERRS), 0)
    chk("march_first", bus.rd(MARCH_FIRST), 0xFFFFFFFF)
    for a in (0, 7, 1023):
        bus.wr(MEM_ADDR, a)
        chk("ram_zero_%d" % a, bus.rd(RAM_DATA), 0)

    # March with injected fault, 3 passes
    bus.wr(MARCH_PASSES, 3)
    bus.wr(MARCH_CTRL, 3)
    for _ in range(2000):
        if bus.rd(MARCH_STATUS) & 1 == 0:
            break
    chk("fault_errs", bus.rd(MARCH_ERRS), 3)
    chk("fault_first", bus.rd(MARCH_FIRST), 0)

    # leave reset values
    bus.wr(MARCH_CTRL, 0)
    bus.wr(MARCH_PASSES, 1)
    bus.wr(MEM_ADDR, 0)
    bus.wr(MEM_CTRL, 0)
    return res
