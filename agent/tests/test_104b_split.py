"""Brief 104B: the per-stage splitter. Code derives per-stage options from a bundled option, each bounded by the stage file, scoped to its own stage's components, with a
provenance link to the bundle; coupled stages and unattributable interface changes are never split; a part that cannot be backed is dropped with a reason; the combiner then runs
over the singles and the parts. Planted bundles throughout; no model is called."""

from __future__ import annotations

import copy
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_104_options import FX10, doc_of, opt  # noqa: E402

from agent.core import managed  # noqa: E402
from flow.options import analysis as A  # noqa: E402
from flow.options import combine as K  # noqa: E402
from flow.options import schema as S  # noqa: E402
from flow.options import split as SP  # noqa: E402


@pytest.fixture(scope="module")
def an10() -> dict:
    return A.analyse(FX10, build_dir=FX10 / "evidence")


@pytest.fixture()
def proj10() -> managed.Project:
    return managed.load(FX10)


COMP = {"decide": "trade_decision", "fs_start": "tx_frame_src", "mac_preamble": "tx_mac", "cross_go": "core", "rx_descramble": "rx_pcs", "rx_mac": "rx_mac", "rx_blk": "rx_pcs", "tx_encode": "tx_pcs"}


def bundle(i: str, stages: list[str], low: float = 0, high: float = 3, ics: list[dict] | None = None, basis: str = "model", **kw) -> dict:
    comps = sorted({COMP[s] for s in stages})
    cites = [f"stage.{s}.clocks" for s in stages] + [f"stage.{s}.removable" for s in stages]
    g = {"metric": "latency_clocks", "low": low, "high": high, "basis": basis, "cites": cites if basis == "model" else [], "basis_note": "stage file"}
    d = dict(id=i, title=f"Bundle {i}", scope={"kind": "modules", "components": comps}, touches_stages=stages, techniques=["merge_stages"], gain=g,
             approach=f"Remove the register in {COMP[stages[0]]} ({stages[0]}). Then do the same in {COMP[stages[-1]]} ({stages[-1]}). Nothing else changes.", interface_changes=ics or [])
    d.update(kw)
    return opt(**d)


def checked(an: dict, proj: managed.Project, *raw: dict) -> list[dict]:
    r = S.check_options(doc_of(*raw), an, proj, goal="latency", min_options=1)
    assert not r["rejected"], r["rejected"]
    return r["options"]


def ic(stage: str, port: str = "x") -> dict:
    return {"component": COMP[stage], "port": port, "change": "one clock earlier"}


# ---- the rule ---------------------------------------------------------------------------------------------------------------------

