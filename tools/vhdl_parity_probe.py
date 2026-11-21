#!/usr/bin/env python3
"""Brief 153 (review item F9): which readers of a design's RTL silently skip a VHDL design? (the "before" and "after" picture)

    python3 tools/vhdl_parity_probe.py run [--out results/153_vhdl_parity/<name>.json]
    python3 tools/vhdl_parity_probe.py checks [--out FILE]      # every registered check on the five brief 55 translations

``run`` stages one design in two languages (the benchmark task ``t1_gray_stepper``: its SystemVerilog reference and the brief 55
VHDL translation, arm B, ``results/55_vhdl/translations/B``), plants the defect each reader is meant to find (a wrong design ID,
an xpm_cdc instance without SIM_ASSERT_CHK, an asynchronous reset, a latch, a clock-domain crossing, a constant-zero build
stamp, an edited source file) and asks every reader of the RTL, in both languages, whether it saw it. Each answer is one of

- ``caught``: the reader found the planted defect (or, for a reader that only lists files, saw the files);
- ``no_reader``: the reader said, in its own result, that it did not read the VHDL (a fail-closed status);
- ``silent``: the reader returned a pass, an empty list or no finding and said nothing: **this is what F9 removes**;
- ``wrong``: the reader ran on the VHDL as if it were SystemVerilog and returned an error that names the wrong problem.

The labelled set is READERS below (reader id, where it lives, the planted defect and what "caught" means). It is written before the
first measurement (``results/153_vhdl_parity/prereg.md``); a reader is added to it only with a dated line in that file.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TASK = "t1_gray_stepper"
WORK = ROOT / "runs" / "parity"
VHDL_RTL = ROOT / "results" / "55_vhdl" / "translations" / "B" / TASK / "rtl"
SV_RTL = ROOT / "benchmark" / "tasks" / TASK / "ref" / "rtl"
SPEC = ROOT / "benchmark" / "tasks" / TASK / "spec.md"
TOP_FILE = {"sv": "t1_gray_stepper_top.sv", "vhdl": "t1_gray_stepper_top.vhd"}


# ---------------------------------------------------------------------------------------------------------------- staging
def stage(lang: str, plant: str | None = None) -> Path:
    """A design directory under build/parity: the task's spec, the build.yaml and XDC a board design has, the RTL in ``lang``,
    with the planted defect ``plant`` (None: the clean design)."""
    from benchmark.tools import ref_build
    base = ref_build.stage(ROOT / "benchmark" / "tasks" / TASK)           # build/bench/<task>: build.yaml, XDC, architecture.yaml
    name = f"{TASK}__{lang}__{plant or 'clean'}"
    d = WORK / name
    shutil.rmtree(d, ignore_errors=True)
    (d / "rtl").mkdir(parents=True)
    for f in sorted((SV_RTL if lang == "sv" else VHDL_RTL).iterdir()):
        shutil.copy2(f, d / "rtl" / f.name)
    shutil.copy2(base / "design.xdc", d / "design.xdc")
    shutil.copy2(SPEC, d / "spec.md")
    arch = yaml.safe_load((base / "architecture.yaml").read_text())
    if lang == "vhdl":
        ents = sorted({e for f in (d / "rtl").iterdir() for e in re.findall(r"^\s*entity\s+(\w+)\s+is", f.read_text(), re.M | re.I)})
        arch["blocks"] = [{"name": e, "function": "VHDL translation of the reference"} for e in ents] + \
            [b for b in arch["blocks"] if b["name"] == "fpga_shell"]
        for c in arch.get("crossings") or []:              # the translation has its own synchroniser entity, sync2_vh (results/55_vhdl)
            if c.get("primitive") == "sync2":
                c["primitive"] = "sync2_vh"
    (d / "architecture.yaml").write_text(yaml.safe_dump(arch, sort_keys=False))
    rel = d.relative_to(ROOT).as_posix()
    cfg = yaml.safe_load((base / "build.yaml").read_text())
    ext = "sv" if lang == "sv" else "vhd"
    cfg["sources"] = ["shell/rtl/*.sv", f"{rel}/rtl/*.{ext}"]
    cfg["constraints"] = [f"{rel}/design.xdc"]
    (d / "build.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    if lang == "vhdl":
        from flow import vhdl
        (d / vhdl.HDL_MARKER).write_text("vhdl\n")
    if plant:
        PLANTS[plant](d, lang)
    return d


def _edit(d: Path, lang: str, fn: Callable[[str], str]) -> None:
    f = d / "rtl" / TOP_FILE[lang]
    t = f.read_text()
    t2 = fn(t)
    assert t2 != t, f"plant did not change {f.name}"
    f.write_text(t2)


def _sv_add(t: str, decl: str, stmt: str = "", dbg: str = "") -> str:
    """Add declarations and statements to the top; ``dbg`` (a signal) drives a new output DBG so that synthesis keeps the logic."""
    if dbg:
        t = t.replace("output logic        UART_RXD_OUT", "output logic        UART_RXD_OUT,\n    output logic        DBG", 1)
        stmt += f"\n    assign DBG = {dbg};"
    return t.replace("endmodule", decl + "\n" + stmt + "\nendmodule", 1)


def _vhdl_add(t: str, decl: str, stmt: str = "", dbg: str = "") -> str:
    if dbg:
        t = re.sub(r"(UART_RXD_OUT\s*:\s*out\s+std_logic)", r"\1;\n        DBG         : out std_logic", t, count=1)
        stmt += f"\n    DBG <= {dbg};"
    t = re.sub(r"(\n\s*signal win_rdata[^\n]*\n)", lambda m: m.group(1) + decl + "\n", t, count=1)
    return re.sub(r"\n(\s*end architecture)", lambda m: "\n" + stmt + "\n" + m.group(1), t, count=1)


def plant_id(d: Path, lang: str) -> None:
    """The design ID bound in the shell instance is not the spec's quoted "GRAY" (0x47524159): one character differs."""
    _edit(d, lang, (lambda t: t.replace("32'h4752_4159", "32'h4752_4158")) if lang == "sv"
          else (lambda t: t.replace('x"47524159"', 'x"47524158"')))


