"""Brief 05n: V3 thresholds the testplan cannot lower, and a minimum number of evaluated mutants.

Fixture ``data/run_dd0e``: the verification files of live run 20261105-074023-dd0e (Sonnet 5.5 through Claude Code), copied
unchanged except that the repo-relative paths inside the testplan and coverage.dat are rewritten to the fixture directory.
That run set cover_properties_pct 0, toggle_pct 60 and mutation_score_pct 60 in its own testplan and passed V3 on
6 of 20 sampled mutants."""

import json
import shutil
from pathlib import Path

import pytest

from flow import mutate as M, verif_gates as G
from flow.tests.test_05j_gate_preconditions import _plan, _seeds

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"
RUN = Path(__file__).parent / "data" / "run_dd0e"
FLOORS = G.load_floors()


# ---- the floors ---------------------------------------------------------------------------------------------------

def test_floor_file_has_every_value_and_a_source_comment():
    text = G.FLOORS_FILE.read_text()
    assert {k: FLOORS[k] for k in G.THRESHOLD_FLOORS} == {"functional_bins_pct": 100, "cover_properties_pct": 100, "line_pct": 90,
                                                          "toggle_pct": 75, "mutation_score_pct": 70, "seeds_min": 3}
    assert FLOORS["mutation_min_evaluated"] == 10
    for k in FLOORS:
        line = next(x for x in text.splitlines() if x.startswith(k + ":"))
        assert "#" in line, f"{k} needs a comment saying where it comes from"


def test_plan_below_floor_is_raised_and_says_so():
    th, ign = G.effective_thresholds({"seeds_min": 1, "functional_bins_pct": 100, "cover_properties_pct": 0, "line_pct": 50,
                                      "toggle_pct": 60, "mutation_score_pct": 60}, FLOORS)
    assert th == {"seeds_min": 3, "functional_bins_pct": 100, "cover_properties_pct": 100, "line_pct": 90, "toggle_pct": 75,
                  "mutation_score_pct": 70}
    assert "testplan asked 0%, the floor is 100%" in ign["cover_properties_pct"]
    assert "functional_bins_pct" not in ign


def test_plan_above_floor_keeps_its_value():
    th, ign = G.effective_thresholds({"seeds_min": 5, "functional_bins_pct": 100, "cover_properties_pct": 100, "line_pct": 95,
                                      "toggle_pct": 80, "mutation_score_pct": 85}, FLOORS)
    assert (th["seeds_min"], th["line_pct"], th["toggle_pct"], th["mutation_score_pct"]) == (5, 95, 80, 85) and ign == {}


def test_missing_or_garbage_plan_value_uses_the_floor():
    th, ign = G.effective_thresholds({"line_pct": "lots"}, FLOORS)
    assert th["line_pct"] == 90 and "line_pct" in ign and th["toggle_pct"] == 75


def test_gate_names_the_floor_when_the_plan_asks_for_less(monkeypatch, tmp_path):
    """T1's evidence with the plan's line threshold at 10: the T1 line coverage is not in this fixture, so use a plan that
    asks for 0% cover properties and no cover properties planned: the floor still demands them."""
    _plan(monkeypatch, cover_props=[], thresholds={"cover_properties_pct": 0, "line_pct": 10, "toggle_pct": 10})
    rep = G.evaluate(T1, _seeds(tmp_path), [], tmp_path / "nof", None, None)
    c = rep["stages"]["V3"]["checks"]
    assert c["cover_properties_pct"]["threshold"] == 100 and not c["cover_properties_pct"]["pass"]
    assert "testplan asked 0%, the floor is 100%" in c["cover_properties_pct"]["why"]
    assert c["line_pct"]["threshold"] == 90 and "testplan asked 10%, the floor is 90%" in c["line_pct"]["floor_note"]
    assert c["toggle_pct"]["threshold"] == 75


def test_waiver_still_excuses_a_named_cover_property(monkeypatch):
    """A waiver with a reason is the only way out: all planned cover properties waived leaves nothing unhit."""
    plan = G.yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    names = sorted({c for r in plan["requirements"] for c in r.get("cover_props", [])})
    plan["waivers"]["cover_properties"] = [{"item": n, "reason": "unreachable in this bench"} for n in names]
    real = G.yaml.safe_load
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "fpga-design-agent/testplan" in t else real(t))
    rep = G.evaluate(T1, RUN / "sim", [], RUN / "nof", None, None)       # coverage data of the other design: only the waiver logic
    c = rep["stages"]["V3"]["checks"]
    assert c["cover_properties_unhit"]["value"] == [] and c["waivers_without_reason"]["pass"]


# ---- the minimum number of evaluated mutants -----------------------------------------------------------------------

def _mut(**kw):
    m = {"score_pct": 100.0, "candidates": 39, "sampled": 20, "evaluated": 20, "killed": 20, "survived": 0, "timed_out": 0,
         "skipped": 0, "invalid": 0, "survivors": [], "survivor_text": []}
    return m | kw


def test_not_enough_evaluated_says_n_of_m_and_skipped():
    why = G.mutation_why(_mut(evaluated=6, skipped=14, candidates=20, score_pct=83.33), None, 10)
    assert "not enough mutants evaluated: 6 of 20 (skipped 14 by the wall cap" in why


def test_gate_fails_a_good_score_on_too_few_mutants(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps(_mut(evaluated=6, skipped=14, candidates=39, sampled=20, score_pct=100.0)))
    rep = G.evaluate(T1, RUN / "sim", [], RUN / "nof", f, None)
    c = rep["stages"]["V3"]["checks"]["mutation_score_pct"]
    assert not c["pass"] and "not enough mutants evaluated: 6 of 39" in c["why"]


