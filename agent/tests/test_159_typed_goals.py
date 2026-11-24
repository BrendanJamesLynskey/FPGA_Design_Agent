"""Brief 159: typed goals (agent.graph.goals) read by the closure loop, the latency loop and the trace matrix, and the goal-revision plan
(agent.graph.revise, `python -m agent revise`). No model call, no Vivado, no simulation."""
import argparse
import json
from pathlib import Path

import pytest
import yaml

from agent.graph import closure, goals as G, latency_loop, pickup, revise as R, spec_schema
from flow import trace_v1

ROOT = Path(__file__).resolve().parents[2]
T1, B58, B96 = (ROOT / "designs" / d for d in ("t1_dimmer_counter", "b58a_trigger", "b96_kr260_10g"))


# --- parsing ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,metric,op,bound,name", [
    ("lut<=700", "lut", "le", 700, None), ("LUTs < 700", "lut", "lt", 700, None), ("bram<=2tiles", "bram_tile", "le", 2, None),
    ("fmax>=150MHz", "fmax_mhz", "ge", 150, None), ("fmax.sys_clk>=1.5GHz", "fmax_mhz", "ge", 1500, "sys_clk"),
    ("power<=0.5W", "power_w", "le", 0.5, None), ("power <= 250 mW", "power_w", "le", 0.25, None),
    ("latency<=22clk", "latency_clk", "le", 22, None), ("latency.echo<=22 cycles", "latency_clk", "le", 22, "echo"), ("dsp<=0", "dsp", "le", 0, None),
])
def test_parse(text, metric, op, bound, name) -> None:
    g = G.parse_goal(text)
    assert (g.metric, g.op, g.bound, g.name) == (metric, op, bound, name) and g.priority == "must"


@pytest.mark.parametrize("text,fragment", [
    ("latency<=10", "unit is required"), ("fmax>=150", "unit is required"), ("power<=1", "unit is required"),
    ("latency<=10ns", "not one of clk"), ("lut=700", "bound, not an exact value"), ("lut>=100", "<= or <"),
    ("fmax<=100MHz", ">= or >"), ("speed>=3", "unknown goal metric"), ("power<=0W", "above zero"), ("lut.foo<=3", "only fmax"),
    ("make it smaller", "cannot read goal"), ("", "cannot read goal"),
])
def test_parse_errors_say_what_to_write(text, fragment) -> None:
    with pytest.raises(G.GoalError) as e:
        G.parse_goal(text)
    assert fragment in str(e.value)


def test_text_round_trip() -> None:
    for t in ("lut<=700", "fmax>=150MHz", "power<=0.5W", "latency.echo<=22clk", "bram<=2"):
        g = G.parse_goal(t)
        assert G.parse_goal(g.text()) == g


def test_spec_block_errors_and_shape_gate() -> None:
    good = {"goals": [{"metric": "lut", "op": "le", "bound": 700, "unit": "LUT"}]}
    assert G.errors(good) == [] and spec_schema.shape_errors(good) == []
    bad = {"goals": [{"metric": "lut", "op": "ge", "bound": 5}, {"metric": "power_w", "op": "le", "bound": "x"},
                     {"metric": "lut", "op": "le", "bound": 5, "priority": "maybe"}, {"metric": "fmax_mhz", "op": "ge", "bound": 5, "unit": "kHz"}]}
    es = spec_schema.shape_errors(bad)
    assert len(es) == 4 and all(e.startswith("goals[") for e in es)
    assert spec_schema.shape_errors({"goals": "lut<=5"}) and G.errors({"goals": [good["goals"][0]] * 2})   # not a list; a metric twice
    with pytest.raises(G.GoalError):
        G.load(bad)


