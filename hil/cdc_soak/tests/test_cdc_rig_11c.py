"""Brief 11c: the three findings of the first board smoke runs, as simulations (sim/scenario.py: focused variants, real
clock ratios, staggered clock starts, storms).

 1. a->c start-up artefact: clk_c (the MMCM output) starts tens of microseconds after clk_a. Without the start-up gate
    (+define CDC_NO_STARTUP_GATE, the first boards' behaviour) every count-checked a->c copy records one error at epoch 0
    and it never grows; with the gate, none.
 2. C13 under reset storms: the first version (+define CDC_C13_LEGACY) re-armed its checker from a raw asynchronous bridge
    output with two flops and loses its relock budget in about one reset event in a hundred, only in the directions where
    the request is asynchronous to the destination (a->b, a->c). The simulation's metastability injection models this;
    the plain zero-delay model (the first RTL, results/11c/s2_c13_base_*.json) does not show it. The fixed version: 0.
 3. M6b/M6c: the checker compares the padded Gray bank with a correct bank captured on the same edges; a tear of two counts
    or more is an error. M6a (skew below one source period) stays 0; M6b (4 stages, about 2 ns) stays 0; M6c (24 stages,
    about 12 ns, three source periods) is caught.

The scenarios are small (a few variants, 3 copies) and take a few minutes each; the full set is in results/11c/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import os

import pytest

QUICK = os.environ.get("CDC_SIM_QUICK") == "1"

HERE = Path(__file__).resolve().parent
RIG = HERE.parent
sys.path.insert(0, str(RIG / "sim"))
import scenario  # noqa: E402

RTL = RIG / "rtl"


def errs(out: dict, variant: str) -> dict[str, list[int]]:
    """Final-epoch errors of each copy of a variant, keyed by direction (a variant has one copy a direction here)."""
    return {r["dir"]: [e["errors"] for e in r["epochs"]] for r in out["variants"][variant]}


def test_startup_artefact_and_gate() -> None:
    kw = dict(sel=["C1", "C6"], copies=3, epochs=2, c_start_ns=100_000, storm_delay_s=100_000)
    old = scenario.run("t11c_start_nogate", RTL, defines={"CDC_NO_STARTUP_GATE": 1}, **kw)
    for v in ("C1", "C6"):
        e = errs(old, v)
        assert e["a->c"] == [1, 1], (v, e)                       # one error at epoch 0, never growing
        assert e["a->b"] == [0, 0] and e["b->a"] == [0, 0], (v, e)
    new = scenario.run("t11c_start_gate", RTL, **kw)
    for v in ("C1", "C6"):
        assert all(sum(x) == 0 for x in errs(new, v).values()), (v, errs(new, v))


@pytest.mark.parametrize("hb_ps", [7687, pytest.param(15625, marks=pytest.mark.skipif(QUICK, reason="slow end only locally")),
                                   pytest.param(5102, marks=pytest.mark.skipif(QUICK, reason="fast end only locally"))])
def test_c13_storms(hb_ps: int) -> None:                      # CFGMCLK at 65 MHz, 32 MHz (slow end), 98 MHz (fast end)
    kw = dict(sel=["C13"], copies=3, epochs=6, hb_ps=hb_ps, storm_maskw=9)
    new = scenario.run(f"t11c_c13_new_{hb_ps}", RTL, **kw)
    e = errs(new, "C13")
    assert all(sum(x) == 0 for x in e.values()), e
    assert all(r["epochs"][-1]["relocks"] > 20 for r in new["variants"]["C13"]), "the storms must reach C13"
    assert all(r["epochs"][-1]["lockups"] == 0 for r in new["variants"]["C13"])


def test_c13_legacy_fails_where_the_board_failed() -> None:
    old = scenario.run("t11c_c13_legacy", RTL, defines={"CDC_C13_LEGACY": 1}, sel=["C13"], copies=3, epochs=6,
                       storm_maskw=9)
    e = errs(old, "C13")
    assert sum(e["a->b"]) + sum(e["a->c"]) >= 1, e             # the directions with an asynchronous request
    assert sum(e["b->a"]) == 0, e                              # request launched in the destination's own clock


def test_m6_tear_is_observable() -> None:
    out = scenario.run("t11c_m6", RTL, sel=["M6a", "M6b", "M6c"], copies=3, epochs=2)
    for v, want_hit in (("M6a", False), ("M6b", False), ("M6c", True)):
        last = [r["epochs"][-1]["errors"] for r in out["variants"][v]]
        assert (min(last) > 0) if want_hit else (max(last) == 0), (v, last)
