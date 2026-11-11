"""Acceptance tests of d24_registered_outputs against model.py (hidden from the agent). The pin structure (flip-flop-driven outputs) is graded
separately (../lib/grade_fsm.py, on the agent's routed build); this bench judges behaviour and latency, cycle by cycle."""

from __future__ import annotations

import os
import random

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import FallingEdge, RisingEdge
from model import ALLOWED_LAGS, BURSTS, CLEAR, DESIGN_ID, ERRS, IN_PINS, OUT_PINS, Model

SKIP = 24                      # clocks after reset ignored (the reset synchroniser)


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {p: 0 for p in IN_PINS})
        self.m = Model()
        self.sampler = None

    def pins(self) -> tuple[int, ...]:
        return tuple(int(getattr(self.dut, p).value) for p in OUT_PINS)

    async def run(self, n: int, rng: random.Random, probs=(0.5, 0.3, 0.15, 0.07, 0.4)) -> tuple[list, list]:
        """n clocks of open-loop random inputs (they do not depend on the outputs). Returns the pins and the model's outputs per clock."""
        got, want = [], []
        for _ in range(n):
            await FallingEdge(self.b.clk)
            ins = tuple(int(rng.random() < p) for p in probs)
            for p, v in zip(IN_PINS, ins):
                getattr(self.dut, p).value = v
            await RisingEdge(self.b.clk)                # the outputs just before this edge: state and inputs of this clock
            got.append(self.pins())
            want.append(self.m.step(*ins))
        return got, want


def lag_report(got: list, want: list) -> tuple[int | None, str]:
    """The allowed lag the pins follow for every output, or the first mismatch for the best lag."""
    best = None
    for lag in sorted(ALLOWED_LAGS):
        bad = [(k, i) for k in range(SKIP + lag, len(got)) for i in range(len(OUT_PINS)) if got[k][i] != want[k - lag][i]]
        if not bad:
            return lag, ""
        if best is None or len(bad) < best[0]:
            k, i = bad[0]
            best = (len(bad), f"lag {lag}: {len(bad)} mismatches, first at clock {k} on {OUT_PINS[i]} (pins {got[k]}, model {want[k - lag]})")
    return None, best[1]


def start_sampler(env: Env) -> None:
    """On the reference design only (it has dut.u_core.st): sample the state register so the bench can show that it reaches every state
    and legal transition (brief 24). A design without that signal is judged on behaviour alone."""
    try:
        from flow.fsm_cov_cocotb import start_fsm_coverage
        st = env.dut.u_core.st
    except (AttributeError, ImportError):
        return
    names = "IDLE LOAD REQ ADDR DATA TURN WACK RETRY RESP ERR COOL".split()
    T = [("IDLE", "LOAD"), ("LOAD", "REQ"), ("REQ", "ADDR"), ("ADDR", "DATA"), ("DATA", "TURN"), ("TURN", "WACK"), ("WACK", "RESP"),
         ("WACK", "RETRY"), ("WACK", "ERR"), ("RETRY", "REQ"), ("RESP", "COOL"), ("ERR", "COOL"), ("COOL", "IDLE")]
    env.sampler = start_fsm_coverage(env.b.clk, st, "burst", {n: i for i, n in enumerate(names)}, T, "IDLE")


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off, what in ((BURSTS, "BURSTS"), (ERRS, "ERRS"), (CLEAR, "CLEAR"), (0x03, "unmapped 0x03"), (0x7F, "unmapped 0x7F")):
        await e.b.expect(off, 0, f"{what} at reset")
    await FallingEdge(e.b.clk)
    assert e.pins() == (0, 0, 0, 0, 0, 0, 1, 0), f"idle pins after reset: {e.pins()} (req addr_v valid last rsp_valid rsp_err cmd_ready cmd_ack)"


@cocotb.test()
async def test_cycle_exact_against_the_model(dut):
    e = Env(dut)
    await e.b.start()
    start_sampler(e)
    rng = random.Random(int(cocotb.RANDOM_SEED))
    got, want = await e.run(6000, rng)
    lag, why = lag_report(got, want)
    if os.environ.get("FDA_DRILL_LAG_FILE"):                  # the grader (lib/grade_fsm.py) reads the lag the pins follow
        open(os.environ["FDA_DRILL_LAG_FILE"], "w").write(str(lag))
    assert lag is not None, "the pins do not follow the state table with an allowed lag " + str(sorted(ALLOWED_LAGS)) + ": " + why
    # every output pattern was exercised, so the comparison means something
    assert {g[2] for g in got} == {0, 1} and {g[5] for g in got} == {0, 1} and {g[3] for g in got} == {0, 1}
    # stop the stimulus, let the machine run on with zeros, and compare the counters
    for _ in range(40):
        await FallingEdge(e.b.clk)
        for p in IN_PINS:
            getattr(dut, p).value = 0
        await RisingEdge(e.b.clk)
        e.m.step(0, 0, 0, 0, 0)
    await e.b.expect(BURSTS, e.m.bursts, "BURSTS after the random run")
    await e.b.expect(ERRS, e.m.errs, "ERRS after the random run")
    assert e.m.bursts > 20 and e.m.errs > 3, (e.m.bursts, e.m.errs)
    if e.sampler is not None:                       # the reference only: the bench itself must reach everything
        miss = [k for k in ("top.fsm_burst.states", "top.fsm_burst.transitions")]
        from cocotb_coverage.coverage import coverage_db
        for k in miss:
            assert coverage_db[k].cover_percentage == 100, f"hidden bench misses {k}: {coverage_db[k].detailed_coverage}"
        assert not e.sampler.unexpected, e.sampler.unexpected


@cocotb.test()
async def test_clear_and_a_short_run(dut):
    e = Env(dut)
    await e.b.start()
    rng = random.Random(7)
    await e.run(400, rng, probs=(0.6, 0.5, 0.5, 0.0, 0.6))
    for _ in range(60):                                 # settle with zero inputs, then clear
        await FallingEdge(e.b.clk)
        for p in IN_PINS:
            getattr(dut, p).value = 0
        await RisingEdge(e.b.clk)
        e.m.step(0, 0, 0, 0, 0)
    assert e.m.bursts > 0
    await e.b.expect(BURSTS, e.m.bursts, "BURSTS")
    await e.b.write(CLEAR, 1)
    e.m.clear()
    await e.b.expect(BURSTS, 0, "BURSTS after CLEAR")
    await e.b.expect(ERRS, 0, "ERRS after CLEAR")
