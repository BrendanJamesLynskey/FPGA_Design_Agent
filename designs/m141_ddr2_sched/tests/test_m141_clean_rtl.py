"""ddr2_sched against the behavioural DDR2 timing model (tb/tb_ddr2.sv, Icarus Verilog 12) (brief 141).

The bench checks every command on the bus against the Micron MT47H64M16 rules, the data-bus rules, the refresh obligation and request integrity and order (its header says what, one by one).
These tests run both policies, every traffic pattern, both timing profiles and all three address maps, and require no violation, every request served once with its own bank, row, column and direction, and request order kept.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
D = HERE.parent
sys.path.insert(0, str(HERE))
import m141_measure as measure  # noqa: E402
import m141_timing as timing  # noqa: E402

RTL = D / "rtl"


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return tmp_path_factory.mktemp("m141")


def test_profile_rounding_is_the_data_sheet_ceiling():
    """The conversion from picoseconds to clocks: every value is the smallest whole number of clocks not below the data sheet value."""
    for name in timing.PROFILES:
        p = timing.params(name)
        for k, ps in timing.DS_PS.items():
            assert p[k] * p["TCK_PS"] >= ps and (p[k] - 1) * p["TCK_PS"] < ps, (name, k)
        assert p["T_REFI"] * p["TCK_PS"] <= timing.TREFI_PS < (p["T_REFI"] + 1) * p["TCK_PS"]
    assert timing.params("nexys_650")["T_RCD"] == 5 and timing.params("ddr2_800")["T_RFC"] == 51


@pytest.mark.parametrize("pol", [0, 1])
@pytest.mark.parametrize("pat,gap", [(0, 40), (1, 5), (2, 0), (3, 0), (4, 30), (5, 0)])
def test_clean_patterns(out, pol, pat, gap):
    r = measure.run(out, "nexys_650", pol, pat, gap, 250)
    assert r["pass"] and r["violations"] == 0 and r["hazards"] == 0 and r["badreq"] == 0, r


@pytest.mark.parametrize("pol", [0, 1])
def test_clean_other_profile(out, pol):
    r = measure.run(out, "ddr2_800", pol, 1, 5, 250)
    assert r["pass"] and r["violations"] == 0, r


@pytest.mark.parametrize("mp", [1, 2])
def test_clean_address_maps(out, mp):
    for pol in (0, 1):
        r = measure.run(out, "nexys_650", pol, 3, 0, 250, mp=mp)
        assert r["pass"] and r["violations"] == 0 and r["badreq"] == 0, r


def test_refresh_is_issued_and_postponement_is_bounded(out):
    r = measure.run(out, "nexys_650", 0, 0, 40, 800, refpost=4, defer=1)
    assert r["pass"] and r["ref"] >= 8 and r["max_ref_gap"] <= 9 * timing.params("nexys_650")["T_REFI"], r


def test_wait_bound_holds_in_a_saturated_run(out):
    """No request waits longer than the bound derived in docs/memory_controller_plan.md section 9 (formal checks it at small parameters; this is the real-parameter evidence), at the default AGE_LIM and at a small one that makes the aging act."""
    sys.path.insert(0, str(D / "verif" / "formal"))
    import run_formal
    p = timing.params("nexys_650")
    for age in (1024, 64):
        cfg = dict(QD=8, AGE_LIM=age, BL2=4, RL=p["RL"], WL=p["WL"], T_WTR=p["T_WTR"], T_WR=p["T_WR"], T_RAS=p["T_RAS"], T_RTP=p["T_RTP"], T_RC=p["T_RC"], T_FAW=p["T_FAW"], T_RPA=p["T_RPA"], T_RP=p["T_RP"],
                   T_RCD=p["T_RCD"], T_RFC=p["T_RFC"])
        bound = run_formal.bound(cfg)
        for pol in (0, 1):
            r = measure.run(out, "nexys_650", pol, 1, 0, 600, extra=dict(AGE_LIM=age))
            assert r["pass"] and r["wait_max"] <= bound, (age, pol, r["wait_max"], bound)



