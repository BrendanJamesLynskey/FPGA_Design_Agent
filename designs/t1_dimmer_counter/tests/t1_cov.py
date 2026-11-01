"""T1's functional coverage (cocotb-coverage, BSD): the bins named in verif/testplan.yaml under `covers`.

Sampling is called from the bench (Env.access, Env.drive_trace) and from a monitor that watches the RTL's
debounced-press and register-write pulses. The coverage database lives in the simulator process, so the last
test of a run (t1_verif.zz_dump_coverage) writes it to $T1_COV_OUT; flow/verif_gates.py merges the files of
every seed. Bins are hit-counts; nothing here is a score by itself.
"""

from __future__ import annotations

import os
from pathlib import Path

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge, First
from cocotb_coverage.coverage import CoverCross, CoverPoint, coverage_db, coverage_section

BTN = ("up", "down", "clear")
KINDS = ("clean", "glitch", "bounce")
COUNT_CLASS = ("zero", "max", "mid")
REGS = ("COUNT", "DUTY", "CTRL", "INPUTS", "PRESSES", "unmapped")
DIRS = ("read", "write")
DUTY_CLASS = ("zero", "low", "mid", "high", "full")
SRC = ("register", "switches")


def _cls(v: int) -> str:
    return "zero" if v == 0 else "max" if v == 0xFFFF else "mid"


def _duty_cls(v: int) -> str:
    return "zero" if v == 0 else "full" if v == 255 else "low" if v < 64 else "high" if v >= 192 else "mid"


@coverage_section(
    CoverPoint("t1.press.button", xf=lambda b, k: b, bins=list(BTN)),
    CoverPoint("t1.press.kind", xf=lambda b, k: k, bins=list(KINDS)),
    CoverCross("t1.press.button_x_kind", items=["t1.press.button", "t1.press.kind"]))
def sample_trace(button: str, kind: str) -> None:
    pass


@coverage_section(
    CoverPoint("t1.op.kind", xf=lambda op, c: op, bins=list(BTN)),
    CoverPoint("t1.op.count", xf=lambda op, c: _cls(c), bins=list(COUNT_CLASS)),
    CoverCross("t1.op.kind_x_count", items=["t1.op.kind", "t1.op.count"]))
def sample_press(op: str, count: int) -> None:
    pass


@coverage_section(CoverPoint("t1.clock.mix", xf=lambda m: m, bins=["single", "multi", "press_with_write"]))
def sample_mix(mix: str) -> None:
    pass


@coverage_section(
    CoverPoint("t1.reg.name", xf=lambda r, d: r, bins=list(REGS)),
    CoverPoint("t1.reg.dir", xf=lambda r, d: d, bins=list(DIRS)),
    CoverCross("t1.reg.name_x_dir", items=["t1.reg.name", "t1.reg.dir"]))
def sample_reg(reg: str, direction: str) -> None:
    pass


@coverage_section(
    CoverPoint("t1.duty.class", xf=lambda d, s: _duty_cls(d), bins=list(DUTY_CLASS)),
    CoverPoint("t1.duty.source", xf=lambda d, s: s, bins=list(SRC)),
    CoverCross("t1.duty.class_x_source", items=["t1.duty.class", "t1.duty.source"]))
def sample_duty(duty_eff: int, source: str) -> None:
    pass


@coverage_section(CoverPoint("t1.display.enable", xf=lambda e: e, bins=[0, 1]))
def sample_display(en: int) -> None:
    pass


@coverage_section(CoverPoint("t1.display.glyph", xf=lambda n: n, bins=list(range(16))))
def sample_glyph(nibble: int) -> None:
    pass


def classify(trace: list[int], n: int) -> str:
    """clean = one run of 1s of at least n clocks; glitch = only runs shorter than n; bounce = both."""
    runs, cur = [], 0
    for x in trace + [0]:
        if x:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if not runs:
        return ""
    long_, short = [r for r in runs if r >= n], [r for r in runs if r < n]
    return "clean" if long_ and not short else "glitch" if short and not long_ else "bounce"


def sample_model(e) -> None:
    t = e.t1
    for k in range(4):
        sample_glyph((t.count >> (4 * k)) & 0xF)
    sample_duty(t.duty_eff, "switches" if t.ctrl & 1 else "register")
    sample_display((t.ctrl >> 1) & 1)


def _reg(off: int) -> str:
    return ("COUNT", "DUTY", "CTRL", "INPUTS", "PRESSES")[off] if off <= 4 else "unmapped"


async def monitor(dut) -> None:
    """Sample on every debounced press and every register write (the RTL's own pulses; coverage only)."""
    clk, d = dut.CLK100MHZ, dut.u_dut
    while True:
        await First(RisingEdge(d.p_up), RisingEdge(d.p_down), RisingEdge(d.p_clear), RisingEdge(d.win_wr))
        await ReadOnly()
        pulses = [n for n, s in zip(BTN, (d.p_up, d.p_down, d.p_clear)) if int(s.value)]
        wr = int(d.win_wr.value) and int(d.win_addr.value) == 0
        for op in pulses:
            sample_press(op, int(d.count.value))
        if pulses or wr:
            sample_mix("press_with_write" if (pulses and wr) else "multi" if len(pulses) > 1 else "single")
        await RisingEdge(clk)


def start(dut) -> None:
    cocotb.start_soon(monitor(dut))


def dump() -> None:
    out = Path(os.environ.get("T1_COV_OUT", "coverage_t1.yml"))
    out.parent.mkdir(parents=True, exist_ok=True)
    coverage_db.export_to_yaml(str(out))
