"""Brief 18: the cross-probe summary and device map, and the MMCM search the Clocking Wizard is compared with.

The xprobe JSON is the one flow/xprobe.tcl wrote from a real routed build (results/project_parity/xprobe/), so the parser
tests run on real Vivado 2025.2 output. The clkwiz comparison reads the wizard's own answers (results/project_parity/clkwiz/).
"""

from __future__ import annotations

import json
import shutil
import xml.dom.minidom
from pathlib import Path

import pytest

from flow import gates, mmcm_search, xprobe

ROOT = Path(__file__).resolve().parents[2]
XP = ROOT / "results" / "project_parity" / "xprobe" / "b2_acl_adxl362.xprobe.json"
CW = ROOT / "results" / "project_parity" / "clkwiz" / "clkwiz.jsonl"


def test_summary_names_rtl_module_file_line_and_region():
    s = xprobe.summary(json.loads(XP.read_text()))
    setup = [p for p in s["paths"] if p["kind"] == "setup"][0]
    assert setup["slack_ns"] == s["wns_ns"]
    for end in ("from", "to"):
        assert setup[end]["module"].startswith("u_")
        assert setup[end]["file"].endswith(".sv") and setup[end]["line"] > 0
        assert setup[end]["clock_region"].startswith("X")
    assert "reset_sync.sv" in setup["text"]
    assert s["high_fanout_nets"][0]["fanout"] >= s["high_fanout_nets"][-1]["fanout"]
    assert s["high_fanout_nets"][0]["net"] == "rst" and s["high_fanout_nets"][0]["driver_line"] == 14   # reset_sync.sv:14


def test_files_are_repo_relative():
    x = json.loads(XP.read_text())
    assert not x["dcp"].startswith("/")
    assert all(not (p["start"]["file"] or "").startswith("/") for p in x["paths"])


def test_svg_is_well_formed_and_has_a_legend():
    svg = xprobe.render_svg(json.loads(XP.read_text()))
    doc = xml.dom.minidom.parseString(svg)
    assert doc.documentElement.tagName == "svg"
    assert "u_shell" in svg and "worst setup paths" in svg


def test_gates_add_xprobe_only_when_the_file_exists(tmp_path: Path):
    assert gates._xprobe_evidence(tmp_path) == {}
    shutil.copy(XP, tmp_path / "xprobe.json")
    ev = gates._xprobe_evidence(tmp_path)
    assert ev["xprobe"]["paths"] and "error" not in ev["xprobe"]
    (tmp_path / "xprobe.json").write_text("not json")
    assert "error" in gates._xprobe_evidence(tmp_path)["xprobe"]


@pytest.mark.parametrize("fin,outs,want", [
    (100, [25], (1, 12, 48)),
    (100, [74.25], (4, 37.125, 12.5)),
    (100, [200], (1, 12, 6)),
])
def test_mmcm_search_matches_the_kb_worked_values(fin, outs, want):
    r = mmcm_search.search(fin, outs)
    assert (r["d"], r["m"], r["o"][0]) == want and r["err"] < 1e-9


def test_mmcm_search_limits():
    assert mmcm_search.search(100, [900]) is None          # above 800 MHz
    assert mmcm_search.search(100, [4]) is None            # below 4.69 MHz
    r = mmcm_search.search(100, [200, 50], "PLL")
    assert 800 <= r["vco"] <= 1600 and r["f"] == [200.0, 50.0]
    r = mmcm_search.search(100, [12.288, 49.152, 98.304])
    assert 600 <= r["vco"] <= 1200


def test_wizard_comparison_rows():
    rows = mmcm_search.compare(str(CW))
    by = {r["name"]: r for r in rows}
    assert by["s1_74"]["wizard"]["m"] == by["s1_74"]["hand"]["m"] == 37.125        # the same M, D, O
    assert str(by["s5_900"]["wizard"]).startswith("rejected")                       # the wizard refuses 900 MHz
    assert by["s2_vga"]["hand"]["err"] < abs(by["s2_vga"]["wizard"]["f"][0] - 25.175)   # the search is closer for 25.175 MHz


def test_repair_visit_sees_the_cross_probe_lines_only_when_present():
    from agent.graph.stages import _stage_pass
    xp = xprobe.summary(json.loads(XP.read_text()))
    gates_json = {"stages": {"post_route": {"ran": True, "gates": {"setup": False, "hold": True}}}}
    ok, bad = _stage_pass(gates_json, "post_route")
    assert not ok and bad == ["post_route:setup"]                                   # unchanged without xprobe
    ok, bad = _stage_pass({**gates_json, "xprobe": xp}, "post_route")
    assert bad[0] == "post_route:setup" and bad[1].startswith("cross-probe: setup slack") and "reset_sync.sv:14" in bad[1]
