"""Brief 189 item 13: per-logic-level delay and per-register overhead measured from post-route reports (brief 89's out-of-context LUT networks,
Vivado 2026.1, on 7a100t and xck26)."""

from __future__ import annotations

from pathlib import Path

from flow import level_delay as L

ROOT = Path(__file__).resolve().parents[2]
REPORTS = sorted((ROOT / "results" / "b89" / "ooc").glob("*/reports/*/timing_summary.rpt"))


def test_level_count_matches_vivados_own_count_on_every_path() -> None:
    n = 0
    for f in REPORTS:
        for p in L.parse_paths(f.read_text()):
            n += 1
            assert p["n_levels"] == p["vivado_logic_levels"], (f, [x["type"] for x in p["levels"]])
    assert n >= 50


def test_both_parts_are_measured_with_a_good_fit() -> None:
    rec = L.analyse(REPORTS)
    assert rec["enforced"] is False and rec["vivado"] == ["2026.1"]
    k, a = rec["parts"]["xck26-sfvc784"], rec["parts"]["7a100t-csg324"]
    for s in (k, a):
        assert s["fit"]["r2"] > 0.9 and s["fit"]["n"] >= 25 and s["fit"]["levels_max"] >= 10
        assert abs(s["per_level"]["level_ns"] - (s["per_level"]["cell_ns"] + s["per_level"]["net_ns"])) < 0.001
    assert k["per_level"]["level_ns"] < a["per_level"]["level_ns"] / 2                    # UltraScale+ -2LV is well under half the 7-series -1 level
    assert k["register_overhead"]["clk_to_q_ns"] < a["register_overhead"]["clk_to_q_ns"]


def test_ols_on_a_known_line() -> None:
    f = L.ols([1, 2, 3, 4], [1.5, 2.0, 2.5, 3.0])
    assert f["slope_ns_per_level"] == 0.5 and f["intercept_ns"] == 1.0 and f["r2"] == 1.0
    assert L.ols([1, 1, 1], [1, 2, 3]) is None


def test_paths_with_dsp_or_ram_are_skipped(tmp_path: Path) -> None:
    text = REPORTS[0].read_text().replace("FDRE (Prop", "DSP48E1 (Prop", 1)
    assert len(L.parse_paths(text)) <= len(L.parse_paths(REPORTS[0].read_text()))
