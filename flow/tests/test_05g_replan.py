"""Brief 05g: a formal proof method is discharged by a SymbiYosys job or re-planned with a reason, never by assertion."""

from pathlib import Path

import yaml

from flow import verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"


def _check(tmp_path, monkeypatch, plan_edit, installed):
    plan = yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    plan_edit(plan)
    real = yaml.safe_load
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "fpga-design-agent/testplan" in t
                        else spec if "fpga-design-agent/spec" in t else real(t))
    monkeypatch.setattr(G, "formal_installed", lambda: installed)
    return G.evaluate(T1, tmp_path, [], tmp_path, None, None)


def _replan(p, to="simulation", why="SymbiYosys is not installed on the build PC, so the check moves to the bench.",
            art="t1_cocotb.debounce_boundary_is_exact"):
    p["proof"] = [e for e in p["proof"] if not (e["requirement"] == "REQ-02" and e["method"] == "formal")]
    p["replan"] = [{"requirement": "REQ-02", "method": "formal", "replaced_by": to, "artefact": art, "why": why}]


def test_a_replan_discharges_the_method_only_when_sby_is_missing(tmp_path, monkeypatch):
    rep = _check(tmp_path, monkeypatch, _replan, installed=False)
    c = rep["stages"]["V1"]["checks"]
    assert c["proof_methods_discharged"]["pass"] and c["proof_references_resolve"]["pass"]
    row = next(r for r in rep["traceability"] if r["requirement"] == "REQ-02" and r["method"] == "formal")
    assert row["artefact"] == "t1_cocotb.debounce_boundary_is_exact" and row["detail"].startswith("re-planned from formal to simulation")
    assert row["result"] == "pending"            # no simulation results yet: the replacement's evidence decides, not the plan


def test_a_replan_is_refused_when_sby_is_installed(tmp_path, monkeypatch):
    c = _check(tmp_path, monkeypatch, _replan, installed=True)["stages"]["V1"]["checks"]
    assert not c["proof_references_resolve"]["pass"]
    assert "is installed here" in c["proof_references_resolve"]["value"][0]


def test_a_replan_needs_a_reason_a_real_replacement_and_only_formal(tmp_path, monkeypatch):
    c = _check(tmp_path, monkeypatch, lambda p: _replan(p, why="no"), installed=False)["stages"]["V1"]["checks"]
    assert "say why" in c["proof_references_resolve"]["value"][0]
    c = _check(tmp_path, monkeypatch, lambda p: _replan(p, art="t1_cocotb.nope"), installed=False)["stages"]["V1"]["checks"]
    assert "not a test in the bench" in c["proof_references_resolve"]["value"][0]
    c = _check(tmp_path, monkeypatch, lambda p: _replan(p, to="formal"), installed=False)["stages"]["V1"]["checks"]
    assert "replaced_by must be" in c["proof_references_resolve"]["value"][0]

    def other(p):
        _replan(p)
        p["replan"][0]["method"] = "simulation"
    c = _check(tmp_path, monkeypatch, other, installed=False)["stages"]["V1"]["checks"]
    assert "only the formal method" in c["proof_references_resolve"]["value"][0]


def test_without_a_replan_the_missing_formal_entry_still_fails(tmp_path, monkeypatch):
    def cut(p):
        p["proof"] = [e for e in p["proof"] if not (e["requirement"] == "REQ-02" and e["method"] == "formal")]
    c = _check(tmp_path, monkeypatch, cut, installed=False)["stages"]["V1"]["checks"]
    assert c["proof_methods_discharged"]["value"] == ["REQ-02:formal"] and not c["proof_methods_discharged"]["pass"]
