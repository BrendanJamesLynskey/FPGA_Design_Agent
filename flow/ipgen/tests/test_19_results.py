"""Brief 19: the committed worked examples, re-checked from their files (no Vivado). The xsim output is the IP's own;
these tests recompute the golden from the committed stimulus and coefficients and compare."""
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("scipy")

from flow.ipgen import chain, cic_design, harness  # noqa: E402
from flow.ipgen.fir_adapter import fir_golden_full  # noqa: E402

ROOT = Path(__file__).resolve().parents[3] / "results" / "19_ipgen"
needs = pytest.mark.skipif(not (ROOT / "fir" / "xsim_output.txt").exists(), reason="worked example not committed")


@needs
def test_fir_example_ip_output_equals_python_golden():
    x = np.loadtxt(ROOT / "fir" / "stimulus.txt", dtype=np.int64)
    got = np.loadtxt(ROOT / "fir" / "xsim_output.txt", dtype=np.int64)
    coef = chain.read_coe(ROOT / "fir" / "fir.coe")
    y = fir_golden_full(x, coef)[::4]
    assert len(got) == len(x) // 4 and np.array_equal(got, y)


@needs
def test_comparison_is_sensitive_to_one_coefficient_lsb_or_one_output_bit():
    x = np.loadtxt(ROOT / "fir" / "stimulus.txt", dtype=np.int64)
    got = np.loadtxt(ROOT / "fir" / "xsim_output.txt", dtype=np.int64)
    coef = chain.read_coe(ROOT / "fir" / "fir.coe")
    bad = coef.copy()
    bad[len(bad) // 2] += 1
    r = harness.compare(got, fir_golden_full(x, bad)[::4])
    assert not r["match"] and r["n_mismatch"] > 0
    flipped = got.copy()
    flipped[500] ^= 1
    assert not harness.compare(flipped, fir_golden_full(x, coef)[::4])["match"]


@needs
def test_fir_example_records_the_spec_and_the_ip_agree():
    d = json.loads((ROOT / "fir" / "design.json").read_text())["design"]
    rb = json.loads((ROOT / "fir" / "readback.json").read_text())
    assert d["quantised_metrics"]["stopband_atten_db"] >= d["spec_attenuation_db"]
    assert d["quantised_metrics"]["passband_ripple_db"] <= d["spec_ripple_db"]
    # what the Python tool predicted is what the IP reported
    assert int(rb["selected"]["CONFIG.Output_Width"]) == rb["predicted"]["output_width_full_precision"]
    assert int(rb["selected"]["MODEL.C_NUM_TAPS"]) == d["taps"]
    assert int(rb["selected"]["MODEL.C_NUM_MADDS"]) == rb["predicted"]["multiply_accumulates"]
    sim = json.loads((ROOT / "fir" / "sim.json").read_text())
    assert all(v["match"] for v in sim["sim"].values()) and sim["schedules_agree"]


@needs
def test_cic_example_ip_output_equals_python_golden():
    x = np.loadtxt(ROOT / "cic" / "stimulus.txt", dtype=np.int64)
    got = np.loadtxt(ROOT / "cic" / "xsim_output.txt", dtype=np.int64)
    d = json.loads((ROOT / "cic" / "design.json").read_text())["design"]
    y = cic_design.golden(x, d["rate"], d["diff_delay"], d["stages"])[::d["rate"]]
    assert np.array_equal(got, y)
