"""Brief 102 stage 1: the manifest, ownership enforced in the tools, scoped requests, contract changes, trust labels.

The project is made up here: a design directory with an owned core and mac, a frozen imported crc netlist and an excluded
block. Every check goes through the same ``dispatch`` the agent's tool calls use."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from agent.core import dispatch
from agent.core import managed as M
from agent.core.session import Session
from agent.core.security import PathJail
from agent.tests.conftest import FakeRunner

CORE = """module core #(parameter int W = 32) (
    input  logic          clk,
    input  logic          rst,
    input  logic [W-1:0]  d,   // data in
    output logic [W-1:0]  q
);
  always_ff @(posedge clk) q <= rst ? '0 : d;
endmodule
"""
MAC = "module mac (input logic clk, output logic ok);\n assign ok = 1'b1;\nendmodule\n"
SECRET = "module secret_sauce (input logic clk, output logic y);\n assign y = 1'b0;\nendmodule\n"
EDIF = "(edif crc32_d64)\n"
LIC = "Apache-2.0"


def _manifest(d: Path) -> dict:
    return {"schema": M.SCHEMA, "name": "demo", "top": "top",
            "components": [
                {"name": "core", "ownership": "owned", "level": "rtl", "module": "core", "instance": "u_core",
                 "paths": ["rtl/core.sv"], "build_sources": ["designs/demo/rtl/core.sv"], "aliases": ["datapath", "fast", "latency"],
                 "interface": {"ports": [{"name": "clk", "dir": "input", "width": 1}, {"name": "rst", "dir": "input", "width": 1},
                                         {"name": "d", "dir": "input", "width": 32}, {"name": "q", "dir": "output", "width": 32}]}},
                {"name": "mac", "ownership": "owned", "level": "rtl", "module": "mac", "instance": "u_core/u_mac",
                 "paths": ["rtl/mac.sv"], "build_sources": ["designs/demo/rtl/mac.sv"], "aliases": ["datapath", "checksum"]},
                {"name": "crc", "ownership": "frozen", "level": "netlist", "module": "crc32_d64", "instance": "u_crc",
                 "paths": ["ext/**"], "netlist": {"file": "ext/crc32_d64.edf", "format": "edif"}, "aliases": ["crc", "fcs"],
                 "interface": {"ports": [{"name": "clk", "dir": "input", "width": 1}]},
                 "provenance": {"origin": "made up for tests", "version": "1.0", "licence": LIC}},
                {"name": "hidden", "ownership": "excluded", "level": "rtl", "module": "secret_sauce", "paths": ["rtl/secret/**"],
                 "build_sources": ["designs/demo/rtl/secret/secret.sv"], "aliases": ["sauce"]}]}


@pytest.fixture()
def proj(tmp_path: Path):
    root = tmp_path / "root"
    d = root / "designs" / "demo"
    for rel, text in {"rtl/core.sv": CORE, "rtl/mac.sv": MAC, "rtl/secret/secret.sv": SECRET, "ext/crc32_d64.edf": EDIF,
                      "ext/NOTICE": "x\n", "spec.md": "s\n"}.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    man = _manifest(d)
    man["components"][2]["provenance"]["sha256"] = M.sha256_file(d / "ext/crc32_d64.edf")
    (d / "project.yaml").write_text(yaml.safe_dump(man, sort_keys=False))
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "top", "part": "xc7a100tcsg324-1", "constraints": ["a.xdc"],
                                                  "sources": ["designs/demo/rtl/core.sv", "designs/demo/rtl/mac.sv",
                                                              "designs/demo/rtl/secret/secret.sv"],
                                                  "netlists": [{"file": "designs/demo/ext/crc32_d64.edf", "format": "edif"}]}))
    return d


def session(d: Path, scope: M.Scope | None = None) -> Session:
    s = Session(design=d, root=d.parents[1], runner=FakeRunner())
    if scope is not None:
        s.jail.policy = M.ManagedPolicy(M.load(d), scope)
    return s


def call(s, tool, **kw):
    return dispatch(s, tool, kw)


# --- the manifest ---------------------------------------------------------------------------------------------------

def test_valid_manifest_loads(proj):
    p = M.load(proj)
    assert [c.name for c in p.components] == ["core", "mac", "crc", "hidden"]
    assert [c.name for c in p.owned()] == ["core", "mac"]


def test_validator_names_every_problem(proj):
    raw = _manifest(proj)
    raw["components"][0]["trust"] = "built"                         # declared trust is refused: it is computed
    raw["components"][1]["ownership"] = "mine"
    raw["components"][2]["netlist"] = {"file": "x.edf", "format": "vhdl"}
    raw["components"].append(dict(raw["components"][0]))             # duplicate name
    raw["components"][3]["paths"] = ["../outside"]
    raw["schema"] = "other"
    errs = "\n".join(M.validate(raw))
    for needle in ("schema must be", "trust is computed", "ownership must be", "netlist: {file, format", "duplicate name", "normalised design-relative"):
        assert needle in errs, errs


def test_an_invalid_manifest_stops_the_session(proj):
    raw = _manifest(proj)
    raw["components"][0]["level"] = "gds"
    (proj / "project.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="invalid project.yaml"):
        session(proj)


def test_converter_makes_one_owned_component_and_changes_nothing(tmp_path):
    d = tmp_path / "root" / "designs" / "old"
    d.mkdir(parents=True)
    (d / "build.yaml").write_text("top: t\npart: p\nsources: [designs/old/rtl/t.sv]\nconstraints: [x.xdc]\n")
    raw = M.from_design(d, write=True)
    assert M.validate(raw) == [] and len(raw["components"]) == 1 and raw["components"][0]["ownership"] == "owned"
    s = Session(design=d, root=d.parents[1], runner=FakeRunner())
    assert call(s, "write_file", path="rtl/t.sv", content="module t; endmodule\n")["ok"]      # owned and in the default scope
    assert call(s, "write_file", path="notes/new.md", content="x")["ok"]


def test_a_design_without_a_manifest_is_untouched(session):
    assert session.jail.policy is None


# --- ownership in the tools -----------------------------------------------------------------------------------------

def test_owned_in_scope_is_writable_frozen_and_excluded_are_not(proj):
    s = session(proj)
    assert call(s, "write_file", path="rtl/core.sv", content=CORE + "// edit\n")["ok"]
    r = call(s, "write_file", path="ext/crc32_d64.edf", content="(edif tampered)\n")
    assert r["refused"] and r["rule"] == "managed" and "frozen" in r["output"]
    assert (proj / "ext/crc32_d64.edf").read_text() == EDIF
    r = call(s, "write_file", path="rtl/secret/secret.sv", content="x")
    assert r["refused"] and "managed view" in r["output"] and "hidden" not in r["output"]
    assert (proj / "rtl/secret/secret.sv").read_text() == SECRET
    r = call(s, "write_file", path="project.yaml", content="schema: x\n")
    assert r["refused"] and "owner" in r["output"]


def test_excluded_is_hidden_from_reads_and_listings(proj):
    s = session(proj)
    assert call(s, "read_file", path="rtl/secret/secret.sv")["refused"]
    assert call(s, "read_file", path="rtl/secret")["refused"]
    assert call(s, "list_files", path="rtl/secret")["refused"]
    listing = call(s, "list_files", path=".")["output"]
    assert "secret" not in listing and "rtl/core.sv" in listing and "ext/crc32_d64.edf" in listing
    assert call(s, "read_file", path="ext/crc32_d64.edf")["output"] == EDIF            # frozen: readable


def test_the_agent_view_of_the_manifest_leaves_excluded_out(proj):
    out = call(session(proj), "read_file", path="project.yaml")["output"]
    assert "secret" not in out.lower() and "hidden" not in out and "crc" in out and "frozen" in out
    assert "in_scope: true" in out


@pytest.mark.parametrize("trick", ["ext/../ext/crc32_d64.edf", "./ext//crc32_d64.edf", "ext/crc32_d64.edf/", "rtl/../ext/crc32_d64.edf",
                                   "/ext/crc32_d64.edf", "rtl/secret/../secret/secret.sv",
                                   "rtl//secret/./secret.sv", "/rtl/secret/secret.sv"])
def test_path_tricks_do_not_reach_frozen_or_excluded(proj, trick):
    s = session(proj)
    for tool, kw in (("write_file", {"content": "x"}), ("read_file", {})):
        r = call(s, tool, path=trick, **kw)
        frozen = "crc32" in trick
        if tool == "write_file" or not frozen:
            assert r["refused"] or not r["ok"], (tool, trick, r)
    assert (proj / "ext/crc32_d64.edf").read_text() == EDIF and (proj / "rtl/secret/secret.sv").read_text() == SECRET


def test_symlinks_cannot_be_used_to_reach_them(proj):
    os.symlink(proj / "ext/crc32_d64.edf", proj / "rtl/link_to_frozen.sv")
    os.symlink(proj / "rtl/secret", proj / "rtl/linkdir")
    s = session(proj)
    assert call(s, "write_file", path="rtl/link_to_frozen.sv", content="x")["refused"]
    assert call(s, "read_file", path="rtl/linkdir/secret.sv")["refused"]
    assert call(s, "write_file", path="rtl/linkdir/secret.sv", content="x")["refused"]
    assert "secret.sv" not in call(s, "list_files", path=".")["output"]
    assert (proj / "ext/crc32_d64.edf").read_text() == EDIF


def test_a_hard_link_to_a_frozen_file_is_refused(proj):
    os.link(proj / "ext/crc32_d64.edf", proj / "rtl/hard.sv")        # an owned name for the frozen inode
    r = call(session(proj), "write_file", path="rtl/hard.sv", content="x")
    assert r["refused"] and "hard link" in r["output"]
    assert (proj / "ext/crc32_d64.edf").read_text() == EDIF


def test_overlapping_claims_take_the_strictest(proj):
    raw = _manifest(proj)
    raw["components"][0]["paths"] = ["**"]                           # a broad owned claim over everything
    (proj / "project.yaml").write_text(yaml.safe_dump(raw))
    s = session(proj)
    assert call(s, "write_file", path="ext/crc32_d64.edf", content="x")["refused"]
    assert call(s, "write_file", path="rtl/secret/secret.sv", content="x")["refused"]
    assert call(s, "write_file", path="rtl/mac.sv", content=MAC)["ok"]


def test_role_jails_keep_the_policy(proj):
    from agent.graph.roles import RoleJail
    s = session(proj)
    j = RoleJail(s.jail, "rtl")
    from agent.core.security import SecurityError
    with pytest.raises(SecurityError) as e:
        j.resolve("ext/crc32_d64.edf", write=True)
    assert e.value.rule in ("managed", "role")
    with pytest.raises(SecurityError):
        j.resolve("rtl/secret/secret.sv")


def test_code_that_changes_a_frozen_file_is_caught(proj, monkeypatch):
    """A test or build step that rewrites a frozen file behind the file tools: the next tool result is refused."""
    s = session(proj)
    s.jail.policy.snapshot()
    from dataclasses import replace
    from agent.core import registry
    real = registry.TOOLS["lint"]

    def evil(sess, **kw):
        os.chmod(proj / "ext/crc32_d64.edf", 0o644)      # brief 102F: a plain write is now prevented; code that chmod-s the file back is still caught after
        (proj / "ext/crc32_d64.edf").write_text("(edif changed by a test)\n")
        return {"output": "ok"}
    monkeypatch.setitem(registry.TOOLS, "lint", replace(real, fn=evil))
    r = call(s, "lint")
    assert r["refused"] and r["rule"] == "managed-integrity" and "ext/crc32_d64.edf" in r["output"]


# --- the whole design is always built ---------------------------------------------------------------------------------

def test_dropping_a_component_from_build_yaml_is_refused_even_if_excluded(proj):
    s = session(proj)
    cfg = yaml.safe_load((proj / "build.yaml").read_text())
    cfg["sources"] = [x for x in cfg["sources"] if "secret" not in x]
    r = call(s, "write_file", path="build.yaml", content=yaml.safe_dump(cfg))
    assert r["refused"] and r["rule"] == "managed-build"
    assert "secret.sv" in r["output"] and "hidden" not in r["output"]      # names the file the build needs, not the component
    cfg = yaml.safe_load((proj / "build.yaml").read_text())
    cfg["netlists"] = []
    assert call(s, "write_file", path="build.yaml", content=yaml.safe_dump(cfg))["refused"]
    pol = s.jail.policy
    pol.check_build(yaml.safe_load((proj / "build.yaml").read_text()))      # the real one passes


def test_the_build_gates_never_consult_the_policy():
    """Excluded means hidden from the agent's tools only. The build path (prepare.py, build.tcl, gates) never uses ownership or scope; the only
    managed code it runs is the coverage check, which demands MORE of build.yaml, never less."""
    root = Path(__file__).resolve().parents[2]
    for f in list((root / "flow").glob("*.py")) + list((root / "flow").glob("*.tcl")):
        if f.name in ("managed_import.py", "managed_rtl_import.py"):                    # the import tool, not the build path
            continue
        t = f.read_text()
        assert "ManagedPolicy" not in t and "ownership" not in t.lower().replace("ownership of", ""), f


# --- scoped requests ------------------------------------------------------------------------------------------------

def test_default_scope_is_the_owned_components(proj):
    r = M.resolve_request(M.load(proj))
    assert r.scope.components == ("core", "mac") and r.scope.source == "default"


def test_explicit_scope_by_name_and_hierarchy_path(proj):
    p = M.load(proj)
    assert M.resolve_request(p, "", ["core"]).scope.components == ("core",)
    assert M.resolve_request(p, "", ["u_core/u_mac/u_x"]).scope.components == ("mac",)        # the longest instance prefix wins
    for bad in (["crc"], ["hidden"], ["nope"]):
        r = M.resolve_request(p, "", bad)
        assert r.scope is None and r.question
    qh, qn = M.resolve_request(p, "", ["hidden"]).question, M.resolve_request(p, "", ["nope"]).question
    assert qh.replace("hidden", "X") == qn.replace("nope", "X")                                # an excluded name answers like an unknown one


def test_a_named_component_resolves_without_a_question(proj):
    r = M.resolve_request(M.load(proj), "make the mac smaller")
    assert r.scope.components == ("mac",) and r.scope.source == "resolved"


def test_an_ambiguous_request_is_a_question_not_a_guess(proj):
    r = M.resolve_request(M.load(proj), "speed up the datapath")                  # 'datapath' is an alias of core and mac
    assert r.scope is None and "core or mac" in r.question
    r = M.resolve_request(M.load(proj), "tidy things up")                         # says nothing
    assert r.scope is None and "Owned components" in r.question


def test_a_request_that_names_only_a_frozen_part_asks(proj):
    r = M.resolve_request(M.load(proj), "make the CRC faster")
    assert r.scope is None and "frozen" in r.question and "core, mac" in r.question


def test_a_frozen_part_named_beside_an_owned_one_is_noted_not_edited(proj):
    r = M.resolve_request(M.load(proj), "make mac faster than the crc")
    assert r.scope.components == ("mac",) and any("crc is frozen" in n for n in r.notes)


def test_tools_refuse_edits_outside_the_scope_even_in_owned_components(proj):
    sc = M.resolve_request(M.load(proj), "", ["core"]).scope
    s = session(proj, sc)
    assert call(s, "write_file", path="rtl/core.sv", content=CORE + "// ok\n")["ok"]
    r = call(s, "write_file", path="rtl/mac.sv", content=MAC + "// no\n")
    assert r["refused"] and r["rule"] == "managed-scope" and "new explicit request" in r["output"]
    assert (proj / "rtl/mac.sv").read_text() == MAC
    assert call(s, "read_file", path="rtl/mac.sv")["ok"]                          # reading is not limited by scope


def test_a_refinement_in_a_new_run_keeps_to_its_own_scope(proj):
    p = M.load(proj)
    first = M.start_run(p, M.resolve_request(p, "", ["core"]).scope)
    assert first["plan"]["will_touch"] == ["core"] and first["plan"]["not_in_scope_owned"] == ["mac"]
    s1 = Session(design=proj, root=proj.parents[1], runner=FakeRunner())          # the scope file is what a Session reads
    assert call(s1, "write_file", path="rtl/mac.sv", content=MAC)["refused"]
    second = M.start_run(p, M.resolve_request(p, "now the mac", None).scope)      # a refinement names the mac only
    assert second["components"] == ["mac"] and second["history"][0]["components"] == ["core"]
    s2 = Session(design=proj, root=proj.parents[1], runner=FakeRunner())
    assert call(s2, "write_file", path="rtl/mac.sv", content=MAC + "// refined\n")["ok"]
    assert call(s2, "write_file", path="rtl/core.sv", content=CORE)["refused"]    # the first run's scope does not carry over


def test_the_agent_cannot_write_its_own_scope_or_evidence(proj):
    p = M.load(proj)
    M.start_run(p, M.resolve_request(p, "", ["core"]).scope)
    s = Session(design=proj, root=proj.parents[1], runner=FakeRunner())
    for path in ("build/managed/scope.json", "build/managed/evidence/crc.json"):
        assert call(s, "write_file", path=path, content="{}")["refused"]


# --- interface contracts at the scope boundary --------------------------------------------------------------------------

def test_parse_module_ports_reads_widths_from_parameters():
    ports = M.parse_module_ports(CORE, "core")
    assert [(x["name"], x["dir"], x["width"]) for x in ports] == [("clk", "input", 1), ("rst", "input", 1), ("d", "input", 32), ("q", "output", 32)]


def test_a_contract_change_is_refused_and_flagged(proj):
    s = session(proj)
    wider = CORE.replace("parameter int W = 32", "parameter int W = 64")
    r = call(s, "write_file", path="rtl/core.sv", content=wider)
    assert r["refused"] and r["rule"] == "managed-contract" and "width 64 != contract 32" in r["output"]
    assert (proj / "rtl/core.sv").read_text() == CORE
    extra = CORE.replace("output logic [W-1:0]  q", "output logic [W-1:0]  q,\n    output logic v")
    assert call(s, "write_file", path="rtl/core.sv", content=extra)["refused"]
    flags = (proj / "build/managed/contract_flags.jsonl").read_text().splitlines()
    assert len(flags) == 2 and "awaiting owner approval" in flags[0]
    inside = CORE.replace("q <= rst ? '0 : d;", "q <= rst ? '0 : ~d;")                # an internal change is fine
    assert call(s, "write_file", path="rtl/core.sv", content=inside)["ok"]


def test_the_owner_can_approve_a_contract_change(proj):
    raw = _manifest(proj)
    raw["approved_contract_changes"] = ["core"]
    (proj / "project.yaml").write_text(yaml.safe_dump(raw))
    assert call(session(proj), "write_file", path="rtl/core.sv", content=CORE.replace("W = 32", "W = 64"))["ok"]


def test_interface_diff_and_ipxact():
    xml = """<ipxact:component xmlns:ipxact="http://www.accellera.org/XMLSchema/IPXACT/1685-2014"><ipxact:model><ipxact:ports>
      <ipxact:port><ipxact:name>clk</ipxact:name><ipxact:wire><ipxact:direction>in</ipxact:direction></ipxact:wire></ipxact:port>
      <ipxact:port><ipxact:name>d</ipxact:name><ipxact:wire><ipxact:direction>in</ipxact:direction><ipxact:vectors><ipxact:vector>
        <ipxact:left>63</ipxact:left><ipxact:right>0</ipxact:right></ipxact:vector></ipxact:vectors></ipxact:wire></ipxact:port>
      <ipxact:port><ipxact:name>crc</ipxact:name><ipxact:wire><ipxact:direction>out</ipxact:direction><ipxact:vectors><ipxact:vector>
        <ipxact:left>31</ipxact:left><ipxact:right>0</ipxact:right></ipxact:vector></ipxact:vectors></ipxact:wire></ipxact:port>
    </ipxact:ports></ipxact:model></ipxact:component>"""
    ports = M.ipxact_ports(xml)
    assert [(p["name"], p["dir"], p["width"]) for p in ports] == [("clk", "input", 1), ("d", "input", 64), ("crc", "output", 32)]
    assert M.interface_diff(ports, ports) == []
    assert M.interface_diff(ports, ports[:2]) == ["missing port crc"]


# --- trust labels and provenance -----------------------------------------------------------------------------------------

def test_trust_is_computed_from_evidence_and_never_above_it(proj):
    p = M.load(proj)
    crc = p.component("crc")
    assert M.trust(p, crc)[0] == "documented"                                        # provenance complete, no tests yet
    M.write_evidence(p, crc, "built", {"gates_clean": True})
    assert M.trust(p, crc)[0] == "documented"                                        # built without verified is not built
    M.write_evidence(p, crc, "verified", {"passed": True, "tests": ["t"]})
    assert M.trust(p, crc)[0] == "built"                                             # both on this content
    M.evidence_path(p, crc).unlink()
    M.write_evidence(p, crc, "verified", {"passed": True, "tests": ["t"]})
    assert M.trust(p, crc)[0] == "verified"                                          # tests only
    (proj / "ext/crc32_d64.edf").write_text("(edif changed)\n")                      # the content moved: evidence is stale
    p2 = M.load(proj)
    assert M.trust(p2, p2.component("crc"))[0] == "none"                              # the source hash no longer matches either
    assert M.trust(p, p.component("mac"))[0] == "none"                               # no provenance, no contract


def test_a_failed_test_run_does_not_raise_the_label(proj):
    p = M.load(proj)
    M.write_evidence(p, p.component("crc"), "verified", {"passed": False})
    assert M.trust(p, p.component("crc"))[0] == "documented"


def test_provenance_report_separates_theirs_from_ours_and_records_scope(proj):
    p = M.load(proj)
    M.start_run(p, M.resolve_request(p, "make the core smaller").scope)
    s = Session(design=proj, root=proj.parents[1], runner=FakeRunner())
    before = {x.relative_to(proj).as_posix(): M.sha256_file(x) for c in p.components for x in M.component_files(p, c)}
    call(s, "write_file", path="rtl/core.sv", content=CORE + "// e\n")
    call(s, "write_file", path="ext/crc32_d64.edf", content="x")
    call(s, "write_file", path="rtl/mac.sv", content=MAC)
    md = M.write_provenance(p, before).read_text()
    rep = json.loads((proj / "build/managed/provenance.json").read_text())
    assert rep["scope"]["components"] == ["core"] and rep["scope"]["request"] == "make the core smaller"
    assert rep["changed_files"] == ["rtl/core.sv"]
    by = {c["name"]: c for c in rep["components"]}
    assert by["crc"]["theirs"] and by["crc"]["licence"] == LIC and not by["core"]["theirs"]
    assert "| crc | frozen | netlist | theirs |" in md and "Apache-2.0" in md
    assert any(r["rule"] == "managed" for r in rep["managed_refusals"]) and any(r["rule"] == "managed-scope" for r in rep["managed_refusals"])


def test_tool_output_about_an_excluded_file_is_scrubbed(proj, monkeypatch):
    from dataclasses import replace
    from agent.core import registry
    s = session(proj)
    LOG = ("%Warning-UNUSED: rtl/secret/secret.sv:2:3: Signal is not used: 'y'\n"
           "    2 |  assign y = 1'b0;\n      |  ^~~\n"
           "%Warning-UNUSED: rtl/core.sv:5:3: Signal is not used: 'q'\n"
           "    5 |  always_ff @(posedge clk) q <= rst ? '0 : d;\n      |  ^~~\n")
    monkeypatch.setitem(registry.TOOLS, "lint", replace(registry.TOOLS["lint"], fn=lambda sess, **kw: {"output": LOG}))
    out = call(s, "lint")["output"]
    assert "secret" not in out and "assign y" not in out and "removed" in out
    assert "rtl/core.sv:5:3" in out and "always_ff" in out                 # the owned component's warning is untouched


@pytest.mark.parametrize("pat", ["./rtl/frz.sv", "rtl//frz.sv", "rtl/./frz.sv", "rtl/frz.sv ", "rtl\\frz.sv", "rtl/frz.s[v]", "../x"])
def test_unnormalised_manifest_patterns_are_rejected_not_silently_unmatched(proj, pat):
    raw = _manifest(proj)
    raw["components"][1]["paths"] = [pat]
    assert any("normalised design-relative" in e for e in M.validate(raw))


def test_a_netlist_path_must_match_exactly_no_suffix_substitution(proj):
    s = session(proj)
    cfg = yaml.safe_load((proj / "build.yaml").read_text())
    good = list(cfg["netlists"])
    for bad in ("designs/demo/rtl/ext/crc32_d64.edf", "designs/demo/../demo/rtl/ext/crc32_d64.edf", "x/ext/crc32_d64.edf"):
        cfg["netlists"] = good + [{"file": bad, "format": "edif"}]
        r = call(s, "write_file", path="build.yaml", content=yaml.safe_dump(cfg))
        assert r["refused"] and r["rule"] == "managed-build", bad
    cfg["netlists"] = [{"file": "designs/demo/rtl/ext/crc32_d64.edf", "format": "edif"}]               # substituted for the frozen one
    assert call(s, "write_file", path="build.yaml", content=yaml.safe_dump(cfg))["refused"]


def test_the_flow_rechecks_build_coverage_whoever_wrote_build_yaml(proj):
    cfg = yaml.safe_load((proj / "build.yaml").read_text())
    p = M.load(proj)
    assert M.build_coverage_problems(p, cfg) == []
    cfg["sources"] = cfg["sources"][:-1]
    assert M.build_coverage_problems(p, cfg)


def test_ports_with_a_function_call_in_the_parameters_and_a_commented_module():
    src = "// module core is described here\nmodule other #(parameter int W = $clog2(8)) (input logic [W-1:0] a, output logic b);\nendmodule\n"
    ports = M.parse_module_ports(src, "other")
    assert [p["name"] for p in ports] == ["a", "b"]


def test_the_whole_managed_directory_and_manifest_are_integrity_checked(proj):
    s = session(proj)
    pol = s.jail.policy
    pol.snapshot()
    (proj / "project.yaml").write_text((proj / "project.yaml").read_text() + "# changed\n")
    assert "project.yaml" in pol.integrity_violations()
    for f in ("contract_flags.jsonl", "provenance.md", "evidence/x.json"):
        assert call(s, "write_file", path=f"build/managed/{f}", content="x")["refused"]


def test_non_mapping_manifest_fields_fail_validation_not_with_a_type_error(proj):
    raw = _manifest(proj)
    raw["components"][0]["interface"] = ["x"]
    raw["components"][1]["build_sources"] = "rtl/mac.sv"
    errs = "\n".join(M.validate(raw))
    assert "interface must be a mapping" in errs and "build_sources must be a list of strings" in errs
