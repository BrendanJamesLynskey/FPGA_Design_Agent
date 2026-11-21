"""Brief 143d: fresh-evidence comparison (flow/fresh_evidence.py) and trace_v1's reading of a fresh record. Pure Python: no simulator, no network."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from flow import fresh_evidence as F
from flow import trace_v1 as T

REPO = Path(__file__).resolve().parents[2]


def junit(path: Path, cases: dict[str, str]) -> Path:
    """cases: 'stem::name' -> pass | fail | skip"""
    path.parent.mkdir(parents=True, exist_ok=True)
    s = ET.Element("testsuite")
    for k, o in cases.items():
        stem, name = k.split("::")
        tc = ET.SubElement(s, "testcase", classname=f"pkg.{stem}", name=name, time="0.1")
        if o == "fail":
            ET.SubElement(tc, "failure", message="x")
        elif o == "skip":
            ET.SubElement(tc, "skipped", message="x")
    root = ET.Element("testsuites")
    root.append(s)
    ET.ElementTree(root).write(path)
    return path


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    monkeypatch.setattr(F, "ROOT", tmp_path)
    (tmp_path / "designs" / "d" / "verif").mkdir(parents=True)
    (tmp_path / "results").mkdir()
    return tmp_path


def make_plan(repo: Path) -> Path:
    items = [
        {"id": "V-T", "requirements": ["R1"], "method": "sim_test", "title": "t", "evidence": {"file": "results/j.xml", "reader": "junit", "tests": ["test_a::one", "test_a::two"]}},
        {"id": "V-W", "requirements": ["R1"], "method": "sim_test", "title": "w", "evidence": {"file": "results/j.xml", "reader": "junit", "tests": ["test_a::*"]}},
        {"id": "V-M", "requirements": ["R2"], "method": "sim_measurement", "title": "m", "evidence": {"file": "results/m.json", "reader": "json", "field": "latency"},
         "pass_when": [{"field": "latency", "op": "le", "value": 10}]},
        {"id": "V-H", "requirements": ["R2"], "method": "board_measurement", "instrument": "jtag_registers", "title": "h", "evidence": {"file": "results/hw.json", "reader": "json", "field": "ok"}},
    ]
    reqs = [{"id": "R1", "kind": "functional", "title": "r1", "spec_status": "draft"}, {"id": "R2", "kind": "functional", "title": "r2", "spec_status": "draft"}]
    (repo / "designs" / "d" / "verif" / "testplan.yaml").write_text(yaml.safe_dump({"schema": T.SCHEMA_V1, "design": "d", "requirements": reqs, "verification": items}))
    junit(repo / "results" / "j.xml", {"test_a::one": "pass", "test_a::two": "pass"})
    (repo / "results" / "m.json").write_text(json.dumps({"latency": 8}))
    (repo / "results" / "hw.json").write_text(json.dumps({"ok": True}))
    return repo / "designs" / "d"


def test_unchanged_tree_reads_the_same_without_a_fresh_directory(repo):
    d = make_plan(repo)
    assert all("fresh" not in i for i in T.collect(d)["items"])


def test_agreeing_fresh_run_marks_nothing_and_leaves_verdicts_alone(repo, tmp_path_factory):
    d = make_plan(repo)
    fr = tmp_path_factory.mktemp("fresh")
    junit(fr / "results" / "j.xml", {"test_a::one": "pass", "test_a::two": "pass"})
    (fr / "results").mkdir(exist_ok=True)
    (fr / "results" / "m.json").write_text(json.dumps({"latency": 8, "seconds": 1.5}))
    base, c = T.collect(d), T.collect(d, fresh=fr)
    assert [i["status"] for i in base["items"]] == [i["status"] for i in c["items"]]
    st = {i["id"]: i["fresh"]["state"] for i in c["items"]}
    assert st == {"V-T": "agrees", "V-W": "agrees", "V-M": "agrees", "V-H": "not_rerun"}   # the board record is never re-run


def test_a_changed_outcome_or_value_is_flagged_distinctly_in_the_matrix(repo, tmp_path_factory):
    d = make_plan(repo)
    fr = tmp_path_factory.mktemp("fresh")
    junit(fr / "results" / "j.xml", {"test_a::one": "fail", "test_a::two": "pass", "test_a::three": "pass"})
    (fr / "results" / "m.json").write_text(json.dumps({"latency": 11}))
    c = T.collect(d, fresh=fr)
    st = {i["id"]: i["fresh"] for i in c["items"]}
    assert st["V-T"]["state"] == "differs" and "committed pass, fresh fail" in st["V-T"]["detail"]
    assert st["V-W"]["state"] == "differs"                      # the wildcard also meets a test the committed record lacks
    assert st["V-M"]["state"] == "differs" and "committed 8, fresh 11" in st["V-M"]["detail"]
    assert next(i for i in c["items"] if i["id"] == "V-T")["status"] == "pass"       # the committed verdict is not rewritten
    md = T.render_md(c, repo)
    assert md.count("committed record differs from fresh run") >= 3
    assert "differs from fresh run" not in T.render_md(T.collect(d), repo)


def test_a_skipped_or_absent_test_is_not_re_run_not_a_difference(repo, tmp_path_factory):
    d = make_plan(repo)
    fr = tmp_path_factory.mktemp("fresh")
    junit(fr / "results" / "j.xml", {"test_a::one": "skip"})
    c = T.collect(d, fresh=fr)
    assert next(i for i in c["items"] if i["id"] == "V-T")["fresh"]["state"] == "not_rerun"
    r = F.compare_record("results/j.xml", "junit", fr)
    assert r["state"] == "agrees" and r["not_rerun"] == 2


def test_compare_flags_and_exit_state(repo, tmp_path_factory):
    d = make_plan(repo)
    fr = tmp_path_factory.mktemp("fresh")
    junit(fr / "results" / "j.xml", {"test_a::one": "fail", "test_a::two": "pass"})
    r = F.compare(fr, [d])
    assert r["differs"] and {i["item"] for i in r["items_differing"]} == {"V-T", "V-W"}
    assert F.compare_record("results/j.xml", "junit", fr)["state"] == "differs"
    assert "committed record differs" in F.render_report(r) or "differs from the fresh run" in F.render_report(r)
    junit(fr / "results" / "j.xml", {"test_a::one": "pass", "test_a::two": "pass"})
    assert not F.compare(fr, [d])["differs"]


def test_a_job_that_never_reported_is_a_failure_when_its_tier_is_expected(repo, tmp_path_factory):
    d = make_plan(repo)
    fr = tmp_path_factory.mktemp("fresh")
    junit(fr / "results" / "j.xml", {"test_a::one": "pass", "test_a::two": "pass"})
    assert not F.compare(fr, [d])["differs"]
    r = F.compare(fr, [d], "github")
    assert r["differs"] and set(r["jobs_without_output"]) == {n for n, j in F.JOBS.items() if j["tier"] == "github"}


def test_volatile_keys_and_floats_do_not_count():
    a = {"seconds": 1, "tool": "yosys 1", "x": {"y": 1.0, "results": [{"seconds": 3, "v": 2}]}}
    b = {"seconds": 9, "tool": "yosys 2", "x": {"y": 1.0 + 1e-12, "results": [{"seconds": 4, "v": 2}]}}
    assert F.json_diff(F.strip_volatile(a), F.strip_volatile(b)) == []
    b["x"]["results"][0]["v"] = 3
    assert F.json_diff(F.strip_volatile(a), F.strip_volatile(b)) == ["x.results.0.v: committed 2 but fresh 3"]
    assert F.json_diff({"a": 1}, {"b": 1}) == ["a: only in the committed record", "b: only in the fresh run"]


def test_lean_record_comparison_ignores_the_log_hash_only():
    rec = {"build_ok": True, "toolchain": "t", "lean_version": "v", "build_log_sha256": "aa", "files": {"A.lean": "h"}, "rtl_sources": {},
           "theorems": {"th": {"build_ok": True, "axioms": ["propext"], "tier": "kernel_only", "statement_sha256": "s", "definitions_sha256": "d"}}}
    other = json.loads(json.dumps(rec))
    other["build_log_sha256"] = "bb"
    assert F.lean_diff(rec, other) == []
    other["lean_version"] = ""
    assert F.lean_diff(rec, other) == []
    other["theorems"]["th"]["tier"] = "unsound"
    other["files"]["A.lean"] = "h2"
    assert len(F.lean_diff(rec, other)) == 2


def test_assemble_joins_junit_parts(tmp_path):
    for n, cases in (("a", {"s::t1": "pass"}), ("b", {"s::t2": "fail", "s::t3": "skip"})):
        out = tmp_path / n
        part = junit(out / "_parts" / f"{n}.xml", cases)
        (out / "_manifests").mkdir()
        (out / "_manifests" / f"{n}.json").write_text(json.dumps({"job": n, "tier": "github", "rc": 0, "seconds": 1, "commit": "c", "dirty": False, "started": "t", "tools": {},
                                                                   "outputs": [{"committed": "results/r.xml", "part": f"_parts/{n}.xml", "kind": "junit", "present": part.exists()}]}))
    idx = F.assemble([tmp_path / "a", tmp_path / "b"], tmp_path / "all")
    assert idx["records"]["results/r.xml"]["jobs"] == ["a", "b"]
    assert F.junit_outcomes(tmp_path / "all" / "results" / "r.xml") == {"s::t1": "pass", "s::t2": "fail", "s::t3": "skip"}


def test_job_registry_points_at_real_records_and_tests():
    wf = (REPO / ".github" / "workflows" / "fresh-evidence.yml").read_text()
    for name, j in F.JOBS.items():
        if j["tier"] == "github":
            assert re.search(rf"\b{re.escape(name)}\b", wf), f"{name} is not run by the nightly workflow"
        for o in j["outputs"]:
            assert (REPO / o["committed"]).exists(), f"{name}: committed record {o['committed']} is missing"
        for a in j["argv"]:
            if a.startswith(("designs/", "flow/")) and not a.startswith("--") and "." in a.split("/")[-1].split("::")[0]:
                assert (REPO / a.split("::")[0]).exists(), f"{name}: {a}"
            elif a.startswith("designs/") and "." not in a.split("/")[-1]:
                assert (REPO / a).is_dir(), f"{name}: {a}"


def test_trace_v1_cli_reads_a_fresh_directory(tmp_path, capsys):
    """The real b119 plan against a directory that holds copies of its committed JUnit and measurement records: every re-run item agrees."""
    d = REPO / "designs" / "b119_tcp_fast"
    for rec in ("results/116_traceability/b119_tcp_fast/pytest_junit.xml", "results/b119/bench_sim.json", "results/b119/top_sim.json"):
        (tmp_path / rec).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rec).write_bytes((REPO / rec).read_bytes())
    c = T.collect(d, fresh=tmp_path)
    states = {i["fresh"]["state"] for i in c["items"]}
    assert "differs" not in states and "agrees" in states
    assert T.main(["show", "designs/b119_tcp_fast", "--fresh", str(tmp_path)]) == 0
    assert "differs from fresh run" not in capsys.readouterr().out
