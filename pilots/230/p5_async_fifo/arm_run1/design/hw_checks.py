"""Bring-up checks for p5_async_fifo_soak over the JTAG register bus."""
import time

from flow.host_transport import MockBus

DESIGN_ID = 0x20950001

CTRL, SNAP = 0x10, 0x30
CNT = {"WORDS_W": 0x14, "WORDS_R": 0x18, "DATA_ERRS": 0x1C,
       "OVERFLOWS": 0x20, "UNDERFLOWS": 0x24, "STALL_W": 0x28,
       "OCC_MAX": 0x2C}


class _Mock(MockBus):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ID = DESIGN_ID
        self.ctrl = 0
        self.live = [0] * 7
        self.snap = [0] * 7
        self.inj = 0

    def _tick(self):
        if self.ctrl & 1:
            self.live[0] += 1000
            self.live[1] += 1000
            self.live[6] = max(self.live[6], 12)
        else:
            self.live[1] = self.live[0]

    def read(self, addr):
        a = addr & 0xFFF
        if a == CTRL:
            return self.ctrl & 0x3
        if 0x14 <= a <= 0x2C and a % 4 == 0:
            return self.snap[(a - 0x14) // 4]
        return super().read(addr)

    def write(self, addr, value):
        a = addr & 0xFFF
        if a == CTRL:
            if value & 4 and not (self.ctrl & 1):
                self.live = [0] * 7
                self.inj = 0
            self.ctrl = value & 0x3
            if self.ctrl & 1:
                self._tick()
            if value & 8:
                self.live[2] += 1
            if not (self.ctrl & 1):
                self.live[1] = self.live[0]
        elif a == SNAP:
            self._tick()
            self.snap = list(self.live)
        else:
            super().write(addr, value)


CAPTURES = []


def restore(sh):
    try:
        sh.wr(CTRL, 0)
        sh.wr(CTRL, 4)
        sh.wr(CTRL, 0)
    except Exception:
        pass


def make_mock():
    return _Mock()


def _snap(bus):
    bus.wr(SNAP, 0)
    return {n: bus.rd(a) for n, a in CNT.items()}


def run(bus):
    res = []
    bus.wr(CTRL, 0)
    bus.wr(CTRL, 4)
    s = _snap(bus)
    res.append(("clear zeroes counters", all(v == 0 for v in s.values()), str(s)))
    bus.wr(CTRL, 1)
    time.sleep(0.05)
    bus.wr(CTRL, 1 | 8)
    time.sleep(0.05)
    bus.wr(CTRL, 0)
    time.sleep(0.05)
    s = _snap(bus)
    res.append(("words written", s["WORDS_W"] > 0, str(s["WORDS_W"])))
    res.append(("drained, read == written", s["WORDS_R"] == s["WORDS_W"],
                "%d vs %d" % (s["WORDS_R"], s["WORDS_W"])))
    res.append(("inject gave 1 error", s["DATA_ERRS"] == 1, str(s["DATA_ERRS"])))
    res.append(("no overflow/underflow", s["OVERFLOWS"] == 0 and s["UNDERFLOWS"] == 0,
                "%d/%d" % (s["OVERFLOWS"], s["UNDERFLOWS"])))
    res.append(("occupancy <= 512", s["OCC_MAX"] <= 512, str(s["OCC_MAX"])))
    res.append(("inject self-clears", (bus.rd(CTRL) & 8) == 0, hex(bus.rd(CTRL))))
    bus.wr(CTRL, 4)
    s = _snap(bus)
    res.append(("final clear", all(v == 0 for v in s.values()), str(s)))
    bus.wr(CTRL, 0)
    res.append(("unmapped reads 0", bus.rd(0x100) == 0, ""))
    return res
