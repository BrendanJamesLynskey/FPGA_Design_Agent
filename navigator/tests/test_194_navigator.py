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
    assert o["settings_keys"] == ["board", "part", "speed_grade", "reference_clocks", "io_standards", "phys", "interfaces", "profile"]


def test_the_profile_and_overrides_become_cli_arguments(env):
    rc, _, sp = make_rc(env)
    body = {**TASK, "profile": "thorough", "switches": {"seeds": 12, "timing_sim": "on", "equivalence": True}}
    body["settings"] = {**TASK["settings"], "profile": {"value": "thorough", "confirmed": True}}
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
    body = {**TASK, **patch}
    if "profile" in patch:
        body["settings"] = {**TASK["settings"], "profile": {"value": patch["profile"], "confirmed": True}}
    r = rc.start(body)
    assert r["started"] is False and word in r["refused"] and not sp.calls


def test_start_is_gated_by_confirmed_settings(env):
    rc, _, sp = make_rc(env)
    no = {k: v for k, v in TASK.items() if k != "settings"}
    assert "confirm the settings first" in rc.start(no)["refused"]
    half = {**TASK, "settings": {**TASK["settings"], "part": {**TASK["settings"]["part"], "confirmed": False}}}
    assert "settings not confirmed: part" in rc.start(half)["refused"]
    empty = {**TASK, "settings": {**TASK["settings"], "phys": {"value": [], "confirmed": True}}}
    assert "phys" in rc.start(empty)["refused"] and "empty" in rc.start(empty)["refused"]
    wrong_board = {**TASK, "settings": {**TASK["settings"], "board": {"value": "kr260", "confirmed": True}}}
    assert "board" in rc.start(wrong_board)["refused"]
    unknown_key = {**TASK, "settings": {**TASK["settings"], "evil": {"value": "x", "confirmed": True}}}
    r = rc.start(unknown_key)                        # an extra key is ignored: the document is rebuilt from the folder's proposal
    assert r["started"] and not any("evil" in str(a) for a in sp.calls[0]["argv"])
    assert len([c for c in sp.calls]) == 1


def test_the_run_reads_a_settings_file_the_service_wrote(env):
    rc, _, sp = make_rc(env)
    edited = {**TASK, "settings": {**TASK["settings"], "speed_grade": {"value": "-2", "confirmed": True}}}
    r = rc.start(edited)
    assert r["started"], r
    argv = sp.calls[0]["argv"]
    f = argv[argv.index("--settings") + 1]
    doc = yaml.safe_load(open(f).read())
    assert doc["settings"]["speed_grade"]["value"] == "-2" and doc["settings"]["speed_grade"]["status"] == "confirmed"
    assert "edited by the user in the navigator" in doc["settings"]["speed_grade"]["sources"][-1]
    assert r["record"]["summary"]["settings"]["speed_grade"] == "edited" and "settings_doc" not in r["record"]["summary"]
    from agent.graph import settings as VS
    assert VS.load_confirmed(f)["board"] == "nexys_a7_100t"                  # what `agent run --settings` accepts


def test_propose_is_read_only_and_lists_sources(env):
    rc, _, sp = make_rc(env)
    p = rc.propose("c10_dds_sine", "nexys_a7_100t")
    assert p["settings"]["part"]["value"] == "xc7a100tcsg324-1" and p["settings"]["part"]["sources"]
    assert all(e["status"] in ("proposed", "ask") for e in p["settings"].values()) and not sp.calls
    with pytest.raises(Exception, match="task"):
        rc.propose("nope", None)


def test_the_live_summary_shows_the_profile_and_overrides(tmp_path):
    from navigator import summary
    rd = tmp_path / "20261123-000000-abcd"
    rd.mkdir()
    (rd / "policy.json").write_text(json.dumps({"profile": "ip_release", "overrides": {"seeds": {"profile_value": 8, "value": 12}}, "set_by": "command line"}))
    assert summary._profile(rd) == {"profile": "ip_release", "overrides": {"seeds": {"profile_value": 8, "value": 12}}, "set_by": "command line"}
    assert summary._profile(tmp_path) is None