def test_gate_accepts_ten_evaluated_and_all_candidates_when_fewer(tmp_path):
    for m in (_mut(evaluated=10, skipped=10), _mut(evaluated=4, candidates=4, sampled=4, skipped=0)):
        f = tmp_path / "m.json"
        f.write_text(json.dumps(m))
        c = G.evaluate(T1, RUN / "sim", [], RUN / "nof", f, None)["stages"]["V3"]["checks"]["mutation_score_pct"]
        assert c["pass"], c


def test_below_floor_score_fails_with_the_floor(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps(_mut(score_pct=65.0, killed=13, survived=7, survivor_text=["x"])))
    c = G.evaluate(T1, RUN / "sim", [], RUN / "nof", f, None)["stages"]["V3"]["checks"]["mutation_score_pct"]
    assert not c["pass"] and c["threshold"] == 85                # T1's own plan asks 85, above the floor of 70
    f2 = tmp_path / "m2.json"
    f2.write_text(json.dumps(_mut(score_pct=75.0, killed=15, survived=5, survivor_text=["x"])))
    assert not G.evaluate(T1, RUN / "sim", [], RUN / "nof", f2, None)["stages"]["V3"]["checks"]["mutation_score_pct"]["pass"]


# ---- the cap ---------------------------------------------------------------------------------------------------------

def test_wall_cap_scales_with_the_baseline():
    assert M.plan_caps(312, 20, 39, None) == (20, 6864)            # the live run: 312 s baseline, 20 sampled, now fits
    assert M.plan_caps(10, 20, 39, None) == (20, 1500)             # a quick bench keeps the old 1500 s
    assert M.plan_caps(312, 20, 39, 1500) == (20, 1500)            # an explicit cap is honoured
    assert M.plan_caps(312, 20, 39, 0) == (20, 0)


def test_sample_shrinks_but_never_below_min_evaluated():
    n, wall = M.plan_caps(600, 20, 39, None)                       # 600*22 > 2 h
    assert wall <= M.MAX_WALL_S and M.MIN_EVALUATED <= n < 20
    assert M.plan_caps(3000, 20, 39, None)[0] == M.MIN_EVALUATED   # even then: 10
    assert M.plan_caps(3000, 20, 6, None)[0] == 6                  # fewer candidates than the minimum: all of them


# ---- replay of live run 20261105-074023-dd0e ------------------------------------------------------------------------------

def _replay():
    d = RUN / "t1_dimmer_counter"
    return G.evaluate(d, RUN / "sim", [], RUN / "nof", RUN / "evidence" / "mutation.json", None, None,
                      RUN / "evidence" / "v3_evidence.json")


def test_replay_of_the_live_run_now_fails_v3_on_cover_properties_and_mutation_evidence():
    rep = _replay()
    c = rep["stages"]["V3"]["checks"]
    assert rep["first_failed"] == "V3"
    cp = c["cover_properties_pct"]
    assert cp["threshold"] == 100 and not cp["pass"] and "testplan asked 0%, the floor is 100%" in cp["why"]
    mu = c["mutation_score_pct"]
    assert not mu["pass"] and "not enough mutants evaluated: 6 of 39" in mu["why"] and "skipped 14" in mu["why"]
    assert "testplan asked 60%, the floor is 70%" in mu["why"]
    assert c["toggle_pct"]["threshold"] == 75 and "testplan asked 60%" in c["toggle_pct"]["floor_note"]
    # the measured numbers are unchanged (75.0 toggle meets its floor exactly)
    assert c["toggle_pct"]["pass"] and c["line_pct"]["pass"] and c["functional_bins_pct"]["pass"]


def test_reference_t1_still_passes_v3_with_its_own_files():
    """T1's own plan asks 100/95/80/85/3, all at or above the floors: nothing is raised, nothing is ignored, and every V3
    check passes on the 04f reference evidence (three seeds of Verilator coverage files; 21 candidates,
    20 evaluated mutants from the 05m container run)."""
    plan = G.yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    th, ign = G.effective_thresholds(plan["thresholds"], FLOORS)
    assert ign == {} and th == plan["thresholds"]
    rep = G.evaluate(T1, Path(__file__).parent / "data" / "ref_t1_sim", [], RUN / "nof",
                     ROOT / "results" / "05m" / "mutation_t1_container.json", None)
    bad = {k: c for k, c in rep["stages"]["V3"]["checks"].items() if not c["pass"]}
    assert bad == {}, bad
    assert not any("floor_note" in c for c in rep["stages"]["V3"]["checks"].values())


# ---- the tests role is told -------------------------------------------------------------------------------------------------

def test_tests_role_checklist_and_prompt_state_the_floors_and_name_no_missing_tool():
    from agent.graph import run as R
    text = R.floors_text()
    for n in ("functional bins 100%", "cover properties 100%", "line 90%", "toggle 75%", "mutation score 70%", "3 seeds"):
        assert n in text
    from types import SimpleNamespace
    rt = SimpleNamespace(cfg=SimpleNamespace(name="t1_dimmer_counter", verif_level="V3"))
    chk = R.tests_checklist(rt, 2, False)
    assert "flow/verif_floors.yaml" in chk and "ignored" in chk and text in chk and "10, or every candidate" in chk
    assert "below the harness floor" in R.CONVENTIONS
    for word in ("`mutate`", "`simulate`", "mutate(", "simulate("):
        assert word not in chk.split("7. V3 floors")[1].split("8.")[0]
