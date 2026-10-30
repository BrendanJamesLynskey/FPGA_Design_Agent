"""cocotb tests of T1 (the board top, through the test shell) against model.py.

Run by test_t1_rtl.py with shrunk time constants (spec.yaml allows it):
CLKS_PER_BIT 8, TIMEOUT_CYCLES 400, DEBOUNCE_CYCLES 20, PWM_PRESCALE 4,
REFRESH_BITS 3. Every register value the RTL returns is compared with the
shell model wrapped round the T1 model, byte for byte.
"""

from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

from designs.t1_dimmer_counter import model as m
from shell.host import protocol as p
from shell.model.shell_model import ShellModel
from shell.tests.uart_bfm import UartBfm

BUTTONS = ("BTNU", "BTND", "BTNC")


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.cpb = int(dut.CLKS_PER_BIT.value)
        self.n = int(dut.DEBOUNCE_CYCLES.value)
        self.t1 = m.DimmerCounterModel(DEBOUNCE_CYCLES=self.n, PWM_PRESCALE=int(dut.PWM_PRESCALE.value),
                                       REFRESH_BITS=int(dut.REFRESH_BITS.value))
        self.shell = ShellModel(m.DESIGN_ID, 0, self.t1)
        self.bfm = UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, self.cpb)

    async def start(self) -> None:
        d = self.dut
        cocotb.start_soon(Clock(d.CLK100MHZ, 10, "ns").start())
        for b in BUTTONS:
            getattr(d, b).value = 0
        d.SW.value = 0
        d.CPU_RESETN.value = 0
        await ClockCycles(d.CLK100MHZ, 5)
        d.CPU_RESETN.value = 1
        await ClockCycles(d.CLK100MHZ, 5)

    async def access(self, cmd: int, addr: int, data: int = 0) -> int:
        req = p.encode_request(cmd, addr, data)
        got = await self.bfm.transact(req)
        want = self.shell.feed(req)
        assert got == want, f"{req.hex(' ')}: RTL {got.hex(' ')} model {want.hex(' ')}"
        return p.decode_response(got).data

    async def read(self, off: int) -> int:
        return await self.access(p.CMD_READ, p.WINDOW_BASE + off)

    async def write(self, off: int, v: int) -> None:
        await self.access(p.CMD_WRITE, p.WINDOW_BASE + off, v)

    async def drive_trace(self, button: str, trace: list[int]) -> None:
        pin = getattr(self.dut, button)
        for x in trace:
            pin.value = x
            await RisingEdge(self.dut.CLK100MHZ)

    async def clean_press(self, button: str) -> None:
        await self.drive_trace(button, [1] * (self.n + 4) + [0] * (self.n + 4))
        self.t1.press(**{dict(zip(BUTTONS, ("up", "down", "clear")))[button]: True})

    async def set_switches(self, v: int) -> None:
        self.dut.SW.value = v
        await ClockCycles(self.dut.CLK100MHZ, 4)
        self.t1.set_switches(v)


@cocotb.test()
async def identity_and_reset_values(dut):
    e = Env(dut)
    await e.start()
    assert await e.access(p.CMD_READ, p.REG_DESIGN_ID) == 0x5431_4443          # "T1DC"
    for off in (m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x05, 0x7F):
        await e.read(off)
    assert await e.read(m.DUTY) == 0x40 and await e.read(m.CTRL) == 0x2


@cocotb.test()
async def debounce_boundary_is_exact(dut):
    """A level held for DEBOUNCE_CYCLES - 1 clocks is ignored; DEBOUNCE_CYCLES clocks is a press."""
    e = Env(dut)
    await e.start()
    n = e.n
    await e.drive_trace("BTNU", [1] * (n - 1) + [0] * (n + 4))
    assert await e.read(m.PRESSES) == 0
    await e.drive_trace("BTNU", [1] * n + [0] * (n + 4))
    e.t1.press(up=True)
    assert await e.read(m.PRESSES) == 1 and await e.read(m.COUNT) == 1


