"""Bring-up checks for p2_mem_test over the JTAG register bus."""
from flow.host_transport import MockBus
from model import Model

DESIGN_ID = 0x20920001

MEM_ADDR, ROM_DATA, RAM_DATA, MEM_CTRL = 0x10, 0x14, 0x18, 0x1C
MARCH_CTRL, MARCH_PASSES, MARCH_STATUS = 0x20, 0x24, 0x28
MARCH_ERRS, MARCH_FIRST = 0x2C, 0x30
_MINE = (MEM_ADDR, ROM_DATA, RAM_DATA, MEM_CTRL, MARCH_CTRL, MARCH_PASSES,
         MARCH_STATUS, MARCH_ERRS, MARCH_FIRST)


class _Mock(MockBus):
    """Register behaviour of a correct design (model.py), registers from 0x010."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.m = Model()
        self.m.reset()

    def read(self, addr):
        a = addr & 0xFFC
        if a == 0:
            return DESIGN_ID
        if a in _MINE:
            if a == MARCH_STATUS and self.m.busy:
                # a march run finishes quickly in the mock
                for _ in range(200000):
                    if not self.m.busy:
                        break
                    self.m.step()
            return self.m.read_reg(a)
        return super().read(addr)

    def write(self, addr, value):
        a = addr & 0xFFC
        if a in _MINE:
            self.m.write_reg(a, value)
            return None
        return super().write(addr, value)


def make_mock():
    try:
        b = _Mock()
    except TypeError:
        b = _Mock(DESIGN_ID)
    for n in ("id", "ID", "design_id", "DESIGN_ID"):
        try:
            setattr(b, n, DESIGN_ID)
        except Exception:
            pass
    return b


CAPTURES = []


def restore(sh):
    """Leave the design at its reset values."""
    for a, v in ((MARCH_CTRL, 0), (MARCH_PASSES, 1), (MEM_ADDR, 0), (MEM_CTRL, 0)):
        sh.write(a, v)


def _wait_done(bus, tries=200):
    st = 0
    for _ in range(tries):
        st = bus.rd(MARCH_STATUS)
        if st & 2 and not st & 1:
            return st
    return st


def run(bus):
    res = []
    ref = Model()
    rom = ref.rom

    bus.wr(MEM_CTRL, 0)
    bus.wr(MEM_ADDR, 0)
    bus.wr(MARCH_PASSES, 1)
    bus.wr(MARCH_CTRL, 0)

    # ROM contents
    bad = []
    bus.wr(MEM_ADDR, 0)
    for i in (0, 1, 2, 511, 1023):
        bus.wr(MEM_ADDR, i)
        v = bus.rd(ROM_DATA)
        if v != rom[i]:
            bad.append((i, v, rom[i]))
    res.append(("rom_spot_reads", not bad, f"mismatches {bad[:3]}"))

    # ROM with autoinc
    bus.wr(MEM_CTRL, 1)
    bus.wr(MEM_ADDR, 100)
    got = [bus.rd(ROM_DATA) for _ in range(8)]
    exp = rom[100:108]
    ai = bus.rd(MEM_ADDR)
    res.append(("rom_autoinc", got == exp and ai == 108, f"got {got[:2]} addr {ai}"))
    bus.wr(MEM_CTRL, 0)

    # RAM initial values
    bad = []
    for i in (0, 1, 1023):
        bus.wr(MEM_ADDR, i)
        v = bus.rd(RAM_DATA)
        if v != 0xC0DE0000 + i:
            bad.append((i, v))
    res.append(("ram_init", not bad, f"bad {bad}"))

    # RAM write/read back
    bus.wr(MEM_ADDR, 5)
    bus.wr(RAM_DATA, 0xA5A55A5A)
    v = bus.rd(RAM_DATA)
    res.append(("ram_rw", v == 0xA5A55A5A, f"read 0x{v:08X}"))
    bus.wr(MEM_ADDR, 5)
    bus.wr(RAM_DATA, 0xC0DE0005)

    # clean march run
    bus.wr(MARCH_PASSES, 2)
    bus.wr(MARCH_CTRL, 1)
    st = _wait_done(bus)
    errs = bus.rd(MARCH_ERRS)
    first = bus.rd(MARCH_FIRST)
    res.append(("march_clean", (st & 3) == 2 and (st >> 16) == 2 and errs == 0
                and first == 0xFFFFFFFF,
                f"status 0x{st:08X} errs {errs} first 0x{first:08X}"))
    bus.wr(MEM_ADDR, 700)
    v = bus.rd(RAM_DATA)
    res.append(("ram_zero_after_march", v == 0, f"ram[700]=0x{v:08X}"))

    # injected fault
    bus.wr(MARCH_PASSES, 3)
    bus.wr(MARCH_CTRL, 2)
    bus.wr(MARCH_CTRL, 3)
    st = _wait_done(bus)
    errs = bus.rd(MARCH_ERRS)
    first = bus.rd(MARCH_FIRST)
    res.append(("march_inject", (st & 3) == 2 and errs > 0 and first == 0,
                f"status 0x{st:08X} errs {errs} first 0x{first:08X}"))

    # leave at reset values
    bus.wr(MARCH_CTRL, 0)
    bus.wr(MARCH_PASSES, 1)
    bus.wr(MEM_ADDR, 0)
    bus.wr(MEM_CTRL, 0)
    return res
