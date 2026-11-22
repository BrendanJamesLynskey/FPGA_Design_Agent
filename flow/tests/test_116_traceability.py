"""Brief 116: the v1 testplan collector (flow/trace_v1.py): statuses are computed from evidence, the gate fails on orphans and untraced
requirements, staleness comes from pinned hashes, and the committed matrices are what the code writes today."""
import json
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from flow import trace_v1 as T


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    (tmp_path / "designs" / "d" / "verif").mkdir(parents=True)
    (tmp_path / "designs" / "d" / "rtl").mkdir()
    (tmp_path / "designs" / "d" / "rtl" / "a.sv").write_text("module a; endmodule\n")
    (tmp_path / "results").mkdir()
    return tmp_path


def plan(repo, reqs, items, extra=None):
    d = {"schema": T.SCHEMA_V1, "design": "d", "requirements": reqs, "verification": items, **(extra or {})}
    (repo / "designs" / "d" / "verif" / "testplan.yaml").write_text(yaml.safe_dump(d))
    return repo / "designs" / "d"


def perf(bound=22, op="le"):
    return {"id": "P1", "kind": "performance", "title": "E", "performance": {"quantity": "E", "unit": "clocks", "op": op, "bound": bound, "condition": "c"}}


def ev(repo, name, obj):
    (repo / "results" / name).write_text(json.dumps(obj))
    return {"file": f"results/{name}", "reader": "json", "field": "v"}


def item(i, req, method, evidence, **k):
    return {"id": i, "requirements": [req], "method": method, "evidence": evidence, **k}


def test_performance_needs_a_measured_value_inside_the_bound(repo):
    d = plan(repo, [perf()], [item("i1", "P1", "board_measurement", ev(repo, "ok.json", {"v": 21.0}), instrument="latency_loop"),
                              item("i2", "P1", "sim_test", {"file": "results/none.xml", "reader": "junit", "tests": ["a::b"]})])
    c = T.collect(d)
    assert c["requirements"][0]["state"] == "verified" and c["requirements"][0]["basis"] == "board"
    d = plan(repo, [perf()], [item("i1", "P1", "board_measurement", ev(repo, "bad.json", {"v": 23.0}), instrument="latency_loop")])
    assert T.collect(d)["requirements"][0]["state"] == "fail"


def test_a_passing_test_alone_does_not_verify_a_performance_requirement(repo):
    (repo / "results" / "j.xml").write_text('<testsuite><testcase classname="x.a" name="b"/></testsuite>')
    d = plan(repo, [perf()], [item("i", "P1", "sim_test", {"file": "results/j.xml", "reader": "junit", "tests": ["a::b"]})])
    c = T.collect(d)
    assert c["requirements"][0]["state"] == "no_measurement"
    assert any(g["type"] == "no_passing_evidence" for g in c["gaps"])


def test_sim_only_performance_is_shown_distinctly(repo):
    d = plan(repo, [perf()], [item("i", "P1", "sim_measurement", ev(repo, "s.json", {"v": 13}))])
    c = T.collect(d)
    assert c["requirements"][0]["basis"] == "simulation"
    assert any(g["type"] == "performance_sim_only" for g in c["gaps"])


def test_external_requirement_is_open_until_hardware_verification(repo):
    req = {"id": "F1", "kind": "functional", "title": "t", "external": "a NIC"}
    sim = item("s", "F1", "sim_measurement", ev(repo, "a.json", {"v": True}), pass_when=[{"field": "v", "op": "true"}])
    c = T.collect(plan(repo, [req], [sim]))
    r = c["requirements"][0]
    assert r["hardware_closure"] == "open" and r["state"] == "verified"
    assert {g["type"] for g in c["gaps"]} >= {"hardware_open", "external_not_hardware_verified"}
    hw = item("h", "F1", "board_measurement", ev(repo, "b.json", {"v": True}), instrument="external_equipment", pass_when=[{"field": "v", "op": "true"}])
    c = T.collect(plan(repo, [req], [sim, hw]))
    assert c["requirements"][0]["hardware_closure"] == "done"
    assert not [g for g in c["gaps"] if g["type"].startswith(("hardware", "external"))]


def test_a_missing_evidence_file_is_not_run_and_a_failing_item_fails(repo):
    req = {"id": "F1", "kind": "functional", "title": "t"}
    c = T.collect(plan(repo, [req], [item("h", "F1", "board_measurement", {"file": "results/x/*.json", "reader": "json"}, instrument="sysmon", planned="later")]))
    assert c["items"][0]["status"] == "not_run" and c["requirements"][0]["state"] == "not_run"
    c = T.collect(plan(repo, [req], [item("h", "F1", "sim_measurement", ev(repo, "f.json", {"v": 1}), pass_when=[{"field": "v", "op": "eq", "value": 2}])]))
    assert c["items"][0]["status"] == "fail" and c["requirements"][0]["state"] == "fail"