def test_a_bundle_gives_one_part_per_stage_with_its_own_bound_scope_and_provenance(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O3", ["decide", "fs_start", "mac_preamble"], 1, 3, [ic("decide", "fire"), ic("fs_start", "s_valid")]))
    res = SP.split(b, an10, proj10, goal="latency")
    assert res["split"] == ["O3"] and len(res["parts"]) == 3
    by = {p["touches_stages"][0]: p for p in res["parts"]}
    assert set(by) == {"decide", "fs_start", "mac_preamble"}
    for s, p in by.items():
        assert p["origin"] == "splitter" and p["split_from"] == "O3" and p["split_bundle_gain"] == [1, 3]
        assert p["scope"]["components"] == [COMP[s]] and p["scope"]["kind"] == "modules"                   # only that stage's component
        assert (p["gain"]["low"], p["gain"]["high"]) == (0, 1)                                              # the stage file's removable clock; the bundle's low is not forced on one part
        assert p["gain"]["basis"] == "model" and f"stage.{s}.clocks" in p["gain"]["cites"]
        assert p["gain"]["ceiling"] == 1 and s in p["title"] and "O3" in p["approach"]
    assert [x["port"] for x in by["decide"]["interface_changes"]] == ["fire"] and [x["port"] for x in by["fs_start"]["interface_changes"]] == ["s_valid"] and by["mac_preamble"]["interface_changes"] == []
    assert by["decide"]["risk"]["contract_change"] and by["decide"]["risk"]["needs_owner_approval"]       # a part that carries an interface change is flagged by the checker's own rule
    assert not by["mac_preamble"]["risk"]["needs_owner_approval"]
    assert res["report"][0]["not_split"] is None and len(res["report"][0]["parts"]) == 3


def test_every_part_passes_the_same_checks_as_a_model_option(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O3", ["decide", "fs_start", "mac_preamble"], 0, 3, [ic("decide", "fire")]))
    for p in SP.split(b, an10, proj10, goal="latency")["parts"]:
        raw = {k: p[k] for k in S.OPTION_KEYS if k in p}
        raw["gain"] = {k: p["gain"][k] for k in S.GAIN_KEYS if k in p["gain"]}
        raw["risk"] = {k: p["risk"][k] for k in S.RISK_KEYS if k in p["risk"]}
        again, probs = S.check_single(raw, p["id"], an10, proj10, goal="latency")
        assert again is not None, probs


def test_a_part_never_claims_more_than_the_bundle_or_the_stage_file_backs(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["decide", "fs_start", "cross_go"], 0, 1))       # the bundle itself claims at most 1 clock
    for p in SP.split(b, an10, proj10, goal="latency")["parts"]:
        assert p["gain"]["high"] <= 1
    b = checked(an10, proj10, bundle("O2", ["cross_go", "fs_start"], 0, 2))                  # cross_go adds 4 clocks, the stage file says 1 is removable
    parts = SP.split(b, an10, proj10, goal="latency")["parts"]
    assert {p["touches_stages"][0]: p["gain"]["high"] for p in parts} == {"cross_go": 1, "fs_start": 1}
    for o in parts:
        cap, _ = S.ceiling("latency_clocks", o["touches_stages"], o["scope"]["components"], an10)
        assert o["gain"]["high"] <= cap


def test_the_bundles_low_end_forces_a_low_end_on_the_parts_when_the_others_cannot_give_it(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["decide", "fs_start"], 2, 2))      # both stages can give at most 1 each: each must give exactly 1
    parts = SP.split(b, an10, proj10, goal="latency")["parts"]
    assert [(p["gain"]["low"], p["gain"]["high"]) for p in parts] == [(1, 1), (1, 1)]


def test_a_part_that_cannot_be_backed_is_dropped_with_the_reason(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["decide", "tx_encode"], 0, 1))        # tx_encode: the stage file lists 0 removable clocks
    res = SP.split(b, an10, proj10, goal="latency")
    assert [p["touches_stages"] for p in res["parts"]] == [["decide"]]
    drop = res["report"][0]["dropped"]
    assert drop[0]["stages"] == ["tx_encode"] and "no gain can be backed" in drop[0]["reason"]


def test_a_guess_bundle_gives_guess_parts_with_no_cited_basis(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["decide", "fs_start"], 0, 2, basis="guess"))
    parts = SP.split(b, an10, proj10, goal="latency")["parts"]
    assert parts and all(p["gain"]["basis"] == "guess" and p["gain"]["cites"] == [] for p in parts)


# ---- coupling: never split across it ----------------------------------------------------------------------------------------------

def test_stages_sharing_one_interface_change_stay_one_part(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["rx_blk", "rx_descramble", "decide"], 0, 2, [ic("rx_blk", "x_d")]))      # one change on rx_pcs spans both of its stages
    res = SP.split(b, an10, proj10, goal="latency")
    assert sorted(sorted(p["touches_stages"]) for p in res["parts"]) == [["decide"], ["rx_blk", "rx_descramble"]]
    assert res["report"][0]["coupled"][0]["rule"] == "shared_interface"
    grp = next(p for p in res["parts"] if len(p["touches_stages"]) == 2)
    assert grp["scope"]["components"] == ["rx_pcs"] and grp["gain"]["high"] == 1       # the group's own bound: rx_blk 0 + rx_descramble 1


def test_a_bundle_whose_every_stage_is_coupled_is_not_split(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["rx_blk", "rx_descramble"], 0, 1, [ic("rx_blk", "x_d")]))
    res = SP.split(b, an10, proj10, goal="latency")
    assert res["parts"] == [] and res["split"] == []
    assert "coupled" in res["report"][0]["not_split"] and res["report"][0]["coupled"]