def plant_xpm(d: Path, lang: str) -> None:
    """An xpm_cdc_single instance with no SIM_ASSERT_CHK."""
    if lang == "sv":
        _edit(d, lang, lambda t: _sv_add(t, "    logic xq;",
                                         "    xpm_cdc_single u_xpm (.src_clk(1'b0), .src_in(BTNU), .dest_clk(CLK100MHZ), .dest_out(xq));", "xq"))
    else:
        _edit(d, lang, lambda t: _vhdl_add(
            t, "    signal xq : std_logic;",
            "    u_xpm : xpm_cdc_single port map (src_clk => '0', src_in => BTNU, dest_clk => CLK100MHZ, dest_out => xq);", "xq"))


def plant_async_reset(d: Path, lang: str) -> None:
    """A register with the reset in its sensitivity list (asynchronous), outside a declared synchroniser."""
    if lang == "sv":
        _edit(d, lang, lambda t: _sv_add(t, "    logic aq;", "    always_ff @(posedge CLK100MHZ or negedge CPU_RESETN) if (!CPU_RESETN) aq <= 1'b0; else aq <= ~aq;", "aq"))
    else:
        _edit(d, lang, lambda t: _vhdl_add(
            t, "    signal aq : std_logic := '0';",
            "    p_async : process (CLK100MHZ, CPU_RESETN) begin\n"
            "        if CPU_RESETN = '0' then aq <= '0'; elsif rising_edge(CLK100MHZ) then aq <= not aq; end if;\n"
            "    end process;", "aq"))


def plant_latch(d: Path, lang: str) -> None:
    """A latch (a signal assigned on one branch of a combinational block)."""
    if lang == "sv":
        _edit(d, lang, lambda t: _sv_add(t, "    logic lq;", "    always_comb if (BTNU) lq = SW[0];", "lq"))
    else:
        _edit(d, lang, lambda t: _vhdl_add(
            t, "    signal lq : std_logic;",
            "    p_latch : process (BTNU, SW) begin\n        if BTNU = '1' then lq <= SW(0); end if;\n    end process;", "lq"))


