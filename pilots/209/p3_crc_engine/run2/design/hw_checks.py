"""Bring-up checks for the CRC-32 engine over the JTAG register bus."""
import random
import zlib

from flow.host_transport import MockBus
from model import Model

DESIGN_ID = 0x20930001

CTRL, PUSH4, PUSH_N, TAIL, CRC, BCNT, BUSY = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28


class _Mock(MockBus):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.m = Model()
        self.ID = DESIGN_ID

    def read(self, addr):
        if addr < 0x10:
            return super().read(addr)
        return self.m.read_reg(addr & 0xFFF)

    def write(self, addr, value):
        if addr < 0x10:
            return super().write(addr, value)
        return self.m.write_reg(addr & 0xFFF, value)


def make_mock():
    return _Mock()


def _push(bus, data):
    i = 0
    while i + 4 <= len(data):
        bus.wr(PUSH4, int.from_bytes(data[i:i + 4], "little"))
        i += 4
    n = len(data) - i
    if n:
        bus.wr(TAIL, n)
        bus.wr(PUSH_N, int.from_bytes(data[i:], "little"))
        bus.wr(TAIL, 0)


def run(bus):
    res = []
    rng = random.Random(7)
    bus.wr(CTRL, 1)
    v = bus.rd(CRC)
    res.append(("empty_crc", v == 0, hex(v)))
    res.append(("ctrl_self_clear", bus.rd(CTRL) == 0, hex(bus.rd(CTRL))))
    bus.wr(PUSH4, 0x34333231)
    bus.wr(PUSH4, 0x38373635)
    exp = zlib.crc32(b"12345678")
    v = bus.rd(CRC)
    res.append(("crc_8_bytes", v == exp, f"{v:#x} exp {exp:#x}"))
    b = bus.rd(BCNT)
    res.append(("byte_count_8", b == 8, str(b)))
    y = bus.rd(BUSY)
    res.append(("busy_2", y == 2, str(y)))
    bad = []
    for ln in (0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65, 200):
        data = bytes(rng.randrange(256) for _ in range(ln))
        bus.wr(CTRL, 1)
        _push(bus, data)
        c, n = bus.rd(CRC), bus.rd(BCNT)
        if c != zlib.crc32(data) or n != ln:
            bad.append(f"len {ln}: crc {c:#x} cnt {n}")
    res.append(("random_messages", not bad, "; ".join(bad) or "12 lengths ok"))
    bus.wr(TAIL, 7)
    t = bus.rd(TAIL)
    res.append(("tail_len_mask", t == 3, str(t)))
    bus.wr(TAIL, 0)
    bus.wr(CTRL, 1)
    ok = (bus.rd(CRC), bus.rd(BCNT), bus.rd(BUSY)) == (0, 0, 0)
    res.append(("reset_values", ok, "CRC/BYTE_COUNT/BUSY_CYCLES after INIT"))
    return res
