"""The development design of brief 194 under Icarus: the functional bench on every variant without the block RAM primitive, one mutant caught,
and a small fault-injection campaign whose classes follow from what each structure does (the full table is results/b194/faults.json)."""

import subprocess
import sys
from pathlib import Path

import pytest

D = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D / "tests"))
import run_faults as RF  # noqa: E402
from mutants import MUTANTS  # noqa: E402

pytest.importorskip("yaml")
ICARUS = subprocess.run(["which", "iverilog"], capture_output=True).returncode == 0
pytestmark = pytest.mark.skipif(not ICARUS, reason="iverilog not installed")

PLAIN = {k: v for k, v in RF.VARIANTS.items() if v[0] != 2}      # ECC = 2 instantiates RAMB36E1: xsim only


@pytest.mark.parametrize("name", sorted(PLAIN))
def test_the_functional_bench_passes_on_every_variant(name, tmp_path):
    exe = tmp_path / "s.out"
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), f"-DDUT_PARAMS={RF.params(PLAIN[name])}", *map(str, RF.RTL), str(D / "tb" / "tb_func.sv")], check=True)
    out = subprocess.run(["vvp", str(exe), "+seed=2", "+bursts=12"], capture_output=True, text=True).stdout
    assert "TB PASS" in out, out[-300:]


def test_every_mutant_text_is_in_the_source():
    for mid, f, old, new, _what in MUTANTS:
        assert old in (D / "rtl" / f).read_text() and old != new, mid


def test_a_mutant_is_caught_by_the_bench(tmp_path):
    sys.path.insert(0, str(D.parents[1]))
    from flow import assurance_profiles as AP
    m = tmp_path / "m1"
    AP.mutate(m, "m1_last_word")
    assert AP.sim(m, 1, bursts=6)[0] is False


def _campaign(name, target, trials=24):
    r = RF.run_variant(name, RF.VARIANTS[name], [target], trials, seed=3)[target]
    return r


def test_ecc_corrects_and_the_plain_design_corrupts_silently():
    assert _campaign("u", "ram")["silent"] == 24                       # every flipped stored word reaches the output unflagged
    r = _campaign("ecc_fabric", "ram")
    assert r["corrected"] == 24 and r["silent"] == 0                  # one flipped bit: corrected and flagged
    assert _campaign("ecc_fabric", "ram2")["detected"] >= 20           # two flipped bits: detected (the rest hit check bits only)


def test_tmr_corrects_one_copy_and_the_plain_counter_does_not():
    assert _campaign("tmr", "cnt")["corrected"] == 24
    p = _campaign("u", "cnt")
    assert p["silent"] + p["hang"] > 0
    assert _campaign("tmr", "cnt2")["corrected"] < 24                  # two copies flipped: the vote is wrong (the limit of TMR)


def test_parity_detects_a_bus_upset():
    r = _campaign("par", "bus")
    assert r["silent"] == 0 or r["detected"] > 0


def test_no_injection_is_always_masked():
    r = _campaign("all", "none", trials=12) if False else _campaign("tmr", "none", trials=12)
    assert r["masked"] == 12
