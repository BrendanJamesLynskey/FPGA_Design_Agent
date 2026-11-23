"""Brief 195: reproducible examples. The compare logic (deterministic against variable fields), the pre-flight guards, the command line a re-run uses, the result
extraction, and redaction of the committed reference records. No model call, no Vivado, no simulator is started."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
import yaml

from agent.repro import compare as C
from agent.repro import extract as X
from agent.repro import registry as R
from agent.repro import runner as RN

ROOT = Path(__file__).resolve().parents[2]


def rec(run_id, rtl="aaa", lut=100, wns=1.5, passed=True, tests=None, **varies):
    t = tests if tests is not None else {"t1": passed, "t2": passed}
    return {"schema": C.SCHEMA, "example": "x", "run_id": run_id,
            "setup": {"claude_cli_version": "2.1.321", "cc_model": "claude-sonnet-5-5", "vivado_version": "2026.1", "kb_commit": "k1", "stop_after": 6},
            "outcome": {"hidden_pass": passed, "tests_passed": sum(t.values()), "tests_total": len(t), "internal_pass": True},
            "tool_results": {"rtl_sha256": rtl, "lut": lut, "ff": 50, "dsp": 0, "bram36": 0, "wns_ns": wns, "whs_ns": 0.1, "build_stamp": "s" + str(rtl), "vivado_version": "2026.1", "bench_tests": t},
            "varies": {"rtl_lines": 100, "repair_visits": 2, "agent_turns": 50, "tokens": 1000, "cost_usd": 1.0, "wall_s": 600, **varies}}


REFS = [rec("r1", "aaa", 100, 1.5, wall_s=500, cost_usd=0.8), rec("r2", "bbb", 120, 1.0, wall_s=700, cost_usd=1.4), rec("r3", "ccc", 110, 1.2, wall_s=900, cost_usd=2.0)]


# --- the comparison: what must match and what may vary --------------------------------------------------------------------------

def row(c, field):
    return next(r for r in c["deterministic"]["rows"] if r["field"] == field)


def test_same_rtl_hash_and_same_tool_results_is_a_match():
    c = C.compare(rec("new", "bbb", 120, 1.0), REFS)
    assert c["deterministic"]["matching_references"] == ["r2"]
    assert row(c, "lut")["verdict"].startswith("match") and row(c, "wns_ns")["verdict"].startswith("match") and row(c, "build_stamp")["verdict"].startswith("match")
    assert row(c, "bench_tests")["verdict"].startswith("match")


def test_same_rtl_but_a_different_tool_result_is_flagged_as_a_tool_finding_not_a_model_one():
    c = C.compare(rec("new", "bbb", lut=121), REFS)
    v = row(c, "lut")["verdict"]
    assert v.startswith("MISMATCH") and "not the model" in v


def test_a_different_bench_verdict_for_the_same_rtl_is_a_mismatch():
    c = C.compare(rec("new", "bbb", tests={"t1": True, "t2": False}), REFS)
    assert row(c, "bench_tests")["verdict"].startswith("MISMATCH") and "t2" in row(c, "bench_tests")["verdict"]


def test_different_rtl_judges_no_tool_result_and_says_why():
    c = C.compare(rec("new", "zzz", lut=999, wns=-3.0), REFS)
    assert c["deterministic"]["matching_references"] == []
    assert all("verdict" not in r for r in c["deterministic"]["rows"])
    assert "no reference run wrote the same RTL" in c["deterministic"]["note"]
    assert next(v for v in c["varies"] if v["field"] == "rtl_same")["where"].startswith("different from every reference")


def test_a_run_without_rtl_has_nothing_to_compare_and_does_not_crash():
    r = rec("new", None)
    r["tool_results"]["rtl_sha256"] = None
    c = C.compare(r, REFS)
    assert "no RTL hash" in c["deterministic"]["note"]


def test_variable_fields_are_shown_against_min_median_max_and_marked_inside_or_outside():
    c = C.compare(rec("new", "zzz", wall_s=600, cost_usd=5.0), REFS)
    by = {v["field"]: v for v in c["varies"]}
    assert by["wall_s"]["reference"] == {"min": 500.0, "median": 700.0, "max": 900.0, "n": 3} and by["wall_s"]["where"] == "inside the reference range"
    assert by["cost_usd"]["where"] == "above the reference range"
    c2 = C.compare(rec("new", "zzz", wall_s=100), REFS)
    assert next(v for v in c2["varies"] if v["field"] == "wall_s")["where"] == "below the reference range"


def test_outcome_compares_hidden_tests_and_resources_with_the_reference_spread_whatever_the_rtl():
    c = C.compare(rec("new", "zzz", lut=115, wns=1.1), REFS)
    o = c["outcome"]
    assert o["hidden_pass"] is True and o["references_passed"] == "3/3" and "as in every reference" in o["verdict"]
    by = {r["field"]: r for r in o["spread"]}
    assert by["lut"]["where"] == "inside the reference range" and by["lut"]["reference"]["max"] == 120.0
    assert C.compare(rec("new", "zzz", lut=500), REFS)["outcome"]["spread"][0]["where"] == "above the reference range"
    bad = C.compare(rec("new", "zzz", passed=False), REFS)["outcome"]
    assert bad["hidden_pass"] is False and "did NOT pass" in bad["verdict"]


def test_a_changed_setup_makes_the_comparison_not_like_for_like():
    r = rec("new", "zzz")
    r["setup"]["claude_cli_version"] = "2.1.400"
    r["setup"]["unpinned_waived"] = ["knowledge_bank"]
    lf = C.compare(r, REFS)["like_for_like"]
    assert lf["same"] is False and "claude_cli_version" in lf["differences"] and lf["waived"] == ["knowledge_bank"]
    assert C.compare(rec("new", "zzz"), REFS)["like_for_like"]["same"] is True


def test_the_limits_say_the_model_cannot_be_pinned():
    assert any("no temperature and no seed" in x for x in C.LIMITS) and any("provider can update" in x for x in C.LIMITS) and any("plan's estimate" in x for x in C.LIMITS)


def test_compare_refuses_a_record_of_another_schema():
    with pytest.raises(ValueError):
        C.compare({"schema": "other"}, REFS)


def test_a_missing_field_is_no_value_not_a_crash():
    r = rec("new", "bbb")
    del r["varies"]["tokens"], r["tool_results"]["lut"]
    c = C.compare(r, REFS)
    assert next(v for v in c["varies"] if v["field"] == "tokens")["where"] == "no value" and row(c, "lut")["verdict"] == "no value"


# --- the registry, the pins and the command -------------------------------------------------------------------------------------

def test_every_example_is_a_development_task_and_never_wavelet_material():
    reg = R.load()
    held, dev = set(), set()
    for f in ("benchmark/split.yaml", "benchmark/course/split.yaml", "benchmark/course/split_c9_c12.yaml"):
        d = yaml.safe_load((ROOT / f).read_text())
        for t in d["tiers"].values():
            held |= set(t.get("held_out") or [])
            dev |= set(t.get("dev") or [])
    for e in reg["examples"]:
        name = Path(e["task"]).name
        assert name in dev and name not in held, name
        text = (R.task_dir(e) / "spec.md").read_text().lower() + e["title"].lower() + e["covers"].lower()
        assert not re.search(r"wavelet|\bdwt\b", text)
        assert e["task"].startswith("benchmark/") and ".." not in e["task"]


def test_the_command_comes_from_the_pins_only_and_the_cost_cap_can_only_go_down():
    reg = R.load()
    e = R.get("gray_stepper", reg)
    cmd = R.argv(e, reg["pins"], "python")
    for flag, val in (("--cc-model", "claude-sonnet-5-5"), ("--oracle-cc-model", "claude-haiku-5-5"), ("--harness", "claude_code"), ("--harness-arm", "H1"), ("--stop-after", "6"), ("--verif-level", "V2"), ("--max-usd", "6")):
        assert cmd[cmd.index(flag) + 1] == val
    assert "--allow-fable" not in cmd and cmd[1:4] == ["-m", "agent", "run"]
    assert R.argv(e, reg["pins"], "python", max_usd=2.5)[R.argv(e, reg["pins"], "python", max_usd=2.5).index("--max-usd") + 1] == "2.5"
    assert R.argv(e, reg["pins"], "python", max_usd=99)[R.argv(e, reg["pins"], "python", max_usd=99).index("--max-usd") + 1] == "6"
    with pytest.raises(R.ExampleError):
        R.argv(e, reg["pins"], "python", max_usd=0)
    with pytest.raises(R.ExampleError):
        R.get("../x", reg)


def test_a_forbidden_model_in_the_pins_is_refused_when_loading(tmp_path):
    d = yaml.safe_load(R.FILE.read_text())
    d["pins"]["cc_model"] = "claude-opus-5-5"
    f = tmp_path / "e.yaml"
    f.write_text(yaml.safe_dump(d))
    with pytest.raises(R.ExampleError):
        R.load(f)
    d = yaml.safe_load(R.FILE.read_text())
    d["examples"][0]["task"] = "benchmark/private/held_out_x"
    f.write_text(yaml.safe_dump(d))
    with pytest.raises(R.ExampleError):
        R.load(f)


def fake_cli(tmp_path, version, body=None):
    d = tmp_path / "pins" / f"claude-{version}" / "bin"
    d.mkdir(parents=True)
    exe = d / "claude"
    exe.write_text(body or f"#!/bin/sh\necho '{version} (Claude Code)'\n")
    exe.chmod(0o755)
    return exe


def test_preflight_refuses_a_missing_wrong_or_changed_cli_before_anything_starts(tmp_path, monkeypatch):
    pins = copy.deepcopy(R.load()["pins"])
    monkeypatch.setattr(R, "PIN_ROOT", tmp_path / "pins")
    miss = next(c for c in R.check(pins)["checks"] if c["name"] == "claude_cli")
    assert miss["ok"] is False and miss["hard"] and "no pinned copy" in miss["detail"]
    exe = fake_cli(tmp_path, pins["claude_cli_version"])
    got = next(c for c in R.check(pins)["checks"] if c["name"] == "claude_cli")
    assert got["ok"] is False and got["hard"] is False and "sha256" in got["detail"]             # right version, not the pinned binary: reported, not a hard stop
    pins["claude_cli_sha256"] = R.sha256_file(exe)
    pre = R.check(pins)
    assert next(c for c in pre["checks"] if c["name"] == "claude_cli")["ok"] and pre["env"]["PATH"].startswith(str(exe.parent))
    exe.write_text("#!/bin/sh\necho '2.1.999 (Claude Code)'\n")
    bad = next(c for c in R.check(pins)["checks"] if c["name"] == "claude_cli")
    assert bad["ok"] is False and bad["hard"] is True


def test_an_unpinned_knowledge_bank_is_waived_only_on_request_and_recorded(tmp_path, monkeypatch):
    pins = R.load()["pins"]
    monkeypatch.setattr(R, "kb_dir", lambda: tmp_path)
    off = R.check(pins)
    assert next(c for c in off["checks"] if c["name"] == "knowledge_bank")["ok"] is False and "worktree add --detach" in next(c for c in off["checks"] if c["name"] == "knowledge_bank")["detail"]
    on = R.check(pins, allow_unpinned=True)
    assert "knowledge_bank" in on["unpinned_waived"] and not any(c["name"] == "vivado" and c["name"] in on["unpinned_waived"] for c in on["checks"])


def test_run_example_refuses_without_starting_anything_when_a_pin_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "PIN_ROOT", tmp_path / "pins")
    real, started = RN.subprocess.run, []

    def guard(argv, *a, **k):
        if "agent" in argv:                                   # the agent command itself; the pre-flight's own git and --version calls are allowed
            started.append(argv)
        return real(argv, *a, **k)
    monkeypatch.setattr(RN.subprocess, "run", guard)
    info = RN.run_example("gray_stepper", slot=False)
    assert info["refused"] and "claude_cli" in info["refused"] and started == []


# --- extraction and redaction ---------------------------------------------------------------------------------------------------

def make_run(tmp_path, rtl="module a; endmodule\n", lut=10):
    rd = tmp_path / "20261123-000000-abcd"
    d = rd / "ex_x"
    (d / "rtl").mkdir(parents=True)
    (d / "spec.md").write_text("x")
    (d / "rtl" / "a.sv").write_text(rtl)
    b = d / "build" / "base"
    b.mkdir(parents=True)
    (b / "gates.json").write_text(json.dumps({"pass": True, "gates": {"setup": True, "hold": True}, "timing": {"wns_ns": 1.25, "whs_ns": 0.05, "timing_met": True},
                                              "utilization": {"lut": lut, "ff": 5, "dsp": 0, "bram_tile": 0}, "build_stamp": "deadbeef", "sources_sha256": "ab" * 32}))
    (b / "run.json").write_text(json.dumps({"vivado_version": "2026.1", "wall_s": 61.5}))
    (b / "manifest.json").write_text(json.dumps({"build_id": "0123abcd"}))
    (rd / "config.json").write_text(json.dumps({"name": "ex_x"}))
    (rd / "summary.json").write_text(json.dumps({"stages_visited": [0, 0, 1, 2, 2, 3, 4, 5, 6], "turns": 70, "tokens": 12345, "loops": 3}))
    (rd / "role_usage.jsonl").write_text(json.dumps({"tokens": 1000, "plan_cost_estimate_usd": 0.5, "wall_s": 20.0}) + "\n" + json.dumps({"tokens": 500, "plan_cost_estimate_usd": 0.25, "wall_s": 10.0}) + "\n")
    return rd


def test_extract_reads_only_files_the_run_wrote(tmp_path):
    rd = make_run(tmp_path)
    r = X.extract(rd, "x", {"pass": True, "tests": {"a": True, "b": True}, "tests_passed": 2, "tests_total": 2}, {"stop_after": 6, "cc_model": "m"}, wall_s=100.0)
    assert r["schema"] == C.SCHEMA and r["outcome"]["hidden_pass"] is True and r["outcome"]["internal_pass"] is True
    t = r["tool_results"]
    assert (t["lut"], t["wns_ns"], t["build_stamp"], t["build_id"], t["vivado_version"]) == (10, 1.25, "deadbeef", "0123abcd", "2026.1") and len(t["rtl_sha256"]) == 64
    v = r["varies"]
    assert v["tokens"] == 1500 and v["cost_usd"] == 0.75 and v["wall_s"] == 100.0 and v["repair_visits"] == 2 and v["rtl_lines"] == 1
    assert X.check_no_text(r) == []


def test_the_rtl_hash_follows_the_text_not_the_place_or_the_line_endings(tmp_path):
    a = X.extract(make_run(tmp_path / "1", rtl="module a;\nendmodule\n"), "x", None, {})["tool_results"]["rtl_sha256"]
    b = X.extract(make_run(tmp_path / "2", rtl="module a;\r\nendmodule\r\n"), "x", None, {})["tool_results"]["rtl_sha256"]
    c = X.extract(make_run(tmp_path / "3", rtl="module b; endmodule\n"), "x", None, {})["tool_results"]["rtl_sha256"]
    assert a == b and a != c


def test_a_run_that_never_built_has_no_internal_pass(tmp_path):
    rd = make_run(tmp_path)
    for p in sorted((rd / "ex_x" / "build" / "base").iterdir()):
        p.unlink()
    r = X.extract(rd, "x", {"pass": False, "tests": {}, "tests_passed": 0, "tests_total": 0}, {"stop_after": 6})
    assert r["outcome"]["internal_pass"] is False and r["tool_results"]["lut"] is None


def test_the_record_check_refuses_long_text_and_absolute_paths():
    assert X.check_no_text({"a": "x" * 300}) and X.check_no_text({"a": {"b": "see /home/someone/file"}}) and not X.check_no_text({"a": "short", "b": [1, 2.5, None]})


def test_committed_reference_records_hold_numbers_names_and_hashes_only():
    d = ROOT / "results" / "195_repro_examples"
    files = sorted(f for f in d.glob("*/ref_*.json") if re.fullmatch(r"ref_\d+\.json", f.name))
    for f in files:
        r = json.loads(f.read_text())
        assert r["schema"] == C.SCHEMA and X.check_no_text(r) == [], f
        assert r["example"] == f.parent.name
        raw = f.read_text()
        assert not re.search(r"sk-[A-Za-z0-9_-]{12,}|FDA_ACCESS_KEY|OPENROUTER|prompt(?!s_manifest_sha256)", raw), f


# --- finishing a run started by the pinned command --------------------------------------------------------------------------------

def pinned_config(pins):
    return {"harness": pins["harness"], "cc_model": pins["cc_model"], "cc_effort": pins["cc_effort"], "oracle": pins["oracle"], "oracle_cc_model": pins["oracle_cc_model"], "interview": pins["interview"],
            "review": pins["review"], "verif_level": pins["verif_level"], "harness_arms": pins["harness_arm"], "docs": pins["docs"], "profile": pins["profile"], "board": pins["board"],
            "hdl": pins["hdl"], "stop_after": str(pins["stop_after"])}


def test_a_run_started_with_other_flags_is_not_an_example_run(tmp_path):
    pins = R.load()["pins"]
    (tmp_path / "config.json").write_text(json.dumps(pinned_config(pins)))
    assert RN.config_differences(tmp_path, pins) == []
    other = pinned_config(pins)
    other["cc_model"], other["stop_after"] = "claude-haiku-5-5", "8"
    (tmp_path / "config.json").write_text(json.dumps(other))
    assert RN.config_differences(tmp_path, pins) == ["cc_model", "stop_after"]
    (tmp_path / "config.json").unlink()
    assert RN.config_differences(tmp_path, pins) == ["config.json"]


def test_the_command_a_run_uses_is_exactly_what_config_differences_accepts(tmp_path):
    """The flags `argv` builds and the keys `config_differences` checks must name the same settings, so a run from `example run` always passes `example finish`."""
    reg = R.load()
    cmd = R.argv(R.get("gray_stepper", reg), reg["pins"], "python")
    flag = {"harness": "--harness", "cc_model": "--cc-model", "cc_effort": "--cc-effort", "oracle": "--oracle", "oracle_cc_model": "--oracle-cc-model", "interview": "--interview", "review": "--review",
            "verif_level": "--verif-level", "harness_arm": "--harness-arm", "docs": "--docs", "profile": "--profile", "board": "--board", "hdl": "--hdl", "stop_after": "--stop-after"}
    assert set(flag) == set(RN.CONFIG_KEYS)
    for k, f in flag.items():
        assert cmd[cmd.index(f) + 1] == str(reg["pins"][k])


def test_wall_time_is_the_runs_own_span(tmp_path):
    (tmp_path / "trace.jsonl").write_text("\n".join(json.dumps({"t": t}) for t in (100.0, 160.5, 400.25)) + "\nnot json\n")
    assert RN.wall_of(tmp_path) == 300.2 or RN.wall_of(tmp_path) == 300.3
    assert RN.wall_of(tmp_path / "none") is None
