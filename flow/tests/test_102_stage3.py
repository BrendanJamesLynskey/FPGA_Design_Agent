"""Brief 102 stage 3: a real third-party block (Alex Forencich's verilog-ethernet lfsr.v, MIT) inside a managed project.

The design is designs/b102_managed_ext. These tests check what is theirs and what is ours: the vendored file is byte-for-byte the
recorded one, the manifest names the licence and commit, a modified or relicensed copy lowers the trust label, the block is correct
against a model and a planted fault in it is caught, the tools refuse every route to edit it while the adapter stays editable, and
the whole design passes its self-test. Simulations need Icarus Verilog (skipped with a notice without it)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.core import dispatch  # noqa: E402
from agent.core import managed as M  # noqa: E402
from agent.core.session import Session  # noqa: E402
from agent.tests.conftest import FakeRunner  # noqa: E402
from flow import managed_rtl_import as R  # noqa: E402

DESIGN = ROOT / "designs" / "b102_managed_ext"
LFSR = "third_party/verilog-ethernet/lfsr.v"
need_iverilog = pytest.mark.skipif(not shutil.which("iverilog"), reason="needs Icarus Verilog; skipped with this notice")


@pytest.fixture()
def project(tmp_path):
    d = tmp_path / "designs" / DESIGN.name
    shutil.copytree(DESIGN, d, ignore=shutil.ignore_patterns("build", "__pycache__"))
    return M.load(d)


def _write_manifest(project, mutate):
    raw = yaml.safe_load((project.design / "project.yaml").read_text())
    mutate(next(c for c in raw["components"] if c["name"] == "lfsr"))
    (project.design / "project.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    return M.load(project.design)


def test_the_manifest_is_valid_and_splits_theirs_from_ours():
    p = M.load(DESIGN)
    assert {c.name: (c.ownership, c.level) for c in p.components} == {
        "top": ("owned", "rtl"), "ctrl": ("owned", "rtl"), "crc_adapter": ("owned", "rtl"), "lfsr": ("frozen", "rtl")}
    assert M.validate(p.raw, DESIGN) == []
    assert "trust" not in json.dumps(p.raw)


def test_the_vendored_files_are_the_recorded_bytes_and_the_licence_is_open():
    p = M.load(DESIGN)
    lfsr = p.component("lfsr")
    assert M.third_party_gaps(p, lfsr) == []
    assert lfsr.provenance["spdx"] in M.OPEN_LICENCES and lfsr.provenance["spdx"] == "MIT"
    assert lfsr.provenance["commit"] == "77320a9471d19c7dd383914bc049e02d9f4f1ffb"
    text = (DESIGN / LFSR).read_text()
    assert "Copyright (c) 2016-2023 Alex Forencich" in text and "Permission is hereby granted" in text          # the licence travels in the file too
    assert "MIT" in (ROOT / "THIRD_PARTY_NOTICES.md").read_text() and "verilog-ethernet" in (ROOT / "THIRD_PARTY_NOTICES.md").read_text()


def test_a_modified_vendored_file_is_a_provenance_gap_and_lowers_the_label(project):
    f = project.design / LFSR
    f.write_text(f.read_text() + "\n// a local edit\n")
    gaps = M.third_party_gaps(project, project.component("lfsr"))
    assert any("differs from the hash recorded" in g for g in gaps)
    assert M.trust(project, project.component("lfsr"))[0] == "none"


@pytest.mark.parametrize("field,value,needle", [
    ("spdx", "GPL-3.0-only", "is not one of"),
    ("spdx", "Proprietary", "is not one of"),
    ("commit", "77320a9", "40-hex"),
    ("licence_file", "third_party/verilog-ethernet/NOPE", "licence_file is missing"),
])
def test_a_closed_licence_a_short_commit_or_a_missing_licence_file_is_a_gap(project, field, value, needle):
    p = _write_manifest(project, lambda c: c["provenance"].__setitem__(field, value))
    gaps = M.third_party_gaps(p, p.component("lfsr"))
    assert any(needle in g for g in gaps), gaps
    assert M.trust(p, p.component("lfsr"))[0] == "none"


def test_a_file_added_to_the_third_party_tree_without_a_recorded_hash_is_a_gap(project):
    (project.design / "third_party" / "extra.v").write_text("module x; endmodule\n")
    assert any("no recorded upstream hash" in g for g in M.third_party_gaps(project, project.component("lfsr")))


def test_the_interface_contract_is_checked_at_the_instantiated_parameters(project):
    assert R.contract_problems(project, project.component("lfsr")) == []
    p = _write_manifest(project, lambda c: c["interface"]["ports"][0].__setitem__("width", 8))     # the default DATA_WIDTH is 8, ours is 16
    assert R.contract_problems(p, p.component("lfsr")) == ["data_in: width 16 != contract 8"]


def test_the_step_model_agrees_with_zlib():
    data = bytes(range(250, 256)) + bytes(range(40))
    reg = 0xFFFFFFFF
    for i in range(0, len(data), 2):
        reg = R.crc_step(reg, int.from_bytes(data[i:i + 2], "little"), 16)
    assert reg == zlib.crc32(data) ^ 0xFFFFFFFF


def test_upstream_check_compares_each_file_with_the_commit_in_a_clone(project, tmp_path):
    clone = tmp_path / "clone"
    (clone / "rtl").mkdir(parents=True)
    for rel, up in project.component("lfsr").provenance["upstream_paths"].items():
        (clone / up).write_text((project.design / rel).read_text())
    env = ["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run([*env, "add", "-A"], check=True)
    subprocess.run([*env, "commit", "-q", "-m", "x"], check=True)
    sha = subprocess.run([*env, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    p = _write_manifest(project, lambda c: c["provenance"].__setitem__("commit", sha))
    assert R.upstream_problems(p.component("lfsr"), p, clone) == []
    (clone / "rtl" / "lfsr.v").write_text("module lfsr; endmodule\n")                                 # the upstream differs from our copy
    subprocess.run([*env, "commit", "-q", "-am", "y"], check=True)
    sha2 = subprocess.run([*env, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    p = _write_manifest(project, lambda c: c["provenance"].__setitem__("commit", sha2))
    assert any("differs from rtl/lfsr.v" in x for x in R.upstream_problems(p.component("lfsr"), p, clone))
    p = _write_manifest(project, lambda c: c["provenance"].__setitem__("commit", "0" * 40))
    assert "is not in" in R.upstream_problems(p.component("lfsr"), p, clone)[0]


@need_iverilog
def test_the_block_matches_the_model_at_four_widths_and_a_planted_fault_is_caught(project, tmp_path):
    p = project
    block = p.design / LFSR
    for w in R.STEP_WIDTHS:
        r = R.simulate_block(block, "lfsr", tmp_path / f"w{w}", w, n=300)
        assert r["passed"] and r["mismatches"] == 0, r
    fault = tmp_path / "fault.v"
    R.planted_fault_copy(block, fault)
    r = R.simulate_block(fault, "lfsr", tmp_path / "wf", 16, n=300)
    assert r["passed"] is False and r["mismatches"] > 0


@need_iverilog
def test_the_import_check_writes_verified_evidence_that_a_later_edit_invalidates(project):
    rep = R.import_check(project.design, work=project.design / "build" / "w")
    assert rep["passed"], json.dumps(rep, indent=1)[:2000]
    lfsr = project.component("lfsr")
    assert rep["components"]["lfsr"]["planted_fault"]["rejected_by_block_sim"] is True
    assert rep["components"]["lfsr"]["planted_fault"]["rejected_by_adapter_sim"] is True
    assert M.trust(project, lfsr) == ("verified", ["no build in this project with every gate clean on the current content"])
    M.write_evidence(project, lfsr, "built", {"gates_clean": True})
    assert M.trust(project, lfsr) == ("built", [])
    (project.design / LFSR).write_text((project.design / LFSR).read_text() + "\n")
    assert M.trust(project, lfsr)[0] == "none"                                      # no longer what was received


@need_iverilog
def test_a_changed_adapter_is_caught_by_the_adapter_simulation(project):
    f = project.design / "rtl" / "crc32_d16.sv"
    f.write_text(f.read_text().replace("32'hFFFFFFFF : crc", "32'h00000000 : crc"))            # the wrong restart value
    rep = R.import_check(project.design, work=project.design / "build" / "w")
    assert rep["passed"] is False and rep["components"]["lfsr"]["adapter_simulation"]["passed"] is False


@need_iverilog
def test_the_whole_design_passes_its_self_test_with_the_third_party_block(tmp_path):
    tb = tmp_path / "tb.sv"
    tb.write_text("module tb; reg c = 0; wire [1:0] led; fcs_top dut (.clk_25(c), .led(led)); always #5 c = ~c; initial dut.por = 0;\n"
                  "initial begin #4000; $display(\"RESULT pass=%0d crc=%h\", led[0], dut.crc); $finish; end endmodule\n")
    srcs = [str(f) for b in M.load(DESIGN).components for f in R.build_files(M.load(DESIGN), b)]
    subprocess.run(["iverilog", "-g2012", "-o", str(tmp_path / "s.vvp"), str(tb), *srcs], check=True, capture_output=True, text=True)
    out = subprocess.run(["vvp", str(tmp_path / "s.vvp")], check=True, capture_output=True, text=True).stdout
    assert "RESULT pass=1" in out, out


# --- the tools -------------------------------------------------------------------------------------------------------

def _session(d: Path) -> Session:
    return Session(design=d, root=d.parents[1], runner=FakeRunner())


def test_every_route_to_the_vendored_block_is_refused_while_the_adapter_stays_editable(project):
    s = _session(project.design)
    ad = (project.design / "rtl/crc32_d16.sv")
    assert dispatch(s, "write_file", {"path": "rtl/crc32_d16.sv", "content": ad.read_text() + "// ours\n"})["ok"]
    before = (project.design / LFSR).read_bytes()
    for tool, kw in (("write_file", {"path": LFSR, "content": "module lfsr; endmodule\n"}),
                     ("write_file", {"path": "third_party/verilog-ethernet/../verilog-ethernet/lfsr.v", "content": "x"}),
                     ("write_file", {"path": "rtl/../third_party/verilog-ethernet/lfsr.v", "content": "x"}),
                     ("write_file", {"path": "third_party/verilog-ethernet/COPYING", "content": "Public domain"}),
                     ("write_file", {"path": "third_party/verilog-ethernet/lfsr2.v", "content": "module lfsr; endmodule\n"})):
        r = dispatch(s, tool, kw)
        assert r.get("refused"), (tool, kw, r)
    assert (project.design / LFSR).read_bytes() == before
    link = project.design / "rtl" / "lfsr_link.v"
    link.symlink_to(project.design / LFSR)
    assert dispatch(s, "write_file", {"path": "rtl/lfsr_link.v", "content": "x"}).get("refused")
    assert (project.design / LFSR).read_bytes() == before


def test_a_build_that_drops_the_third_party_block_is_refused(project):
    s = _session(project.design)
    cfg = yaml.safe_load((project.design / "build.yaml").read_text())
    cfg["sources"] = [x for x in cfg["sources"] if "lfsr" not in x]
    r = dispatch(s, "write_file", {"path": "build.yaml", "content": yaml.safe_dump(cfg)})
    assert r.get("refused"), r
    assert M.build_coverage_problems(project, cfg)


def test_a_request_about_the_frozen_block_alone_asks_and_one_about_the_adapter_resolves(project):
    q = M.resolve_request(project, "make the lfsr faster")
    assert q.scope is None and q.question
    ok = M.resolve_request(project, "pipeline the crc adapter")
    assert ok.scope is not None and ok.scope.components == ("crc_adapter",)


def test_the_provenance_report_lists_theirs_and_ours(project):
    rep = M.provenance_report(project)
    by = {c["name"]: c for c in rep["components"]}
    assert by["lfsr"]["theirs"] is True and by["lfsr"]["licence"].startswith("MIT") and by["lfsr"]["origin"].startswith("Alex Forencich")
    assert all(by[n]["theirs"] is False for n in ("top", "ctrl", "crc_adapter"))
    assert any(f.endswith("lfsr.v") for f in by["lfsr"]["files"]) and not any(f.endswith("lfsr.v") for n in ("top", "ctrl", "crc_adapter") for f in by[n]["files"])
