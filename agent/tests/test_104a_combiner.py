"""Brief 104A: the deterministic combiner. Code, not the model, builds the cumulative options from the valid single ones, composes the gain bound, validates the result with
the same checks as any option, ranks and caps. Also the ``prior_run`` facts (measured 97/97C variants), the guarantee that a back-test's truth never reaches its analysis, and
that the back-test scoring code is the one brief 104 used. No model is called."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_104_options import (BT, FX10, FXC, ROOT, doc_of, needs_prompts, opt)  # noqa: E402

from agent.core import managed  # noqa: E402
from flow.options import analysis as A  # noqa: E402
from flow.options import cli as C  # noqa: E402
from flow.options import combine as K  # noqa: E402
from flow.options import generate as G  # noqa: E402
from flow.options import schema as S  # noqa: E402


@pytest.fixture(scope="module")
def an10() -> dict:
    return A.analyse(FX10, build_dir=FX10 / "evidence")


@pytest.fixture()
def proj10() -> managed.Project:
    return managed.load(FX10)


def single(i: str, comp: str, stage: str, low: float = 0, high: float = 1, **kw) -> dict:
    d = dict(id=i, title=f"Cut {stage}", scope={"kind": "modules", "components": [comp]}, touches_stages=[stage], techniques=[f"cut_{stage}"],
             gain={"metric": "latency_clocks", "low": low, "high": high, "basis": "model", "cites": [f"stage.{stage}.clocks", f"stage.{stage}.removable"], "basis_note": "stage file"})
    d.update(kw)
    return opt(**d)


def checked(an: dict, proj: managed.Project, *raw: dict, goal: str = "latency") -> list[dict]:
    r = S.check_options(doc_of(*raw), an, proj, goal=goal, min_options=1)
    assert not r["rejected"], r["rejected"]
    return r["options"]


def four(an: dict, proj: managed.Project) -> list[dict]:
    return checked(an, proj, single("O1", "tx_frame_src", "fs_start"), single("O2", "core", "cross_go"), single("O3", "trade_decision", "decide"),
                   single("O4", "tx_mac", "mac_preamble"))


# ---- composing -------------------------------------------------------------------------------------------------------------------

def test_disjoint_latency_cuts_add_and_the_options_are_built_by_code(an10: dict, proj10: managed.Project) -> None:
    opts = four(an10, proj10)
    res = K.combine(opts, an10, proj10, goal="latency")
    assert res["considered"] == 11                                                          # 6 pairs, 4 triples, 1 quadruple
    sizes = sorted(len(o["combined_from"]) for o in res["options"])
    assert set(sizes) == {2, 3, 4} and len(res["options"]) == K.MAX_COMBINED == 4
    pair = next(o for o in res["options"] if len(o["combined_from"]) == 2)
    a, b = (next(x for x in opts if x["id"] == i) for i in pair["combined_from"])
    assert pair["gain"]["low"] == a["gain"]["low"] + b["gain"]["low"] and pair["gain"]["high"] == a["gain"]["high"] + b["gain"]["high"]
    assert pair["gain"]["basis"] == "model" and "Composed by code" in pair["gain"]["basis_note"] and pair["gain"]["cites"]
    assert set(pair["touches_stages"]) == set(a["touches_stages"]) | set(b["touches_stages"])
    assert pair["origin"] == "combiner" and all(o["origin"] == "combiner" for o in res["options"])


def test_a_combined_option_passes_the_same_checks_and_flags_the_boundary_by_code(an10: dict, proj10: managed.Project) -> None:
    opts = four(an10, proj10)
    res = K.combine(opts, an10, proj10, goal="latency")
    for o in res["options"]:
        raw = K.build_raw([next(x for x in opts if x["id"] == i) for i in o["combined_from"]], {k: o["gain"][k] for k in ("metric", "low", "high", "basis", "cites", "basis_note")},
                          [c.name for c in proj10.owned()])
        again, probs = S.check_single(raw, o["id"], an10, proj10, goal="latency")                    # rebuilt from the parts, it passes the same per-option checks
        assert again is not None and not probs and again["risk"]["needs_owner_approval"] == o["risk"]["needs_owner_approval"]
        assert o["scope"]["components"] and set(o["scope"]["components"]) <= {c.name for c in proj10.owned()}
        spans = {c for c in o["stage_components"].values() if c}
        if len(spans) >= 2:                                                                  # a change across two components is a contract change, and needs the owner
            assert o["risk"]["contract_change"] and o["risk"]["needs_owner_approval"] and o["risk"]["contract_flags"]
        assert o["not_touched"] is not None
    assert any(o["risk"]["needs_owner_approval"] for o in res["options"])


def test_alternatives_that_touch_the_same_stage_are_never_combined(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, single("O1", "core", "cross_go"), single("O2", "core", "cross_go", title="Another way to cut cross_go"))
    res = K.combine(opts, an10, proj10, goal="latency")
    assert res["options"] == [] and "both touch stage cross_go" in res["not_composable"][0]["reason"]


def test_conflicting_interface_changes_are_not_combined(an10: dict, proj10: managed.Project) -> None:
    ic = [{"component": "core", "port": "go", "change": "pulse becomes a level"}]
    opts = checked(an10, proj10, single("O1", "core", "cross_go", interface_changes=ic), single("O2", "core", "decide", scope={"kind": "modules", "components": ["core", "trade_decision"]},
                                                                                              interface_changes=ic))
    res = K.combine(opts, an10, proj10, goal="latency")
    assert not res["options"] and "interface changes conflict" in res["not_composable"][0]["reason"]


def test_a_guess_part_makes_the_whole_a_guess_with_no_cited_basis(an10: dict, proj10: managed.Project) -> None:
    g = single("O2", "core", "cross_go", gain={"metric": "latency_clocks", "low": 0, "high": 1, "basis": "guess", "cites": [], "basis_note": "no basis"})
    res = K.combine(checked(an10, proj10, single("O1", "tx_frame_src", "fs_start"), g), an10, proj10, goal="latency")
    assert len(res["options"]) == 1 and res["options"][0]["gain"]["basis"] == "guess" and res["options"][0]["gain"]["cites"] == []


def test_the_composed_high_end_never_exceeds_the_analysis_ceiling(an10: dict, proj10: managed.Project) -> None:
    big = [single("O1", "tx_frame_src", "fs_start", 0, 1), single("O2", "core", "cross_go", 0, 1)]
    res = K.combine(checked(an10, proj10, *big), an10, proj10, goal="latency")
    for o in res["options"]:
        cap, _ = S.ceiling("latency_clocks", o["touches_stages"], o["scope"]["components"], an10)
        assert o["gain"]["high"] <= cap + 1e-9 and o["gain"]["ceiling"] == cap


def test_a_slack_gain_is_not_composable_and_says_why() -> None:
    anc = A.analyse(FXC, build_dir=FXC / "evidence")
    projc = managed.load(FXC)
    names = [c.name for c in projc.owned()]
    assert len(names) >= 1
    a = {"id": "O1", "scope": {"kind": "modules", "components": names[:1]}, "touches_stages": [], "gain": {"metric": "wns_ns", "low": 0, "high": 0.5, "basis": "guess", "cites": []},
         "interface_changes": [], "origin": "model"}
    b = copy.deepcopy(a) | {"id": "O2"}
    g, why = K.compose_gain([a, b], anc, blind=False, scope=names[:1])
    assert g is None and "do not add" in why
    res = K.combine([a, b], anc, projc, goal="timing")
    assert res["options"] == [] and "do not add" in res["not_composable"][0]["reason"]


def test_area_gains_add_only_across_different_components() -> None:
    an = {"facts": {"res.a.lut": {"value": 100}, "res.b.lut": {"value": 50}}, "latency": None}

    def o(i, comp, hi):
        return {"id": i, "scope": {"components": [comp]}, "touches_stages": [], "gain": {"metric": "lut", "low": 1, "high": hi, "basis": "model", "cites": [f"res.{comp}.lut"]}}
    g, why = K.compose_gain([o("O1", "a", 10), o("O2", "b", 5)], an, blind=False, scope=["a", "b"])
    assert why is None and (g["low"], g["high"]) == (2, 15) and g["basis"] == "model"
    g, why = K.compose_gain([o("O1", "a", 10), o("O2", "a", 5)], an, blind=False, scope=["a"])
    assert g is None and "can overlap" in why


# ---- ranking and the cap -----------------------------------------------------------------------------------------------------------

def test_ranking_is_deterministic_and_capped_whatever_the_order_of_the_input(an10: dict, proj10: managed.Project) -> None:
    opts = four(an10, proj10)
    first = [(o["combined_from"], o["gain"]["high"]) for o in K.combine(opts, an10, proj10, goal="latency")["options"]]
    again = [(o["combined_from"], o["gain"]["high"]) for o in K.combine(copy.deepcopy(opts), an10, proj10, goal="latency")["options"]]
    assert first == again and len(first) <= K.MAX_COMBINED
    sizes = [len(f) for f, _ in first]
    assert sizes == sorted(sizes) and {2, 3, 4} <= set(sizes)                                # the menu has a small, a medium and the full combination


def test_a_higher_composed_gain_ranks_first_within_a_size(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, single("O1", "tx_frame_src", "fs_start", 0, 1), single("O2", "core", "cross_go", 0, 1), single("O3", "trade_decision", "decide", 1, 1))
    res = K.combine(opts, an10, proj10, goal="latency")
    pairs = [o for o in res["options"] if len(o["combined_from"]) == 2]
    assert pairs and "O3" in pairs[0]["combined_from"]                                       # the pair with the 1-to-1 part has the higher mid-gain


def test_apply_numbers_everything_and_is_idempotent(an10: dict, proj10: managed.Project) -> None:
    rec = {"options": four(an10, proj10)}
    K.apply(rec, an10, proj10, goal="latency")
    ids = [o["id"] for o in rec["options"]]
    assert [o["n"] for o in rec["options"]] == list(range(1, len(ids) + 1)) and len(set(ids)) == len(ids)
    assert ids[:4] == ["O1", "O2", "O3", "O4"] and all(i.startswith("C") for i in ids[4:])
    again = copy.deepcopy(rec)
    K.apply(again, an10, proj10, goal="latency")
    assert json.dumps(again["options"], sort_keys=True) == json.dumps(rec["options"], sort_keys=True)
    assert rec["combiner"]["offered"] and rec["combiner"]["not_composable"] is not None and rec["combiner"]["version"] == K.COMBINER_VERSION


def test_a_set_the_model_already_offered_is_not_offered_again(an10: dict, proj10: managed.Project) -> None:
    both = single("O3", "core", "cross_go", scope={"kind": "modules", "components": ["core", "trade_decision"]}, touches_stages=["cross_go", "decide"],
                  gain={"metric": "latency_clocks", "low": 0, "high": 2, "basis": "model", "cites": ["stage.cross_go.clocks", "stage.decide.clocks"], "basis_note": "two stages"})
    opts = checked(an10, proj10, single("O1", "core", "cross_go"), single("O2", "trade_decision", "decide"), both)
    res = K.combine(opts, an10, proj10, goal="latency")
    assert not [o for o in res["options"] if set(o["touches_stages"]) == {"cross_go", "decide"}]
    assert any("already offered" in x["reason"] for x in res["not_composable"])


def test_a_frozen_or_excluded_component_never_enters_a_combined_scope(an10: dict, proj10: managed.Project) -> None:
    res = K.combine(four(an10, proj10), an10, proj10, goal="latency")
    frozen = {c.name for c in proj10.components if c.ownership != "owned"}
    assert frozen and all(not (set(o["scope"]["components"]) & frozen) for o in res["options"])
    assert all(any(n["component"] in frozen and "read only" in n["why"] for n in o["not_touched"]) for o in res["options"])


def test_the_whole_design_kind_is_used_when_the_union_is_every_owned_component(an10: dict, proj10: managed.Project) -> None:
    owned = [c.name for c in proj10.owned()]
    raw = K.build_raw([{"id": "O1", "title": "a", "approach": "x", "scope": {"components": owned[:6]}, "touches_stages": ["cross_go"], "techniques": [], "interface_changes": [],
                        "cost": {"iterations": {"low": 1, "high": 2}}, "risk": {"gates": ["g"], "contract_change": False, "needs_eqy": False, "needs_board": False, "summary": "s"}},
                       {"id": "O2", "title": "b", "approach": "y", "scope": {"components": owned[6:]}, "touches_stages": ["decide"], "techniques": [], "interface_changes": [],
                        "cost": {"iterations": {"low": 1, "high": 7}}, "risk": {"gates": ["g"], "contract_change": False, "needs_eqy": False, "needs_board": False, "summary": "s"}}],
                      {"metric": "latency_clocks", "low": 0, "high": 2, "basis": "guess", "cites": [], "basis_note": "x"}, owned)
    assert raw["scope"]["kind"] == "whole_design" and raw["cost"]["iterations"] == {"low": 1, "high": 8}


# ---- the generator and the CLI ------------------------------------------------------------------------------------------------------------

@needs_prompts
def test_improve_adds_the_combined_options_and_the_record_says_so(an10: dict, proj10: managed.Project) -> None:
    doc = doc_of(single("O1", "tx_frame_src", "fs_start"), single("O2", "core", "cross_go"), single("O3", "trade_decision", "decide"),
                 single("O4", "rx_path", "rx_mac", scope={"kind": "whole_design", "components": [c.name for c in proj10.owned()]}))
    rec = G.improve(an10, "lower latency", proj10, lambda s, u: json.dumps(doc), model_info={"model": "fake"})
    assert rec["status"] == "options" and rec["attempts"] == 1
    origins = [o["origin"] for o in rec["options"]]
    assert origins.count("model") == 4 and origins.count("combiner") == len(rec["options"]) - 4 > 0
    assert rec["combiner"]["offered"] and rec["options_hash"] == G._sha(json.dumps(rec["options"], sort_keys=True))
    off = G.improve(an10, "lower latency", proj10, lambda s, u: json.dumps(doc), model_info={"model": "fake"}, combiner=False)
    assert all(o["origin"] if "origin" in o else True for o in off["options"]) and not [o for o in off["options"] if o.get("origin") == "combiner"] and "combiner" not in off
    text = C.render(rec, an10)
    assert "COMBINED by code from" in text and "combinations not offered" in text


@needs_prompts
def test_a_question_and_a_failure_get_no_combined_options(an10: dict, proj10: managed.Project) -> None:
    q = G.improve(an10, "make it faster", proj10, None)
    assert q["status"] == "question" and "combiner" not in q and not q["options"]
    f = G.improve(an10, "lower latency", proj10, lambda s, u: "no json")
    assert f["status"] == "failed" and "combiner" not in f


# ---- prior runs and the truth -----------------------------------------------------------------------------------------------------------

def _prior_doc() -> dict:
    import yaml
    return yaml.safe_load((ROOT / "designs" / "b96_kr260_10g" / "prior_runs.yaml").read_text())


def test_prior_run_values_match_the_committed_measurements() -> None:
    doc = _prior_doc()
    post = json.loads((ROOT / "results" / "b97" / "postroute.json").read_text())
    assert {r["name"] for r in doc["runs"]} == {"agent_cdc", "hand_ref", "agent_both", "all3"}
    for r in doc["runs"]:
        ev = {e["id"]: e for e in r["evidence"]}
        assert ev["gain"]["value"] == 11 - post[r["name"]]["sim_clocks"] and ev["wns"]["value"] == post[r["name"]]["wns_ns"]
        for e in r["evidence"]:
            assert (ROOT / e["file"]).is_file()
        if "sim_after_97c" in ev:
            sim = json.loads((ROOT / ev["sim_after_97c"]["file"]).read_text())
            assert sim["tick_to_trade_digital_sim"]["gt_rxdata_price_word_to_gt_txdata_order_start_clocks"] == ev["sim_after_97c"]["value"] == 11 - ev["gain"]["value"]
    both, all3 = (next(r for r in doc["runs"] if r["name"] == n) for n in ("agent_both", "all3"))
    assert {e["id"]: e["value"] for e in both["evidence"]}["board_cut"] == 2 and {e["id"]: e["value"] for e in all3["evidence"]}["board_cut"] == 4


def test_the_back_test_fixtures_never_see_the_truth(an10: dict) -> None:
    for fx in (FX10, FXC):
        assert not (fx / "prior_runs.yaml").exists()
        an = A.analyse(fx, build_dir=fx / "evidence")
        assert "prior_runs" not in an and not [f for f in an["facts"].values() if f["origin"] == "prior_run"]
        assert not [s for s in an["sources"] if "/truth/" in s["file"] or "b97" in s["file"] or "postroute" in s["file"]]
        for p in fx.rglob("*"):
            if p.is_file() and p.suffix in (".yaml", ".json", ".rpt", ".sv", ".v", ".txt", ".md", ".tcl"):
                t = p.read_text(errors="ignore")
                assert "agent_both" not in t and "all3" not in t and "hand_ref" not in t, p
    assert not any(f["origin"] == "prior_run" for f in an10["facts"].values())


def test_prior_runs_become_facts_when_the_chain_has_the_stages(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    shutil.copytree(FX10, fx)
    shutil.copy(ROOT / "designs" / "b96_kr260_10g" / "prior_runs.yaml", fx / "prior_runs.yaml")
    an = A.analyse(fx, build_dir=fx / "evidence")
    assert [r["name"] for r in an["prior_runs"]] == ["agent_cdc", "hand_ref", "agent_both", "all3"]
    f = an["facts"]["prior.all3.gain"]
    assert f["origin"] == "prior_run" and f["value"] == 3 and f["file"] == "results/b97/postroute.json"
    assert an["hash"] != A.analyse(FX10, build_dir=FX10 / "evidence")["hash"]


def test_the_current_design_lists_but_does_not_use_runs_measured_on_another_chain() -> None:
    an = A.analyse(ROOT / "designs" / "b96_kr260_10g", build_dir=FX10 / "evidence")
    assert an["prior_runs"] == [] and any("prior_runs.yaml" in n and "cross_go" in n for n in an["notes"])


def test_an_exact_measured_set_replaces_the_sum_and_ranks_first(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    shutil.copytree(FX10, fx)
    shutil.copy(ROOT / "designs" / "b96_kr260_10g" / "prior_runs.yaml", fx / "prior_runs.yaml")
    an = A.analyse(fx, build_dir=fx / "evidence")
    proj = managed.load(fx)
    opts = checked(an, proj, single("O1", "tx_frame_src", "fs_start", 0, 1), single("O2", "core", "cross_go", 0, 1), single("O3", "trade_decision", "decide", 0, 1))
    res = K.combine(opts, an, proj, goal="latency")
    meas = [o for o in res["options"] if o["gain"]["basis"] == "measurement"]
    assert {frozenset(o["touches_stages"]) for o in meas} >= {frozenset({"cross_go", "decide"}), frozenset({"cross_go", "decide", "fs_start"})} - {frozenset({"cross_go", "decide", "fs_start"})}
    pair = next(o for o in res["options"] if set(o["touches_stages"]) == {"cross_go", "decide"})
    assert (pair["gain"]["low"], pair["gain"]["high"]) == (2, 2) and "prior.agent_both.gain" in pair["gain"]["cites"] and "Measured earlier" in pair["gain"]["basis_note"]
    assert res["options"][0]["gain"]["basis"] == "measurement"


def test_the_scoring_code_is_the_code_brief_104_used() -> None:
    """Brief 104A re-runs the same back-test with the scoring code unchanged: flow/options/backtest.py is byte-identical to its 104 version."""
    sha = hashlib.sha256((ROOT / "flow" / "options" / "backtest.py").read_bytes()).hexdigest()
    assert sha == "ce03d1c40dc551feded01a8371912e522b09540b2e39808749936d24b7170187"


# ---- the CLI keeps the combined options consistent ---------------------------------------------------------------------------------------------

def test_edit_of_a_combined_option_is_refused_and_more_rebuilds_the_combinations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    from test_104_options import FakeResolver, ns, wide
    if not _prompts_ok():
        pytest.skip("private prompts are not available here")
    d = tmp_path / "d"
    shutil.copytree(FX10, d)
    first = doc_of(single("O1", "tx_frame_src", "fs_start"), single("O2", "core", "cross_go"), wide(id="O3"))
    more = doc_of(single("O1", "trade_decision", "decide"), single("O2", "tx_mac", "mac_preamble"), wide(id="O3", touches_stages=["rx_mac"], gain={"metric": "latency_clocks", "low": 0, "high": 1, "basis": "guess", "cites": [], "basis_note": "no basis"}))
    res = FakeResolver([json.dumps(first), json.dumps(more)])
    monkeypatch.setattr(C, "_resolver", lambda a, dd, o: res)
    assert C.improve_cmd(ns(d, "lower latency"), main_fn=None) == 0
    st = json.loads(C.state_path(d).read_text())["current"]["options"]
    assert [o["id"] for o in st[:3]] == ["O1", "O2", "O3"] and st[3]["origin"] == "combiner" and set(st[3]["combined_from"]) <= {"O1", "O2", "O3"}
    capsys.readouterr()
    assert C.improve_cmd(ns(d, "x", edit=4), main_fn=None) == 2 and "built by the combiner" in capsys.readouterr().err
    assert C.improve_cmd(ns(d, more=True), main_fn=None) == 0
    cur = json.loads(C.state_path(d).read_text())["current"]["options"]
    assert len([o for o in cur if o["origin"] == "model"]) == 6 and len({o["id"] for o in cur}) == len(cur)
    assert json.loads(C.state_path(d).read_text())["current"]["combiner"]["considered"] == 57      # every subset of the six singles of both rounds (2^6 - 6 - 1)


def _prompts_ok() -> bool:
    from test_104_options import _prompts_available
    return _prompts_available()
