"""Brief 218: the graded paired comparison (tools/run_stats/graded.py)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import graded as g  # noqa: E402


def rows(arm, vals, col="holes_per_mtok", seed=1, stop=""):
    return [{"id": f"d{i}", "seed": seed, "arm": arm, col: v, "stop_reason": stop} for i, v in enumerate(vals)]


def test_a_paired_effect_with_an_interval_and_a_sign_test():
    base, arm = rows("A0", [1, 2, 3, 4, 5, 6]), rows("A1", [3, 4, 5, 6, 7, 8])
    p = g.paired_numeric(arm, base, "holes_per_mtok")
    assert p["items"] == 6 and p["effect"] == 2.0 and (p["lo"], p["hi"]) == (2.0, 2.0) and p["better"] == 6 and p["worse"] == 0 and p["detectable"]
    assert abs(p["p_sign"] - 2 / 64) < 1e-12


def test_repeats_of_an_item_are_averaged_before_pairing():
    base = rows("A0", [2, 2], seed=1) + rows("A0", [4, 4], seed=2)
    arm = rows("A1", [3, 3], seed=1) + rows("A1", [3, 3], seed=2)
    assert g.paired_numeric(arm, base, "holes_per_mtok")["effect"] == 0.0


def test_three_items_that_disagree_give_no_detectable_effect():
    p = g.paired_numeric(rows("A1", [5, 1, 9]), rows("A0", [4, 4, 4]), "holes_per_mtok")
    assert p["items"] == 3 and p["lo"] < 0 < p["hi"] and not p["detectable"]
    assert "no detectable effect" in g.report(rows("A1", [5, 1, 9]) + rows("A0", [4, 4, 4]), "A0", ["holes_per_mtok"])


def test_a_run_that_was_not_run_is_left_out_not_scored(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("id,seed,arm,holes_per_mtok,stop_reason\nd0,1,A0,1,\nd0,1,A1,9,rate_limited\nd0,2,A1,3,\n")
    rs = g.load(str(f))
    assert [r["arm"] + r["seed"] for r in rs] == ["A01", "A12"]
    p = g.paired_numeric([r for r in rs if r["arm"] == "A1"], [r for r in rs if r["arm"] == "A0"], "holes_per_mtok")
    assert p["effect"] == 2.0


def test_an_item_missing_from_one_arm_is_listed_not_dropped_silently():
    p = g.paired_numeric(rows("A1", [1, 2, 3]), rows("A0", [1, 2]), "holes_per_mtok")
    assert p["items"] == 2 and p["arm_only"] == ["d2"]


def test_a_run_record_becomes_a_row():
    r = g.rows_from_run_record({"tokens_total": 5, "real_usd": 1.5, "reached_stage": 2, "verif_stages": {"V0": True, "V1": True, "V2": True, "V3": False}}, "p2", "A0",
                               extra={"holes_end": 4})
    assert r["verif_level_reached"] == 2 and r["tokens"] == 5 and r["holes_end"] == 4 and r["arm"] == "A0"
