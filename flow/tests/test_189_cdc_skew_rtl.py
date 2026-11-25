"""Brief 189 item 8 (idea from Edwards 2026, ch 12): a per-bit skew injected into the synchronisers, and a torn-pointer mutant.

cdcfx_m12 is the C10 asynchronous FIFO with its pointers crossed in binary. A zero-delay simulation passes it. With a per-bit skew
of up to four destination cycles (FDA_CDC_INJECT_SKEW=4, flow/cdc_models/cdc_inj_pkg.sv) its own test fails, while the Gray-pointer
FIFO (C10) passes under the same skew, because only one Gray bit changes at a time and a skewed single bit is the old or the new
value. Advisory: nothing here is a gate (enforced: false in results/189_verification_rules/cdc_skew.json)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

FX = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FX / "cdc_mutants"))
SRC = {"cdcfx_m12": FX / "cdc_pointer" / "rtl" / "cdcfx_m12.sv", "cdcfx_c10": FX / "cdc_mutants" / "rtl" / "cdcfx_c10.sv"}
SKEW = 4
SEEDS = (1, 2, 3)


def _run(name: str, seed: int, skew: int | None, root: Path) -> bool:
    """True when the fixture's own test passes."""
    from flow import cocotb_run
    os.environ["CDCFX_NAME"] = name
    for k, v in (("FDA_CDC_INJECT_SEED", seed or None), ("FDA_CDC_INJECT_SKEW", skew)):
        if v:
            os.environ[k] = str(v)
        else:
            os.environ.pop(k, None)
    try:
        cocotb_run.run(f"{name}_s{seed}_k{skew}", name, [SRC[name]], "cdcfx_tb", FX / "cdc_mutants" / "tb", seed=1, build_root=root)
        return True
    except AssertionError:
        return False
    finally:
        os.environ.pop("FDA_CDC_INJECT_SEED", None)
        os.environ.pop("FDA_CDC_INJECT_SKEW", None)


def test_binary_pointer_fifo_passes_a_plain_simulation(tmp_path: Path) -> None:
    assert _run("cdcfx_m12", 0, None, tmp_path)


@pytest.mark.parametrize("seed", SEEDS)
def test_binary_pointer_fifo_fails_under_per_bit_skew(seed: int, tmp_path: Path) -> None:
    assert not _run("cdcfx_m12", seed, SKEW, tmp_path)


@pytest.mark.parametrize("seed", SEEDS)
def test_gray_pointer_fifo_passes_under_the_same_skew(seed: int, tmp_path: Path) -> None:
    assert _run("cdcfx_c10", seed, SKEW, tmp_path)


def test_skew_one_is_the_old_model() -> None:
    """The default (no skew, or 1) adds no plusarg: results of every earlier injected run are unchanged."""
    from flow import cdc_inject
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        _, p1, _ = cdc_inject.prepare([SRC["cdcfx_c10"]], Path(d), 5)
        _, p1b, _ = cdc_inject.prepare([SRC["cdcfx_c10"]], Path(d), 5, skew=1)
        _, p4, i4 = cdc_inject.prepare([SRC["cdcfx_c10"]], Path(d), 5, skew=4)
    assert p1 == p1b == ["+CDC_INJ_SEED=5"]
    assert p4 == ["+CDC_INJ_SEED=5", "+CDC_INJ_SKEW=4"] and i4["skew"] == 4
