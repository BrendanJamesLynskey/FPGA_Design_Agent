"""Brief 104C: the menu rule does not depend on the order in which the model listed its options. The combiner's ties (many parts claim 0 to 1 clock) used to be broken by list position;
now they are broken by the stage file's timing headroom and then by content only. Planted options throughout; no model is called."""

from __future__ import annotations

import copy
import itertools
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_104_options import FX10, opt  # noqa: E402
from test_104b_split import bundle, checked, ic  # noqa: E402

from agent.core import managed  # noqa: E402
from flow.options import analysis as A  # noqa: E402
from flow.options import combine as K  # noqa: E402
from flow.options import schema as S  # noqa: E402


@pytest.fixture(scope="module")
def an10() -> dict:
    return A.analyse(FX10, build_dir=FX10 / "evidence")


@pytest.fixture()
def proj10() -> managed.Project:
    return managed.load(FX10)


def model_options(an: dict, proj: managed.Project) -> list[dict]:
    """Four valid model options in the 104A shape: one stage alone, three bundles that overlap in stages (so the splitter has ties to break)."""
    return checked(an, proj,
                   opt(id="O1", scope={"kind": "modules", "components": ["core"]}, touches_stages=["cross_go"]),
                   bundle("O2", ["decide", "fs_start", "mac_preamble"], 1, 3, [ic("decide", "fire")]),
                   bundle("O3", ["rx_descramble", "rx_mac", "fs_start"], 0, 3),
                   bundle("O4", ["mac_preamble", "rx_mac"], 0, 2))


def menu(an: dict, proj: dict, opts: list[dict], **kw) -> dict:
    rec = K.apply({"options": copy.deepcopy(opts)}, an, proj, goal="latency", **kw)
    return rec


def content(rec: dict) -> list[tuple]:
    """Everything a user sees of the derived options except their place in the list: id, origin, stages, scope, gain, where they came from."""
    out = []
    for o in rec["options"]:
        if o.get("origin", "model") == "model":
            continue
        out.append((o["id"], o["origin"], tuple(o["touches_stages"]), tuple(o["scope"]["components"]), o["gain"]["low"], o["gain"]["high"], o["gain"]["basis"], o["gain"]["basis_note"],
                    tuple(o.get("combined_from") or ()), o.get("split_from"), o["title"], o["approach"]))
    return sorted(out)


def test_the_menu_is_the_same_for_every_order_of_the_models_options(an10: dict, proj10: managed.Project) -> None:
    opts = model_options(an10, proj10)
    assert len(opts) == 4
    base = menu(an10, proj10, opts)
    want = content(base)
    assert any(c[1] == "combiner" for c in want) and any(c[1] == "splitter" for c in want)
    for perm in itertools.permutations(opts):
        got = menu(an10, proj10, list(perm))
        assert content(got) == want, [o["id"] for o in perm]
        assert got["combiner"]["offered"] == base["combiner"]["offered"]
        assert got["splitter"]["offered"] == base["splitter"]["offered"]


def test_the_menu_is_the_same_with_the_cap_lifted_and_with_a_small_cap(an10: dict, proj10: managed.Project) -> None:
    opts = model_options(an10, proj10)
    rng = random.Random(104)
    for cap in (1000, 2, 3):
        want = content(menu(an10, proj10, opts, cap=cap))
        for _ in range(12):
            p = list(opts)
            rng.shuffle(p)
            assert content(menu(an10, proj10, p, cap=cap)) == want


def test_the_menu_does_not_depend_on_the_models_option_ids(an10: dict, proj10: managed.Project) -> None:
    opts = model_options(an10, proj10)
    relabel = {"O1": "Z9", "O2": "A1", "O3": "M5", "O4": "B2"}
    other = copy.deepcopy(opts)
    for o in other:
        o["id"] = relabel[o["id"]]

    def shape(rec: dict) -> list[tuple]:
        lab = {v: k for k, v in relabel.items()} if any(o["id"] in relabel.values() for o in rec["options"]) else {}
        return sorted((o["origin"], tuple(o["touches_stages"]), o["gain"]["low"], o["gain"]["high"], tuple(sorted(lab.get(i, i) for i in o.get("combined_from") or ())))
                      for o in rec["options"] if o.get("origin", "model") != "model")
    a, b = menu(an10, proj10, opts), menu(an10, proj10, other)
    assert [t[1:4] for t in shape(a)] == [t[1:4] for t in shape(b)]
    assert [x for x in (o["touches_stages"] for o in a["options"] if o["origin"] == "combiner")] == [x for x in (o["touches_stages"] for o in b["options"] if o["origin"] == "combiner")]


