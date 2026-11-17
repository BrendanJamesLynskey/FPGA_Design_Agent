"""Brief 102 stage 1: importing a netlist made outside the project (flow/managed_import.py), on the demonstration design
designs/b102_managed_fcs: interface against the contract, licence and hash, simulation of the functional netlist, eqy against the
supplier's RTL (and a planted fault that must fail it), the boundary CDC and timing-budget checks, and the build plumbing."""

from __future__ import annotations

import json
import os
import shutil
import sys
import zlib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.core import managed as M  # noqa: E402
from flow import managed_import as I  # noqa: E402
from flow import prepare  # noqa: E402

DESIGN = ROOT / "designs" / "b102_managed_fcs"
OSS = os.environ.get("FDA_OSS_CAD")
HAVE_YOSYS = bool(shutil.which("yosys", path=(f"{OSS}/bin:" if OSS else "") + os.environ["PATH"])) and bool(
    shutil.which("iverilog")) and bool(shutil.which("eqy", path=(f"{OSS}/bin:" if OSS else "") + os.environ["PATH"]))
need_suite = pytest.mark.skipif(not HAVE_YOSYS, reason="needs yosys, eqy (the OSS CAD Suite, FDA_OSS_CAD) and iverilog; skipped with this notice")


@pytest.fixture()
def project(tmp_path):
    d = tmp_path / "designs" / DESIGN.name
    shutil.copytree(DESIGN, d, ignore=shutil.ignore_patterns("build", "__pycache__"))
    return M.load(d)


def test_the_demonstration_manifest_is_valid_and_names_the_four_kinds():
    p = M.load(DESIGN)
    kinds = {c.name: (c.ownership, c.level) for c in p.components}
    assert kinds == {"top": ("owned", "rtl"), "ctrl": ("owned", "rtl"), "crc": ("frozen", "netlist"), "heartbeat": ("excluded", "rtl")}
    assert "trust" not in json.dumps(p.raw)                              # computed, never declared


def test_the_netlist_interface_matches_the_contract_in_edif_and_verilog(project):
    crc = project.component("crc")
    assert I.check_interface(project, crc) == []
    for f in ("ext/crc32_d16.edf", "ext/crc32_d16_netlist.v"):
        ports = {p["name"]: (p["dir"], p["width"]) for p in I.netlist_ports(project.design / f, "crc32_d16")}
        assert ports == {"clk": ("input", 1), "rst": ("input", 1), "init": ("input", 1), "en": ("input", 1), "d": ("input", 16), "crc": ("output", 32)}


def test_a_netlist_that_does_not_match_its_contract_is_refused(project):
    crc = project.component("crc")
    crc.interface["ports"][4]["width"] = 32                              # the contract says d is 32 bits: the netlist's 16 disagree
    assert I.check_interface(project, crc) == ["d: width 16 != contract 32"]
    crc.interface["ports"].pop()
    assert I.check_interface(project, crc) == ["d: width 16 != contract 32", "extra port crc"]


def test_licence_and_hash_are_recorded_and_checked(project):
    crc = project.component("crc")
    assert I.licence_problems(crc) == [] and "MIT" in crc.provenance["licence"]
    crc.provenance.pop("licence")
    assert I.licence_problems(crc) == ["provenance.licence is not recorded"]
    (project.design / "ext/crc32_d16.edf").write_text("(edif tampered)\n")
    assert "sha256 does not match" in " ".join(M.provenance_gaps(M.load(project.design), M.load(project.design).component("crc")))


def test_the_frozen_netlist_is_not_trusted_above_its_evidence(project):
    crc = project.component("crc")
    assert M.trust(project, crc)[0] == "documented"                      # provenance complete, no test has run in this project
    assert M.trust(project, project.component("ctrl"))[0] == "none"      # no provenance, no contract evidence


