"""State and transition bins for a cocotb bench (brief 24): the Python fallback when a simulator has no FSM coverage.

    from flow.fsm_cov_cocotb import start_fsm_coverage
    ...
    start_fsm_coverage(dut.clk, dut.g.dut.st, "ctl", {"IDLE": 0, "LOAD": 1, ...}, [("IDLE", "LOAD"), ...])   # in every test

It samples the state register on every rising clock edge and feeds cocotb-coverage points ``top.fsm_<name>.states`` (one bin per
state) and ``top.fsm_<name>.transitions`` (one bin ``A->B`` per legal transition), so the existing V3 functional-bin gate counts
them (name them in the testplan's ``bins:``). A change that is not in ``transitions`` goes into ``unexpected`` (a list on the
returned object) for the bench to assert on. ``flow/fsm_coverage.py`` is the trace-based check of the same thing; this one needs no
VCD or $fopen, only cocotb-coverage, and works in every simulator cocotb runs in.
"""

from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge
from cocotb_coverage.coverage import CoverPoint


class FsmSampler:
    def __init__(self, name: str, states: dict[str, int], transitions: list[tuple[str, str]], reset_state: str | None = None) -> None:
        self.by_val = {v: n for n, v in states.items()}
        self.legal = {(a, b) for a, b in transitions}
        self.reset_state = reset_state
        self.unexpected: list[str] = []
        self.prev: str | None = None

        @CoverPoint(f"top.fsm_{name}.states", xf=lambda s, t: s, bins=list(states))
        @CoverPoint(f"top.fsm_{name}.transitions", xf=lambda s, t: t, bins=[f"{a}->{b}" for a, b in transitions])
        def _sample(s: str, t: str) -> None:
            pass

        self._sample = _sample

    def step(self, value: int) -> None:
        s = self.by_val.get(value)
        if s is None:
            return
        t = ""
        if self.prev is not None and s != self.prev:
            t = f"{self.prev}->{s}"
            if (self.prev, s) not in self.legal and s != self.reset_state:
                self.unexpected.append(t)
        self._sample(s, t)
        self.prev = s


def start_fsm_coverage(clk, state, name: str, states: dict[str, int], transitions: list[tuple[str, str]],
                       reset_state: str | None = None) -> FsmSampler:
    """Start sampling ``state`` (a cocotb handle) on every rising edge of ``clk``. Call it in EVERY test: cocotb ends a test's tasks with the test, and the coverage database is shared by all of them."""
    sampler = FsmSampler(name, states, transitions, reset_state)

    async def run() -> None:
        while True:
            await RisingEdge(clk)
            try:
                sampler.step(int(state.value))
            except ValueError:                       # x or z before reset
                pass

    cocotb.start_soon(run())
    return sampler
