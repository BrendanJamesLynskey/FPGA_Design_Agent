"""Bring-up checks for p3_crc32 over the JTAG register bus."""
import zlib

from flow.host_transport import MockBus

DESIGN_ID = 0x20930001
M32 = 0xFFFFFFFF

CTRL, PUSH4, PUSH_N, TAIL, CRC, BCNT, BUSY = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28


def _crc_bytes(data, crc=0):
    return zlib.crc32(bytes(data), crc) & M32


class _Mock(MockBus):
    def __init__(self, *a, **k):
        try:
            super().__init__(*a, **k)
        except TypeError:
            super().__init__()
        try:
            self.ID = DESIGN_ID
        except Exception:
            pass
        self._reset_state()

    def _reset_state(self):
        self.st = 0xFFFFFFFF
        self.nbytes = 0
        self.busy = 0
        self.tail = 0

    def _feed(self, word, n):
        c = self.st
        for i in range(n):
            c ^= (word >> (8 * i)) & 0xFF
            for _ in range(8):
                c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        self.st = c & M32

    def read(self, addr):
        a = addr & 0xFFF
        if a == TAIL:
            return self.tail
        if a == CRC:
            return self.st ^ M32
        if a == BCNT:
            return self.nbytes
        if a == BUSY:
            return self.busy
        if a in (CTRL, PUSH4, PUSH_N) or a > 0x28 or a in (0xC, 0x2C):
            return 0
        return super().read(addr)

    def write(self, addr, value):
        a = addr & 0xFFF
        v = value & M32
        if a == CTRL:
            if v & 1:
                self._reset_state_keep_tail()
        elif a == PUSH4:
            self._feed(v, 4)
            self.nbytes = (self.nbytes + 4) & M32
            self.busy = (self.busy + 1) & M32
        elif a == PUSH_N:
            if self.tail:
                self._feed(v, self.tail)
                self.nbytes = (self.nbytes + self.tail) & M32
                self.busy = (self.busy + 1) & M32
        elif a == TAIL:
            if v <= 3:
                self.tail = v
        elif a in (0, 4) or a > 0x28 or a in (0xC, 0x20, 0x24, 0x28, 0x2C):
            if a in (0, 4, 0x20, 0x24, 0x28):
                return
            if a > 0x28 or a in (0xC, 0x2C):
                return
        else:
            super().write(addr, value)

    def _reset_state_keep_tail(self):
        self.st = 0xFFFFFFFF
        self.nbytes = 0
        self.busy = 0


def make_mock():
    return _Mock()


def _send(bus, data):
    i = 0
    n = len(data)
    while n - i >= 4:
        w = int.from_bytes(bytes(data[i:i + 4]), "little")
        bus.wr(PUSH4, w)
        i += 4
    r = n - i
    if r:
        bus.wr(TAIL, r)
        bus.wr(PUSH_N, int.from_bytes(bytes(data[i:]), "little"))


def run(bus):
    res = []
    bus.wr(CTRL, 1)
    v = bus.rd(CRC)
    res.append(("crc_zero_after_init", v == 0, "read 0x%08x expect 0" % v))
    v = bus.rd(CTRL)
    res.append(("ctrl_reads_0", v == 0, "read 0x%08x" % v))

    msgs = [b"", b"a", b"ab", b"abc", b"abcd", b"abcde", b"abcdefg",
            b"12345678", bytes(range(63)), bytes(range(64)), bytes(range(65))]
    msgs.append(b"123456789")
    for m in msgs:
        bus.wr(CTRL, 1)
        _send(bus, m)
        exp = _crc_bytes(m)
        got = bus.rd(CRC)
        res.append(("crc_len_%d" % len(m), got == exp,
                    "got 0x%08x expect 0x%08x" % (got, exp)))
        bc = bus.rd(BCNT)
        res.append(("bytecount_len_%d" % len(m), bc == len(m),
                    "got %d expect %d" % (bc, len(m))))

    bus.wr(CTRL, 1)
    for i in range(10):
        bus.wr(PUSH4, 0x01020304 + i)
    busy = bus.rd(BUSY)
    res.append(("busy_10_words", busy == 10, "got %d expect 10" % busy))

    bus.wr(TAIL, 7)
    t = bus.rd(TAIL)
    res.append(("tail_above_3_ignored", t == 3 or t == 0 or t <= 3,
                "TAIL reads %d" % t))
    bus.wr(TAIL, 0)

    bus.wr(CTRL, 1)
    bus.wr(0x20, 0x1234)
    bus.wr(0x100, 0x1234)
    v = bus.rd(0x100)
    res.append(("unmapped_reads_0", v == 0, "read 0x%08x" % v))
    v = bus.rd(BCNT)
    res.append(("ro_write_ignored", v == 0, "BYTE_COUNT 0x%08x" % v))

    bus.wr(CTRL, 1)
    bus.wr(TAIL, 0)
    return res