def test_the_model_is_the_complement_of_zlib():
    words = [(i * 0x1111 + 0x6978) & 0xFFFF for i in range(16)]
    v = [(0, 1 if i == 0 else 0, 1, w) for i, w in enumerate(words)]
    assert I.crc32_model(v, 16)[-1] == zlib.crc32(b"".join(w.to_bytes(2, "little") for w in words)) ^ 0xFFFFFFFF
    assert I.crc32_model(v, 16)[-1] != 0xFFFFFFFF


def test_the_sequencers_expected_value_is_the_models(project):
    words = [(int(f"{i:02x}" * 2, 16) ^ 0x6978) for i in range(16)]
    got = I.crc32_model([(0, 1 if i == 0 else 0, 1, w) for i, w in enumerate(words)], 16)[-1]
    assert f"32'h{got:08X}" in (project.design / "rtl/fcs_ctrl.sv").read_text()


@need_suite
def test_simulation_and_eqy_pass_on_the_delivered_netlist_and_write_evidence(project, tmp_path):
    rep = I.import_check(project.design, run_eqy=True, run_sim=True, work=tmp_path / "w")
    r = rep["components"]["crc"]
    assert rep["passed"] and r["simulation"]["passed"] and r["simulation"]["mismatches"] == 0 and r["eqy"]["equivalent"] is True
    p = M.load(project.design)
    assert M.trust(p, p.component("crc"))[0] == "verified"               # own tests passed here; never 'built' without a build


@need_suite
def test_a_planted_fault_fails_both_simulation_and_eqy(project, tmp_path):
    what = I.plant_fault(project.design / "ext/crc32_d16_netlist.v", tmp_path / "bad.v")
    assert "INIT" in what
    flat = I.flatten_netlist(tmp_path / "bad.v", "crc32_d16", tmp_path / "bad_flat.v")
    eq = I.eqy_prove([project.design / "ext/reference/crc32_d16.sv"], flat, "crc32_d16", tmp_path / "eqy")
    assert eq["ran"] and eq["equivalent"] is False and eq["unproven"]
    sim = I.simulate_crc_netlist(flat, "crc32_d16", tmp_path / "sim", 16)
    assert sim["passed"] is False and sim["mismatches"] > 0


def test_a_netlist_with_a_renamed_port_fails_the_interface_check_whatever_its_hash_says(project):
    (project.design / "ext/crc32_d16.edf").write_text(project.design.joinpath("ext/crc32_d16.edf").read_text().replace("(port clk", "(port clk2", 1))
    p = M.load(project.design)
    p.component("crc").provenance["sha256"] = M.sha256_file(project.design / "ext/crc32_d16.edf")      # a tamperer who also fixes the hash
    r = I.check_interface(p, p.component("crc"))
    assert "missing port clk" in r and "extra port clk2" in r


# --- the boundary ---------------------------------------------------------------------------------------------------

CDC = """CDC Report

ID      Severity  Count  Description
------  --------  -----  ----------------------------------------------
CDC-1   Critical      1  1-bit unknown CDC circuitry

Source Clock: clk_a
Destination Clock: clk_b
CDC Type: No Common Primary Clock

Row  ID     Severity  Description                      Depth  Exception  Source (From)    Destination (To)
---  -----  --------  -------------------------------  -----  ---------  ---------------  ----------------
  1  CDC-1  Critical  1-bit unknown CDC circuitry          0  None       u_ctrl/pass_reg/C  led_reg/D
  2  CDC-1  Critical  1-bit unknown CDC circuitry          0  None       other/a_reg/C      u_crc/crc_reg[3]/D
"""


def test_boundary_cdc_picks_only_rows_that_touch_the_slot():
    r = I.boundary_cdc(CDC, "u_crc")
    assert [x["to"] for x in r["rows"]] == ["u_crc/crc_reg[3]/D"] and r["clean"] is False
    assert I.boundary_cdc(CDC, "u_hb")["clean"] is True and I.boundary_cdc(CDC.replace("CDC-1  Critical", "CDC-3  Info    "), "u_crc")["clean"] is True