def test_formal_with_a_depth_is_bounded_not_pass(repo):
    req = {"id": "F1", "kind": "functional", "title": "t"}
    it = item("f", "F1", "formal", ev(repo, "f.json", {"v": True}), bounded={"depth": 24}, pass_when=[{"field": "v", "op": "true"}])
    c = T.collect(plan(repo, [req], [it]))
    assert c["items"][0]["status"] == "bounded" and c["requirements"][0]["state"] == "bounded"


def test_junit_wildcard_and_missing_tests(repo):
    (repo / "results" / "j.xml").write_text('<testsuite><testcase classname="x.m" name="t1"/><testcase classname="x.m" name="t2"><failure/></testcase></testsuite>')
    req = {"id": "F1", "kind": "functional", "title": "t"}
    j = lambda tests: item("i", "F1", "sim_test", {"file": "results/j.xml", "reader": "junit", "tests": tests})
    assert T.collect(plan(repo, [req], [j(["m::t1"])]))["items"][0]["status"] == "pass"
    assert T.collect(plan(repo, [req], [j(["m::*"])]))["items"][0]["status"] == "fail"          # t2 is present and failed
    assert T.collect(plan(repo, [req], [j(["m::t9"])]))["items"][0]["status"] == "not_in_run"   # brief 138: absent is not a failure


def _junit_plan(repo, xml, tests):
    (repo / "results" / "j.xml").write_text(xml)
    req = {"id": "F1", "kind": "functional", "title": "t"}
    return T.collect(plan(repo, [req], [item("i", "F1", "sim_test", {"file": "results/j.xml", "reader": "junit", "tests": tests})]))


def test_status_pass_fail_not_in_run_and_skipped_are_distinct(repo):
    xml = ('<testsuite><testcase classname="x.m" name="ok"/><testcase classname="x.m" name="bad"><failure/></testcase>'
           '<testcase classname="x.m" name="sk"><skipped/></testcase></testsuite>')
    got = {name: _junit_plan(repo, xml, tests) for name, tests in
           {"pass": ["m::ok"], "fail": ["m::ok", "m::bad", "m::new"], "not_in_run": ["m::ok", "m::new"], "skipped": ["m::ok", "m::sk"]}.items()}
    assert {k: c["items"][0]["status"] for k, c in got.items()} == {k: k for k in got}
    assert {k: c["requirements"][0]["state"] for k, c in got.items()} == {"pass": "verified", "fail": "fail", "not_in_run": "not_in_run", "skipped": "skipped"}


def test_not_in_run_and_skipped_are_no_passing_evidence_not_failing_and_name_the_tests(repo):
    xml = '<testsuite><testcase classname="x.m" name="sk"><skipped/></testcase></testsuite>'
    c = _junit_plan(repo, xml, ["m::new", "n::*"])
    assert "not in the recorded run: m::new, n::*" in c["items"][0]["detail"]          # an empty wildcard counts as absent too
    gap = [g for g in c["gaps"] if g["type"] == "no_passing_evidence"][0]
    assert gap["state"] == "not_in_run" and "m::new" in gap["text"] and not gap["gate"]
    assert "1 with no passing evidence (1 not in the recorded run)" in c["summary"]["line"] and "failing" not in c["summary"]["line"]
    c = _junit_plan(repo, xml, ["m::sk"])
    assert c["requirements"][0]["state"] == "skipped" and "m::sk" in [g for g in c["gaps"] if g["type"] == "no_passing_evidence"][0]["text"]
    assert "1 with no passing evidence (1 skipped in the recorded run)" in c["summary"]["line"]


def test_gate_fails_on_orphans_untraced_requirements_and_bad_entries(repo):
    req = {"id": "F1", "kind": "functional", "title": "t"}
    good = item("g", "F1", "sim_measurement", ev(repo, "a.json", {"v": True}), pass_when=[{"field": "v", "op": "true"}])
    assert T.gate(plan(repo, [req], [good])) == []
    assert any("untraced_requirement" in p for p in T.gate(plan(repo, [req, {"id": "F2", "kind": "functional", "title": "u"}], [good])))
    assert any("orphan_check" in p for p in T.gate(plan(repo, [req], [good, item("o", "NOPE", "sim_test", {"file": "x"})])))
    assert any("unknown method" in p for p in T.gate(plan(repo, [req], [good, item("m", "F1", "magic", {"file": "x"})])))
    assert any("instrument" in p for p in T.gate(plan(repo, [req], [good, item("b", "F1", "board_measurement", {"file": "x"})])))
    assert any("needs quantity" in p for p in T.gate(plan(repo, [{"id": "P", "kind": "performance", "title": "p"}], [])))
    assert any("does not exist" in p for p in T.gate(plan(repo, [req], [dict(good, checks=["designs/d/rtl/none.sv"])])))