@cocotb.test()
async def bouncy_buttons_match_the_model(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    n = e.n
    total = 0
    for _ in range(30):
        b = rng.choice(BUTTONS)
        trace: list[int] = []
        for _ in range(rng.randint(1, 8)):          # bounce: runs around the debounce time
            trace += [rng.randint(0, 1)] * rng.randint(1, n + 6)
        trace += [0] * (n + 4)                       # always end released
        await e.drive_trace(b, trace)
        k = m.presses_in(trace, n)
        total += k
        for _ in range(k):
            e.t1.press(**{dict(zip(BUTTONS, ("up", "down", "clear")))[b]: True})
        await e.read(m.PRESSES)
        await e.read(m.COUNT)
    assert 5 < total < 60, total   # the random bounces must exercise both outcomes
    dut._log.info("30 bouncy sequences, %d presses predicted and seen", total)


@cocotb.test()
async def count_wraps_both_ways(dut):
    e = Env(dut)
    await e.start()
    await e.write(m.COUNT, 0xFFFF)
    await e.clean_press("BTNU")
    assert await e.read(m.COUNT) == 0
    await e.clean_press("BTND")
    assert await e.read(m.COUNT) == 0xFFFF
    await e.clean_press("BTNC")
    assert await e.read(m.COUNT) == 0


@cocotb.test()
async def inputs_register_shows_levels(dut):
    e = Env(dut)
    await e.start()
    await e.set_switches(0xA5C3)
    e.dut.BTND.value = 1
    await ClockCycles(e.dut.CLK100MHZ, e.n + 4)
    e.t1.btn[1] = 1
    e.t1.press(down=True)
    assert await e.read(m.INPUTS) == 0xA5C3 | 1 << 17
    e.dut.BTND.value = 0
    await ClockCycles(e.dut.CLK100MHZ, e.n + 4)
    e.t1.btn[1] = 0
    await e.read(m.INPUTS)


async def led_on_clocks(e: Env) -> list[int]:
    period = e.t1.pwm_period_clocks
    on = [0] * 16
    for _ in range(period):
        await RisingEdge(e.dut.CLK100MHZ)
        v = int(e.dut.LED.value)
        for i in range(16):
            on[i] += (v >> i) & 1
    return on


@cocotb.test()
async def pwm_on_time_matches_duty(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED) + 1)
    await e.write(m.COUNT, 0xB5A1)
    for duty in [0x00, 0x01, 0x40, 0x80, 0xFE, 0xFF] + [rng.randrange(256) for _ in range(4)]:
        await e.write(m.DUTY, duty)
        await ClockCycles(dut.CLK100MHZ, 4)
        assert await led_on_clocks(e) == e.t1.led_on_clocks(), f"duty 0x{duty:02X}"
    # brightness from the switches
    await e.write(m.CTRL, m.CTRL_DUTY_SRC | m.CTRL_DISPLAY_EN)
    for sw in (0x0000, 0xFF20, 0x00C0):
        await e.set_switches(sw)
        assert await led_on_clocks(e) == e.t1.led_on_clocks(), f"switches 0x{sw:04X}"


async def scan(e: Env, frames: int = 2) -> tuple[dict[int, set[int]], list[int]]:
    """Digits seen lit (with their segment patterns) and the run lengths of the AN bus."""
    seen: dict[int, set[int]] = {}
    runs: list[int] = []
    last, run = None, 0
    for _ in range(frames * 8 * e.t1.digit_clocks()):
        await RisingEdge(e.dut.CLK100MHZ)
        an = int(e.dut.AN.value)
        seg = int(e.dut.CG.value) << 6 | int(e.dut.CF.value) << 5 | int(e.dut.CE.value) << 4 | \
            int(e.dut.CD.value) << 3 | int(e.dut.CC.value) << 2 | int(e.dut.CB.value) << 1 | int(e.dut.CA.value)
        assert int(e.dut.DP.value) == 1
        low = [k for k in range(8) if not (an >> k) & 1]
        assert len(low) <= 1, f"two digits lit at once: AN={an:08b}"
        if low:
            seen.setdefault(low[0], set()).add(seg)
        if an == last:
            run += 1
        else:
            if last is not None:
                runs.append(run)
            last, run = an, 1
    return seen, runs[1:]   # the first run is cut by where sampling started


