"""Brief 194: verification profiles, the interview questions and the run record. Scripted: no model, no tools."""


import pytest
import yaml

from agent.graph import assurance as A
from agent.graph import profiles as P
from agent.graph.spec_schema import shape_errors


# ---- the registry ---------------------------------------------------------------------------------------------------------------

def test_every_profile_resolves_and_has_a_summary():
    assert set(P.PROFILES) == set(P.SUMMARY)
    for n, sw in P.PROFILES.items():
        assert set(sw) == {s.name for s in P.SWITCHES}, n
        r = P.resolve(n)
        assert r["profile"] == n and r["overrides"] == {}


def test_standard_is_today_and_prototype_stops_at_v1():
    s = P.PROFILES["standard"]
    assert s["verif_level"] == "V3" and s["indep_spec_test"] is False and s["post_synth_sim"] is False   # what `agent run` does today
    assert P.PROFILES["prototype"]["verif_level"] == "V1" and P.PROFILES["prototype"]["random_sim"] is False


def test_profiles_are_cumulative_where_the_names_say_so():
    for lower, higher in (("standard", "thorough"), ("thorough", "ip_release"), ("thorough", "high_reliability")):
        lo, hi = P.PROFILES[lower], P.PROFILES[higher]
        for k, v in lo.items():
            if isinstance(v, bool) and v:
                assert hi[k], (lower, higher, k)
            elif isinstance(v, int) and not isinstance(v, bool):
                assert hi[k] >= v, (lower, higher, k)


def test_overrides_are_validated_and_recorded():
    r = P.resolve("standard", P.parse_sets(["seeds=5", "timing_sim=on", "uvm=pyuvm"]))
    assert r["effective"]["seeds"] == 5 and r["overrides"]["seeds"] == {"profile_value": 3, "value": 5}
    assert "uvm" in r["not_wired"]                                    # recorded, not run by the flow
    for bad in ("seeds=0", "seeds=x", "nonsense=1", "timing_sim=maybe", "lint", "seeds=999"):
        with pytest.raises(P.ProfileError):
            P.parse_sets([bad])
    with pytest.raises(P.ProfileError):
        P.resolve("fast")


def test_a_profile_never_lowers_a_v3_floor():
    with pytest.raises(P.ProfileError, match="floor"):
        P.resolve("standard", {"mutation_floor": 60})
    with pytest.raises(P.ProfileError, match="floor"):
        P.resolve("standard", {"seeds": 2})
    P.resolve("prototype", {"seeds": 1})                              # V1: the floors do not apply
    assert P.resolve("standard", {"mutation_floor": 90})["effective"]["mutation_floor"] == 90   # raising is allowed


def test_floors_follow_flow_verif_floors_yaml():
    floors = yaml.safe_load((P.__file__.rsplit("/agent/", 1)[0] + "/flow/verif_floors.yaml") and open(P.__file__.rsplit("/agent/", 1)[0] + "/flow/verif_floors.yaml").read())
    assert P.FLOORS["mutation_floor"] == floors["mutation_score_pct"]
    assert P.FLOORS["seeds"] == floors["seeds_min"]
    assert P.FLOORS["coverage_target"] == floors["functional_bins_pct"]


def test_old_flags_are_overrides_of_their_switches():
    r = P.from_cli(None, None, "V2", True)
    assert r["cfg"] == {"verif_level": "V2", "spec_tests": True}
    assert r["overrides"]["verif_level"] == {"profile_value": "V3", "value": "V2"}
    assert r["overrides"]["indep_spec_test"] == {"profile_value": False, "value": True}
    d = P.from_cli(None, None, None, False)                           # no flags: exactly today's run, nothing to record
    assert d["cfg"] == {"verif_level": "V3", "spec_tests": False} and d["overrides"] == {}


def test_method_mix_and_ip_release_gaps_are_named():
    assert P.method_mix_gap(P.PROFILES["standard"]) == []
    assert any("formal" in g for g in P.method_mix_gap(P.PROFILES["prototype"]))
    assert P.ip_release_ok(P.PROFILES["ip_release"]) == []
    assert any(g.startswith("equivalence") for g in P.ip_release_ok(P.PROFILES["standard"]))


def test_the_method_groups_the_policy_names_exist():
    pol = yaml.safe_load(open(P.__file__.rsplit("/agent/", 1)[0] + "/flow/method_mix_policy.yaml").read())
    assert {"simulation", "formal", "board"} <= set(pol["groups"])   # method_mix_gap reasons in these three groups


# ---- the interview side ---------------------------------------------------------------------------------------------------------

def test_the_proposed_profile_follows_the_spec_and_gives_a_reason():
    assert A.propose_profile({"requirements": [{"text": "A reusable IP block for the library"}]})[0] == "ip_release"
    assert A.propose_profile({"requirements": [{"text": "The FIFO must recover from a single event upset"}]})[0] == "high_reliability"
    assert A.propose_profile({"requirements": [{"text": "tick-to-trade latency under 100 ns"}]})[0] == "low_latency"
    assert A.propose_profile({"requirements": [{"text": "A quick look prototype"}]})[0] == "prototype"
    assert A.propose_profile({"requirements": [{"text": "A counter"}]})[0] == "standard"
    assert A.propose_profile({"verif_profile": "thorough"}) == ("thorough", "spec.yaml names it (thorough)")
    text, default, reason = A.profile_question({"requirements": [{"text": "A counter"}]})
    assert default == "standard" and reason and all(n in text for n in P.PROFILES)
    assert A.profile_from_answer("ip_release please", "standard") == "ip_release" and A.profile_from_answer("dunno", "standard") == "standard"


def test_structure_questions_only_for_high_reliability_and_name_the_cost():
    spec = {"requirements": [{"text": "A FIFO feeds a state machine and a counter"}]}
    assert A.structure_questions(spec, P.PROFILES["standard"]) == []
    qs = A.structure_questions(spec, P.PROFILES["high_reliability"])
    assert len(qs) == 3 and all(q[1] and q[2] for q in qs)
    assert "protect with ecc" == qs[0][1] and "cost:" in qs[0][2] or "measured" in qs[0][2]


def test_spec_fields_are_checked():
    assert shape_errors({"verif_profile": "ip_release", "timing_sim": True}) == []
    assert any("verif_profile" in e for e in shape_errors({"verif_profile": "fast"}))
    assert any("timing_sim" in e for e in shape_errors({"timing_sim": "yes"}))