def plant_crossing(d: Path, lang: str) -> None:
    """An ASYNC_REG register: a clock-domain crossing the CDC injection run must exercise."""
    if lang == "sv":
        _edit(d, lang, lambda t: _sv_add(t, '    (* ASYNC_REG = "TRUE" *) logic [1:0] sy;',
                                         "    always_ff @(posedge CLK100MHZ) sy <= {sy[0], BTNU};", "sy[1]"))
    else:
        _edit(d, lang, lambda t: _vhdl_add(
            t, '    signal sy : std_logic_vector(1 downto 0);\n    attribute ASYNC_REG : string;\n    attribute ASYNC_REG of sy : signal is "TRUE";',
            "    p_sy : process (CLK100MHZ) begin\n        if rising_edge(CLK100MHZ) then sy <= sy(0) & BTNU; end if;\n    end process;", "sy(1)"))


def plant_stamp(d: Path, lang: str) -> None:
    """The shell's BUILD_STAMP is bound to a constant 0 (the bring-up's still_alive check needs the build's stamp)."""
    _edit(d, lang, (lambda t: t.replace(".BUILD_STAMP(BUILD_STAMP)", ".BUILD_STAMP(32'h0)")) if lang == "sv"
          else (lambda t: re.sub(r"BUILD_STAMP\s*=>\s*BUILD_STAMP", 'BUILD_STAMP => x"00000000"', t)))


def plant_edit(d: Path, lang: str) -> None:
    """A one-token change to the RTL (an edit after a verification result was recorded)."""
    _edit(d, lang, (lambda t: t + "\n// edited after the evidence\n") if lang == "sv" else (lambda t: t + "\n-- edited after the evidence\n"))


PLANTS: dict[str, Callable[[Path, str], None]] = {
    "wrong_id": plant_id, "xpm_no_sim_assert": plant_xpm, "async_reset": plant_async_reset, "latch": plant_latch,
    "crossing": plant_crossing, "stamp_zero": plant_stamp, "edit": plant_edit,
}


# ---------------------------------------------------------------------------------------------------------------- outcomes
def _outcome(kind: str, detail: str = "") -> dict[str, str]:
    return {"outcome": kind, "detail": detail[:300]}


def _check_result(name: str, d: Path, want_code: str | None = None, lang: str = "sv") -> dict[str, str]:
    """Run one registered check (scope rtl, no Vivado) and classify its result against the planted defect."""
    from flow import checks as C
    r = C.run_one(name, d, "rtl")
    return _classify_check(r, want_code)


def _classify_check(r: dict[str, Any], want_code: str | None) -> dict[str, str]:
    st = r.get("status")
    inc = [f"{k}: {v}" for k, v in (r.get("parts") or {}).items() if v != "ran"]
    codes = [f.get("code") for f in r.get("findings") or []]
    text = (r.get("why") or "") + " " + " ".join(inc)
    if want_code and want_code in codes:
        return _outcome("caught", f"{want_code} raised")
    reads_vhdl_said = re.search(r"no reader|not read|cannot read|does not read|VHDL", text, re.I)
    if st == "not_run":
        return _outcome("no_reader" if reads_vhdl_said else "silent", f"not_run: {r.get('why', '')}")
    if st == "fail" and not want_code:
        return _outcome("caught", f"fail: {codes[:3]}")
    if st == "fail":
        return _outcome("wrong", f"fail with other findings: {codes[:3]}")
    if reads_vhdl_said:
        return _outcome("no_reader", text.strip())
    return _outcome("silent", f"status {st}, no finding, nothing said about the language")


# ---------------------------------------------------------------------------------------------------------------- readers
def r_lint(d: Path, lang: str) -> dict[str, str]:
    """flow.checks 'lint' (the CLI route: Verilator, or the language's own lint)."""
    from flow import checks as C
    r = C.run_one("lint", d, "rtl")
    if r.get("status") == "fail":
        codes = [f.get("code") for f in r["findings"]]
        msg = " ".join(f.get("message", "") for f in r["findings"])
        if re.search(r"syntax error|unexpected|expecting", msg) and lang == "vhdl":
            return _outcome("wrong", f"Verilator read the VHDL as Verilog: {msg[:120]}")
        return _outcome("caught", f"fail: {codes[:3]}")
    return _classify_check(r, None)


def r_standards(d: Path, lang: str) -> dict[str, str]:
    from flow import checks as C
    r = C.run_one("standards", d, "rtl")
    codes = [f.get("code") for f in r.get("findings") or []]
    return _outcome("caught", f"{codes[:2]}") if "STD-RST-01" in codes else _classify_check(r, "STD-RST-01")


