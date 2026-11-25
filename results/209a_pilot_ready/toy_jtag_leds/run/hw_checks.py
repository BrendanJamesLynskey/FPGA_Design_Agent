"""Bring-up checks for jtag_blink over the JTAG register bus."""
from flow.host_transport import MockBus

DESIGN_ID = 0x20920001

A_DIV = 0x10
A_CTRL = 0x14
DIV_RESET = 12500000


class _Mock(MockBus):
    def __init__(self):
        super().__init__()
        self.ID = DESIGN_ID
        self.div = DIV_RESET
        self.en = 0

    def read(self, addr):
        if addr == A_DIV:
            return self.div
        if addr == A_CTRL:
            return self.en
        return super().read(addr)

    def write(self, addr, value):
        value &= 0xFFFFFFFF
        if addr == A_DIV:
            self.div = value if value else 1
        elif addr == A_CTRL:
            self.en = value & 1
        else:
            super().write(addr, value)


def make_mock():
    return _Mock()


def run(bus):
    res = []

    def chk(name, got, exp):
        res.append((name, got == exp, "got 0x%08x expected 0x%08x" % (got, exp)))

    chk("BLINK_DIV reset", bus.rd(A_DIV), DIV_RESET)
    chk("CTRL reset", bus.rd(A_CTRL), 0)
    bus.wr(A_DIV, 0)
    chk("BLINK_DIV write 0 reads 1", bus.rd(A_DIV), 1)
    bus.wr(A_DIV, 0x12345678)
    chk("BLINK_DIV readback", bus.rd(A_DIV), 0x12345678)
    bus.wr(A_CTRL, 0xFFFFFFFF)
    chk("CTRL bits 31:1 read 0", bus.rd(A_CTRL), 1)
    bus.wr(A_CTRL, 0)
    chk("CTRL clear", bus.rd(A_CTRL), 0)
    chk("unmapped 0x00C reads 0", bus.rd(0x00C), 0)
    chk("unmapped 0x018 reads 0", bus.rd(0x018), 0)
    bus.wr(0x018, 0xFFFFFFFF)
    chk("unmapped write ignored", bus.rd(0x018), 0)
    # restore reset values
    bus.wr(A_DIV, DIV_RESET)
    chk("BLINK_DIV restored", bus.rd(A_DIV), DIV_RESET)
    return res