@cocotb.test()
async def display_shows_count_and_duty(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED) + 2)
    dc = e.t1.digit_clocks()
    # every glyph at least once (directed), then random values
    cases = [(0x3210, 0x54), (0x9876, 0xBA), (0xFEDC, 0x10)] + \
            [(rng.randrange(1 << 16), rng.randrange(256)) for _ in range(3)]
    for count, duty in cases:
        await e.write(m.COUNT, count)
        await e.write(m.DUTY, duty)
        seen, runs = await scan(e)
        want = e.t1.display()
        assert seen == {k: {v} for k, v in enumerate(want) if v is not None}, (seen, want)
        assert set(runs) <= {dc, 2 * dc}, sorted(set(runs))   # digits 4 and 5 make one dark slot of two
        digits = {k: m.pins_to_digit(next(iter(v))) for k, v in seen.items()}
        dut._log.info("display %s", " ".join(f"{digits.get(k, ' '):X}" if k in digits else "-" for k in range(7, -1, -1)))
    await e.write(m.CTRL, 0)
    await ClockCycles(dut.CLK100MHZ, 2)
    seen, _ = await scan(e, 1)
    assert seen == {} and e.t1.display() == [None] * 8


@cocotb.test()
async def random_operations_match_the_model(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED) + 3)
    for _ in range(60):
        op = rng.random()
        if op < 0.3:
            await e.clean_press(rng.choice(BUTTONS))
        elif op < 0.55:
            await e.write(rng.choice([m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x11]), rng.getrandbits(32))
        elif op < 0.65:
            await e.set_switches(rng.getrandbits(16))
        else:
            await e.read(rng.choice([m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x05, 0x7F]))
    for off in (m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES):
        await e.read(off)


async def clocks_until(clk, sig, limit: int) -> int:
    """Rising edges from now until ``sig`` is 1 at an edge (sampled just after the edge)."""
    for k in range(1, limit + 1):
        await RisingEdge(clk)
        await ReadOnly()
        if int(sig.value) == 1:
            return k
    raise AssertionError(f"{sig._name} never rose within {limit} clocks")


@cocotb.test()
async def register_write_and_press_on_the_same_clock(dut):
    """spec.yaml: a COUNT write and a debounced press on one clock: the write wins, the press is still counted.

    The two latencies (start of a UART write to its win_wr pulse; button edge to its press
    pulse) are measured first, then the button is pushed so both pulses land on one clock,
    which the test checks before comparing COUNT and PRESSES with the model.
    """
    e = Env(dut)
    await e.start()
    clk = dut.CLK100MHZ
    pulses = {"BTNU": dut.u_dut.p_up, "BTND": dut.u_dut.p_down, "BTNC": dut.u_dut.p_clear}
    limit = 40 * e.cpb * p.REQ_LEN

    # latency of a write: from the clock it starts to win_wr
    await RisingEdge(clk)
    task = cocotb.start_soon(e.access(p.CMD_WRITE, p.WINDOW_BASE + m.COUNT, 0x0100))
    l_wr = await clocks_until(clk, dut.win_wr, limit)
    await task
    # latency of a press: from the clock the button rises to the press pulse
    await RisingEdge(clk)
    dut.BTNU.value = 1
    l_press = await clocks_until(clk, pulses["BTNU"], 4 * e.n)
    await RisingEdge(clk)
    await e.drive_trace("BTNU", [1] * 4 + [0] * (e.n + 4))
    e.t1.press(up=True)
    assert await e.read(m.COUNT) == 0x0101
    assert l_wr > l_press, (l_wr, l_press)
    dut._log.info("write reaches win_wr after %d clocks, a press its pulse after %d", l_wr, l_press)

    for button, value in (("BTNU", 0x1234), ("BTND", 0x8000), ("BTNC", 0xBEEF)):
        hits: list[str] = []

        async def watch() -> None:
            for _ in range(l_wr + 8):
                await RisingEdge(clk)
                await ReadOnly()
                if int(dut.win_wr.value) == 1 and int(pulses[button].value) == 1:
                    hits.append(button)

        await RisingEdge(clk)
        task = cocotb.start_soon(e.access(p.CMD_WRITE, p.WINDOW_BASE + m.COUNT, value))
        watcher = cocotb.start_soon(watch())
        await ClockCycles(clk, l_wr - l_press)
        await e.drive_trace(button, [1] * (e.n + 4) + [0] * (e.n + 4))
        await task
        await watcher
        assert hits == [button], f"{button}: win_wr and the press did not land on one clock"
        e.t1.press(**{dict(zip(BUTTONS, ("up", "down", "clear")))[button]: True, "reg_write": True})
        assert await e.read(m.COUNT) == value, f"{button}: the register write must win"
        await e.read(m.PRESSES)            # compared with the model: the press is still counted
