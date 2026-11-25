"""Bring-up checks for p1_freq_meter over the JTAG register bus."""
import time

from flow.host_transport import MockBus

DESIGN_ID = 0x20910001

GATE_LEN_RESET = 156250000
GATE_SHORT = 156250          # 1 ms of clk_ref
EXPECT_SHORT = 25000         # C3 edges in 1 ms


class _Mock(MockBus):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for n in ("id", "ID", "design_id", "DESIGN_ID"):
            try:
                setattr(self, n, DESIGN_ID)
            except Exception:
                pass
        self._reset_regs()

    def _reset_regs(self):
        self.gate_len = GATE_LEN_RESET
        self.led_en = 0
        self.done = 0
        self.count = 0
        self.gate_actual = 0
        self.meas_done = 0

    def read(self, addr):
        if addr == 0x00:
            return DESIGN_ID
        if addr == 0x10:
            return self.gate_len
        if addr == 0x14:
            return self.led_en << 1
        if addr == 0x18:
            return self.done << 1
        if addr == 0x1C:
            return self.count
        if addr == 0x20:
            return self.gate_actual
        if addr == 0x24:
            return self.meas_done
        return super().read(addr)

    def write(self, addr, value):
        value &= 0xFFFFFFFF
        if addr == 0x10:
            self.gate_len = value
        elif addr == 0x14:
            self.led_en = (value >> 1) & 1
            if value & 1:
                g = max(self.gate_len, 1000)
                self.gate_actual = g
                self.count = round(g * 25 / 156.25)
                self.meas_done = (self.meas_done + 1) & 0xFFFFFFFF
                self.done = 1
        else:
            super().write(addr, value)


CAPTURES = []  # no ILA build on this board: nothing to capture


def restore(sh):
    """Return the design to its reset values over a bus/shell object."""
    wr = getattr(sh, "wr", None) or getattr(sh, "write")
    wr(0x14, 0)
    wr(0x10, GATE_LEN_RESET)
    wr(0x08, 0)


def make_mock():
    return _Mock()


def _measure(bus, gate):
    bus.wr(0x10, gate)
    bus.wr(0x14, 1)
    t0 = time.time()
    st = 0
    while time.time() - t0 < 2.0:
        st = bus.rd(0x18)
        if st & 2:
            break
    return st


def run(bus):
    res = []
    rd, wr = bus.rd, bus.wr

    v = rd(0x10)
    res.append(("gate_len_reset", v == GATE_LEN_RESET, f"read {v}"))
    v = rd(0x14)
    res.append(("ctrl_reset", v == 0, f"read {v:#x}"))
    v = rd(0x18)
    res.append(("status_idle", (v & 1) == 0, f"read {v:#x}"))

    m0 = rd(0x24)
    st = _measure(bus, GATE_SHORT)
    res.append(("done_set", bool(st & 2) and not (st & 1), f"status {st:#x}"))
    cnt = rd(0x1C)
    ga = rd(0x20)
    m1 = rd(0x24)
    res.append(("gate_actual", ga == GATE_SHORT, f"{ga} vs {GATE_SHORT}"))
    res.append(("count", abs(cnt - EXPECT_SHORT) <= EXPECT_SHORT // 10000 + 1,
                f"{cnt} vs {EXPECT_SHORT} (+-3)" if False else f"{cnt} vs {EXPECT_SHORT}"))
    res.append(("meas_done_inc", ((m1 - m0) & 0xFFFFFFFF) == 1, f"{m0} -> {m1}"))

    # clamp below minimum
    st = _measure(bus, 10)
    ga = rd(0x20)
    res.append(("gate_clamp", bool(st & 2) and ga == 1000, f"gate_actual {ga}"))

    # LED_EN bit readback, then restore reset values
    wr(0x14, 2)
    v = rd(0x14)
    res.append(("led_en_rw", v == 2, f"read {v:#x}"))
    wr(0x14, 0)
    wr(0x10, GATE_LEN_RESET)
    wr(0x08, 0)
    v = rd(0x10)
    res.append(("restored", v == GATE_LEN_RESET and rd(0x14) == 0, f"gate_len {v}"))
    return res
