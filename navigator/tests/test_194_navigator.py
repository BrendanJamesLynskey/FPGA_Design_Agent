"""Brief 194: the profile picker, the switch drawer's arguments and the confirm-settings step of the Navigator's Start page."""

import json

import pytest
import yaml

from navigator.tests.test_103s2_navigator import FakeSpawner, TASK, env, make_rc  # noqa: F401  (env is a fixture)


def _argv(rc, sp, body):
    r = rc.start(body)
    return r, (sp.calls[0]["argv"] if sp.calls else None)


def test_the_options_carry_the_profiles_and_the_switch_schema(env):
    rc, _, _ = make_rc(env)
    o = rc.options()
    assert [p["name"] for p in o["profiles"]][:2] == ["prototype", "standard"] and all(p["summary"] and p["extra_time"] for p in o["profiles"])
    assert {w["name"] for w in o["switches"]} >= {"seeds", "mutation_floor", "post_synth_sim", "timing_sim"}


def test_the_profile_and_overrides_become_cli_arguments(env):
    rc, _, sp = make_rc(env)
    body = {**TASK, "profile": "thorough", "switches": {"seeds": 12, "timing_sim": "on", "equivalence": True}}
    r, argv = _argv(rc, sp, body)
    assert r["started"], r
    assert argv[argv.index("--verif-profile") + 1] == "thorough"
    sets = [argv[i + 1] for i, a in enumerate(argv) if a == "--set"]
    assert sorted(sets) == ["seeds=12", "timing_sim=on"]            # equivalence is the profile's own value: not passed
    assert r["record"]["summary"]["overrides"]["seeds"] == {"profile_value": 8, "value": 12}


@pytest.mark.parametrize("patch,word", [({"profile": "fast"}, "profile"), ({"switches": {"seeds": 0}}, "seeds"), ({"switches": {"nope": 1}}, "switches"),
                                        ({"switches": {"timing_sim": "maybe"}}, "timing_sim"), ({"switches": {"mutation_floor": 50}}, "floor")])
def test_a_bad_profile_or_switch_is_refused_before_anything_starts(env, patch, word):
    rc, _, sp = make_rc(env)
    r = rc.start({**TASK, **patch})
    assert r["started"] is False and word in r["refused"] and not sp.calls


def test_the_proposals_go_to_the_interview_not_to_a_second_screen(env):
    from agent.graph import settings as VS
    rc, _, sp = make_rc(env)
    r = rc.start({**TASK, "profile": "ip_release"})
    assert r["started"], r
    argv = sp.calls[0]["argv"]
    f = argv[argv.index("--settings") + 1]
    assert argv[argv.index("--interview") + 1] == "on"                       # the questions come up on the Live page
    doc = VS.load_proposals(f)
    assert doc["settings"]["board"]["value"] == "nexys_a7_100t" and doc["settings"]["profile"]["value"] == "ip_release"
    assert doc["settings"]["board"]["sources"] and all(e["status"] in ("proposed", "ask") for e in doc["settings"].values())   # nothing is confirmed here
    assert "settings_doc" not in r["record"]["summary"] and r["record"]["summary"]["settings"].startswith("proposed to the interview")
    assert [q[0] for q in VS.questions(doc)] == list(VS.KEYS)


def test_a_project_resume_takes_no_settings_flags(env):
    rc, _, sp = make_rc(env)
    from navigator.tests.test_103s2_navigator import PROJ
    assert rc.start(dict(PROJ))["started"]
    assert "--settings" not in sp.calls[0]["argv"]


def test_the_live_summary_shows_the_profile_and_overrides(tmp_path):
    from navigator import summary
    rd = tmp_path / "20261123-000000-abcd"
    rd.mkdir()
    (rd / "policy.json").write_text(json.dumps({"profile": "ip_release", "overrides": {"seeds": {"profile_value": 8, "value": 12}}, "set_by": "command line"}))
    assert summary._profile(rd) == {"profile": "ip_release", "overrides": {"seeds": {"profile_value": 8, "value": 12}}, "set_by": "command line"}
    assert summary._profile(tmp_path) is None