def test_an_interface_change_that_belongs_to_no_stage_stops_the_split(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["decide", "fs_start"], 0, 2, [{"component": "tx_mac", "port": "start", "change": "the preamble starts with start"}],
                                      scope={"kind": "modules", "components": ["trade_decision", "tx_frame_src", "tx_mac"]}))
    res = SP.split(b, an10, proj10, goal="latency")
    assert res["parts"] == [] and "belongs to none of the bundle's stages" in res["report"][0]["not_split"]


def test_the_stage_file_can_mark_stages_as_coupled(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    shutil.copytree(FX10, fx)
    f = fx / "latency_stages.yaml"
    f.write_text(re.sub(r"(      - id: fs_start\n)", r"\1        coupled_with: [decide]\n", f.read_text()))
    an = A.analyse(fx, build_dir=fx / "evidence")
    proj = managed.load(fx)
    assert next(s for s in an["latency"]["stages"] if s["id"] == "fs_start")["coupled_with"] == ["decide"]
    assert all("coupled_with" not in s for s in an["latency"]["stages"] if s["id"] != "fs_start")
    b = checked(an, proj, bundle("O1", ["decide", "fs_start", "cross_go"], 0, 3))
    res = SP.split(b, an, proj, goal="latency")
    assert sorted(sorted(p["touches_stages"]) for p in res["parts"]) == [["cross_go"], ["decide", "fs_start"]]
    assert [c["rule"] for c in res["report"][0]["coupled"]] == ["stage_file"]
    two = checked(an, proj, bundle("O2", ["decide", "fs_start"], 0, 2))                      # the planted bundle that must not split
    r2 = SP.split(two, an, proj, goal="latency")
    assert r2["parts"] == [] and "coupled" in r2["report"][0]["not_split"]


def test_back_test_analyses_are_unchanged_by_the_new_optional_stage_key() -> None:
    an = A.analyse(FX10, build_dir=FX10 / "evidence")
    assert all("coupled_with" not in s for s in an["latency"]["stages"])


# ---- what is not split ------------------------------------------------------------------------------------------------------------

def test_single_stage_slack_and_non_latency_options_are_not_split(an10: dict, proj10: managed.Project) -> None:
    one = checked(an10, proj10, bundle("O1", ["decide"], 0, 1))
    assert SP.split(one, an10, proj10, goal="latency")["parts"] == []
    b = checked(an10, proj10, bundle("O2", ["decide", "fs_start"], 0, 2))
    assert SP.split(b, an10, proj10, goal="timing")["parts"] == []            # only a latency request is split
    slack = copy.deepcopy(b[0])
    slack["gain"]["metric"] = "wns_ns"
    assert not SP._is_bundle(slack)


def test_a_stage_the_model_already_offers_alone_is_not_duplicated(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, bundle("O1", ["decide", "fs_start"], 0, 2), opt(id="O2", scope={"kind": "modules", "components": ["tx_frame_src"]}, touches_stages=["fs_start"],
                   gain={"metric": "latency_clocks", "low": 0, "high": 1, "basis": "model", "cites": ["stage.fs_start.clocks"], "basis_note": "one register"}))
    res = SP.split(opts, an10, proj10, goal="latency")
    assert [p["touches_stages"] for p in res["parts"]] == [["decide"]]
    assert "already offers" in res["report"][0]["dropped"][0]["reason"]


def test_a_blind_run_gets_no_technique_hint_and_the_clocks_bound(an10: dict, proj10: managed.Project) -> None:
    b = checked(an10, proj10, bundle("O1", ["cross_go", "decide"], 0, 2))
    parts = SP.split(b, an10, proj10, goal="latency", blind=True)["parts"]
    assert all(p["techniques"] == [] and "technique" not in p["approach"] for p in parts)
    assert {p["touches_stages"][0]: p["gain"]["high"] for p in parts} == {"cross_go": 2, "decide": 1}       # blind: the stage's own clocks (4 for cross_go), capped by the bundle's 2
    assert all(not any(c.endswith(".removable") for c in p["gain"]["cites"]) for p in parts)


# ---- the combiner over singles and parts -----------------------------------------------------------------------------------------

def _rec(opts: list[dict]) -> dict:
    return {"options": copy.deepcopy(opts)}


def test_the_combiner_builds_the_pair_the_model_never_offered_alone(an10: dict, proj10: managed.Project) -> None:
    """The 104A failure: cross_go offered alone, decide only inside bundles. The splitter supplies decide; the combiner adds it to cross_go."""
    opts = checked(an10, proj10, opt(id="O1", scope={"kind": "modules", "components": ["core"]}, touches_stages=["cross_go"]),
                   bundle("O2", ["decide", "fs_start", "mac_preamble"], 1, 3, [ic("decide", "fire")]))
    rec = K.apply(_rec(opts), an10, proj10, goal="latency", cap=1000)
    kinds = {o["id"]: o["origin"] for o in rec["options"]}
    assert "splitter" in kinds.values() and "combiner" in kinds.values()
    both = [o for o in rec["options"] if o["origin"] == "combiner" and set(o["touches_stages"]) == {"cross_go", "decide"}]
    assert len(both) == 1 and any(kinds[i] == "splitter" for i in both[0]["combined_from"])
    assert (both[0]["gain"]["low"], both[0]["gain"]["high"]) == (1, 2)      # the model's own cross_go (1 to 1) plus the part decide (0 to 1)
    assert rec["splitter"]["split"] == ["O2"] and {x["id"] for x in rec["splitter"]["offered"]} == {o["id"] for o in rec["options"] if o["origin"] == "splitter"}
    assert [o["n"] for o in rec["options"]] == list(range(1, len(rec["options"]) + 1)) and len({o["id"] for o in rec["options"]}) == len(rec["options"])


def test_the_split_bundle_is_replaced_by_its_parts_in_the_combiner_pool(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, opt(id="O1", scope={"kind": "modules", "components": ["core"]}, touches_stages=["cross_go"]), bundle("O2", ["decide", "fs_start"], 0, 2))
    rec = K.apply(_rec(opts), an10, proj10, goal="latency", cap=1000)
    assert all("O2" not in o["combined_from"] for o in rec["options"] if o["origin"] == "combiner")
    assert [o["id"] for o in rec["options"] if o["origin"] == "model"] == ["O1", "O2"]        # the bundle itself is still offered


def test_parts_of_one_bundle_never_add_up_to_more_than_the_bundle_claimed(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, bundle("O1", ["decide", "fs_start", "mac_preamble"], 0, 1))
    rec = K.apply(_rec(opts), an10, proj10, goal="latency", cap=1000)
    pairs = [o for o in rec["options"] if o["origin"] == "combiner"]
    assert pairs and all(o["gain"]["high"] <= 1 for o in pairs)
    assert any("count at most that bundle's own high end" in o["gain"]["basis_note"] for o in pairs)


def test_no_offered_option_is_outside_the_stage_files_bounds(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, opt(id="O1", scope={"kind": "modules", "components": ["core"]}, touches_stages=["cross_go"]),
                   bundle("O2", ["decide", "fs_start", "mac_preamble", "rx_descramble"], 1, 4, [ic("decide", "fire")]))
    rec = K.apply(_rec(opts), an10, proj10, goal="latency", cap=1000)
    assert rec["options"]
    for o in rec["options"]:
        cap, _ = S.ceiling("latency_clocks", o["touches_stages"], o["scope"]["components"], an10)
        assert o["gain"]["high"] <= cap, o["id"]
        assert o["gain"]["low"] <= o["gain"]["high"]


def test_apply_is_idempotent_and_the_splitter_can_be_switched_off(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, opt(id="O1", scope={"kind": "modules", "components": ["core"]}, touches_stages=["cross_go"]), bundle("O2", ["decide", "fs_start", "mac_preamble"], 0, 3))
    once = K.apply(_rec(opts), an10, proj10, goal="latency")
    again = K.apply(copy.deepcopy(once), an10, proj10, goal="latency")
    assert [(o["id"], o["origin"], o["touches_stages"]) for o in once["options"]] == [(o["id"], o["origin"], o["touches_stages"]) for o in again["options"]]
    off = K.apply(_rec(opts), an10, proj10, goal="latency", splitter=False)
    assert not any(o["origin"] == "splitter" for o in off["options"]) and "splitter" not in off


def test_a_non_latency_goal_records_no_parts(an10: dict, proj10: managed.Project) -> None:
    opts = checked(an10, proj10, bundle("O1", ["decide", "fs_start"], 0, 2))
    rec = K.apply(_rec(opts), an10, proj10, goal="timing")
    assert not any(o["origin"] == "splitter" for o in rec["options"]) and rec["splitter"]["split"] == []