def r_resets(d: Path, lang: str) -> dict[str, str]:
    from flow import checks as C
    r = C.run_one("resets", d, "rtl")
    codes = [f.get("code") for f in r.get("findings") or []]
    return _outcome("caught", f"{codes[:2]}") if "RST-ASYNC-01" in codes else _classify_check(r, "RST-ASYNC-01")


def r_xpm(d: Path, lang: str) -> dict[str, str]:
    return _check_result("xpm_sim", d, "XPM-SIM-01", lang)


def r_constants(d: Path, lang: str) -> dict[str, str]:
    return _check_result("constants", d, "CONST-ID-01", lang)


def r_axi(d: Path, lang: str) -> dict[str, str]:
    """Control: AMD IP named in the design's text (Tcl, VLNV) is found whatever the RTL language."""
    from flow import amd_ip_notes as N
    (d / "ip.tcl").write_text("create_ip -name axi_gpio -vendor xilinx.com -library ip -version 2.0 -module_name g0\n")
    rep = N.scan([d])
    return _outcome("caught", str(sorted(rep["ips"]))) if rep["ips"] else _outcome("silent", "no AMD IP found")


def r_axi_profile(d: Path, lang: str) -> dict[str, str]:
    """A design that declares AXI4-Lite interfaces: its register blocks are read only when the generator wrote them (SystemVerilog)."""
    spec = d / "spec.yaml"
    spec.write_text(yaml.safe_dump({"interfaces": {"axi_lite_profile": "house", "blocks": {}}}))
    from flow import checks as C
    r = C.run_one("axi_profile", d, "rtl")
    st = r.get("status")
    inc = r.get("incomplete") or []
    if lang == "sv":
        return _outcome("control", f"status {st}: the check reads generated SystemVerilog blocks (the generator emits no VHDL); none here")
    if inc or st == "not_run":
        return _classify_check(r, None)
    return _outcome("silent", f"status {st}: the design declares interfaces: and has VHDL register logic that is not read; nothing said")


def r_fsm(d: Path, lang: str) -> dict[str, str]:
    """fsm_coverage: the state table is read from the RTL file named in verif/fsm.yaml."""
    from flow import fsm_coverage as F
    rtl = d / "rtl" / ("fsm.sv" if lang == "sv" else "fsm.vhd")
    if lang == "sv":
        rtl.write_text("module fsm; typedef enum logic [1:0] {S_A, S_B} st_t; endmodule\n")
    else:
        rtl.write_text("entity fsm is end entity;\narchitecture r of fsm is type st_t is (S_A, S_B); begin end architecture;\n")
    (d / "verif").mkdir(exist_ok=True)
    (d / "verif" / "fsm.yaml").write_text(yaml.safe_dump({"fsms": [{"name": "m", "signal": "*.st", "file": f"rtl/{rtl.name}", "enum": "st_t"}]}))
    vcd = d / "t.vcd"
    vcd.write_text("$timescale 1ns $end\n$scope module tb $end\n$var reg 2 ! st [1:0] $end\n$upscope $end\n$enddefinitions $end\n#0\nb00 !\n#10\nb01 !\n")
    try:
        rep = F.evaluate(d, [vcd])
    except (OSError, ValueError, KeyError) as e:
        msg = f"{type(e).__name__}: {e}"
        return _outcome("no_reader" if re.search(r"no reader|VHDL", msg, re.I) else "wrong", f"raised {msg[:160]}")
    return _outcome("caught", f"states read: {sorted(rep.get('fsms', [{}])[0].get('states', []) or [])}")


def r_cdc_inject_detect(d: Path, lang: str) -> dict[str, str]:
    """flow.cdc_inject.design_crosses: does the design have a crossing the injection run must exercise?"""
    from flow import cdc_inject
    return _outcome("caught", "crossing found") if cdc_inject.design_crosses(d) else _outcome("silent", "design_crosses is False: no crossing, so no CDC check")