def test_merge_and_block_text_keep_other_lines() -> None:
    a, b = G.parse_goal("lut<=700"), G.parse_goal("lut<=400")
    assert G.merge([a, G.parse_goal("power<=1W")], [b]) == [G.parse_goal("power<=1W"), b]
    txt = "name: x\n# a comment\ngoals:\n  - {metric: lut, op: le, bound: 9}\n\nclocks:\n  - {name: c}\n"
    out = G.set_block(txt, [b])
    assert "# a comment" in out and "clocks:\n  - {name: c}" in out and yaml.safe_load(out)["goals"][0]["bound"] == 400
    assert yaml.safe_load(G.set_block("name: x\n", [a]))["goals"][0]["metric"] == "lut"


# --- readers: closure, latency loop, trace v1 ----------------------------------------------------------------------------------

SPEC = {"clocks": [{"name": "sys_clk", "freq_mhz": 100}, {"name": "aux", "freq_mhz": 50}], "budget": {"lut": 900, "ff": 1200, "power_w": 1.0}}


def test_closure_reads_must_goals_and_says_so() -> None:
    base = closure.goals_from_spec(SPEC)
    assert "typed_goals" not in base and base["G3"]["budget"]["lut"] == 900 and base["G4"]["power_w"] == 1.0
    spec = {**SPEC, "goals": [G.parse_goal(t).as_dict() for t in ("lut<=700", "fmax.aux>=75MHz", "power<=0.5W", "dsp<=0", "latency<=9clk")]
            + [{**G.parse_goal("ff<=100").as_dict(), "priority": "should"}]}
    g = closure.goals_from_spec(spec)
    assert g["G3"]["budget"]["lut"] == 700 and "typed goal lut<=700" in g["G3"]["why"]["lut"] and "replaces 900" in g["G3"]["why"]["lut"]
    assert g["G3"]["budget"]["dsp"] == 0 and g["G3"]["budget"]["ff"] == 1200       # the should goal is recorded, not applied
    assert g["G4"]["power_w"] == 0.5 and "typed goal power<=0.5W" in g["G4"]["why"]
    c = {c["name"]: c for c in g["G2"]["clocks"]}
    assert c["aux"]["freq_mhz"] == 75 and c["aux"]["period_ns"] == 13.333 and c["sys_clk"]["freq_mhz"] == 100
    applied = {t["text"]: t["applied"] for t in g["typed_goals"]}
    assert applied["latency<=9clk"] is None and applied["ff<=100"] is None and applied["fmax.aux>=75MHz"] == "G2 clock aux"


def test_closure_goal_for_an_unknown_clock_is_listed_unapplied() -> None:
    g = closure.goals_from_spec({**SPEC, "goals": [G.parse_goal("fmax.nope>=75MHz").as_dict()]})
    assert g["typed_goals"][0]["applied"].startswith("unapplied") and g["G2"]["clocks"][0]["freq_mhz"] == 100


def test_closure_goal_makes_the_vector_fail(tmp_path) -> None:
    dg = {"ran": True, "timing": {"period_ns": 10, "wns_ns": 1.0, "whs_ns": 0.1}, "gates": {}, "utilization": {"lut": 800, "ff": 10, "bram_tile": 0, "dsp": 0, "iob": 1},
          "power": {"total_w": 0.4, "junction_c": 30, "confidence": "low"}, "synth": {}}
    spec = {**SPEC, "goals": [G.parse_goal("lut<=700").as_dict()]}
    v = closure.goal_vector({"pass": True, "tests": {"a": True}}, dg, closure.goals_from_spec(spec))
    assert v["G3"]["met"] is False and v["G3"]["target"]["lut"] == 700
    assert closure.goal_vector({"pass": True, "tests": {"a": True}}, dg, closure.goals_from_spec(SPEC))["G3"]["met"] is True


