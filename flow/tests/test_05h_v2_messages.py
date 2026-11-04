"""Brief 05h: the V2/V3 gate names what is missing, the harness writes the seeded results the gate reads, and the
formal check does not demand a task the plan never names. Fixture: the results.xml the live Opus run
(20261104-031217-a444, t1_dimmer_counter) left in the repo-wide build/sim instead of <design>/build/verif/sim."""

import shutil
from pathlib import Path

from agent.graph.repair import verif_failures
from flow import cocotb_run, verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"
FIXTURE = Path(__file__).parent / "data" / "opus_run_results.xml"


def _v2(tmp_path):
    return G.evaluate(T1, tmp_path / "none", [], tmp_path / "nof", None, None)["stages"]["V2"]["checks"]


def test_no_seeded_results_gives_one_actionable_line(tmp_path):
    c = _v2(tmp_path)
    hint = c["seeds_run"]["value"]
    assert not c["seeds_run"]["pass"]
    assert "/seed*/results.xml" in hint and "seed<N>/results.xml" in hint     # directory read and file expected
    assert "flow.cocotb_run.run(" in hint and "seed=N" in hint and "simulate" in hint   # how the tests role makes it
    for k in ("planned_tests_missing", "failing_tests", "constrained_random_test_ran", "assertions_bound_zero_failures"):
        assert c[k]["value"] == G.NOT_EVALUATED and not c[k]["pass"]


def test_repair_text_is_one_line_for_the_tests_role(tmp_path):
    rep = G.evaluate(T1, tmp_path / "none", [], tmp_path / "nof", None, None)
    lines = verif_failures(rep, "V3")
    # one line for the cause; T1 also plans formal tasks that did not run, which is a real second finding
    assert lines[0].startswith("V2 seeds_run: no seeded results")
    assert [x.split(":")[0] for x in lines] == ["V2 seeds_run", "V2 formal_tasks_not_passing"]
    assert not any("[] (need" in x or "[0]" in x or "not evaluated" in x for x in lines)


def test_formal_check_passes_when_the_plan_names_no_formal_task(tmp_path, monkeypatch):
    plan = G.yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    for r in plan["requirements"]:
        r["formal"] = []
    real = G.yaml.safe_load
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "fpga-design-agent/testplan" in t else real(t))
    c = G.evaluate(T1, tmp_path / "none", [], tmp_path / "nof", None, None)["stages"]["V2"]["checks"]
    assert c["formal_tasks_not_passing"]["pass"] and c["formal_tasks_not_passing"]["value"] == []


def test_a_planned_formal_task_that_is_absent_still_fails(tmp_path):
    c = _v2(tmp_path)          # T1 plans formal tasks, none ran
    assert not c["formal_tasks_not_passing"]["pass"] and c["formal_tasks_not_passing"]["value"]


def test_collect_results_writes_what_the_gate_reads(tmp_path, monkeypatch):
    build = tmp_path / "build" / "sim" / "t1_dimmer_counter"
    build.mkdir(parents=True)
    shutil.copy(FIXTURE, build / "results.xml")
    dest = tmp_path / "design" / "build" / "verif" / "sim"
    monkeypatch.setenv("FDA_SIM_RESULTS_DIR", str(dest))
    out = cocotb_run.collect_results(build, seed=2)
    assert out == dest / "seed2" / "results.xml"
    res = G.read_results([dest])
    assert list(res) == [2] and "t1_dimmer_counter_tb.test_reset_values" in res[2]
    cocotb_run.collect_results(build, seed=2)               # same seed again: replaced, not duplicated
    assert len(G.read_results([dest])[2]) == len(res[2])


def test_collect_results_merges_two_modules_of_one_seed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d, case in ((a, "test_x"), (b, "test_y")):
        d.mkdir()
        (d / "results.xml").write_text(f'<testsuites><testsuite name="all"><testcase name="{case}" classname="m.bench"/></testsuite></testsuites>')
    dest = tmp_path / "out"
    cocotb_run.collect_results(a, None, dest)
    cocotb_run.collect_results(b, None, dest)
    assert sorted(G.read_results([dest])[1]) == ["bench.test_x", "bench.test_y"]


def test_collect_results_is_off_without_the_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("FDA_SIM_RESULTS_DIR", raising=False)
    (tmp_path / "results.xml").write_text("<testsuites/>")
    assert cocotb_run.collect_results(tmp_path, 1) is None