def r_cdc_inject_run(d: Path, lang: str) -> dict[str, str]:
    """flow.cdc_inject_run.evaluate on a design with a crossing: for VHDL there is no injector (it rewrites SystemVerilog registers),
    so the run must say so; a True ``pass`` with no run is a silent pass."""
    from flow import cdc_inject_run as R
    tests = d / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_x_rtl.py").write_text("def test_x():\n    assert True\n")
    rep = R.evaluate(d, seeds=1, timeout_s=120)
    if lang == "sv":
        return _outcome("caught", f"applicable={rep.get('applicable')} pass={rep.get('pass')} (a trivial test: injection ran)")
    if rep.get("applicable") is False and rep.get("pass"):
        return _outcome("silent", f"applicable False, pass True: {rep.get('why', '')}")
    if rep.get("pass") is False or re.search(r"no injector|VHDL|no reader", str(rep.get("why", "")), re.I):
        return _outcome("no_reader", f"pass={rep.get('pass')}: {rep.get('why', '')}")
    return _outcome("silent", f"pass={rep.get('pass')} with no injection into VHDL: {rep.get('why', '')}")


def r_spectest(d: Path, lang: str) -> dict[str, str]:
    """agent.graph.spectest: the RTL list the harness-written entry file hands the simulator."""
    from agent.graph import spectest as S
    t = S.ENTRY_TEMPLATE
    m = re.search(r"own = (.+)\n", t)
    if m and "own_sources" in m.group(1):
        from flow import vhdl
        files = vhdl.own_sources(d, {})
        return _outcome("caught", f"{len(files)} source(s): {[Path(p).name for p in files]}") if files else _outcome("silent", "no sources")
    files = sorted((d / "rtl").glob("*.sv"))
    return _outcome("caught", f"{len(files)} source(s)") if files else _outcome("silent", "own = rtl/*.sv is empty for a design that has RTL")


def r_trace_hash(d: Path, lang: str) -> dict[str, str]:
    """agent.graph.spectest.rtl_hash: an edit to the RTL after the evidence must change the hash (stale-evidence check)."""
    from agent.graph import spectest as T
    h0 = T.rtl_hash(d)
    ext = "sv" if lang == "sv" else "vhd"
    f = d / "rtl" / f"gray_stepper.{ext}"
    f.write_text(f.read_text() + ("\n// edited\n" if lang == "sv" else "\n-- edited\n"))
    h1 = T.rtl_hash(d)
    return _outcome("caught", "hash changed") if h0 != h1 else _outcome("silent", "an edit to the RTL leaves the hash unchanged: stale evidence is not seen")


def r_trace_items(d: Path, lang: str) -> dict[str, str]:
    """flow.trace_v1.legacy_items: the RTL files each v0 item is checked against."""
    from flow import trace_v1 as T
    items = T.legacy_items(d, {"evidence_record": "x.json", "requirements": [{"id": "R1", "tests": ["t"]}]})
    files = items[0]["checks"] if items else []
    return _outcome("caught", f"{len(files)} RTL file(s)") if files else _outcome("silent", "no RTL file listed")


def r_hw_dry(d: Path, lang: str) -> dict[str, str]:
    from flow import hw_dry_check as H
    probs = H.check_design(d)["problems"]
    hit = [p for p in probs if "BUILD_STAMP" in p]
    return _outcome("caught", hit[0]) if hit else _outcome("silent", f"{len(probs)} other problem(s); a constant-0 BUILD_STAMP is not seen")


def r_managed(d: Path, lang: str) -> dict[str, str]:
    """flow.managed_rtl_import.build_files: the component's source files as the build compiles them."""
    from agent.core import managed as M
    from flow import managed_rtl_import as MI
    rel = d.relative_to(ROOT).as_posix()
    ext = "sv" if lang == "sv" else "vhd"
    comp = M.Component(name="c", ownership="owned", level="rtl", paths=["rtl/**"], module="t1_gray_stepper_top",
                       build_sources=[f"{rel}/rtl/gray_stepper.{ext}"])
    proj = M.Project(name="p", top="t1_gray_stepper_top", components=[comp], design=d)
    files = MI.build_files(proj, comp)
    return _outcome("caught", f"{len(files)} file(s)") if files else _outcome("silent", "build_files drops the VHDL source: the component has no files")


def r_review(d: Path, lang: str) -> dict[str, str]:
    """flow.review.prepare.infer_top: the top of a design that comes without a build.yaml (a user's own RTL)."""
    from flow.review import prepare as P
    files = sorted(p.relative_to(d) for p in (d / "rtl").iterdir())
    full = [d / f for f in files]
    top = P.infer_top(full)
    return _outcome("caught", f"top {top}") if top else _outcome("silent", "no top found: the hierarchy of VHDL is empty")


