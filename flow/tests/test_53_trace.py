"""Brief 53: the traceability matrix and its gates (flow/traceability.py), the change record (flow/change_record.py), the
migration helper (flow/trace_tag.py) and the HDL coding standard (flow/lint_ruleset.py).

The fixture design (fixtures/trace53/mini) is copied to a temporary directory and given run records written here, so
every known-bad case is a small edit of a copy. T1 is checked on the committed reference run (data/ref_t1_sim).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from flow import change_record as cr
from flow import lint_ruleset as lr
from flow import traceability as tr
from flow import trace_tag as tt

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
MINI = HERE / "fixtures" / "trace53" / "mini"
T1 = ROOT / "designs" / "t1_dimmer_counter"
TESTS = ["counts_and_wraps", "holds_when_disabled", "reset_mid_count", "zz_export"]


def results_xml(path: Path, tests: dict[str, bool]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = "".join(f'<testcase classname="mini_bench" name="{n}">' + ("" if ok else "<failure/>") + "</testcase>"
                    for n, ok in tests.items())
    path.write_text(f'<testsuites><testsuite name="all">{cases}</testsuite></testsuites>\n')


def cov_line(f: str, line: int, typ: str, obj: str, n: int) -> str:
    page = "v_user/mini_checker" if typ == "user" else f"v_{typ}/mini"
    return f"C '\x01f\x02{f}\x01l\x02{line}\x01t\x02{typ}\x01page\x02{page}\x01o\x02{obj}\x01h\x02top.{obj}' {n}\n"


def make_run(design: Path, tests: dict[str, bool] | None = None, extra_cov: list[str] | None = None,
             wrap_hits: int = 3) -> Path:
    """Write seed1 results, coverage.dat and coverage_func.yml for the copy; formal status files; gates.json."""
    run = design / "build" / "sim"
    results_xml(run / "seed1" / "results.xml", tests or {t: True for t in TESTS})
    rtl = f"/x/{design.name}/rtl/mini.sv"
    chk = f"/x/{design.name}/verif/checkers/mini_checker.sv"
    lines = [cov_line(rtl, 5, "line", "block", 9), cov_line(rtl, 6, "line", "block", 7),
             cov_line(rtl, 3, "toggle", "en:0->1", 2), cov_line(rtl, 3, "toggle", "en:1->0", 2),
             cov_line(rtl, 3, "toggle", "rst:0->1", 1), cov_line(rtl, 3, "toggle", "rst:1->0", 0),
             cov_line(chk, 5, "user", "C_WRAP", wrap_hits)] + (extra_cov or [])
    (run / "seed1" / "coverage.dat").write_text("# SystemC::Coverage-3\n" + "".join(lines))
    (run / "seed1" / "coverage_func.yml").write_text(yaml.safe_dump({"mini.en": {"bins:_hits": {"on": 4, "off": 2}}}))
    for task in ("bmc", "cover"):
        (design / "build" / "formal" / f"mini_{task}").mkdir(parents=True, exist_ok=True)
        (design / "build" / "formal" / f"mini_{task}" / "status").write_text("PASS 0\n")
    (design / "build" / "gates.json").write_text(json.dumps({"stages": {"post_route": {"gates": {"setup": True}}}}))
    return run


def build(design: Path, **kw):
    run = design / "build" / "sim"
    return tr.build(design, run, formal=design / "build" / "formal", gates=design / "build" / "gates.json", **kw)


@pytest.fixture
def mini(tmp_path: Path) -> Path:
    d = tmp_path / "mini"
    shutil.copytree(MINI, d)
    return d


# ---- the clean case ---------------------------------------------------------------------------------------------
def test_mini_matrix_passes(mini):
    make_run(mini)
    t = build(mini)
    assert t["pass"], {k: v.get("why") for k, v in t["gates"].items() if not v["pass"]}
    rows = {r["id"]: r for r in t["requirements"]}
    assert [m["method"] for m in rows["REQ-01"]["methods"]] == ["simulation", "formal"]
    assert all(m["status"] == "pass" for r in rows.values() for m in r["methods"])
    assert rows["REQ-01"]["design_elements"] == ["mini"]                 # RTL header tag and the bound checker
    assert {s["name"] for s in rows["REQ-01"]["supporting"]} == {"A_COUNT_UP", "C_WRAP"}
    s = t["artefact_summary"]
    assert (s["total"], s["citing"], s["robustness"], s["structural"], s["untagged"]) == (8, 6, 1, 1, 0)
    assert t["inputs"]["source"] == "computed" and t["inputs"]["kb_pin"]
    assert "not a claim of compliance" in t["note"]
    md = tr.to_markdown(t)
    assert "| **REQ-01**" in md and "coverage_holes_justified | PASS" in md


# ---- the three known-bad runs of the brief --------------------------------------------------------------------------
def test_known_bad_deleted_test_fails_requirements_verified(mini):
    bench = mini / "tests" / "mini_bench.py"
    src = bench.read_text()
    cut = src.index("# req: REQ-02")
    bench.write_text(src[:cut] + src[src.index("# robustness"):])        # the only test of REQ-02 is gone
    make_run(mini, {t: True for t in TESTS if t != "holds_when_disabled"})
    t = build(mini)
    g = t["gates"]["requirements_verified"]
    assert not g["pass"] and g["value"] == ["REQ-02:simulation=missing"]
    assert "REQ-02:simulation=missing" in g["why"]
    assert not t["pass"]


def test_known_bad_untagged_test_fails_artefacts_cite(mini):
    bench = mini / "tests" / "mini_bench.py"
    bench.write_text(bench.read_text() + "\n\n@cocotb.test()\nasync def extra_smoke(dut):\n    pass\n")
    make_run(mini, {**{t: True for t in TESTS}, "extra_smoke": True})
    g = build(mini)["gates"]["artefacts_cite_requirements"]
    assert not g["pass"]
    assert len(g["value"]) == 1 and g["value"][0].startswith("test mini_bench.extra_smoke (")
    assert "untagged: test mini_bench.extra_smoke" in g["why"]


def test_known_bad_unjustified_hole_fails_coverage(mini):
    rtl = f"/x/{mini.name}/rtl/mini.sv"
    make_run(mini, extra_cov=[cov_line(rtl, 7, "line", "block", 0)])     # an added branch no test reaches
    g = build(mini)["gates"]["coverage_holes_justified"]
    assert not g["pass"] and g["value"] == ["line mini.sv:7 block"]
    assert "1 coverage hole(s)" in g["why"] and "mini.sv:7 block" in g["why"]


# ---- the other gates and rules ------------------------------------------------------------------------------------
def test_failing_seed_and_missing_formal_fail(mini):
    make_run(mini, {**{t: True for t in TESTS}, "counts_and_wraps": False})
    shutil.rmtree(mini / "build" / "formal" / "mini_cover")
    (mini / "build" / "formal" / "mini_bmc" / "status").write_text("FAIL 1\n")
    g = build(mini)["gates"]["requirements_verified"]
    assert set(g["value"]) == {"REQ-01:simulation=fail", "REQ-01:formal=fail"}


def test_pending_evidence_only_passes_when_deferred(mini):
    make_run(mini)
    (mini / "build" / "gates.json").unlink()
    assert build(mini)["gates"]["requirements_verified"]["value"] == ["REQ-03:analysis=pending"]
    assert build(mini, defer=("analysis",))["gates"]["requirements_verified"]["pass"]


def test_unknown_id_and_reasonless_marks_fail(mini):
    bench = mini / "tests" / "mini_bench.py"
    s = bench.read_text().replace('@req("REQ-01")', '@req("REQ-99")').replace(
        "# structural: exports the functional-coverage database; checks nothing", "# structural: x")
    bench.write_text(s)
    make_run(mini)
    v = build(mini)["gates"]["artefacts_cite_requirements"]["value"]
    assert "test mini_bench.counts_and_wraps cites REQ-99" in v
    assert "test mini_bench.zz_export is structural without a reason" in v


def test_waiver_without_owner_or_date_fails(mini):
    j = mini / "verif" / "justifications.yaml"
    d = yaml.safe_load(j.read_text())
    del d["coverage"][0]["owner"]
    d["coverage"][0]["date"] = "last week"
    j.write_text(yaml.safe_dump(d))
    make_run(mini)
    g = build(mini)["gates"]["waivers_complete"]
    assert not g["pass"] and "no owner, no date (YYYY-MM-DD)" in g["value"][0]


def test_inline_std_waive_needs_owner_and_date(mini):
    rtl = mini / "rtl" / "mini.sv"
    rtl.write_text(rtl.read_text().replace("    always_ff", "    // std-waive: STD-RST-01 the spec asks for it\n    always_ff"))
    make_run(mini)
    assert not build(mini)["gates"]["waivers_complete"]["pass"]
    rtl.write_text(rtl.read_text().replace("the spec asks for it", "the spec asks for it [owner: a reviewer; date: 2026-11-11]"))
    assert build(mini)["gates"]["waivers_complete"]["pass"]


def test_no_coverage_points_in_design_rtl_fails(mini):
    run = make_run(mini)
    dat = run / "seed1" / "coverage.dat"
    dat.write_text(dat.read_text().replace(f"/x/{mini.name}/rtl/", "/elsewhere/rtl/"))
    g = build(mini)["gates"]["coverage_holes_justified"]
    assert not g["pass"] and g["value"] == "no points in the design RTL"


def test_match_item_brackets_are_literal():
    assert tr.match_item("a.sv:3 x[4]:0->1", "a.sv:* x[4]:*")
    assert not tr.match_item("a.sv:3 x[5]:0->1", "a.sv:* x[4]:*")
    assert tr.match_item("a.sv:3 x[5]:0->1", r"re:a\.sv:\d+ x\[[45]\]:.*")


# ---- change record --------------------------------------------------------------------------------------------------
def test_changed_requirement_is_stale_until_reconfirmed(mini, tmp_path):
    make_run(mini)
    base = tmp_path / "base.json"
    base.write_text(json.dumps(build(mini)))
    spec = mini / "spec.yaml"
    spec.write_text(spec.read_text().replace("COUNT holds its value while enable is low",
                                             "COUNT holds its value while enable is low or reset is high"))
    t = build(mini, baseline=base)
    assert t["change"]["text_changed"] == ["REQ-02"] and t["change"]["stale"] == ["REQ-02"]
    assert not t["gates"]["changed_requirements_reverified"]["pass"]
    assert {r["id"]: r["status"] for r in t["requirements"]}["REQ-02"] == "stale"
    h = {r["id"]: r["req_hash"] for r in t["requirements"]}["REQ-02"]
    j = mini / "verif" / "justifications.yaml"
    d = yaml.safe_load(j.read_text())
    d["reconfirmed"] = [{"requirement": "REQ-02", "req_hash": h[:12], "owner": "a reviewer", "date": "2026-11-11",
                         "reason": "the hold test already holds reset low throughout"}]
    j.write_text(yaml.safe_dump(d))
    assert build(mini, baseline=base)["gates"]["changed_requirements_reverified"]["pass"]


def test_changed_evidence_clears_stale(mini, tmp_path):
    make_run(mini)
    base = tmp_path / "base.json"
    base.write_text(json.dumps(build(mini)))
    spec = mini / "spec.yaml"
    spec.write_text(spec.read_text().replace("while enable is low", "while enable is low or reset is high"))
    bench = mini / "tests" / "mini_bench.py"
    bench.write_text(bench.read_text().replace("async def holds_when_disabled(dut):\n    pass",
                                               "async def holds_when_disabled(dut):\n    pass  # now also under reset"))
    t = build(mini, baseline=base)
    assert t["change"]["evidence_changed"] == ["REQ-02"] and t["change"]["stale"] == []


def test_manifest_is_read_when_present(mini):
    m = {"inputs": {"rtl/mini.sv": "ab" * 32}, "tools": {"vivado": "2026.1"}, "kb_pin": "811b840",
         "flow": {"commit": "abc", "dirty": False}, "options": {"threads": 2}}
    (mini / "build" / "base").mkdir(parents=True)
    (mini / "build" / "base" / "manifest.json").write_text(json.dumps(m))
    r = cr.read_manifest(mini)
    assert r["source"] == "manifest" and r["tools"] == {"vivado": "2026.1"} and r["extra"] == {"options": {"threads": 2}}
    assert r["missing_keys"] == []
    (mini / "build" / "base" / "manifest.json").write_text("not json")
    r = cr.read_manifest(mini)
    assert r["source"] == "computed" and "not readable JSON" in r["note"] and "rtl/mini.sv" in "".join(r["inputs"])


# ---- T1 on the committed reference run ------------------------------------------------------------------------------
def test_t1_matrix_on_reference_run(tmp_path):
    formal = tmp_path / "formal"
    for job in ("debounce", "scan"):
        for task in ("bmc", "cover"):
            (formal / f"{job}_{task}").mkdir(parents=True)
            (formal / f"{job}_{task}" / "status").write_text("PASS 0\n")
    t = tr.build(T1, HERE / "data" / "ref_t1_sim", formal=formal, hw=ROOT / "results" / "f0b" / "t1_dimmer_counter_bringup.json",
                 defer=("analysis",))
    assert t["pass"], {k: v.get("why") for k, v in t["gates"].items() if not v["pass"]}
    assert len(t["requirements"]) == 11 and t["artefact_summary"]["untagged"] == 0
    assert t["artefact_summary"]["structural"] == 1
    holes = t["coverage"]["holes"]
    assert len(holes) == 113 and all(h["justified_by"] for h in holes)       # 111 toggle points and two covers
    analysis = [m for r in t["requirements"] for m in r["methods"] if m["method"] == "analysis"]
    assert analysis and all(m["status"] == "pending" for m in analysis)


def test_t1_spec_requirements_pass_the_quality_check():
    from agent.graph.spec_schema import requirement_quality_errors
    assert requirement_quality_errors(yaml.safe_load((T1 / "spec.yaml").read_text())) == []


def test_static_problems_name_untagged(mini):
    assert tr.static_problems(mini) == []
    bench = mini / "tests" / "mini_bench.py"
    bench.write_text(bench.read_text() + "\n\n@cocotb.test()\nasync def extra(dut):\n    pass\n")
    p = tr.static_problems(mini)
    assert len(p) == 1 and "mini_bench.extra" in p[0]


# ---- migration helper -------------------------------------------------------------------------------------------------
def test_trace_tag_migrates_from_the_testplan(mini):
    bench = mini / "tests" / "mini_bench.py"
    bench.write_text(bench.read_text().replace('@req("REQ-01")\n', ""))
    chk = mini / "verif" / "checkers" / "mini_checker.sv"
    chk.write_text(chk.read_text().replace("   // req: REQ-01", "", 1))
    plan = mini / "verif" / "testplan.yaml"
    p = yaml.safe_load(plan.read_text())
    p["proof"].append({"requirement": "REQ-01", "method": "simulation", "artefact": "mini_bench.counts_and_wraps"})
    p["requirements"].append({"id": "REQ-01", "spec": [], "assertions": ["A_COUNT_UP"]})
    plan.write_text(yaml.safe_dump(p))
    todo, left = tt.propose(mini)
    assert {(x["kind"], x["name"]): x["ids"] for x in todo} == {("test", "mini_bench.counts_and_wraps"): ["REQ-01"],
                                                                 ("assertion", "A_COUNT_UP"): ["REQ-01"]}
    assert left == []
    assert tt.insert(mini, todo) == 2
    assert "# req: REQ-01 (from testplan)\n@cocotb.test()\nasync def counts_and_wraps" in bench.read_text()
    assert tt.propose(mini) == ([], [])


# ---- FDA-HDL: the coding standard ------------------------------------------------------------------------------------
def test_rule_set_is_well_formed():
    rs = lr.load_rules()
    assert lr.rule_problems(rs) == []
    assert rs["standard"] == "FDA-HDL" and rs["version"] == "1.0"
    assert lr.rule_for(rs, "verilator", "LATCH") == "HDL-SYN-01"
    assert lr.rule_for(rs, "verilator", "WIDTHTRUNC") == "HDL-WID-01"
    assert lr.rule_for(rs, "verilator", "SOMETHINGNEW") == "HDL-LINT-00"
    assert lr.rule_for(rs, "vivado", "XDCH-2") == "HDL-XDC-01"
    assert lr.rule_for(rs, "vivado", "CFGBVS-1") == "HDL-DRC-01"
    assert lr.rule_for(rs, "vivado", "ZZZZ-9") == "HDL-VIV-00"
    assert lr.rule_for(rs, "standards", "STD-CDC-01") == "HDL-CDC-01"


def test_rule_set_waivers(mini):
    gates = mini / "gates.json"
    gates.write_text(json.dumps({"stages": {"rtl": {"methodology": {"rules": [
        {"rule": "XDCH-2", "severity": "Warning", "description": "Same min and max delay values on IO port", "count": 3},
        {"rule": "RFFH-1", "severity": "Advisory", "description": "high fanout", "count": 1}]}}}}))
    rep = lr.evaluate(mini, gates, None, run_verilator=False)
    xdc = next(r for r in rep["rules"] if r["id"] == "HDL-XDC-01")
    assert xdc["status"] == "fail" and xdc["findings"][0]["key"] == "vivado:XDCH-2@rtl" and not rep["pass"]
    (mini / "lint").mkdir()
    (mini / "lint" / "waivers.yaml").write_text(yaml.safe_dump({"waivers": [
        {"rule": "HDL-XDC-01", "match": "vivado:XDCH-2@*", "reason": "the shell's I/O delays are deliberately symmetric",
         "owner": "a reviewer", "date": "2026-11-11"}]}))
    rep = lr.evaluate(mini, gates, None, run_verilator=False)
    xdc = next(r for r in rep["rules"] if r["id"] == "HDL-XDC-01")
    assert xdc["status"] == "waived" and rep["pass"] and rep["unused_waivers"] == []
    (mini / "lint" / "waivers.yaml").write_text(yaml.safe_dump({"waivers": [{"rule": "HDL-XDC-01", "match": "vivado:XDCH-2@*"}]}))
    rep = lr.evaluate(mini, gates, None, run_verilator=False)
    assert not rep["pass"] and rep["bad_waivers"]
    assert next(r for r in rep["rules"] if r["id"] == "HDL-WAIVE-01")["status"] == "fail"
