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
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "requirements:" in t else real(t))
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
