"""Bring-up checks for p1_freq_meter over the JTAG register bus."""
from flow.host_transport import MockBus
import model

DESIGN_ID = 0x20910001

R_GL, R_CTRL, R_ST, R_CNT, R_GA, R_MD = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
GATE_DEFAULT = 156250000
SHORT_GATE = 1562500  # 10 ms of ref_clk
M32 = 0xFFFFFFFF


class _Mock(MockBus):
    def __init__(self):
        super().__init__()
        self.ID = DESIGN_ID
        self.gate_len = GATE_DEFAULT
        self.led_en = 0
        self.busy = 0
        self.done = 0
        self.count = 0
        self.gate_actual = 0
        self.meas_done = 0
        self.polls = 0

    def read(self, addr):
        if addr == R_GL:
            return self.gate_len
        if addr == R_CTRL:
            return self.led_en << 1
        if addr == R_ST:
            if self.busy:  # finishes after one poll
                self.busy = 0
                self.done = 1
                self.meas_done = (self.meas_done + 1) & M32
            return self.busy | (self.done << 1)
        if addr == R_CNT:
            return self.count
        if addr == R_GA:
            return self.gate_actual
        if addr == R_MD:
            return self.meas_done
        return None if False else 0

    def write(self, addr, value):
        value &= M32
        if addr == R_GL:
            self.gate_len = value
        elif addr == R_CTRL:
            self.led_en = (value >> 1) & 1
            if (value & 1) and not self.busy:
                self.done = 0
                self.busy = 1
                g = max(self.gate_len, 1000)
                self.gate_actual = g
                self.count = (g * 4 + 12) // 25


def make_mock():
    return _Mock()


def _measure(bus, gate):
    bus.wr(R_GL, gate)
    bus.wr(R_CTRL, 1)
    st = 0
    for _ in range(200):
        st = bus.rd(R_ST)
        if st & 2:
            break
    return st


def run(bus):
    res = []
    res.append(("GATE_LEN reset", bus.rd(R_GL) == GATE_DEFAULT,
                f"{bus.rd(R_GL)}"))
    c = bus.rd(R_CTRL)
    res.append(("LED_EN reset 0, START reads 0", c == 0, f"CTRL={c:#x}"))
    md0 = bus.rd(R_MD)

    st = _measure(bus, SHORT_GATE)
    res.append(("measurement done", bool(st & 2) and not st & 1, f"STATUS={st:#x}"))
    ga = bus.rd(R_GA)
    res.append(("GATE_ACTUAL exact", ga == SHORT_GATE, f"{ga} vs {SHORT_GATE}"))
    cnt = bus.rd(R_CNT)
    exp = SHORT_GATE * 4 / 25
    res.append(("COUNT within 100 ppm", abs(cnt - exp) <= max(2, exp * 1e-4),
                f"{cnt} vs {exp:.1f}"))
    md = bus.rd(R_MD)
    res.append(("MEAS_DONE +1", md == (md0 + 1) & M32, f"{md0} -> {md}"))

    # gate below minimum is clamped to 1000
    _measure(bus, 10)
    ga = bus.rd(R_GA)
    res.append(("GATE_LEN clamp", ga == 1000, f"GATE_ACTUAL={ga}"))

    # leave reset values
    bus.wr(R_GL, GATE_DEFAULT)
    bus.wr(R_CTRL, 0)
    res.append(("restored", bus.rd(R_GL) == GATE_DEFAULT and bus.rd(R_CTRL) == 0, ""))
    return res
