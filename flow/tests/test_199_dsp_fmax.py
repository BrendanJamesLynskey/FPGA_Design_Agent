"""Brief 199: the DSP-slice Fmax is the lowest of setup, slice minimum period and clock-buffer minimum period."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_dsp", ROOT / "results" / "185_dsp_slices" / "run_dsp.py")
run_dsp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_dsp)


def test_buffer_limit_binds_k26():
    f, why, buf = run_dsp.fmax_limits(836.8, 1176.5, "DSP_OUTPUT/CLK", 1.379)
    assert (f, buf) == (725.2, 725.2) and "BUFG" in why


def test_setup_binds_when_lowest():
    f, why, _ = run_dsp.fmax_limits(500.0, 1176.5, "DSP_OUTPUT/CLK", 1.379)
    assert f == 500.0 and why.startswith("setup")


def test_slice_limit_named_on_tie_with_buffer():
    f, why, _ = run_dsp.fmax_limits(495.5, 464.3, "DSP48E1/CLK", 2.155)   # a7: slice 2.154 ns, BUFG 2.155 ns
    assert f == 464.3 and why == "minimum period of DSP48E1/CLK"


def test_no_buffer_measured_changes_nothing():
    assert run_dsp.fmax_limits(900.0, None, None, None)[0] == 900.0


def test_published_data_respects_buffer_limit():
    for pk, ns in (("a7", 2.155), ("k26", 1.379)):
        d = json.loads((ROOT / "results" / "185_dsp_slices" / "data" / f"{pk}.json").read_text())
        top = 1000.0 / ns + 0.5
        for p in d["points"]:
            if p.get("fmax_mhz"):
                assert p["fmax_mhz"] <= top, (pk, p["id"], p["fmax_mhz"])
