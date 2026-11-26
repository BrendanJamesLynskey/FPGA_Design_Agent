"""Brief 201: a published Fmax never exceeds the clock-buffer minimum period of its part (flow/fmax_cap.py), and the raw figure is kept."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import fmax_cap, ipchar  # noqa: E402


def test_family_of_the_parts_in_use():
    assert fmax_cap.family("xc7a100tcsg324-1") == "a7" and fmax_cap.family("xc7a35tcpg236-1") == "a7"
    assert fmax_cap.family("xc7z020clg484-1") == "z7"
    assert fmax_cap.family("xck26-sfvc784-2LV-c") == "k26"
    assert fmax_cap.family("xczu3eg-sfvc784-2-e") == "zu2" and fmax_cap.family("xczu3eg-sfvc784-2LV-e") is None
    assert fmax_cap.family("xcvu2p-fsvj2104-3") is None       # no measurement: no cap
    assert fmax_cap.family("xc7a100tcsg324-2") is None        # -2 not measured: no cap claimed


def test_limits_are_the_measured_ones():
    assert fmax_cap.buffer_limit_mhz("xck26-sfvc784-2LV-c") == 725.2
    assert fmax_cap.buffer_limit_mhz("xc7a100tcsg324-1") == 464.0
    assert fmax_cap.buffer_limit_mhz("xc7z020clg484-1") == 464.0
    assert fmax_cap.buffer_limit_mhz("xczu3eg-sfvc784-2-e") == 775.2


def test_cap_binds_above_the_limit_and_names_it():
    v, why, buf = fmax_cap.cap("k26", 832.64)
    assert (v, buf) == (725.2, 725.2) and "BUFG" in why


def test_cap_leaves_a_lower_figure_alone_and_keeps_its_bound():
    assert fmax_cap.cap("k26", 615.38, "pulse width") == (615.38, "pulse width", 725.2)


def test_a_figure_within_half_a_megahertz_keeps_the_earlier_bound():
    assert fmax_cap.cap("a7", 464.3, "minimum period of DSP48E1/CLK")[1] == "minimum period of DSP48E1/CLK"


def test_no_limit_and_no_figure_change_nothing():
    assert fmax_cap.cap("xcvu2p-fsvj2104-3", 900.0) == (900.0, "setup slack at the target clock", None)
    assert fmax_cap.cap("k26", None)[0] is None


def test_restate_keeps_the_raw_figure_to_the_caller():
    r = fmax_cap.restate("k26", 769.2)
    assert r == {"fmax_capped_mhz": 725.2, "fmax_bound": "clock-buffer minimum period (BUFG)", "fmax_clock_buffer_mhz": 725.2}


def test_the_dsp_study_uses_the_same_numbers():
    spec = importlib.util.spec_from_file_location("run_dsp", ROOT / "results" / "185_dsp_slices" / "run_dsp.py")
    run_dsp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_dsp)
    assert run_dsp.BUF_MIN_PERIOD_NS["a7"] == fmax_cap.LIMITS["a7"][0] and run_dsp.BUF_MIN_PERIOD_NS["k26"] == fmax_cap.LIMITS["k26"][0]


# ---- ipchar.parse on small synthetic reports --------------------------------------------------------------------
def _run_dir(tmp_path, wns, wpws):
    (tmp_path / "done.txt").write_text("1\n")
    (tmp_path / "utilization.rpt").write_text("| Slice LUTs | 10 |\n| Slice Registers | 20 |\n| DSPs | 0 |\n")
    (tmp_path / "timing_summary.rpt").write_text(
        "    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints\n"
        "    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------\n"
        f"      {wns}        0.000                      0                  100        0.050        0.000                      0                  100        {wpws}        0.000                       0                    50\n")
    (tmp_path / "power.rpt").write_text("| Total On-Chip Power (W) | 0.1 |\n| Dynamic (W) | 0.05 |\n| Device Static (W) | 0.05 |\n| Confidence Level | Low |\n")
    return tmp_path


def test_ipchar_caps_a_k26_run_that_beats_the_buffer(tmp_path):
    r = ipchar.parse(_run_dir(tmp_path, "0.380", "0.500"), 2.0, "xck26-sfvc784-2LV-c")     # setup 1000 / 1.62 = 617: below the cap
    assert r["fmax_setup_mhz"] == r["fmax_mhz"] == 617.3 and r["fmax_bound"].startswith("setup")
    r = ipchar.parse(_run_dir(tmp_path, "0.800", "0.500"), 2.0, "xck26-sfvc784-2LV-c")     # setup 1000 / 1.2 = 833: above the cap
    assert r["fmax_setup_mhz"] == 833.3 and r["fmax_mhz"] == 725.2 and "BUFG" in r["fmax_bound"] and r["fmax_clock_buffer_mhz"] == 725.2


def test_ipchar_names_pulse_width_when_it_is_the_lowest(tmp_path):
    r = ipchar.parse(_run_dir(tmp_path, "0.800", "-0.100"), 2.0, "xck26-sfvc784-2LV-c")    # 1000 / 2.2 = 454.5 < 725.2
    assert r["fmax_mhz"] == 454.5 and "WPWS" in r["fmax_bound"]


def test_ipchar_without_a_part_or_a_known_limit_is_as_before(tmp_path):
    for part in (None, "xcvu2p-fsvj2104-3"):
        r = ipchar.parse(_run_dir(tmp_path, "0.800", "0.500"), 2.0, part)
        assert r["fmax_mhz"] == 833.3 and "fmax_bound" not in r


# ---- the published figures ----------------------------------------------------------------------------------------
def test_ip_library_characterisations_are_within_the_limit():
    for f in (ROOT / "ip_lib").glob("*/char/*.json"):
        d = json.loads(f.read_text())
        lim = fmax_cap.buffer_limit_mhz(d.get("part", ""))
        for r in d["results"]:
            if lim and r.get("fmax_mhz"):
                assert r["fmax_mhz"] <= lim + 0.5, (f.name, r["variant"], r["fmax_mhz"])


def test_summaries_carry_the_capped_figure_and_keep_the_raw_one():
    rows = {"b87": json.loads((ROOT / "results/b87/summary.json").read_text())["rows"]}
    rows["b101"] = json.loads((ROOT / "results/b101/summary.json").read_text())
    for r in rows["b87"]:
        assert r["closed_at_mhz"] >= r["fmax_capped_mhz"] and r["fmax_capped_mhz"] <= 725.2
    imb = next(r for r in rows["b87"] if r["arm"] == "imb_rule")
    assert imb["closed_at_mhz"] == 1818.2 and imb["fmax_capped_mhz"] == 725.2
    for r in rows["b101"]:
        lim = fmax_cap.buffer_limit_mhz(r["part"])
        assert r["fmax_mhz"] is None or r["fmax_capped_mhz"] <= lim + 0.5     # None: the arm did not close
    crc = [r for r in rows["b101"] if r["part"] == "k26" and r["block"] == "crc64_rx" and r["arm"].startswith("viv")]
    assert crc and all(r["fmax_mhz"] == 769.2 and r["fmax_capped_mhz"] == 725.2 for r in crc)


def test_137_k26_post_synthesis_estimate_is_capped_and_raw_kept():
    d = json.loads((ROOT / "results/137_arith_pareto/k26/measured.json").read_text())
    p07 = next(r for r in d["rows"] if r["id"] == "P07")
    assert p07["synth"]["fmax_mhz"] == 832.64 and p07["synth"]["fmax_capped_mhz"] == 725.2
    assert p07["route"]["fmax_mhz"] == p07["route"]["fmax_capped_mhz"] == 615.38