def r_inspect(d: Path, lang: str) -> dict[str, str]:
    """flow.inspect_views: the source files handed to the schematic drawer."""
    src = (ROOT / "flow" / "inspect_views.py").read_text()
    m = re.search(r"src_files = (.+)\n", src)
    if "sources.readable" in (m.group(1) if m else ""):
        return _outcome("caught", "schematic sources come from the shared helper")
    files = [p for p in sorted((d / "rtl").iterdir()) if p.suffix in (".sv", ".v")]
    return _outcome("caught", f"{len(files)} file(s)") if files else _outcome("silent", "src_files is empty for VHDL: no schematic, and no note that VHDL was not read")


#: id, where it lives, the planted defect, the reader function
READERS: list[dict[str, Any]] = [
    {"id": "R01", "reader": "flow.checks lint (lint_ruleset.verilator_findings)", "where": "flow/lint_ruleset.py:103", "plant": "latch", "fn": r_lint},
    {"id": "R02", "reader": "flow.checks standards (flow/standards_check.py)", "where": "flow/standards_check.py:311,334", "plant": "async_reset", "fn": r_standards},
    {"id": "R03", "reader": "flow.checks resets, source part (flow/checks/resets.py)", "where": "flow/checks/__init__.py:299", "plant": "async_reset", "fn": r_resets},
    {"id": "R04", "reader": "flow.checks xpm_sim (constraint_gates.xpm_sim_findings)", "where": "flow/checks/__init__.py:436", "plant": "xpm_no_sim_assert", "fn": r_xpm},
    {"id": "R05", "reader": "flow.checks constants (flow/derived_constants.py)", "where": "flow/derived_constants.py:124", "plant": "wrong_id", "fn": r_constants},
    {"id": "R06", "reader": "flow.checks axi (flow/amd_ip_notes.py), control", "where": "flow/amd_ip_notes.py:29", "plant": None, "fn": r_axi},
    {"id": "R07", "reader": "flow.checks axi_profile (flow/checks/axi_profile.py)", "where": "flow/checks/axi_profile.py:57", "plant": None, "fn": r_axi_profile},
    {"id": "R08", "reader": "flow.checks fsm (flow/fsm_coverage.py parse_enum)", "where": "flow/fsm_coverage.py:48", "plant": None, "fn": r_fsm},
    {"id": "R09", "reader": "flow.cdc_inject.design_crosses (V3 CDC checks)", "where": "flow/cdc_inject.py:238", "plant": "crossing", "fn": r_cdc_inject_detect},
    {"id": "R10", "reader": "flow.cdc_inject_run.evaluate (CDC injection run)", "where": "flow/cdc_inject_run.py:58", "plant": "crossing", "fn": r_cdc_inject_run},
    {"id": "R11", "reader": "agent.graph.spectest (spec-test role RTL list)", "where": "agent/graph/spectest.py:213,327", "plant": None, "fn": r_spectest},
    {"id": "R12", "reader": "agent.graph.spectest.rtl_hash (stale-evidence key)", "where": "agent/graph/spectest.py:327", "plant": "edit", "fn": r_trace_hash},
    {"id": "R13", "reader": "flow.trace_v1.legacy_items (RTL files per item)", "where": "flow/trace_v1.py:132", "plant": None, "fn": r_trace_items},
    {"id": "R14", "reader": "flow.hw_dry_check (constant-0 BUILD_STAMP)", "where": "flow/hw_dry_check.py:77", "plant": "stamp_zero", "fn": r_hw_dry},
    {"id": "R15", "reader": "flow.managed_rtl_import.build_files (managed project)", "where": "flow/managed_rtl_import.py:125", "plant": None, "fn": r_managed},
    {"id": "R16", "reader": "flow.review.prepare.infer_top (review of a user's RTL)", "where": "flow/review/prepare.py:66", "plant": None, "fn": r_review},
    {"id": "R17", "reader": "flow.inspect_views schematic sources", "where": "flow/inspect_views.py:424", "plant": None, "fn": r_inspect},
]


