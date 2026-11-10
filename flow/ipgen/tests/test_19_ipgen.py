"""Brief 19: the Python side of ipgen (no Vivado): FIR design, quantisation, the fixed-point golden, the harness files."""
import numpy as np
import pytest

pytest.importorskip("scipy")

from flow.ipgen import fir_design, harness  # noqa: E402
from flow.ipgen.fir_adapter import fir_golden_full, full_precision_width, test_signal as make_signal  # noqa: E402

SPEC = dict(fs_in_hz=20e6, pass_edge_hz=1e6, stop_edge_hz=1.5e6, ripple_db=0.1, atten_db=60, design_margin_db=2,
            coef_width=14, decimation=4, data_width=16)


def test_design_meets_spec_after_quantisation():
    d = fir_design.design(SPEC)
    q = d["quantised_metrics"]
    assert q["passband_ripple_db"] <= SPEC["ripple_db"]
    assert q["stopband_atten_db"] >= SPEC["atten_db"]
    assert d["attenuation_lost_db"] >= 0
    assert d["symmetric"] and d["taps"] % 2 == 1
    assert int(np.max(np.abs(d["coef"]))) < 2 ** (d["coef_width"] - 1)


def test_quantisation_loop_widens_when_too_narrow():
    spec = dict(SPEC, atten_db=90, design_margin_db=1, coef_width=8)
    d = fir_design.design(spec)
    assert d["coef_width"] > 8
    assert not d["width_search"][0]["ok"]


def test_coe_text_roundtrip():
    txt = fir_design.coe_text(np.array([1, -2, 3]))
    assert txt.startswith("radix = 10;") and txt.strip().endswith("3;")


def test_golden_is_exact_convolution():
    x = np.array([1, 0, 0, 0, 5, -3, 2], dtype=np.int64)
    c = np.array([1, 2, 3], dtype=np.int64)
    y = fir_golden_full(x, c)
    assert list(y) == [1, 2, 3, 0, 5, 7, 11]


def test_full_precision_width_is_enough_for_the_test_signal():
    d = fir_design.design(SPEC)
    spec = dict(SPEC)
    x = make_signal(spec, d, n=2048)
    y = fir_golden_full(x, d["coef"])
    w = full_precision_width(spec["data_width"], d["coef"])
    assert np.max(np.abs(y)) < 2 ** (w - 1)
    assert np.max(np.abs(x)) <= 2 ** (spec["data_width"] - 1)


def test_stimulus_file_and_response_parse(tmp_path):
    p = tmp_path / "s.txt"
    harness.write_stimulus(p, [1, -1, 32767, -32768], 16)
    assert p.read_text().split("\n")[:4] == ["0001 0", "ffff 0", "7fff 0", "8000 0"]
    r = tmp_path / "r.txt"
    r.write_text("5 ffff 0\n9 0002 1\n# first_in 3\n# last_out 9\n")
    rr = harness.read_response(r, 16)
    assert rr["data"] == [-1, 2] and rr["tlast"] == [0, 1] and rr["meta"]["first_in"] == 3


def test_schedule_is_seeded_and_continuous_is_all_ones():
    assert harness.schedule("random", 64, 3) == harness.schedule("random", 64, 3)
    assert harness.schedule("random", 64, 3) != harness.schedule("random", 64, 4)
    assert set(harness.schedule("continuous", 8)) == {(1, 1)}


def test_compare_finds_phase_and_mismatch():
    assert harness.compare([3, 4, 5], [1, 2, 3, 4, 5, 6], phases=(0, 2))["phase"] == 2
    r = harness.compare([1, 9, 3], [1, 2, 3])
    assert not r["match"] and r["first_mismatch"] == 1


def test_tb_renders_with_no_placeholders_left(tmp_path):
    out = tmp_path / "tb.sv"
    harness.render_tb(out, dut_inst="    dut d();", in_w=16, out_w=40, n_in=10, stim=tmp_path / "a", sched=tmp_path / "b",
                      resp=tmp_path / "c", n_sched=16)
    import re
    body = "\n".join(ln for ln in out.read_text().splitlines() if not ln.lstrip().startswith("//"))
    assert not re.search(r"@[A-Z_]+@", body)


def test_bmg_table_coe_and_check(tmp_path):
    from flow.ipgen.bmg_adapter import BmgAdapter, make_table
    spec = dict(kind="sine", points=64, width=8)
    t = make_table(spec)
    assert t[0] == 0 and t[16] == 127 and t[48] == -127 and len(t) == 64
    ad = BmgAdapter()
    d = ad.design(spec)
    art = ad.design_artifacts(spec, d, tmp_path)
    lines = art["coe"].read_text().split("\n")
    assert lines[0] == "memory_initialization_radix=16;" and lines[2] == "00,"
    assert lines[2 + 48] == "81,"  # -127 in 8-bit two's complement
    addrs = list(range(64)) * 2
    # a ROM with latency 2: D[r + 2] = table[A[r]]
    data = [0, 0] + [int(t[a]) & 0xFF for a in addrs]
    r = ad.check_mem(spec, d, addrs, data[: len(addrs)] + [0, 0, 0], 8)
    assert r["match"] and r["latency_cycles"] == 2
    bad = list(data)
    bad[30] ^= 1
    assert not ad.check_mem(spec, d, addrs, bad[: len(addrs)] + [0, 0, 0], 8)["match"]
