"""Brief 05j: every failed V0-V3 check says why in plain words, above all when its value meets the threshold and a
hidden precondition (bins planned, code-coverage data present, mutation evidence) is what fails. Fixture: the
results.xml of the live Opus run, copied as three seeds."""

import re
import shutil
from pathlib import Path

import pytest

from agent.graph.repair import verif_failures
from flow import cocotb_run, verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"
FIXTURE = Path(__file__).parent / "data" / "opus_run_results.xml"


def _plan(monkeypatch, **kw):
    """T1's testplan with the evidence-bearing fields changed (bins, cover_props and thresholds)."""
    plan = G.yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    for r in plan["requirements"]:
        for k in ("bins", "cover_props"):
            if kw.get(k) is not None:
                r[k] = kw[k]
    plan["thresholds"].update(kw.get("thresholds", {}))
    real = G.yaml.safe_load
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "fpga-design-agent/testplan" in t else real(t))


def _seeds(tmp_path, n=3):
    runs = tmp_path / "sim"
    for s in range(1, n + 1):
        (runs / f"seed{s}").mkdir(parents=True)
        shutil.copy(FIXTURE, runs / f"seed{s}" / "results.xml")
    return runs


def _num(v):
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", v) if isinstance(v, str) else None
    return float(m.group(1)) if m else (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None)


def meets(c):
    """True when the check's value, read alone, satisfies its threshold (so a failure needs an explanation)."""
    v, t = c["value"], c["threshold"]
    if isinstance(t, list):
        return v == []
    if isinstance(t, bool):
        return v is t
    if isinstance(t, (int, float)):
        n = _num(v)
        return n is not None and n >= t if t else n == 0 or (n is not None and n >= t)
    if isinstance(t, str) and t.startswith(">="):
        n = _num(v)
        return n is not None and n >= float(t[2:])
    return False


def _every_failure_is_explained(rep):
    bad = []
    for st in ("V0", "V1", "V2", "V3"):
        for n, c in (rep["stages"].get(st) or {}).get("checks", {}).items():
            if c["pass"] or c["value"] == G.NOT_EVALUATED:
                continue
            if meets(c) and not c.get("why"):
                bad.append(f"{st} {n}: value {c['value']!r} meets {c['threshold']!r} but fails with no reason")
            if _num(c["value"]) is None and c["value"] is None:
                bad.append(f"{st} {n}: value None")
            if "None (need" in str(c):
                bad.append(f"{st} {n}: prints None")
    return bad


def test_no_check_fails_with_a_passing_looking_value_and_no_reason(tmp_path, monkeypatch):
    scenarios = []
    scenarios.append(G.evaluate(T1, tmp_path / "none", [], tmp_path / "nof", None, None))             # no seeds
    runs = _seeds(tmp_path)
    scenarios.append(G.evaluate(T1, runs, [], tmp_path / "nof", None, None))                           # seeds only
    _plan(monkeypatch, bins=[], cover_props=[], thresholds={"functional_bins_pct": 0, "cover_properties_pct": 0,
                                                               "line_pct": 80, "toggle_pct": 50})
    scenarios.append(G.evaluate(T1, runs, [], tmp_path / "nof", None, None))                           # the live run's plan
    mut = tmp_path / "m.json"
    mut.write_text('{"score_pct": 10}')
    scenarios.append(G.evaluate(T1, runs, [], tmp_path / "nof", mut, None))
    for rep in scenarios:
        assert _every_failure_is_explained(rep) == []


def test_the_live_runs_v3_failures_name_their_preconditions(tmp_path, monkeypatch):
    runs = _seeds(tmp_path)
    _plan(monkeypatch, bins=[], cover_props=[], thresholds={"functional_bins_pct": 0, "cover_properties_pct": 0,
                                                               "line_pct": 80, "toggle_pct": 50, "mutation_score_pct": 50})
    rep = G.evaluate(T1, runs, [], tmp_path / "nof", None, None)
    c = rep["stages"]["V3"]["checks"]
    assert "no functional bins planned" in c["functional_bins_pct"]["why"]
    assert "bins:" in c["functional_bins_pct"]["why"]
    for k in ("cover_properties_pct", "cover_properties_unhit"):
        assert not c[k]["pass"] and "no code-coverage data" in c[k]["why"] and "Verilator run of your bench" in c[k]["why"]
    for k in ("line_pct", "toggle_pct"):
        assert c[k]["value"] == "not measured" and c[k]["why"].startswith("not measured:") and "Verilator run of your bench" in c[k]["why"]
    assert c["mutation_score_pct"]["value"] == "not measured" and "the flow runs the mutation step itself" in c["mutation_score_pct"]["why"]
    rep["first_failed"], rep["reached"] = "V3", "V2"          # the repair text of the stage the live run stopped at
    text = "\n".join(verif_failures(rep, "V3"))
    assert "None" not in text and "no functional bins planned" in text and "no code-coverage data" in text
    assert "not measured" in text


def test_a_toggle_value_below_threshold_says_so(tmp_path, monkeypatch):
    c = G.chk(10.0, 50, False, "toggle coverage is 10.0%, below the threshold")
    assert c["why"] and not meets(c)
    assert "why" not in G.chk(1, 1, True, "ignored on a pass")


def test_other_hidden_preconditions_are_named(tmp_path):
    rep = G.evaluate(T1, _seeds(tmp_path), [], tmp_path / "nof", None, None)
    v2 = rep["stages"]["V2"]["checks"]
    assert "`formal` tool" in v2["formal_tasks_not_passing"]["why"]
    assert "FDA_COV_OUT" in rep["stages"]["V3"]["checks"]["functional_bins_pct"]["why"]


def test_collect_results_keeps_coverage_evidence(tmp_path, monkeypatch):
    build = tmp_path / "b"
    build.mkdir()
    shutil.copy(FIXTURE, build / "results.xml")
    (build / "coverage.dat").write_text("")
    (build / "coverage_func.yml").write_text("{}")
    dest = tmp_path / "out"
    cocotb_run.collect_results(build, 3, dest)
    cocotb_run.collect_results(build, 3, dest)
    names = sorted(p.name for p in (dest / "seed3").iterdir())
    assert names == ["coverage.dat", "coverage_2.dat", "coverage_func.yml", "coverage_func_2.yml", "results.xml"]
    assert len(list(dest.glob("seed*/coverage*.dat"))) == 2 and len(list(dest.glob("seed*/coverage*.yml"))) == 2


def test_merge_func_cov_reads_any_design_name(tmp_path):
    d = tmp_path / "seed1"
    d.mkdir()
    (d / "coverage_func.yml").write_text("top.cp:\n  bins:_hits:\n    a: 2\n    b: 0\n")
    assert G.merge_func_cov(tmp_path) == {"top.cp": {"a": 2, "b": 0}}