def test_ties_are_broken_by_the_stage_files_timing_headroom(an10: dict, proj10: managed.Project) -> None:
    """Three single stages, equal claims. The pair offered is the one whose tightest stage has the most slack; changing the slack changes the pair; the order of listing does not."""
    singles = checked(an10, proj10,
                      opt(id="O1", scope={"kind": "modules", "components": ["core"]}, touches_stages=["cross_go"]),
                      bundle("O2", ["decide", "fs_start"], 0, 2),
                      bundle("O3", ["mac_preamble", "rx_mac"], 0, 2))
    slack = {"cross_go": 4.19, "decide": 1.7, "fs_start": 1.4, "mac_preamble": 1.1, "rx_mac": 0.6}

    def pairs(a: dict, cap: int) -> list[frozenset]:
        return [frozenset(o["touches_stages"]) for o in menu(a, proj10, singles, cap=cap)["options"] if o["origin"] == "combiner" and len(o["combined_from"]) == 2]

    def with_slack(sl: dict) -> dict:
        a = copy.deepcopy(an10)
        for s in a["latency"]["stages"]:
            s["setup_slack_ns"] = sl.get(s["id"])
        return a
    a1 = with_slack(slack)
    first = pairs(a1, 2)
    assert first == [frozenset({"cross_go", "decide"})]                       # the weakest stage, decide (1.7), beats fs_start (1.4), mac_preamble (1.1), rx_mac (0.6)
    assert pairs(with_slack({**slack, "decide": 0.2}), 2) == [frozenset({"cross_go", "fs_start"})]
    assert pairs(with_slack({k: v for k, v in slack.items() if k != "decide"}), 2) == [frozenset({"cross_go", "fs_start"})]       # no slack figure ranks below every known one


def test_leximin_breaks_a_tie_in_the_tightest_stage(an10: dict) -> None:
    assert K.headroom_key(["a", "b", "c"], {"a": 1.0, "b": 2.0, "c": 5.0}) < K.headroom_key(["a", "b", "d"], {"a": 1.0, "b": 2.0, "d": 3.0})
    assert K.headroom_key(["a", "b"], {"a": 1.0, "b": 9.0}) < K.headroom_key(["a", "c"], {"a": 0.5, "c": 9.0})
    assert K.headroom_key(["a", "z"], {"a": 1.0}) > K.headroom_key(["a", "b"], {"a": 1.0, "b": 0.1})


def test_no_offered_option_is_outside_the_stage_files_bounds_in_any_order(an10: dict, proj10: managed.Project) -> None:
    opts = model_options(an10, proj10)
    for perm in itertools.permutations(opts):
        for cap in (None, 1000):
            for o in menu(an10, proj10, list(perm), cap=cap)["options"]:
                if o["gain"]["metric"] != "latency_clocks":
                    continue
                ceil, _ = S.ceiling("latency_clocks", o["touches_stages"], o["scope"]["components"], an10)
                assert o["gain"]["high"] <= ceil and o["gain"]["low"] <= o["gain"]["high"], (o["id"], [p["id"] for p in perm])


def test_the_cap_is_kept_in_any_order(an10: dict, proj10: managed.Project) -> None:
    opts = model_options(an10, proj10)
    for perm in itertools.permutations(opts):
        rec = menu(an10, proj10, list(perm))
        assert len([o for o in rec["options"] if o["origin"] == "combiner"]) <= K.MAX_COMBINED
    for cap in (1, 2, 3):
        assert len([o for o in menu(an10, proj10, opts, cap=cap)["options"] if o["origin"] == "combiner"]) <= cap


def test_a_truncated_pool_drops_the_same_options_in_any_order(an10: dict, proj10: managed.Project, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(K, "MAX_POOL", 3)
    opts = model_options(an10, proj10)
    want = content(menu(an10, proj10, opts))
    for perm in itertools.permutations(opts):
        assert content(menu(an10, proj10, list(perm))) == want


def test_two_bundles_that_give_the_same_part_are_resolved_by_content(an10: dict, proj10: managed.Project) -> None:
    """O2 and O3 both contain fs_start; whichever bundle supplies the part, it is the same one whatever the listing."""
    opts = checked(an10, proj10, bundle("O2", ["decide", "fs_start"], 0, 2), bundle("O3", ["fs_start", "mac_preamble"], 0, 1))
    a, b = menu(an10, proj10, opts), menu(an10, proj10, list(reversed(opts)))
    assert content(a) == content(b)
    assert a["splitter"]["report"] == b["splitter"]["report"]