# ---------------------------------------------------------------------------------------------------------------- the runs
def run_readers() -> dict[str, Any]:
    rows = []
    for r in READERS:
        row: dict[str, Any] = {"id": r["id"], "reader": r["reader"], "where": r["where"], "plant": r["plant"]}
        for lang in ("sv", "vhdl"):
            d = stage(lang, r["plant"])
            try:
                row[lang] = r["fn"](d, lang)
            except Exception as e:                      # noqa: BLE001 - a reader that raises on VHDL is a result, not a crash of the probe
                row[lang] = _outcome("wrong", f"raised {type(e).__name__}: {e}")
        rows.append(row)
    n = {k: sum(1 for r in rows if r["vhdl"]["outcome"] == k) for k in ("caught", "no_reader", "silent", "wrong", "control")}
    return {"schema": "fda-vhdl-parity-probe/1", "task": TASK, "readers": rows, "vhdl_summary": n,
            "sv_summary": {k: sum(1 for r in rows if r["sv"]["outcome"] == k) for k in ("caught", "no_reader", "silent", "wrong", "control")}}


def run_all_checks() -> dict[str, Any]:
    """Every registered check (scope rtl, no Vivado) on the five brief 55 translations (arm B) and on their SystemVerilog references."""
    from benchmark.tools import ref_build
    from flow import checks as C
    out: dict[str, Any] = {"schema": "fda-vhdl-parity-checks/1", "tasks": {}}
    for task in ("t1_gray_stepper", "t1_elevator_fsm", "d24_registered_outputs", "t1_sync_fifo_regs", "t1_debounce_bank"):
        tdir = ROOT / "benchmark" / ("drills" if task.startswith("d24") else "tasks") / task
        vrtl = ROOT / "results" / "55_vhdl" / "translations" / "B" / task / "rtl"
        base = ref_build.stage(tdir)
        for lang in ("sv", "vhdl"):
            d = WORK / f"{task}__{lang}__checks"
            shutil.rmtree(d, ignore_errors=True)
            (d / "rtl").mkdir(parents=True)
            src = (tdir / "ref" / "rtl") if lang == "sv" else vrtl
            for f in sorted(src.iterdir()):
                shutil.copy2(f, d / "rtl" / f.name)
            shutil.copy2(base / "design.xdc", d / "design.xdc")
            shutil.copy2(tdir / "spec.md", d / "spec.md")
            arch = yaml.safe_load((base / "architecture.yaml").read_text())
            (d / "architecture.yaml").write_text(yaml.safe_dump(arch, sort_keys=False))
            cfg = yaml.safe_load((base / "build.yaml").read_text())
            rel = d.relative_to(ROOT).as_posix()
            cfg["sources"] = ["shell/rtl/*.sv", f"{rel}/rtl/*." + ("sv" if lang == "sv" else "vhd")]
            cfg["constraints"] = [f"{rel}/design.xdc"]
            (d / "build.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
            if lang == "vhdl":
                from flow import vhdl
                (d / vhdl.HDL_MARKER).write_text("vhdl\n")
            res = {}
            for name in C.CHECKS:
                if name in ("methodology", "drc", "cdc", "exceptions", "io", "clocking", "constraint_scope", "dsp_ram_mapping",
                            "control_sets", "stale"):
                    continue                    # records of Vivado reports: no source is read, so no language question (listed in the report)
                reason = C.CHECKS[name].applies(d) if C.CHECKS[name].applies else None
                if reason:
                    res[name] = {"status": "not_applicable", "why": reason}
                    continue
                r = C.run_one(name, d, "rtl")
                res[name] = {"status": r.get("status"), "incomplete": r.get("incomplete"), "why": (r.get("why") or "")[:160],
                             "codes": sorted({f["code"] for f in r.get("findings") or []})[:6]}
            out["tasks"].setdefault(task, {})[lang] = res
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=("run", "checks"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rep = run_readers() if a.what == "run" else run_all_checks()
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rep, indent=1) + "\n")
    if a.what == "run":
        for r in rep["readers"]:
            print(f"{r['id']} {r['reader'][:58]:58} sv={r['sv']['outcome']:9} vhdl={r['vhdl']['outcome']:9} {r['vhdl']['detail'][:70]}")
        print("VHDL:", rep["vhdl_summary"], " SV:", rep["sv_summary"])
    else:
        for t, v in rep["tasks"].items():
            for lang, res in v.items():
                print(t, lang, {k: x["status"] for k, x in res.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