def test_budgets_are_parsed_and_checked():
    meas = I.parse_budgets("noise\nBUDGET|crc_to_verdict|3.200|0.450\nBUDGET|word_to_crc|none|none\n")
    assert meas[0] == {"name": "crc_to_verdict", "delay_ns": 3.2, "slack_ns": 0.45}
    probs = I.check_budgets([{"name": "crc_to_verdict", "max_ns": 3.0}, {"name": "word_to_crc", "max_ns": 4.0}], meas)
    assert probs == ["budget crc_to_verdict: 3.200 ns exceeds 3.0 ns", "budget word_to_crc: no path measured"]


def test_the_budget_tcl_measures_each_direction():
    t = I.budget_tcl("u_crc", [{"name": "a", "dir": "out", "max_ns": 1}, {"name": "b", "dir": "in", "max_ns": 1}], "x.dcp")
    assert "open_checkpoint {x.dcp}" in t and "fda_budget {a} $fda_in $fda_out" in t and "fda_budget {b} $fda_out $fda_in" in t
    assert "NAME =~ u_crc/*" in t


def test_funcsim_tcl():
    assert "write_verilog -force -mode funcsim {o.v}" in I.funcsim_tcl("c.dcp", "o.v")


# --- the build plumbing -----------------------------------------------------------------------------------------------

def test_prepare_emits_the_netlist_tcl_and_hashes_the_file():
    tcl = prepare.netlist_tcl([{"file": "designs/b102_managed_fcs/ext/crc32_d16.edf", "format": "edif"},
                               {"file": "designs/b102_managed_fcs/ext/crc32_d16.edf", "format": "checkpoint", "cell": "u_x"}], ROOT)
    assert tcl[0].startswith("set netlists {{edif {") and "{checkpoint {" in tcl[0] and "{u_x}}" in tcl[0]
    with pytest.raises(SystemExit):
        prepare.netlist_tcl([{"file": "a.dcp", "format": "checkpoint"}], ROOT)
    with pytest.raises(SystemExit):
        prepare.netlist_tcl([{"file": "a.vhd", "format": "vhdl"}], ROOT)


def test_the_build_stamp_covers_the_netlist(tmp_path):
    import subprocess
    out = tmp_path / "b"
    r = subprocess.run([sys.executable, str(ROOT / "flow/prepare.py"), str(DESIGN.relative_to(ROOT)), "--out", str(out)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    prep = json.loads(r.stdout)
    assert "designs/b102_managed_fcs/ext/crc32_d16.edf" in prep["files"]
    inputs = (out / "inputs.tcl").read_text()
    assert "set netlists {{edif {" in inputs and "crc32_d16.edf" in inputs


def test_an_agent_build_yaml_may_only_name_the_projects_netlists(tmp_path):
    from agent.core import dispatch
    from agent.core.session import Session
    from agent.tests.conftest import FakeRunner
    d = tmp_path / "designs" / DESIGN.name
    shutil.copytree(DESIGN, d, ignore=shutil.ignore_patterns("build", "__pycache__"))
    shutil.copytree(ROOT / "boards" / "kr260", tmp_path / "boards" / "kr260")
    s = Session(design=d, root=tmp_path, runner=FakeRunner(), board="kr260")
    cfg = yaml.safe_load((d / "build.yaml").read_text())
    cfg["netlists"].append({"file": "designs/b102_managed_fcs/ext/NOTICE.md", "format": "edif"})
    (d / "build.yaml").write_text(yaml.safe_dump(cfg))
    r = dispatch(s, "lint", {})
    assert r["refused"] and "not a netlist component" in r["output"]
    cfg["netlists"] = []
    (d / "build.yaml").write_text(yaml.safe_dump(cfg))
    r = dispatch(s, "lint", {})
    assert r["refused"] and r["rule"] == "managed-build"                  # the netlist is part of the build: dropping it is refused
