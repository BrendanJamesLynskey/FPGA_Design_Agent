"""Brief 102 stage 2: placed-and-routed components. The manifest rules, the keep-out on constraints and on the RapidWright tools' arguments, the
trust label's need for placement evidence, the import check's reading of a checkpoint's facts, the placement comparison, and the scope in the
run record. No Vivado and no RapidWright here (CI has neither): the checkpoint's facts and the placement runs are fixtures in the form the
Tcl scripts write; the real ones are in results/102_managed_pr/."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest
import yaml

from agent.core import TOOLS, dispatch
from agent.core import managed as M
from agent.core import rapidwright_tools as rt
from agent.core.session import Session
from agent.tests.conftest import FakeRunner
from flow import managed_import as MI
from flow import managed_placed as MP
from flow import rapidwright_pin as pin

DCP = b"not a real checkpoint, only bytes for hashing"
GLUE = "module glue (input logic clk, output logic q);\n always_ff @(posedge clk) q <= ~q;\nendmodule\n"
PORTS = [{"name": n, "dir": d, "width": 1} for n, d in (("clk", "input"), ("rst", "input"), ("din", "input"), ("dout", "output"))]
FACTS = """VIVADO|2026.1
PART|xck26-sfvc784-2LV-c
TOP|blk
PORT|clk|in|1
PORT|din|in|1
PORT|dout|out|1
PORT|rst|in|1
CELLS|100|100|100|0
NETS|120|90|90|0
SITE|SLICEL|20
RECT|27|72|34|90
"""


def _manifest(d: Path) -> dict:
    return {"schema": M.SCHEMA, "name": "pr", "top": "top", "components": [
        {"name": "glue", "ownership": "owned", "level": "rtl", "module": "glue", "instance": "u_glue", "paths": ["rtl/glue.sv", "design.xdc"],
         "build_sources": ["designs/pr/rtl/glue.sv"], "aliases": ["driver"]},
        {"name": "blk", "ownership": "frozen", "level": "placed_routed", "module": "blk", "instance": "u_blk", "paths": ["ext/**"],
         "build_sources": ["designs/pr/ext/blk_bb.sv"], "netlist": {"file": "ext/blk.dcp", "format": "checkpoint", "cell": "u_blk"},
         "placement": {"lock": "routing", "region": "SLICE_X26Y70:SLICE_X37Y91", "anchor": "SLICE_X29Y80", "timing_tolerance_ps": 5},
         "interface": {"ports": PORTS, "timing_budgets": [{"name": "out_b", "dir": "out", "max_ns": 2.0}]},
         "provenance": {"origin": "made up for tests", "version": "1.0", "licence": "MIT"}, "aliases": ["block"]}]}


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    d = tmp_path / "root" / "designs" / "pr"
    for rel, text in {"rtl/glue.sv": GLUE, "ext/blk_bb.sv": "(* black_box *) module blk(input logic clk);endmodule\n", "design.xdc": "# none\n", "spec.md": "s\n"}.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    (d / "ext/blk.dcp").write_bytes(DCP)
    man = _manifest(d)
    man["components"][1]["provenance"]["sha256"] = M.sha256_file(d / "ext/blk.dcp")
    (d / "project.yaml").write_text(yaml.safe_dump(man, sort_keys=False))
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "top", "part": "xck26-sfvc784-2LV-c", "constraints": ["designs/pr/design.xdc"],
                                                  "sources": ["designs/pr/rtl/glue.sv", "designs/pr/ext/blk_bb.sv"],
                                                  "netlists": [{"file": "designs/pr/ext/blk.dcp", "format": "checkpoint", "cell": "u_blk"}]}))
    return d


def sess(d: Path) -> Session:
    s = Session(design=d, root=d.parents[1], runner=FakeRunner())
    s.jail.policy = M.policy_for(d)
    return s


def write(s, path, content):
    return dispatch(s, "write_file", {"path": path, "content": content})


# --- the manifest ---------------------------------------------------------------------------------------------------------------

def test_a_placed_routed_component_loads_with_its_placement(proj):
    c = M.load(proj).component("blk")
    assert c.level == "placed_routed" and c.placement["region"] == "SLICE_X26Y70:SLICE_X37Y91" and M.slice_rect(c.placement["region"]) == (26, 70, 37, 91)


@pytest.mark.parametrize("mutate,needle", [
    (lambda c: c.update(ownership="owned"), "is frozen"),
    (lambda c: c.pop("netlist"), "needs netlist"),
    (lambda c: c["netlist"].update(format="edif"), "needs netlist"),
    (lambda c: c["placement"].update(lock="placement"), "placement.lock must be 'routing'"),
    (lambda c: c["placement"].update(region="SLICE_X1Y1"), "slice range"),
    (lambda c: c["placement"].update(region="DSP48E2_X1Y1:DSP48E2_X1Y2"), "slice range"),
    (lambda c: c["placement"].update(sneaky=1), "unknown placement key"),
    (lambda c: c["placement"].update(timing_tolerance_ps=-1), "timing_tolerance_ps"),
    (lambda c: c["placement"].update(timing_tolerance_ps=True), "timing_tolerance_ps"),
    (lambda c: c.pop("instance"), "module and instance"),
])
def test_validator_refuses_a_bad_placed_routed_component(proj, mutate, needle):
    raw = _manifest(proj)
    mutate(raw["components"][1])
    assert needle in "\n".join(M.validate(raw))


def test_placement_belongs_to_a_placed_routed_component(proj):
    raw = _manifest(proj)
    raw["components"][0]["placement"] = {"lock": "routing", "region": "SLICE_X1Y1:SLICE_X2Y2"}
    assert "belongs to a placed_routed component" in "\n".join(M.validate(raw))


def test_build_yaml_must_still_build_the_checkpoint(proj):
    s = sess(proj)
    cfg = yaml.safe_load((proj / "build.yaml").read_text())
    cfg["netlists"] = []
    r = write(s, "build.yaml", yaml.safe_dump(cfg))
    assert r["refused"] and r["rule"] == "managed-build" and "ext/blk.dcp" in r["output"]
    assert write(s, "build.yaml", (proj / "build.yaml").read_text())["ok"]                 # the unchanged file is fine
    cfg2 = yaml.safe_load((proj / "build.yaml").read_text())
    cfg2["netlists"].append({"file": "designs/pr/ext/other.dcp", "format": "checkpoint", "cell": "u_x"})
    assert write(s, "build.yaml", yaml.safe_dump(cfg2))["rule"] == "managed-build"          # a checkpoint that is not a component


def test_the_block_files_are_frozen_for_writes_and_open_for_reads(proj):
    s = sess(proj)
    assert dispatch(s, "write_file", {"path": "ext/blk.dcp", "content": "x"})["refused"]
    assert dispatch(s, "write_file", {"path": "ext/blk_bb.sv", "content": "x"})["refused"]
    assert dispatch(s, "read_file", {"path": "ext/blk_bb.sv"})["ok"]


# --- the keep-out on constraints ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "create_pblock pb; resize_pblock pb -add SLICE_X30Y75:SLICE_X40Y80",             # overlaps the region
    "resize_pblock [get_pblocks pb] -add {SLICE_X37Y91:SLICE_X50Y100}",              # touches the corner
    "set_property LOC SLICE_X30Y80 [get_cells u_glue/q_reg]",                        # a LOC inside the region
    "set_property LOC SLICE_X26Y70 [get_cells foo]",
    "set_property LOC SLICE_X1Y1 [get_cells u_blk/sh_reg[3]]",                       # a placement property on the block's cells
    "add_cells_to_pblock pb [get_cells u_blk/*]",
    "set_property DONT_TOUCH true [get_cells u_blk]",
    "set_property IS_ROUTE_FIXED 0 [get_nets u_blk/din]",
    "set_property PBLOCK pb [get_cells {u_blk/u_core}]",
    "resize_pblock pb -add SLICE_X20Y60:SLICE_X30Y72 ;# a trailing comment",         # a statement, then a comment
    "resize_pblock pb -add \\\n  SLICE_X30Y75:SLICE_X31Y76",                         # a continued line
])
def test_xdc_that_places_inside_the_block_is_refused(proj, line):
    s = sess(proj)
    r = write(s, "design.xdc", line + "\n")
    assert r["refused"] and r["rule"] == "managed-keepout", (line, r)
    assert (proj / "design.xdc").read_text() == "# none\n"                                 # nothing was written


@pytest.mark.parametrize("line", [
    "set_property LOC SLICE_X40Y80 [get_cells u_glue/q_reg]",                         # outside the region
    "create_pblock pb; resize_pblock pb -add SLICE_X0Y0:SLICE_X25Y200",               # next to it, not over it
    "resize_pblock pb -add SLICE_X38Y70:SLICE_X50Y91",
    "resize_pblock pb -add SLICE_X26Y92:SLICE_X37Y120",                               # just above
    "set_false_path -from [get_cells u_blk/sh_reg[0]] -to [get_ports led[0]]",        # a timing exception on the block is not placement
    "set_max_delay 2.0 -from [get_pins u_blk/dout_reg/C]",
    "# set_property LOC SLICE_X30Y80 [get_cells u_blk/x]  (a comment)",
    "set_property LOC SLICE_X40Y80 [get_cells u_blk_other/x]",                         # a different instance name
])
def test_xdc_around_the_block_is_allowed(proj, line):
    s = sess(proj)
    assert write(s, "design.xdc", line + "\n")["ok"], line


def test_keepout_applies_to_every_xdc_not_only_the_named_one(proj):
    s = sess(proj)
    (proj / "extra").mkdir()
    r = write(s, "extra/more.xdc", "set_property LOC SLICE_X30Y80 [get_cells a]\n")
    assert r["refused"] and r["rule"] == "managed-keepout"


# --- the keep-out on the RapidWright tools ------------------------------------------------------------------------------------------

@pytest.fixture()
def rwsess(proj, monkeypatch):
    monkeypatch.setenv("FDA_RAPIDWRIGHT", "1")
    importlib.reload(rt)
    monkeypatch.setattr(pin, "available", lambda: (True, ""))
    s = sess(proj)
    b = proj / "build" / "base"
    b.mkdir(parents=True, exist_ok=True)
    (b / "post_route.dcp").write_bytes(b"x")
    yield s
    for n in [n for n in TOOLS if n.startswith("rw_")]:
        TOOLS.pop(n)
    monkeypatch.delenv("FDA_RAPIDWRIGHT")
    importlib.reload(rt)


# a pattern that names only a leaf (*/sh_reg*) cannot be judged here: flow/rw/place_chain.py sees the real cell names and refuses it
@pytest.mark.parametrize("pat", ["u_blk/*", "u_blk/sh_reg[*]", "*", "u_*/*", "u_blk", "u_blk/u_core/x"])
def test_place_chain_refuses_patterns_that_could_select_the_block(rwsess, pat):
    r = dispatch(rwsess, "rw_place_chain", {"checkpoint": "post_route.dcp", "output": "o.dcp", "cells": [pat], "anchor": "SLICE_X30Y80"})
    assert r["refused"] and r["rule"] == "managed-keepout" and not rwsess.runner.calls


def test_place_chain_names_the_protected_cells_and_region_to_the_script(rwsess):
    dispatch(rwsess, "rw_place_chain", {"checkpoint": "post_route.dcp", "output": "o.dcp", "cells": ["u_glue/*"], "anchor": "SLICE_X30Y80"})
    cfg = json.loads(Path(rwsess.runner.calls[0][1][5]).read_text())
    assert cfg["cells"] == ["u_glue/*"] and cfg["protect"] == {"cells": ["u_blk/*", "u_blk"], "regions": ["SLICE_X26Y70:SLICE_X37Y91"]}


def test_route_full_and_nets_inside_the_block_are_refused(rwsess):
    r = dispatch(rwsess, "rw_route", {"checkpoint": "post_route.dcp", "output": "r.dcp", "mode": "full"})
    assert r["refused"] and r["rule"] == "managed-keepout" and "mode full" in r["output"]
    r = dispatch(rwsess, "rw_route", {"checkpoint": "post_route.dcp", "output": "r.dcp", "mode": "nets", "nets": ["a", "u_blk/n[3]"]})
    assert r["refused"] and "inside" in r["output"]
    assert not rwsess.runner.calls
    dispatch(rwsess, "rw_route", {"checkpoint": "post_route.dcp", "output": "r.dcp", "mode": "nets", "nets": ["u_glue/n"]})
    assert rwsess.runner.calls                                                            # owned nets are fine
    r = dispatch(rwsess, "rw_route", {"checkpoint": "post_route.dcp", "output": "r.dcp", "mode": "nets", "nets": ["clk"]})
    assert r["refused"] and "pins inside" in r["output"]                                  # a boundary net may reach into the block


def test_relocating_a_checkpoint_that_may_hold_the_block_is_refused(rwsess):
    r = dispatch(rwsess, "rw_relocate_block", {"checkpoint": "post_route.dcp", "output": "m.dcp", "target_site": "SLICE_X40Y80"})
    assert r["refused"] and r["rule"] == "managed-keepout" and not rwsess.runner.calls


def test_relocate_takes_exactly_one_of_checkpoint_and_component(rwsess):
    r = dispatch(rwsess, "rw_relocate_block", {"output": "m.dcp", "target_site": "SLICE_X40Y80"})
    assert r["refused"] and "exactly one" in r["output"]
    r = dispatch(rwsess, "rw_relocate_block", {"checkpoint": "post_route.dcp", "component": "blk", "output": "m.dcp", "target_site": "SLICE_X40Y80"})
    assert r["refused"] and "exactly one" in r["output"]
    r = dispatch(rwsess, "rw_relocate_block", {"component": "glue", "output": "m.dcp", "target_site": "SLICE_X40Y80"})
    assert r["refused"] and "not a placed-and-routed component" in r["output"]
    r = dispatch(rwsess, "rw_relocate_block", {"component": "nonsense", "output": "m.dcp", "target_site": "SLICE_X40Y80"})
    assert r["refused"]


def test_relocating_the_component_moves_a_copy_and_leaves_the_frozen_file_alone(rwsess, proj):
    before = M.sha256_file(proj / "ext/blk.dcp")
    out = {"ok": True, "dx": 0, "dy": -60, "anchor_before": "SLICE_X29Y80", "anchor_after": "SLICE_X29Y20"}
    rwsess.runner.results["rw_relocate"] = type("R", (), {"returncode": 0, "stdout": json.dumps(out) + "\n", "stderr": "", "seconds": 1.0})()
    r = dispatch(rwsess, "rw_relocate_block", {"component": "blk", "output": "m.dcp", "target_site": "SLICE_X29Y20"})
    argv = rwsess.runner.calls[0][1]
    assert r["ok"] and argv[4].endswith("ext/blk.dcp") and argv[5].endswith("build/base/rw/m.dcp")
    assert r["moved_region"] == "SLICE_X26Y10:SLICE_X37Y31" and M.sha256_file(proj / "ext/blk.dcp") == before


def test_relocation_onto_another_blocks_region_is_refused_and_the_candidate_deleted(rwsess, proj, tmp_path):
    raw = yaml.safe_load((proj / "project.yaml").read_text())
    other = json.loads(json.dumps(raw["components"][1]))
    other.update(name="blk2", instance="u_blk2", paths=["ext2/**"], build_sources=[], netlist={"file": "ext2/b.dcp", "format": "checkpoint", "cell": "u_blk2"})
    other["placement"]["region"] = "SLICE_X26Y10:SLICE_X37Y31"
    raw["components"].append(other)
    (proj / "ext2").mkdir()
    (proj / "ext2/b.dcp").write_bytes(b"y")
    other["provenance"]["sha256"] = M.sha256_file(proj / "ext2/b.dcp")
    (proj / "project.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    s = sess(proj)
    out = {"ok": True, "anchor_before": "SLICE_X29Y80", "anchor_after": "SLICE_X29Y20"}
    s.runner.results["rw_relocate"] = type("R", (), {"returncode": 0, "stdout": json.dumps(out) + "\n", "stderr": "", "seconds": 1.0})()
    d = proj / "build" / "base" / "rw"
    d.mkdir(parents=True, exist_ok=True)
    (d / "m.dcp").write_bytes(b"candidate")
    r = dispatch(s, "rw_relocate_block", {"component": "blk", "output": "m.dcp", "target_site": "SLICE_X29Y20"})
    assert r["refused"] and r["rule"] == "managed-keepout" and "blk2" in r["output"] and not (d / "m.dcp").exists()


# --- the import check ----------------------------------------------------------------------------------------------------------------

def test_facts_parse_and_a_complete_lock_has_no_problems():
    f = MP.parse_facts(FACTS)
    assert f["ports"][2] == {"name": "dout", "dir": "output", "width": 1} and f["rect"] == (27, 72, 34, 90) and f["cells"]["leaf"] == 100
    assert MP.lock_problems(f) == []


@pytest.mark.parametrize("sub,needle", [
    (("CELLS|100|100|100|0", "CELLS|100|97|100|0"), "no fixed location"),
    (("CELLS|100|100|100|0", "CELLS|100|100|98|0"), "no fixed BEL"),
    (("CELLS|100|100|100|0", "CELLS|100|100|100|2"), "unplaced"),
    (("NETS|120|90|90|0", "NETS|120|90|90|3"), "unrouted"),
    (("NETS|120|90|90|0", "NETS|120|90|80|0"), "not fixed"),
])
def test_an_unlocked_or_incomplete_checkpoint_is_reported(sub, needle):
    assert needle in "\n".join(MP.lock_problems(MP.parse_facts(FACTS.replace(*sub))))


def test_the_footprint_must_be_inside_the_declared_region(proj):
    c = M.load(proj).component("blk")
    assert MP.footprint_problems(c, MP.parse_facts(FACTS)) == []
    assert "outside the declared keep-out region" in MP.footprint_problems(c, MP.parse_facts(FACTS.replace("RECT|27|72|34|90", "RECT|27|72|38|90")))[0]


def test_check_placed_passes_on_good_facts_and_fails_on_a_changed_file(proj, tmp_path):
    f = tmp_path / "facts.txt"
    f.write_text(FACTS)
    rep = MP.check_placed(proj, facts_file=f)
    assert rep["passed"] and rep["components"]["blk"]["interface"] == [] and rep["components"]["blk"]["sha256_matches"]
    (proj / "ext/blk.dcp").write_bytes(DCP + b"!")                                          # the file changed behind the manifest's hash
    assert not MP.check_placed(proj, facts_file=f)["passed"]
    (proj / "ext/blk.dcp").write_bytes(DCP)
    f.write_text(FACTS.replace("PORT|din|in|1\n", "PORT|din|in|2\n"))                       # a port with the wrong width
    r = MP.check_placed(proj, facts_file=f)
    assert not r["passed"] and r["components"]["blk"]["interface"]


# --- trust ----------------------------------------------------------------------------------------------------------------------------

def test_built_needs_placement_evidence_for_every_placement_tried(proj):
    p = M.load(proj)
    c = p.component("blk")
    assert M.trust(p, c)[0] == "documented"
    M.write_evidence(p, c, "verified", {"passed": True})
    M.write_evidence(p, c, "built", {"gates_clean": True})
    t, why = M.trust(p, c)
    assert t == "verified" and "placement evidence" in why[0]                                # gates alone are not enough for a placed block
    M.write_evidence(p, c, "placement", {"passed": True, "placements_tried": 1})
    assert M.trust(p, c)[0] == "verified" and "fewer than two" in M.trust(p, c)[1][0]
    M.write_evidence(p, c, "placement", {"passed": False, "placements_tried": 4})
    assert M.trust(p, c)[0] == "verified"
    M.write_evidence(p, c, "placement", {"passed": True, "placements_tried": 4})
    assert M.trust(p, c) == ("built", [])
    (proj / "ext/blk_bb.sv").write_text("(* black_box *) module blk(input logic clk, input logic x);endmodule\n")     # the content changed
    assert M.trust(M.load(proj), M.load(proj).component("blk"))[0] != "built"


# --- the placement comparison -------------------------------------------------------------------------------------------------------

def _run(d: Path, pre: str, delays: dict[str, float], sites: dict[str, str], routes: dict[str, str], after_routes: dict[str, str] | None = None,
         wns: float = 0.2, errors: int = 0, after_sites: dict[str, str] | None = None, directive: str = "Default") -> None:
    (d / f"{pre}_run.json").write_text(json.dumps({"vivado": "2026.1", "part": "xck26", "period_ns": 4.0, "directive": directive, "wns_ns": wns, "whs_ns": 0.05,
                                                   "routing_errors": errors, "block_cells": len(sites), "times_s": {}}))
    (d / f"{pre}_block.csv").write_text("endpoint,data_path_delay_ns,slack_ns,logic_levels\n" + "".join(f"{e},{v},1.0,2\n" for e, v in delays.items()))
    (d / f"{pre}_sites_before.txt").write_text("".join(f"{c}|{s}|A6LUT|1\n" for c, s in sites.items()))
    (d / f"{pre}_sites_after.txt").write_text("".join(f"{c}|{s}|A6LUT|1\n" for c, s in (after_sites or sites).items()))
    (d / f"{pre}_routes_before.txt").write_text("".join(f"{n}|1|{r}\n" for n, r in routes.items()))
    (d / f"{pre}_routes_after.txt").write_text("".join(f"{n}|1|{r}\n" for n, r in (after_routes or routes).items()))


BASE = dict(delays={"a": 1.0, "b": 2.0, "c": 3.5}, sites={"u/a": "SLICE_X30Y80", "u/b": "SLICE_X30Y81"},
            routes={"n1": "{ INT_X21Y76/A INT_X21Y74/B }", "n2": "{ INT_X21Y77/C }"})


def test_identical_internal_delays_after_a_relocation_pass(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", delays=BASE["delays"], sites={"u/a": "SLICE_X30Y20", "u/b": "SLICE_X30Y21"},
         routes={"n1": "{ INT_X21Y16/A INT_X21Y14/B }", "n2": "{ INT_X21Y17/C }"})
    ev = MP.compare_placements([{"tag": "p0", "dir": str(tmp_path), "prefix": "p0"},
                                {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "relocated to SLICE_X30Y20", "eqy": {"equivalent": True, "seconds": 2}}], 0)
    assert ev["passed"] and ev["placements_tried"] == 2 and ev["placements"]["p1"]["max_abs_diff_ps"] == 0 and ev["placements"]["p1"]["route_shape_equal"]
    assert ev["placements"]["p1"]["region"] == (30, 20, 30, 21)


def test_a_difference_above_the_tolerance_fails_and_is_reported_in_ps(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", delays={"a": 1.0, "b": 2.012, "c": 3.5}, sites={"u/a": "SLICE_X30Y20"}, routes=BASE["routes"])
    runs = [{"tag": "p0", "dir": str(tmp_path), "prefix": "p0"}, {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "relocated to X"}]
    ev = MP.compare_placements(runs, 10)
    assert not ev["passed"] and ev["placements"]["p1"]["max_abs_diff_ps"] == 12 and "differs by 12 ps" in ev["problems"][0]
    assert MP.compare_placements(runs, 12)["passed"]                                          # the tolerance is the owner's number, applied as written


def test_vivado_changing_the_block_is_caught(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", delays=BASE["delays"], sites=BASE["sites"], routes=BASE["routes"], after_routes={"n1": "{ INT_X21Y76/Z }", "n2": BASE["routes"]["n2"]},
         after_sites={"u/a": "SLICE_X31Y80", "u/b": "SLICE_X30Y81"})
    ev = MP.compare_placements([{"tag": "p0", "dir": str(tmp_path), "prefix": "p0"},
                                {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "re-placed"}], 0)
    assert not ev["passed"]
    assert any("moved a cell" in p for p in ev["problems"]) and any("changed the routing" in p for p in ev["problems"])
    assert ev["placements"]["p1"]["moved_cells"] == ["u/a"] and ev["placements"]["p1"]["changed_nets"] == ["n1"]


def test_routing_errors_missing_endpoints_and_failed_eqy_each_fail(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", delays={"a": 1.0, "b": 2.0, "zz": 1.0}, sites=BASE["sites"], routes=BASE["routes"], errors=2)
    ev = MP.compare_placements([{"tag": "p0", "dir": str(tmp_path), "prefix": "p0"}, {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "relocated to X",
                                                                                       "eqy": {"equivalent": False}}], 0)
    text = "\n".join(ev["problems"])
    assert "routing errors" in text and "set of internal endpoints differs" in text and "eqy did not prove" in text and not ev["passed"]


def test_an_eqy_that_could_not_finish_is_not_a_pass(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", **BASE)
    ev = MP.compare_placements([{"tag": "p0", "dir": str(tmp_path), "prefix": "p0"},
                                {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "relocated", "eqy": {"equivalent": None, "why": "timeout"}}], 0)
    assert not ev["passed"]


def test_one_placement_is_not_evidence(tmp_path):
    _run(tmp_path, "p0", **BASE)
    assert not MP.compare_placements([{"tag": "p0", "dir": str(tmp_path), "prefix": "p0"}], 0)["passed"]


def test_boundary_budgets_are_checked_per_placement(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", **BASE)
    runs = [{"tag": "p0", "dir": str(tmp_path), "prefix": "p0", "budgets": "BUDGET|out_b|1.5|2.0\n"},
            {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "x", "budgets": "BUDGET|out_b|2.4|1.6\n"}]
    ev = MP.compare_placements(runs, 0, [{"name": "out_b", "dir": "out", "max_ns": 2.0}])
    assert not ev["passed"] and "out_b" in ev["problems"][0] and ev["placements"]["p0"]["budget_problems"] == []


def test_the_written_checkpoint_is_checked_for_the_block_and_for_intruders(tmp_path):
    _run(tmp_path, "p0", **BASE)
    good = ("BLOCK|u/a|SLICE_X30Y80|A6LUT|1\nBLOCK|u/b|SLICE_X30Y81|A6LUT|1\nROUTE|n1|1|{ INT_X21Y76/A INT_X21Y74/B }\nROUTE|n2|1|{ INT_X21Y77/C }\n"
            "OTHER|g/q_reg|SLICE_X40Y80\nOTHER|g/r_reg|SLICE_X25Y80\n")
    run = {"tag": "p0", "dir": str(tmp_path), "prefix": "p0", "dump": good}
    ev = MP.compare_placements([run], 0, None, "SLICE_X26Y70:SLICE_X37Y91")
    w = ev["placements"]["p0"]["written_checkpoint"]
    assert w["cells_unchanged"] and w["routes_unchanged"] and w["other_cells_inside_region_count"] == 0 and w["block_nets"] == 2
    bad = good.replace("SLICE_X40Y80", "SLICE_X30Y85").replace("ROUTE|n2|1|{ INT_X21Y77/C }", "ROUTE|n2|0|{ INT_X21Y77/C }").replace("u/b|SLICE_X30Y81", "u/b|SLICE_X30Y82")
    ev = MP.compare_placements([{**run, "dump": bad}], 0, None, "SLICE_X26Y70:SLICE_X37Y91")
    w = ev["placements"]["p0"]["written_checkpoint"]
    assert not w["cells_unchanged"] and not w["routes_unchanged"] and w["other_cells_inside_region"] == ["g/q_reg@SLICE_X30Y85"]
    text = "\n".join(ev["problems"])
    assert "differs from the block as delivered" in text and "inside the keep-out region" in text


def test_a_relocated_runs_keepout_moves_with_the_block(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", delays=BASE["delays"], sites={"u/a": "SLICE_X30Y20", "u/b": "SLICE_X30Y21"}, routes=BASE["routes"])
    d1 = "BLOCK|u/a|SLICE_X30Y20|A6LUT|1\nBLOCK|u/b|SLICE_X30Y21|A6LUT|1\nROUTE|n1|1|{ INT_X21Y76/A INT_X21Y74/B }\nROUTE|n2|1|{ INT_X21Y77/C }\nOTHER|g|SLICE_X30Y80\n"
    runs = [{"tag": "p0", "dir": str(tmp_path), "prefix": "p0"}, {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "relocated", "dump": d1}]
    ev = MP.compare_placements(runs, 0, None, "SLICE_X26Y70:SLICE_X37Y91")
    # the keep-out of p1 is the declared region moved down by 60 rows: Y10..Y31; a glue cell at Y80 (the old place) is fine, one at Y25 would not be
    assert ev["placements"]["p1"]["written_checkpoint"]["other_cells_inside_region_count"] == 0
    runs[1]["dump"] = d1.replace("SLICE_X30Y80", "SLICE_X30Y25")
    assert MP.compare_placements(runs, 0, None, "SLICE_X26Y70:SLICE_X37Y91")["placements"]["p1"]["written_checkpoint"]["other_cells_inside_region_count"] == 1


def test_shape_removes_coordinates_only():
    assert MP.shape("INT_X21Y76/SS2_E_BEG6 CLEL_R_X21Y76/HQ") == "INT_X#Y#/SS2_E_BEG6 CLEL_R_X#Y#/HQ"


def test_slice_rect_and_overlap():
    assert M.slice_rect("SLICE_X5Y9:SLICE_X1Y2") == (1, 2, 5, 9)
    assert M.rects_overlap((0, 0, 5, 5), (5, 5, 9, 9)) and not M.rects_overlap((0, 0, 5, 5), (6, 0, 9, 9))
    with pytest.raises(ValueError):
        M.slice_rect("SLICE_X5Y9")


# --- budgets on a placed-routed component's boundary ------------------------------------------------------------------------------------

def test_budget_tcl_for_a_session_with_the_design_open(proj, tmp_path):
    out = tmp_path / "b.tcl"
    assert MI.main(["budget-tcl", str(proj), "-", str(out)]) == 0
    t = out.read_text()
    assert "open_checkpoint" not in t and "NAME =~ u_blk/*" in t and "fda_budget {out_b}" in t


# --- the scope in the run record and on resume ---------------------------------------------------------------------------------------------

def test_resume_refuses_an_ambiguous_or_frozen_request_and_reports_a_scope(proj, monkeypatch, capsys):
    from agent import __main__ as cli
    from agent.graph import pickup

    class A:
        change, scope = "make the block faster", None

    monkeypatch.setattr(pickup, "load", lambda ddir: {"fresh": {"design": "pr", "errors": [], "stale": [], "changed_files": [], "kb_pin": None, "vivado": None},
                                                      "agent_tokens": 0, "files_tokens": 0, "handover": {}})
    monkeypatch.setattr(pickup, "entry_stage", lambda *a, **k: {"stage": 3, "kind": "rtl", "notes": [], "reasons": []})
    a = A()
    a.run_id, a.kind, a.from_stage, a.dry_run = str(proj), None, None, True
    assert cli.pickup_cmd(a) == 2                                    # 'block' is the frozen component: a question, no scope
    out = json.loads(capsys.readouterr().out)
    assert "frozen" in out["question"] and "owned" in out["question"]
    a.change, a.scope = "speed up the driver", "glue"
    assert cli.pickup_cmd(a) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"]["components"] == ["glue"] and out["scope"]["source"] == "explicit"
    a.scope = "blk"
    assert cli.pickup_cmd(a) == 2                                    # an explicit scope naming a frozen part is refused too


def test_summary_json_carries_the_scope(proj):
    """__main__._drive adds the request's scope (build/managed/scope.json of the run's design) to summary.json through with_scope."""
    from agent import __main__ as cli
    assert "scope" not in cli.with_scope({"stop": "done"}, proj)                              # an ordinary run: summary unchanged
    M.start_run(M.load(proj), M.Scope(("glue",), "explicit", "faster", "explicit --scope"))
    s = cli.with_scope({"stop": "done"}, proj)
    assert s["stop"] == "done" and s["scope"]["components"] == ["glue"] and s["scope"]["request"] == "faster" and s["scope"]["plan"]["read_only"] == ["blk"]


@pytest.mark.parametrize("path,line", [
    ("cons.txt", "set_property LOC SLICE_X30Y80 [get_cells u_glue/x]"),        # a constraints file under another name, once listed in build.yaml
    ("design.XDC", "set_property LOC SLICE_X30Y80 [get_cells u_glue/x]"),
    ("design.xdc", "set b [get_cells u_blk/*]"),                                # a variable holding the block's objects
    ("design.xdc", "set_property IS_LOC_FIXED false [get_cells -hier u_b*/*]"),  # a wildcard that reaches the instance
    ("design.xdc", "set_property IS_LOC_FIXED false [get_cells -nocase U_BLK/x]"),
    ("design.xdc", "set_property ROUTE {} [get_nets u_blk/n1]"),
    ("design.xdc", "set_property loc slice_x30y80 [get_cells u_glue/q]"),
])
def test_review_bypasses_of_the_keepout_are_refused(proj, path, line):
    s = sess(proj)
    if path == "cons.txt":
        cfg = yaml.safe_load((proj / "build.yaml").read_text())
        cfg["constraints"].append("designs/pr/cons.txt")
        (proj / "build.yaml").write_text(yaml.safe_dump(cfg))
        s = sess(proj)
    (proj / path).parent.mkdir(exist_ok=True)
    r = write(s, path, line + "\n")
    assert r["refused"] and r["rule"] == "managed-keepout", (path, line, r)


def test_build_yaml_must_keep_top_format_and_cell_and_listed_constraints_are_checked(proj):
    s = sess(proj)
    cfg = yaml.safe_load((proj / "build.yaml").read_text())
    for edit in (lambda c: c.update(top="glue"), lambda c: c["netlists"][0].update(cell="u_other"), lambda c: c["netlists"][0].update(format="edif")):
        c2 = json.loads(json.dumps(cfg))
        edit(c2)
        assert write(s, "build.yaml", yaml.safe_dump(c2))["rule"] == "managed-build"
    (proj / "bad.xdc").write_text("resize_pblock pb -add SLICE_X30Y75:SLICE_X40Y80\n")      # already on disk: listing it is refused too
    c3 = json.loads(json.dumps(cfg))
    c3["constraints"].append("designs/pr/bad.xdc")
    assert write(s, "build.yaml", yaml.safe_dump(c3))["rule"] == "managed-keepout"


def test_a_changed_manifest_is_new_content_for_the_evidence(proj):
    p = M.load(proj)
    c = p.component("blk")
    M.write_evidence(p, c, "verified", {"passed": True})
    M.write_evidence(p, c, "placement", {"passed": True, "placements_tried": 3})
    M.write_evidence(p, c, "built", {"gates_clean": True})
    assert M.trust(p, c)[0] == "built"
    raw = yaml.safe_load((proj / "project.yaml").read_text())
    raw["components"][1]["placement"]["timing_tolerance_ps"] = 5000
    (proj / "project.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    p2 = M.load(proj)
    assert M.trust(p2, p2.component("blk"))[0] == "documented"


def test_strict_evidence_cannot_pass_vacuously(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", **BASE)                                                       # same region: not a placement at all
    a = {"tag": "p0", "dir": str(tmp_path), "prefix": "p0"}
    b = {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "", "eqy": {"equivalent": True}, "dump": "BLOCK|u/a|SLICE_X30Y80|A6LUT|1\n"}
    text = "\n".join(MP.compare_placements([a, b], 0, [{"name": "x", "dir": "out", "max_ns": 1}], "SLICE_X26Y70:SLICE_X37Y91", strict=True)["problems"])
    assert "nothing was relocated" in text and "budget" in text
    ev = MP.compare_placements([a, {**b, "eqy": {"equivalent": "no"}}], 0)
    assert not ev["passed"] and "eqy" in "\n".join(ev["problems"])
    ev = MP.compare_placements([a, {k: v for k, v in b.items() if k != "eqy"}], 0, strict=True)
    assert "nothing was relocated" in "\n".join(ev["problems"])


def test_a_relocated_blocks_netlist_fingerprint_must_equal_the_delivered_one(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", delays=BASE["delays"], sites={"u/a": "SLICE_X30Y20", "u/b": "SLICE_X30Y21"},
         routes={"n1": "{ INT_X21Y16/A INT_X21Y14/B }", "n2": "{ INT_X21Y17/C }"})
    nl = "NL|u/a|LUT6|INIT=64'h1|I0=n1,O=n2\nNL|u/b|FDRE||C=clk,D=n2\n"
    d0 = "BLOCK|u/a|SLICE_X30Y80|A6LUT|1\nBLOCK|u/b|SLICE_X30Y81|A6LUT|1\nROUTE|n1|1|{ INT_X21Y76/A INT_X21Y74/B }\nROUTE|n2|1|{ INT_X21Y77/C }\n" + nl
    d1 = "BLOCK|u/a|SLICE_X30Y20|A6LUT|1\nBLOCK|u/b|SLICE_X30Y21|A6LUT|1\nROUTE|n1|1|{ INT_X21Y16/A INT_X21Y14/B }\nROUTE|n2|1|{ INT_X21Y17/C }\n"
    runs = lambda n1: [{"tag": "p0", "dir": str(tmp_path), "prefix": "p0", "dump": d0},
                       {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "relocated", "dump": d1 + n1}]
    ok = MP.compare_placements(runs(nl), 0)
    assert ok["placements"]["p1"]["netlist_identical_to_delivered"] is True and not any("netlist" in p for p in ok["problems"])
    bad = MP.compare_placements(runs(nl.replace("64'h1", "64'h3")), 0)
    assert bad["placements"]["p1"]["netlist_identical_to_delivered"] is False and not bad["passed"]
    assert "logical netlist" in "\n".join(bad["problems"])
    none = MP.compare_placements(runs(""), 0, strict=True)                                   # no fingerprint at all: relocation is unproven
    assert "nothing shows" in "\n".join(none["problems"])


def test_interconnect_delays_are_the_gate_and_path_delays_only_information(tmp_path):
    _run(tmp_path, "p0", **BASE)
    _run(tmp_path, "p1", delays={"a": 1.0, "b": 2.042, "c": 3.5}, sites={"u/a": "SLICE_X30Y20", "u/b": "SLICE_X30Y21"},
         routes={"n1": "{ INT_X21Y16/A INT_X21Y14/B }", "n2": "{ INT_X21Y17/C }"})            # a worst-slack path that moved with the clock tree
    head = "BLOCK|u/a|SLICE_X30Y%s|A6LUT|1\nBLOCK|u/b|SLICE_X30Y%s|A6LUT|1\nROUTE|n1|1|{ INT_X21Y%s/A }\nROUTE|n2|1|{ INT_X21Y%s/C }\n"
    d0 = head % (80, 81, 76, 77) + "NETD|n1_to_u/b/D|600|300|0\nNETD|n2_to_u/a/D|900|450|0\n"
    runs = lambda n: [{"tag": "p0", "dir": str(tmp_path), "prefix": "p0", "dump": d0},
                      {"tag": "p1", "dir": str(tmp_path), "prefix": "p1", "note": "relocated", "dump": head % (20, 21, 16, 17) + n}]
    ok = MP.compare_placements(runs("NETD|n1_to_u/b/D|600|300|0\nNETD|n2_to_u/a/D|900|450|0\n"), 0)
    assert ok["placements"]["p1"]["net_delays"]["identical_pins"] == 2 and ok["placements"]["p1"]["max_abs_diff_ps"] == 42
    assert not any("delay" in p for p in ok["problems"])                                     # the 42 ps path difference is not the gate
    bad = MP.compare_placements(runs("NETD|n1_to_u/b/D|603|300|0\nNETD|n2_to_u/a/D|900|450|0\n"), 2)
    assert not bad["passed"] and "interconnect delay inside the block differs by 3 ps" in "\n".join(bad["problems"])
    assert not any("interconnect" in p for p in MP.compare_placements(runs("NETD|n1_to_u/b/D|603|300|0\nNETD|n2_to_u/a/D|900|450|0\n"), 3)["problems"])