def test_a_test_in_the_bench_that_no_item_names_is_an_orphan(repo):
    (repo / "designs" / "d" / "tests").mkdir()
    (repo / "designs" / "d" / "tests" / "test_x.py").write_text("def test_a():\n    pass\n\ndef test_b():\n    pass\n")
    req = {"id": "F1", "kind": "functional", "title": "t"}
    (repo / "results" / "j.xml").write_text('<testsuite><testcase classname="x.test_x" name="test_a"/></testsuite>')
    it = item("i", "F1", "sim_test", {"file": "results/j.xml", "reader": "junit", "tests": ["test_x::test_a"]})
    probs = T.gate(plan(repo, [req], [it], {"discover": [{"glob": "designs/d/tests/test_*.py"}]}))
    assert probs == ["orphan_check: test_x::test_b: a test found in the bench that no item names"]


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


def test_evidence_goes_stale_when_a_checked_file_changes_after_it(repo):
    req = {"id": "F1", "kind": "functional", "title": "t"}
    e = ev(repo, "a.json", {"v": True})
    d = plan(repo, [req], [item("i", "F1", "sim_measurement", e, pass_when=[{"field": "v", "op": "true"}], checks=["designs/d/rtl/a.sv"])])
    assert T.collect(d)["items"][0]["status"] == "stale"                    # no pin yet
    git(repo, "init", "-q"); git(repo, "add", "-A"); git(repo, "commit", "-qm", "evidence")
    T.write_pins(d)
    assert T.collect(d)["items"][0]["status"] == "pass"
    (repo / "designs" / "d" / "rtl" / "a.sv").write_text("module a; wire x; endmodule\n")
    c = T.collect(d)
    assert c["items"][0]["status"] == "stale" and "a.sv" in c["items"][0]["stale_because"]
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "rtl")
    T.write_pins(d)                                                         # pinned at the evidence's commit: still stale after the RTL commit
    assert T.collect(d)["items"][0]["status"] == "stale"
    (repo / "results" / "a.json").write_text(json.dumps({"v": True, "again": 1}))   # evidence re-recorded and committed
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "re-record")
    T.write_pins(d)
    assert T.collect(d)["items"][0]["status"] == "pass"


def test_v0_plan_is_upgraded(repo):
    d = repo / "designs" / "d"
    (d / "verif" / "testplan.yaml").write_text(yaml.safe_dump({"schema": T.SCHEMA_V0, "design": "d", "evidence_record": "results/g.json",
        "requirements": [{"id": "R1", "spec": ["a"], "tests": ["m.t"], "formal": ["deb"]}]}))
    (repo / "results" / "g.json").write_text(json.dumps({"stages": {"V2": {"checks": {"planned_tests_missing": {"value": [], "pass": True},
        "failing_tests": {"value": [], "pass": True}, "seeds_run": {"value": [1], "pass": True}, "formal_tasks_not_passing": {"value": [], "pass": True}}}}}))
    c = T.collect(d)
    assert c["source_schema"] == T.SCHEMA_V0
    assert {i["method"] for i in c["items"]} == {"sim_test", "formal"}
    assert next(i for i in c["items"] if i["method"] == "formal")["status"] in ("stale", "bounded")
    assert T.gate(d) == []                                                  # v0 files are gated by verif_gates


def test_every_committed_v1_testplan_passes_the_gate():
    for d in T.v1_designs():
        assert T.gate(d) == [], d.name


def test_committed_matrices_are_what_the_code_writes():
    ds = [d for d in T.v1_designs()]
    for p, text in T.outputs(ds).items():
        assert p.exists(), f"{T.rel(p)}: run python -m flow.trace_v1 write"
        assert p.read_text() == text, f"{T.rel(p)} is out of date: run python -m flow.trace_v1 write"


def test_matrix_names_no_status_the_code_did_not_compute():
    d = T.v1_designs()
    for dd in d:
        c = T.collect(dd)
        assert all(i["status"] in T.STATUSES for i in c["items"])
        assert all(r["kind"] in T.KINDS for r in c["requirements"])