def test_latency_loop_target(tmp_path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    assert latency_loop.latency_goal_clocks(d, None) is None
    assert latency_loop.latency_goal_clocks(d, "latency<=12clk") == 12
    assert latency_loop.latency_goal_clocks(d, "latency.tick_to_trade<=12clk") == 12
    for bad in ("latency.echo<=12clk", "lut<=5", "latency<=12"):
        with pytest.raises(G.GoalError):
            latency_loop.latency_goal_clocks(d, bad)
    (d / "spec.yaml").write_text(yaml.safe_dump({"goals": [G.parse_goal("latency.echo<=22clk").as_dict(), G.parse_goal("latency<=9clk").as_dict()]}))
    assert latency_loop.latency_goal_clocks(d, None) == 9                          # the unnamed one; the echo goal is not this loop's
    assert latency_loop.latency_goal_clocks(d, "latency<=7clk") == 7                # --goal wins


def test_latency_loop_stops_at_the_goal(tmp_path, monkeypatch) -> None:
    """The baseline already meets the target: no visit, no model call; the summary says so."""
    monkeypatch.setattr(latency_loop, "kb_text", lambda n: "x")
    monkeypatch.setattr(latency_loop, "measure", lambda root, design: {"tests_pass": True, "ttt_clocks": 8, "echo_clocks": 5})
    monkeypatch.setattr(latency_loop, "rtl_sha", lambda d: "0")
    monkeypatch.setattr("agent.graph.closure.Workspace", lambda d: type("W", (), {"read": lambda s: {}})())
    monkeypatch.setattr("agent.graph.roles.role_session", lambda s, r: s)
    (tmp_path / "d").mkdir()
    loop = latency_loop.LatencyLoop(tmp_path, tmp_path / "d", "A1", lambda *a, **k: 1 / 0, tmp_path / "out", target_clocks=10)
    s = loop.run()
    assert s["goal_met"] is True and s["visits"] == 0 and s["target_clocks"] == 10
    assert "already holds" in (tmp_path / "out" / "history.jsonl").read_text()


def test_trace_v1_turns_goals_into_untraced_requirements(tmp_path, monkeypatch) -> None:
    d = tmp_path / "designs" / "x"
    (d / "verif").mkdir(parents=True)
    (d / "verif" / "testplan.yaml").write_text(yaml.safe_dump({
        "schema": trace_v1.SCHEMA_V1, "design": "x",
        "requirements": [{"id": "GOAL-LUT", "kind": "functional", "title": "mine", "text": "", "source": "s", "spec_status": "draft"}],
        "verification": []}))
    (d / "spec.yaml").write_text(yaml.safe_dump({"goals": [G.parse_goal(t).as_dict() for t in ("lut<=700", "latency.echo<=22clk", "fmax>=150MHz")]}))
    plan = trace_v1.load(d)
    ids = [r["id"] for r in plan["requirements"]]
    assert ids == ["GOAL-LUT", "GOAL-LATENCY-CLK-ECHO", "GOAL-FMAX-MHZ"]            # the plan's own GOAL-LUT is kept, not replaced
    r = plan["requirements"][1]
    assert r["kind"] == "performance" and r["performance"] == {"quantity": "latency_clk.echo", "unit": "clk", "op": "le", "bound": 22,
                                                               "condition": r["performance"]["condition"]}
    assert not [x for x in trace_v1.find_gaps(plan, [], [], {}, None) if x["type"] == "bad_item"]       # a valid performance requirement
    (d / "spec.yaml").write_text("goals: [{metric: lut, op: ge, bound: 3}]")
    with pytest.raises(trace_v1.PlanError):
        trace_v1.load(d)


# --- the revision plan --------------------------------------------------------------------------------------------------------

def _plan(design: Path, goals: list[str], retarget: str | None = None) -> dict:
    return R.plan(design, pickup.load(design), [G.parse_goal(g) for g in goals], retarget)


@pytest.mark.parametrize("design,goals,retarget,verdict,stage", [
    (T1, ["lut<=700"], None, "met_by_evidence", None), (T1, ["lut<=400"], None, "not_met", 1),
    (T1, ["fmax>=100MHz"], None, "met_by_evidence", None),      # built and met timing at 100 MHz
    (T1, ["fmax>=150MHz"], None, "not_met", 3), (T1, ["power<=0.1W"], None, "not_met", 3), (T1, ["power<=0.2W"], None, "met_by_evidence", None),
    (B58, ["latency.decision_clocks_speculative<=10clk"], None, "met_by_evidence", None),
    (B58, ["latency.decision_clocks_speculative<=6clk"], None, "not_met", 1),
    (B58, ["latency<=10clk"], None, "unknown", 1),              # several latencies are measured: a name is needed, never guessed
    (B58, ["fmax>=100MHz"], None, "unknown", 3),                # no spec.yaml clock to read an Fmax against
    (B96, ["power<=1.5W"], None, "met_by_evidence", None), (B96, ["lut<=5000"], None, "not_met", 1),
])
def test_plan_per_goal(design, goals, retarget, verdict, stage) -> None:
    p = _plan(design, goals, retarget)
    assert (p["changes"][0]["verdict"], p["changes"][0]["stage"]) == (verdict, stage) and p["goal_stage"] == stage
    assert p["goal_vector_sha"]["before"] != p["goal_vector_sha"]["after"]


def test_plan_retarget() -> None:
    assert _plan(T1, [], "xc7a200tfbg484-1")["retarget"]["stage"] == 3 and _plan(T1, [], "xc7a200tfbg484-1")["goal_stage"] == 3
    assert _plan(B58, [], "xc7a200tfbg484-1")["retarget"]["verdict"] == "other_family" and _plan(B58, [], "xc7a200tfbg484-1")["goal_stage"] == 1
    assert _plan(T1, [], "xc7a100tcsg324-1")["retarget"]["verdict"] == "unchanged" and _plan(T1, [], "xc7a100tcsg324-1")["goal_stage"] is None
    assert _plan(T1, [], "arty_a7_100t")["retarget"]["to"]["part"] == "xc7a100tcsg324-1"          # a board directory gives its part
    with pytest.raises(R.ReviseError):
        _plan(T1, [], "not-a-board")
    with pytest.raises(R.ReviseError):
        _plan(T1, [])                                                                                   # nothing to revise


def test_plan_takes_the_earliest_goal_and_lists_kept_stages() -> None:
    p = _plan(T1, ["lut<=700", "fmax>=150MHz", "lut<=400"][1:])           # fmax 3 and lut 1: the area goal wins
    assert p["goal_stage"] == 1 and p["entry"]["kind"] == "area"
    p = _plan(T1, ["fmax>=150MHz", "power<=0.1W"])
    assert p["goal_stage"] == 3 and p["stages_rerun_by_the_goal_alone"] == 7 and p["full_rerun_stages"] == 10
    acts = [s["action"] for s in p["stages"]]
    assert acts.count("re-run") == p["stages_rerun"] and acts[-1] == "re-run" and acts[:p["entry"]["stage"]] == ["kept"] * p["entry"]["stage"]
    assert any("goal change" in r["why"] for r in p["entry"]["reasons"])


def test_plan_same_goal_is_unchanged(tmp_path) -> None:
    d = tmp_path / "designs" / "t1"
    import shutil
    shutil.copytree(T1, d, ignore=shutil.ignore_patterns("build", "__pycache__"))
    (d / "spec.yaml").write_text(G.set_block((d / "spec.yaml").read_text(), [G.parse_goal("lut<=400")]))
    assert R.current_goals(d) == [G.parse_goal("lut<=400")]
    p = R.plan(d, {"handover": yaml.safe_load((d / "handover.yaml").read_text()), "fresh": {"design": "t1", "stale": [], "ddir": str(d)}},
               [G.parse_goal("lut<=400")], None)
    assert p["changes"][0]["verdict"] == "unchanged" and p["goal_stage"] is None


def test_a_stale_measurement_is_no_evidence() -> None:
    ld = pickup.load(T1)
    ld["fresh"]["stale"] = ["M1: the RTL changed"]
    p = R.plan(T1, ld, [G.parse_goal("lut<=700")], None)
    assert p["changes"][0]["verdict"] == "unknown" and p["goal_stage"] == 1 and "stale" in p["changes"][0]["why"]


def test_write_goals_and_part(tmp_path) -> None:
    (tmp_path / "spec.yaml").write_text("part: xc7a100tcsg324-1\n# kept\ngoals:\n  - {metric: lut, op: le, bound: 9}\n")
    (tmp_path / "build.yaml").write_text("part: xc7a100tcsg324-1\ntop: t\n")
    out = R.write_goals(tmp_path, [G.parse_goal("lut<=700")], {"part": "xc7a200tfbg484-1"}, "xc7a100tcsg324-1")
    assert out == ["spec.yaml", "build.yaml"]
    sp = yaml.safe_load((tmp_path / "spec.yaml").read_text())
    assert sp["part"] == "xc7a200tfbg484-1" and sp["goals"][0]["bound"] == 700 and "# kept" in (tmp_path / "spec.yaml").read_text()
    assert "xc7a200tfbg484-1" in (tmp_path / "build.yaml").read_text()


# --- the command ---------------------------------------------------------------------------------------------------------------------

def _main(*argv):
    from agent.__main__ import main
    return main(list(argv))


def test_revise_dry_run_command(capsys) -> None:
    assert _main("revise", str(T1), "--goal", "lut<=700", "--goal", "fmax>=150MHz", "--dry-run") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["revise"] == "dry run" and [c["verdict"] for c in out["changes"]] == ["met_by_evidence", "not_met"] and out["goal_stage"] == 3
    assert len(out["stages"]) == 10 and "_after" not in out


def test_revise_errors_exit_2(capsys) -> None:
    assert _main("revise", str(T1), "--goal", "latency<=10", "--dry-run") == 2
    assert "unit is required" in capsys.readouterr().err
    assert _main("revise", str(T1), "--dry-run") == 2 and "nothing to revise" in capsys.readouterr().err
    assert _main("revise", str(T1), "--retarget", "nope", "--dry-run") == 2


def test_revise_live_hands_the_plan_to_the_run(monkeypatch, capsys) -> None:
    seen = {}
    monkeypatch.setattr("agent.__main__.pickup_cmd", lambda b: seen.update(vars(b)) or 0)
    assert _main("revise", str(T1), "--goal", "lut<=400") == 0
    assert seen["entry_override"]["stage"] == 1 and seen["entry_override"]["kind"] == "area" and seen["run_id"] == str(T1)
    assert [g.text() for g in seen["revise_goals"]] == ["lut<=400"] and seen["change"].startswith("revise: lut<=400") and seen["kind"] is None
    assert json.loads(capsys.readouterr().out)["goals_after"][0]["bound"] == 400


def test_revise_with_everything_met_runs_nothing(monkeypatch, capsys) -> None:
    """When the evidence meets the goal AND the handover is current, nothing runs and nothing is written (here the worktree's extra
    files make the handover stale, so the run is only skipped when there are none: the plan is checked with a clean fresh report)."""
    ld = pickup.load(T1)
    ld["fresh"].update(changed_files=[], added_files=[], stale=[], build_id={})
    monkeypatch.setattr(pickup, "load", lambda d, deep=True: ld)
    called = []
    monkeypatch.setattr("agent.__main__.pickup_cmd", lambda b: called.append(1) or 0)
    assert _main("revise", str(T1), "--goal", "lut<=700") == 0
    assert not called and "nothing to re-run" in json.loads(capsys.readouterr().out)["revise"]


def test_help_names_what_a_user_could_guess_wrong(capsys) -> None:
    with pytest.raises(SystemExit):
        _main("revise", "--help")
    h = capsys.readouterr().out
    for s in ("a bare number is an", "met by evidence", "never extrapolates", "never edits the source design", "no live retarget run"):
        assert s.replace("  ", " ") in " ".join(h.split()), s
