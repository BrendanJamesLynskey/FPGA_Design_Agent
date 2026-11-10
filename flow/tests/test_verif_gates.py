"""flow/verif_gates.py: the traceability stages on T1, and the readers on synthetic data."""

from pathlib import Path

import yaml

from flow import verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"


def test_spec_items_are_all_traced_in_t1_testplan():
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    plan = yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    items = G.spec_items(spec)
    assert len(items) == 26
    traced = {s for r in plan["requirements"] for s in r["spec"]}
    assert set(items) == traced


def test_v0_v1_pass_and_v2_fails_without_run_data(tmp_path):
    rep = G.evaluate(T1, tmp_path / "none", [], tmp_path / "nof", None, None)
    assert rep["stages"]["V0"]["pass"] and rep["stages"]["V1"]["pass"]
    assert not rep["stages"]["V2"]["pass"] and rep["reached"] == "V1" and rep["first_failed"] == "V2"


def test_an_untraced_item_fails_v1(tmp_path, monkeypatch):
    plan = yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    plan["requirements"] = plan["requirements"][1:]
    real = yaml.safe_load
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "fpga-design-agent/testplan" in t else real(t))
    rep = G.evaluate(T1, tmp_path, [], tmp_path, None, None)
    assert not rep["stages"]["V1"]["checks"]["spec_items_traced"]["pass"]
    assert rep["stages"]["V1"]["checks"]["untraced_items"]["value"] == ["behaviour.counter[0]"]


def test_parse_cov_dat(tmp_path):
    f = tmp_path / "coverage.dat"
    f.write_text("# SystemC::Coverage-3\nC '\x01f\x02a.sv\x01l\x0210\x01t\x02line\x01o\x02block' 7\n")
    (kv, n), = G.parse_cov_dat(f)
    assert kv["t"] == "line" and kv["l"] == "10" and n == 7


def test_finish_reports_first_failed_stage():
    out = {"stages": {"V0": {"checks": {"a": {"pass": True}}}, "V1": {"checks": {"a": {"pass": False}}}}}
    r = G.finish(out)
    assert r["reached"] == "V0" and r["first_failed"] == "V1"


# ---- proof methods and sign-off traceability (brief 05d, Taylor addition 1) ---------------------------------

def _evaluate_with(spec_edit=None, plan_edit=None, tmp=None):
    plan = yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    (plan_edit or (lambda p: None))(plan)
    (spec_edit or (lambda s: None))(spec)
    real = yaml.safe_load
    def fake(text):
        if "fpga-design-agent/testplan" in text:
            return plan
        if "fpga-design-agent/spec" in text:
            return spec
        return real(text)
    return plan, spec, fake


def test_v1_fails_when_a_requirement_has_no_proof_method(tmp_path, monkeypatch):
    def drop(s):
        del s["requirements"][2]["proof"]
    _, _, fake = _evaluate_with(spec_edit=drop)
    monkeypatch.setattr(G.yaml, "safe_load", fake)
    c = G.evaluate(T1, tmp_path, [], tmp_path, None, None)["stages"]["V1"]["checks"]
    assert c["requirements_have_proof_method"]["value"] == ["REQ-03"] and not c["requirements_have_proof_method"]["pass"]


def test_v1_fails_when_a_method_has_no_artefact_and_when_one_does_not_resolve(tmp_path, monkeypatch):
    def cut(p):
        p["proof"] = [e for e in p["proof"] if not (e["requirement"] == "REQ-02" and e["method"] == "formal")]
        p["proof"].append({"requirement": "REQ-03", "method": "simulation", "artefact": "t1_cocotb.no_such_test"})
    _, _, fake = _evaluate_with(plan_edit=cut)
    monkeypatch.setattr(G.yaml, "safe_load", fake)
    c = G.evaluate(T1, tmp_path, [], tmp_path, None, None)["stages"]["V1"]["checks"]
    assert c["proof_methods_discharged"]["value"] == ["REQ-02:formal"]
    assert c["proof_references_resolve"]["value"] == ["REQ-03:simulation:t1_cocotb.no_such_test: not a test in the bench"]


def test_v1_fails_without_any_requirements(tmp_path, monkeypatch):
    _, _, fake = _evaluate_with(spec_edit=lambda s: s.pop("requirements"))
    monkeypatch.setattr(G.yaml, "safe_load", fake)
    c = G.evaluate(T1, tmp_path, [], tmp_path, None, None)["stages"]["V1"]["checks"]
    assert c["requirements_have_proof_method"]["value"] == ["spec.yaml has no requirements"]


def test_signoff_table_pass_fail_and_pending():
    reqs = [{"id": "R1", "text": "a", "proof": ["simulation", "formal", "hardware", "analysis"]}]
    entries = [{"requirement": "R1", "method": "simulation", "artefact": "m.t"},
               {"requirement": "R1", "method": "formal", "artefact": "job"},
               {"requirement": "R1", "method": "hardware", "artefact": "uart_tests:test_x"},
               {"requirement": "R1", "method": "analysis", "artefact": "post_route:setup"}]
    gj = {"stages": {"post_route": {"gates": {"setup": True}}}, "gates": {"setup": True}}
    hw = {"steps": {"uart_tests": {"pass": True, "cases": {"test_x": 0.1}}}}
    rows = G.trace_table(reqs, entries, {1: {"m.t": True}, 2: {"m.t": True}}, {"job_bmc": "PASS", "job_cover": "PASS"}, gj, hw)
    assert [r["result"] for r in rows] == ["pass"] * 4
    # a failing seed, a failing cover task, a missing bring-up case, a failed gate
    rows = G.trace_table(reqs, entries, {1: {"m.t": True}, 2: {"m.t": False}}, {"job_bmc": "PASS", "job_cover": "FAIL"},
                         {"stages": {"post_route": {"gates": {"setup": False}}}}, {"steps": {"uart_tests": {"pass": True, "cases": {}}}})
    assert [r["result"] for r in rows] == ["fail"] * 4
    # no evidence source yet: pending, which is not a pass
    rows = G.trace_table(reqs, entries, {}, {}, None, None)
    assert [r["result"] for r in rows] == ["pending"] * 4


def test_signoff_stage_fails_until_all_evidence_passes(tmp_path):
    rep = G.evaluate(T1, tmp_path / "none", [], tmp_path / "nof", None, None)
    so = rep["stages"]["SIGNOFF"]
    assert so["pass"] is False and len(rep["traceability"]) == 16
    assert "REQ-08:hardware=pending" in so["checks"]["every_method_has_passing_evidence"]["value"]


def test_a_skipped_testcase_is_not_a_pass(tmp_path):
    """QR1: cocotb writes <skipped/> for skip=True; it must not count as a passing test (V2 planned tests, random test)."""
    d = tmp_path / "seed1"
    d.mkdir()
    (d / "results.xml").write_text('<testsuites><testsuite name="s">'
                                   '<testcase classname="m" name="test_ok"/>'
                                   '<testcase classname="m" name="test_random_traffic"><skipped/></testcase>'
                                   '<testcase classname="m" name="test_bad"><failure/></testcase></testsuite></testsuites>')
    assert G.read_results([tmp_path]) == {1: {"m.test_ok": True, "m.test_random_traffic": False, "m.test_bad": False}}
