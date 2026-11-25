"""Brief 209a: a blocking report finding (RPT-LL-02, RPT-CS-02, RPT-LOG-03) of brief 204a sends the run back to the Designer before handover;
advisories never block. Recorded reports from flow/tests/data/204a: the c15 build that cannot close at 10 ns, and clean ones."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.graph import run as R
from agent.graph import stages as S
from agent.graph.repair import stage2_owners

D = Path(__file__).resolve().parents[2] / "flow" / "tests" / "data" / "204a"


def design(tmp_path: Path, files: dict[str, str]) -> SimpleNamespace:
    b = tmp_path / "d" / "build" / "base"
    b.mkdir(parents=True)
    for n, src in files.items():
        (b / n).write_text((D / src).read_text() if (D / src).is_file() else src)
    return SimpleNamespace(design=tmp_path / "d")


C15 = {"logic_levels_synth.rpt": "logic_levels_c15_deep.rpt", "timing_summary_synth.rpt": "timing_synth_deep_fails.rpt"}
CLEAN = {"logic_levels_synth.rpt": "logic_levels_ok.rpt", "timing_summary_synth.rpt": "timing_synth_ok.rpt"}


def test_a_c15_report_fails_the_gate_with_the_findings_own_text(tmp_path):
    rt = design(tmp_path, C15)
    r = R.report_gates_eval(rt)
    assert {f["code"] for f in r["findings"]} == {"RPT-LL-02"} and all(f["blocking"] for f in r["findings"])
    ok, why = S.report_gates_stage(r)
    assert not ok and why[0].startswith("report gate RPT-LL-02 ") and "setup path" in why[0] and "Fix:" in why[0]


def test_a_clean_report_passes(tmp_path):
    r = R.report_gates_eval(design(tmp_path, CLEAN))
    assert r["findings"] == [] and S.report_gates_stage(r) == (True, [])


def test_no_synthesis_report_or_no_record_is_not_a_failure(tmp_path):
    (tmp_path / "d" / "build" / "base").mkdir(parents=True)
    assert R.report_gates_eval(SimpleNamespace(design=tmp_path / "d")) is None
    assert S.report_gates_stage(None) == (True, [])


def test_advisories_are_listed_and_never_block():
    r = {"findings": [], "advisories": [{"code": "RPT-LL-01", "where": "clk", "message": "deep", "blocking": False}]}
    assert S.report_gates_stage(r) == (True, [])
    r2 = {"findings": [{"code": "RPT-CLK-02", "blocking": True, "message": "x"}], "advisories": []}      # a non-listed code never blocks here
    assert S.report_gates_stage(r2) == (True, [])


def test_the_gate_is_on_stages_2_3_and_4_and_routes_to_the_designer():
    for n in (2, 3, 4):
        assert "report_gates" in S.MACHINE[n].gates
    fails = S.report_gates_stage({"findings": [{"code": "RPT-LL-02", "blocking": True, "where": "x", "message": "m"}]})[1]
    for n in (3, 4):
        assert S.classify(S.MACHINE[n], fails) == "rtl"
        assert S.route_failure(S.MACHINE[n], "rtl") == 2
    ok, f = S.exit_check(S.MACHINE[3], {"constants": None, "gates_base": None, "report_gates": {"findings": [
        {"code": "RPT-LL-02", "blocking": True, "where": "x", "message": "m"}]}})
    assert any("report gate RPT-LL-02" in x for x in f)


def test_stage_2_hands_the_finding_to_the_rtl_role_with_the_advisories():
    ev = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True}, "verif": {"reached": "V3"}, "verif_level": "V3",
          "report_gates": {"findings": [{"code": "RPT-LL-02", "blocking": True, "where": "t:a->b", "message": "fails with no net delay", "fix": "pipeline it"}],
                           "advisories": [{"code": "RPT-LL-01", "where": "clk", "message": "12 levels", "blocking": False}]}}
    owners, sig = stage2_owners(ev)
    assert list(owners) == ["rtl"] and "report_gates" in sig
    text = owners["rtl"][0]
    assert "[report gates]" in text and "pipeline it" in text and "[advisories, not blocking] RPT-LL-01" in text
