"""Bring-up checks for fir32_sym over the JTAG register bus (and the same checks on a mock)."""
from flow.host_transport import MockBus
from model import Model

DESIGN_ID = 0x20940001

A_CTRL, A_PUSH, A_POP, A_STATUS, A_SAT, A_DONE = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24


class _Mock(MockBus):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ID = DESIGN_ID
        self.m = Model()

    def read(self, addr):
        if addr < 0x10:
            return super().read(addr)
        return self.m.read_reg(addr) & 0xFFFFFFFF

    def write(self, addr, value):
        if addr < 0x10:
            return super().write(addr, value)
        self.m.write_reg(addr, value)
        if addr == A_CTRL and self.m.busy:
            for _ in range(100000):
                if not self.m.busy:
                    break
                self.m.step()
        return None


def make_mock():
    return _Mock()


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def run(bus):
    res = []
    m = Model()
    coeffs = m.coeffs

    bus.wr(A_CTRL, 1)  # CLEAR
    st = bus.rd(A_STATUS)
    res.append(("clear_status_idle", st == 0, "STATUS=0x%08X" % st))

    # Impulse then a few steps, small enough to avoid saturation
    xs = [1000, 0, 0, 0, -2000, 12345, -32768, 32767, 5, 0, 0, 0]
    expect = [m._sample(x) for x in xs]
    for x in xs:
        bus.wr(A_PUSH, x & 0xFFFF)
    st = bus.rd(A_STATUS)
    cnt = (st >> 4) & 0xFFF
    res.append(("in_fifo_count", cnt == len(xs), "count=%d expected %d" % (cnt, len(xs))))

    bus.wr(A_CTRL, 2)  # RUN
    busy = 1
    for _ in range(2000):
        st = bus.rd(A_STATUS)
        busy = st & 1
        if not busy:
            break
    res.append(("run_completes", busy == 0, "STATUS=0x%08X" % st))
    ocnt = (st >> 20) & 0xFFF
    res.append(("out_fifo_count", ocnt == len(xs), "count=%d expected %d" % (ocnt, len(xs))))

    got = []
    for _ in xs:
        v = bus.rd(A_POP)
        got.append(v)
    ok = all((g >> 31) == 1 and (g & 0xFFFF) == e for g, e in zip(got, expect))
    res.append(("fir_outputs", ok, "got %s expected %s" % ([hex(g & 0xFFFF) for g in got],
                                                          [hex(e) for e in expect])))
    v = bus.rd(A_POP)
    res.append(("pop_empty_zero", v == 0, "0x%08X" % v))

    done = bus.rd(A_DONE)
    res.append(("samples_done", done == len(xs), "done=%d" % done))
    sat = bus.rd(A_SAT)
    res.append(("sat_count", sat == m.sat, "sat=%d expected %d" % (sat, m.sat)))

    bus.wr(A_CTRL, 1)  # leave at reset values
    done = bus.rd(A_DONE)
    sat = bus.rd(A_SAT)
    st = bus.rd(A_STATUS)
    res.append(("clear_resets", done == 0 and sat == 0 and st == 0,
                "done=%d sat=%d status=0x%X" % (done, sat, st)))
    _ = coeffs
    return res
