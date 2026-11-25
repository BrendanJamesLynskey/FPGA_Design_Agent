"""The check suite (brief 71): every design check behind one registry, one runner and one compact digest.

    python3 -m flow.checks designs/<d> [--names all|resets,cdc,...] [--scope auto|rtl|synth|route] [--level summary|standard|detail]
                           [--variant base|ila] [--vivado auto|never] [--json OUT]

The agent's ``check`` tool (agent/core/tools.py) and the CLI call :func:`run`. Where the knowledge lives:

- **how to detect**: the check's code (this package, and the checkers it wraps: flow/standards_check.py,
  flow/cdc_structure.py, flow/exceptions_check.py, flow/io_check.py, flow/fsm_coverage.py, flow/amd_ip_notes.py,
  flow/gt_plan.py, flow/handover.py, flow/cmt_check.tcl);
- **what is a violation, why, the one-line fix and the waiver policy**: ``flow/hdl_rules.yaml`` (FDA-HDL); every code a
  check can raise maps to a rule there (``test_71_check_suite.py`` fails otherwise, and fails for a rule no check covers
  unless the rule is marked ``manual``);
- **the background**: the KB skill each rule names (``skill``).

Two kinds of check. **Source** and **record** checks (our Python checkers, Verilator lint, the build's recorded reports)
are cheap and run concurrently. **Vivado** checks need a report the build did not write (``report_control_sets``, the
reset netlist scan, the MMCM range check, ``report_qor_suggestions``): those reports are made in ONE Vivado session on the
stage's checkpoint (``post_synth.dcp`` or ``post_route.dcp``), all of them in sequence
(flow/checks/run_vivado_checks.sh), never one session per check. Reports the build already wrote are read, not re-run.

AMD's reports come first: a check digests ``report_methodology``, ``report_drc``, ``report_cdc``, ``report_control_sets``,
``report_clock_interaction`` and the rest, and our own code covers only the house rules no AMD report covers (the reset
netlist scan, the structural CDC check, the exception and I/O checks, the MMCM range check).

Verdicts: a check is ``pass``, ``fail`` (an unwaived blocking finding), or ``not_run`` (with the reason). A check with a
part that could not run says so (``incomplete``) and is never reported as a full pass. Waivers are the coding standard's
(``lint/waivers.yaml``: rule, match over the finding key, reason, owner, date).

The digest is what the caller sees: one line per check, then the findings (rule, severity, where, one-line fix, KB
skill), capped by ``level``. The full result is written to ``build/checks/<scope>.json`` and named in the digest; it is
never returned whole.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ("rtl", "synth", "route")
LEVELS = {"summary": 0, "standard": 5, "detail": 30}
#: the build's own report file for each report name and stage (flow/build.tcl); None: the build does not write it
BUILD_FILES = {
    "methodology": {"rtl": "methodology_rtl.rpt", "synth": "methodology_synth.rpt", "route": "methodology.rpt"},
    "drc": {"synth": "drc_synth.rpt", "route": "drc.rpt"},
    "cdc": {"synth": "cdc_synth.rpt", "route": "cdc.rpt"},
    "clock_interaction": {"synth": "clock_interaction_synth.rpt", "route": "clock_interaction_route.rpt"},
    "high_fanout": {"synth": "high_fanout_synth.rpt"},
    "timing_summary": {"synth": "timing_summary_synth.rpt", "route": "timing_summary.rpt"},
    "utilization": {"synth": "utilization_synth.rpt", "route": "utilization.rpt"},
    # written by flow/build.tcl after synthesis since brief 71; the route scope reads the same post-synthesis scan
    "reset_scan": {"synth": "reset_scan_synth.tsv", "route": "reset_scan_synth.tsv"},
    "control_sets": {"synth": "control_sets_synth.rpt"},
    "mtbf": {"route": "mtbf.rpt"},               # brief 189: flow/mtbf.py parses it (advisory; UltraScale+ only)
    "dsp_cells": {"synth": "dsp_cells_synth.txt", "route": "dsp_cells.txt"},      # brief 185: written by flow/build.tcl (flow/dsp_cells.tcl)
    # brief 204a: written by flow/build.tcl after synthesis and routing; the route scope reads the post-synthesis ones where the
    # guide asks for them before placement (logic levels, high-fanout nets)
    "logic_levels": {"synth": "logic_levels_synth.rpt", "route": "logic_levels_synth.rpt"},
    "clock_utilization": {"synth": "clock_utilization_synth.rpt", "route": "clock_utilization_route.rpt"},
    "clock_networks": {"synth": "clock_networks_synth.rpt", "route": "clock_networks_synth.rpt"},
    "congestion": {"route": "congestion_route.rpt"},
}
#: the post-synthesis report the high-fanout check reads at both scopes
BUILD_FILES["high_fanout"]["route"] = "high_fanout_synth.rpt"
DCP = {"synth": "post_synth.dcp", "route": "post_route.dcp"}
GATE_STAGE = {"rtl": "rtl", "synth": "post_synth", "route": "post_route"}


@dataclass
class Ctx:
    design: Path
    scope: str
    variant: str = "base"
    root: Path = ROOT
    level: str = "summary"
    #: session hooks (agent/core/tools.py): ``lint() -> {"ok", "output"}``, ``vivado(dcp, out, names) -> (rc, text)``;
    #: ``vivado=None`` means Vivado may not run (CI, ``--vivado never``)
    lint: Callable[[], dict[str, Any]] | None = None
    vivado: Callable[[Path, Path, list[str]], tuple[int, str]] | None = None
    #: ``cmd(kind, argv, timeout) -> returncode``: how a source check runs a checker script (a session's runner)
    cmd: Callable[[str, list[str], int], int] | None = None
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def build(self) -> Path:
        return self.design / "build" / self.variant

    @property
    def out(self) -> Path:
        return self.design / "build" / "checks" / self.variant / self.scope

    def report(self, name: str) -> Path | None:
        """The report for this scope: the build's own file, else one the check suite's Vivado session wrote."""
        f = BUILD_FILES.get(name, {}).get(self.scope)
        if f and (self.build / f).is_file() and not (self.build / (Path(f).stem + ".not_run.txt")).is_file():
            return self.build / f
        if (self.out / f"{name}.not_run.txt").is_file():       # the session refused or failed it: never read a partial file
            return None
        refs = [q for q in (self.build / DCP.get(self.scope, "post_synth.dcp"), self.build / "run.json",
                            self.build / "timing_summary_synth.rpt") if q.is_file()]
        for ext in ("rpt", "tsv"):
            p = self.out / f"{name}.{ext}"
            # a session's report older than the build (its checkpoint, run.json or synthesis report) belongs to an
            # earlier build; with no build to compare against it is stale too (review fixes)
            if p.is_file() and refs and p.stat().st_mtime >= max(q.stat().st_mtime for q in refs):
                return p
        return None

    def not_run_reason(self, name: str) -> str:
        p = self.out / f"{name}.not_run.txt"
        if p.is_file():
            return p.read_text(errors="replace").strip()[:300]
        return self.cache.get("vivado_why") or f"no {name} report for scope {self.scope}"

    def gates(self) -> dict[str, Any] | None:
        if "gates" not in self.cache:
            try:
                self.cache["gates"] = json.loads((self.build / "gates.json").read_text())
            except (OSError, ValueError):
                self.cache["gates"] = None
        return self.cache["gates"]


@dataclass(frozen=True)
class Check:
    name: str
    kind: str                                   # "source", "records" or "vivado"
    scopes: tuple[str, ...]                     # the scopes at which ``all`` runs it
    codes: dict[str, tuple[str, ...]]           # hdl_rules.yaml tool key -> the codes (or patterns, "*": any) it can raise
    summary: str
    run: Callable[[Ctx], dict[str, Any]]
    reports: tuple[str, ...] = ()               # the Vivado reports it reads (built or made by the Vivado session)
    amd: bool = False                           # True: AMD's own reports decide it; False: our code (or both, see summary)
    applies: Callable[[Path], str | None] | None = None   # a reason the check does not apply to this design, or None
    #: False: lint/waivers.yaml does not apply (the Designer may write lint/). The reset check's exceptions are
    #: architecture decisions (architecture.yaml reset.synchronisers / reset.async_inputs, frozen at approval); the DOC
    #: gate has none.
    waivable: bool = True
    #: True: the check mirrors a stage gate; a waiver is shown but a blocking row still fails the check, as it fails the
    #: gate (review fix: the Designer may write lint/waivers.yaml)
    gate_mirror: bool = False


CHECKS: dict[str, Check] = {}
#: monitors that raise their rule in simulation, not through this suite (rule ids in hdl_rules.yaml under their tool key)
MONITORS = {"axi_checker": ("RESP_LOST",)}


def register(c: Check) -> Check:
    CHECKS[c.name] = c
    return c


# ---- shared helpers ----------------------------------------------------------------------------------------------
def rules() -> dict[str, Any]:
    from flow.lint_ruleset import load_rules
    return load_rules()


def _parse_rules(path: Path | None) -> list[dict[str, Any]] | None:
    from flow.gates import parse_rule_table
    if path is None:
        return None
    try:
        return parse_rule_table(path.read_text(errors="replace"))
    except ValueError:
        return None


def _parse_cdc(path: Path | None) -> dict[str, Any] | None:
    from flow.gates import parse_cdc
    if path is None:
        return None
    try:
        return parse_cdc(path.read_text(errors="replace"))
    except ValueError:
        return None


def _vrow(r: dict[str, Any], ctx: Ctx, report: str, blocking: bool) -> dict[str, Any]:
    return {"tool": "vivado", "code": r["rule"], "severity": str(r.get("severity", "")),
            "where": f"{report}@{GATE_STAGE[ctx.scope]}", "key": f"vivado:{r['rule']}@{GATE_STAGE[ctx.scope]}",
            "message": f"{r.get('description', '')} (x{r.get('count', 1)})", "count": r.get("count", 1), "blocking": blocking}


def _result(findings: list[dict[str, Any]], parts: dict[str, str] | None = None, records: list[Path] | None = None,
            why: str = "") -> dict[str, Any]:
    return {"findings": findings, "parts": parts or {}, "records": [str(p) for p in records or [] if p], "why": why}


def _not_run(why: str) -> dict[str, Any]:
    return {"status": "not_run", "why": why, "findings": [], "parts": {}, "records": []}


def build_sources(design: Path, root: Path = ROOT) -> list[Path]:
    """The build's own source list, every language (flow/sources.py, brief 153)."""
    from flow import sources
    return sources.build_sources(design, root)


def build_top(design: Path) -> str | None:
    try:
        return str((yaml.safe_load((design / "build.yaml").read_text()) or {}).get("top") or "") or None
    except (OSError, yaml.YAMLError):
        return None


# ---- the checks ----------------------------------------------------------------------------------------------------
def _lint(ctx: Ctx) -> dict[str, Any]:
    """Verilator -Wall (and, in a session, the agent's lint tool unchanged: Icarus elaboration, FDA-CON-8/9)."""
    if ctx.lint is not None:
        r = ctx.lint()
        out = str(r.get("output", ""))
        fs = _verilator_lines(out, ctx)
        if not r.get("ok") and not fs:          # a failure with no Verilator line (Icarus, ports, a refusal): keep its text
            fs = [{"tool": "verilator", "code": "ERROR", "severity": "error", "where": "lint",
                   "message": out.strip()[-400:] or "lint failed", "blocking": True}]
        return {**_result(fs), "verdict": bool(r.get("ok"))}
    from flow import sources
    from flow.lint_ruleset import verilator_findings
    g = sources.by_language(build_sources(ctx.design, ctx.root))
    if g["vhdl"]:
        return _lint_vhdl(ctx, g)
    vf, note = verilator_findings(ctx.design)
    if vf is None:
        return _not_run(note)
    if note and not vf:                                  # Verilator itself failed (a crash, a bad VERILATOR_ROOT): that is not a clean lint
        return _not_run(note)
    fs = [{"tool": "verilator", "code": f["code"], "severity": f["severity"], "where": f["key"].split(" ", 1)[-1],
           "key": f["key"], "message": f["message"], "blocking": True} for f in vf]
    return _result(fs)


def _lint_vhdl(ctx: Ctx, g: dict[str, list[Path]]) -> dict[str, Any]:
    """The lint of a design with VHDL in its build list (brief 153): the VHDL tool's own lint, as the agent's lint tool runs it
    (``flow.vhdl.lint``: GHDL analysis with -Wall, then synthesis of the top; latches and double drivers refused; the shell's modules
    may stay unbound components). A VHDL top with SystemVerilog beside it (the test shell) is linted as VHDL. A SystemVerilog top over
    VHDL entities has no lint that reads both languages: it is not run, and says so. The findings carry the tool key ``verilator``
    (the lint tool's key in the rule set) with the code ``GHDL``, so they map to the lint catch-all rule HDL-LINT-00."""
    from flow import vhdl
    top = build_top(ctx.design)
    vh = [f for f in g["vhdl"] if f.is_file()]
    own_vhdl_top = bool(top) and any(re.search(rf"(?im)^\s*entity\s+{re.escape(top)}\s+is\b", f.read_text(errors="replace")) for f in vh)
    if not own_vhdl_top:
        return _not_run(f"no reader: the build's top {top!r} is not a VHDL entity but the build has VHDL files "
                        f"({', '.join(f.name for f in vh[:3])}): no lint reads SystemVerilog and VHDL together")
    r = vhdl.lint(vh, vhdl.top_entity(vh, top))
    if r["ok"]:
        return {**_result([]), "verdict": True}
    text = str(r.get("output", "")).strip()
    where = next((m.group(1) for m in re.finditer(r"([\w./-]+\.vhdl?):\d+", text)), "lint")
    return {**_result([{"tool": "verilator", "code": "GHDL", "severity": "error", "where": where, "key": f"verilator:GHDL {where}",
                        "message": text[-400:] or "GHDL lint failed", "blocking": True}]), "verdict": False}


def _verilator_lines(text: str, ctx: Ctx) -> list[dict[str, Any]]:
    from flow.lint_ruleset import _VL
    out = []
    for line in text.splitlines():
        m = _VL.match(line.strip())
        if m:
            sev, code, f, ln, msg = m.groups()
            code = code or ("ERROR" if sev == "Error" else "WARNING")
            try:
                f = Path(f).resolve().relative_to(ctx.root).as_posix()
            except ValueError:
                pass
            out.append({"tool": "verilator", "code": code, "severity": sev.lower(), "where": f"{f}:{ln}",
                        "key": f"verilator:{code} {f}:{ln}", "message": msg.strip(), "blocking": True})
    return out


def _standards(ctx: Ctx) -> dict[str, Any]:
    """flow/standards_check.py (docs/design_standards.md), the post-synthesis rules from the build at synth/route."""
    import subprocess
    import sys
    out = ctx.out / "standards.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    argv = [sys.executable, str(ctx.root / "flow" / "standards_check.py"), str(ctx.design), "--json", str(out)]
    if ctx.scope != "rtl":
        argv += ["--variant", ctx.variant]
    if ctx.cmd is not None:
        ctx.cmd("standards", argv, 300)
    else:
        subprocess.run(argv, cwd=ctx.root, capture_output=True, text=True, timeout=600)
    try:
        rep = json.loads(out.read_text())
    except (OSError, ValueError):
        return _not_run("flow/standards_check.py wrote no result")
    fs = []
    for r in rep.get("rules") or []:
        if r.get("status") in ("fail", "not_run") and (ctx.scope != "rtl" or r.get("stage") in ("rtl", None)):
            for f in r.get("findings") or [{"file": "-", "line": 0, "message": r.get("why_not_run", r["status"])}]:
                where = f"{f.get('file')}:{f.get('line')}"
                fs.append({"tool": "standards", "code": r["id"], "severity": r["status"], "where": where,
                           "key": f"standards:{r['id']} {where}", "message": f.get("message", ""), "blocking": True})
    for r in rep.get("rules") or []:        # rtl.initial_values: warn (brief 205): shown, never blocking
        if r.get("status") == "warn" and (ctx.scope != "rtl" or r.get("stage") in ("rtl", None)):
            for f in r.get("warnings") or []:
                where = f"{f.get('file')}:{f.get('line')}"
                fs.append({"tool": "standards", "code": r["id"], "severity": "warning", "where": where,
                           "key": f"standards:{r['id']} {where}", "message": f.get("message", ""), "blocking": False})
    return _result(fs, records=[out])


def _ip_names(ctx: Ctx) -> set[str]:
    """Names of the build's IP cores (generated, so not in the source list): build/<variant>/ip/<name> and design ip/ stems."""
    names: set[str] = set()
    for base in ctx.design.glob("build/*/ip"):
        names |= {p.stem for p in base.glob("*")}
    ipd = ctx.design / "ip"
    if ipd.is_dir():
        names |= {p.stem for p in ipd.glob("*")}
    try:                                  # IP created by the build's ip_tcl scripts: ``fda_ip <vlnv> <name> ...`` or -module_name
        for t in (yaml.safe_load((ctx.design / "build.yaml").read_text()) or {}).get("ip_tcl") or []:
            txt = (ctx.root / str(t)).read_text(errors="replace")
            names |= set(re.findall(r"(?m)^\s*fda_ip\s+\S+\s+(\w+)\b", txt)) | set(re.findall(r"-module_name\s+(\w+)", txt))
    except (OSError, yaml.YAMLError):
        pass
    return names


def _resets(ctx: Ctx) -> dict[str, Any]:
    from flow.checks import resets as R
    cfg = R.reset_config(ctx.design)
    parts: dict[str, str] = {}
    fs = []
    srcs = build_sources(ctx.design, ctx.root)         # every file of the build list: the front end reports what it cannot read
    if srcs:
        try:
            defines = [str(x) for x in (yaml.safe_load((ctx.design / "build.yaml").read_text()) or {}).get("defines") or []]
        except (OSError, yaml.YAMLError):
            defines = []
        try:
            pats = [str(g) for g in (yaml.safe_load((ctx.design / "build.yaml").read_text()) or {}).get("sources") or []]
        except (OSError, yaml.YAMLError):
            pats = []
        unmatched = [g for g in pats if not list(ctx.root.glob(g))]
        fs += R.source_findings(ctx.design, srcs, cfg, root=ctx.root, top=build_top(ctx.design), parts=parts, defines=defines,
                                unmatched=unmatched, ip_names=_ip_names(ctx))
    else:
        parts["source"] = "not run: no sources in build.yaml"
    # AMD IP in the design: what its resets need (flow/amd_ip_resets.py, brief 70); advice, never a failure
    from flow import amd_ip_resets as AIR
    for name, files in sorted(AIR.scan([ctx.design]).items()):
        fs.append({"tool": "resets", "code": "RST-IP-01", "rule": "HDL-RST-06", "severity": "warning", "file": None, "line": None,
                   "where": ", ".join(Path(f).name for f in files[:2]) or name, "key": f"resets:RST-IP-01 {name}", "count": 1,
                   "message": f"{AIR.MAP[name]['title']}: " + "; ".join(AIR.notes_for(name)[:3])[:400],
                   "fix": "give the IP the reset it needs (polarity, synchronised to its clock, held long enough); see the KB skill amd-ip-reset-map",
                   "blocking": False})
    records = []
    if ctx.scope == "rtl":
        parts["amd"] = parts["netlist"] = "not run: scope rtl (needs a synthesised design)"
    else:
        meth, drc, cdc = ctx.report("methodology"), ctx.report("drc"), ctx.report("cdc")
        for r in R.amd_findings(_parse_rules(meth), _parse_rules(drc), _parse_cdc(cdc), GATE_STAGE[ctx.scope],
                                 meth_text=meth.read_text(errors="replace") if meth else None):
            fs.append({**r, "key": f"vivado:{r['code']}@{GATE_STAGE[ctx.scope]}",
                       "blocking": r["severity"].lower() not in ("advisory", "info")})
        for nm, pth in (("methodology", meth), ("drc", drc), ("cdc", cdc)):
            parts[f"amd_{nm}"] = "ran" if pth else "not run: " + ctx.not_run_reason(nm)
        records += [x for x in (meth, drc, cdc) if x]
        scan = ctx.report("reset_scan")
        if scan:
            ips = {p.stem for p in (ctx.build / "ip").glob("*") if p.is_dir()} if (ctx.build / "ip").is_dir() else set()
            nf = R.netlist_findings(R.read_scan(scan), cfg, ips)
            fs += [{**f, "key": f"resets:{f['code']} {f['where']}", "blocking": True} for f in nf if not f.get("incomplete")]
            parts["netlist"] = "ran"
            unk = [f for f in nf if f.get("incomplete")]
            parts["netlist_clocks"] = ("not run: " + unk[0]["message"]) if unk else "ran"
            records.append(scan)
        else:
            parts["netlist"] = "not run: " + ctx.not_run_reason("reset_scan")
    # the measured cost behind each of our findings (results/70_resets, flow/checks/reset_costs.json), for the design's family
    try:
        part = str((yaml.safe_load((ctx.design / "build.yaml").read_text()) or {}).get("part") or "")
    except (OSError, yaml.YAMLError):
        part = ""
    for f in fs:
        note = R.cost_note(str(f.get("code", "")), part)
        if note:
            f["cost"] = note
    # polarity (HDL-RST-02): judged on the elaborated source (every reset pin of every register, traced to its root signal)
    # and again on the netlist; it ran when either did
    parts["polarity"] = "ran" if parts.get("source") == "ran" or parts.get("netlist") == "ran" else \
        (parts.get("source") or "not run: no source and no netlist scan")
    return _result(fs, parts, records)


def _rows_check(report: str, pattern: str | None, block: Callable[[str], bool]):
    """A check that digests one AMD rule report: rows matching ``pattern`` (all rows when None)."""
    import fnmatch

    def run(ctx: Ctx) -> dict[str, Any]:
        if ctx.scope == "rtl" and report != "methodology":
            return _not_run(f"report_{report} needs a synthesised design (scope synth or route)")
        p = ctx.report(report)
        rows = _parse_rules(p)
        if rows is None:
            return _not_run(ctx.not_run_reason(report) if p is None else f"{p.name} is not a {report} report")
        pats = pattern.split(",") if pattern else None
        fs = [_vrow(r, ctx, p.name, block(r["severity"])) for r in rows
              if pats is None or any(fnmatch.fnmatchcase(r["rule"], x) for x in pats)]
        if pats is None:          # a pass-through check keeps every blocking row (the gate's decision) but leaves the
            # advisory rows another check owns to that check, so one AMD row is not shown with two meanings
            fs = [f for f in fs if f["blocking"] or not _owned(f["code"], report)]
        return _result(fs, records=[p])
    return run


def _design_board(ctx: Ctx) -> str | None:
    """The board the build was made for (prepare.json), else the design's build.yaml ``board``."""
    try:
        b = json.loads((ctx.build / "prepare.json").read_text()).get("board")
        if b:
            return str(b)
    except (OSError, ValueError):
        pass
    try:
        return (yaml.safe_load((ctx.design / "build.yaml").read_text()) or {}).get("board")
    except (OSError, yaml.YAMLError):
        return None


def _drc(ctx: Ctx) -> dict[str, Any]:
    """report_drc as the gate reads it, plus brief 105A: CFGBVS-1/2 block when the board's configuration voltage is confirmed in its
    board file (the gate ``config_voltage_declared``); on any other board they stay advisory."""
    r = _rows_check("drc", None, _err_or_crit)(ctx)
    if r.get("status") == "not_run":
        return r
    from flow import constraint_gates as CG
    cfg = CG.board_config(_design_board(ctx), ctx.root)
    if cfg and cfg["confirmed"]:
        for f in r["findings"]:
            if f["code"] in CG.CFGBVS_RULES and not f["blocking"]:
                f["blocking"] = True
                f["message"] += f"; blocking: the configuration voltage of board {cfg['board']} is confirmed (boards/{cfg['board']}/board.yaml)"
    return r


def _async_groups(ctx: Ctx) -> dict[str, Any]:
    """Brief 105A, advisory: set_clock_groups -asynchronous over clock pairs that have paths between them, or over every clock
    (flow/constraint_gates.py). Never blocking."""
    if ctx.scope != "route":
        return _not_run("needs the routed design's report_clock_interaction (scope route)")
    p = ctx.report("clock_interaction")
    if p is None:
        return _not_run(ctx.not_run_reason("clock_interaction"))
    from flow import constraint_gates as CG
    try:
        cons = (yaml.safe_load((ctx.design / "build.yaml").read_text()) or {}).get("constraints") or []
    except (OSError, yaml.YAMLError):
        cons = []
    xdcs = [x for g in cons for x in sorted(ctx.root.glob(g))] or sorted(ctx.design.glob("*.xdc"))     # the build's own constraint list
    fs = [{"tool": "constraint_scope", "code": f["code"], "severity": "advisory", "where": f["where"],
           "key": f"constraint_scope:{f['code']} {f['where']}", "message": f["message"], "blocking": False}
          for f in CG.async_group_findings(p.read_text(errors="replace"), [x.read_text(errors="replace") for x in xdcs])]
    return _result(fs, records=[p])


def _xpm_sim(ctx: Ctx) -> dict[str, Any]:
    """Brief 105A, advisory: an xpm_cdc instance (of a macro that has the parameter) whose SIM_ASSERT_CHK is not 1 (flow/constraint_gates.py).
    Reads the build's own source list; only text of the design's RTL, never a vendor file."""
    from flow import constraint_gates as CG
    from flow import sources
    srcs = [f for f in build_sources(ctx.design, ctx.root) if sources.language(f)]
    if not srcs:
        return _not_run("no HDL source file in the build list")
    fs = []
    for f in srcs:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(ctx.root)) if f.is_relative_to(ctx.root) else str(f)
        for x in (CG.xpm_sim_findings_vhdl if sources.language(f) == "vhdl" else CG.xpm_sim_findings)(text, rel):
            fs.append({"tool": "xpm_sim", "code": x["code"], "severity": "advisory", "where": x["where"],
                       "key": f"xpm_sim:{x['code']} {x['where']}", "message": x["message"], "blocking": False})
    return _result(fs, records=srcs)


def _fastpath(ctx: Ctx) -> dict[str, Any]:
    """Brief 190, advisory: a data-dependent shift or index of a wide vector in a module declared fast-path (flow/checks/wide_index.py).
    Modules are declared in architecture.yaml ``fast_path: [module, ...]`` or by a ``// fda:fast_path`` comment inside the module."""
    from flow.checks import wide_index as WI
    try:
        declared = {str(x) for x in ((yaml.safe_load((ctx.design / "architecture.yaml").read_text()) or {}).get("fast_path") or [])}
    except (OSError, yaml.YAMLError, AttributeError):
        declared = set()
    srcs = [f for f in build_sources(ctx.design, ctx.root) if f.suffix in (".sv", ".v")]
    r = WI.run(srcs, declared, ctx.root)
    fs = [{"tool": "fastpath", "code": x["code"], "severity": "advisory", "where": x["where"], "key": f"fastpath:{x['code']} {x['where']} {x['vector']}",
           "message": x["message"], "blocking": False} for x in r["findings"]]
    parts = {"modules": f"{r['modules']} fast-path module(s) examined" if r["modules"] else
             "no module declared fast-path (architecture.yaml fast_path: [...] or a // fda:fast_path comment)"}
    if r["unjudged"]:
        parts["unjudged"] = f"{r['unjudged']} shift(s) or index(es) on vectors whose width could not be evaluated were not judged"
    return _result(fs, parts, srcs)


def _cdc_margin(ctx: Ctx) -> dict[str, Any]:
    """Brief 207: clock-crossing intent constrained and met (flow/cdc_margin.py, the same function as the gate post_route_bus_skew_met):
    a bus-skew violation blocks; missing bus-skew coverage, a loose datapath-only value, a missing or low MTBF (UltraScale+) and high
    user clock uncertainty are advisory."""
    if ctx.scope != "route":
        return _not_run("needs the routed design's report_bus_skew (scope route)")
    if not (ctx.build / "bus_skew_route.rpt").is_file():
        return _not_run("the build has no bus_skew_route.rpt (made before brief 207)")
    from flow import gates as G
    try:
        prep = json.loads((ctx.build / "prepare.json").read_text()) if (ctx.build / "prepare.json").is_file() else {}
        r = G._cdc_margin(ctx.build, None, prep)
    except (OSError, ValueError, KeyError) as e:
        return _not_run(f"{type(e).__name__}: {e}")
    fs = [{"tool": "cdc_margin", "code": f["code"], "severity": "error" if f["level"] == "gate" else "advisory",
           "where": str(f.get("cell") or f.get("net") or f.get("position") or f.get("id") or "bus_skew_route.rpt"),
           "key": f"cdc_margin:{f['code']} {f.get('cell') or f.get('net') or f.get('position') or f.get('id') or ''}".strip(),
           "message": str(f.get("text") or f)[:240], "blocking": f["level"] == "gate"} for f in (r or {}).get("findings", [])]
    return _result(fs, records=[ctx.build / "bus_skew_route.rpt"])


def _owned(code: str, by: str) -> str | None:
    """The dedicated check that reads this AMD rule id (resets, cdc, clocking, ...), other than the pass-through ``by``."""
    import fnmatch
    for n, c in CHECKS.items():
        if n in (by, "methodology", "drc"):
            continue
        if any(x != "*" and fnmatch.fnmatchcase(code, x) for x in c.codes.get("vivado", ())):
            return n
    return None


def _crit(sev: str) -> bool:
    return sev.lower() == "critical warning"


def _err_or_crit(sev: str) -> bool:
    return sev.lower() in ("error", "critical warning")


def _cdc(ctx: Ctx) -> dict[str, Any]:
    """report_cdc (Critical rows fail, as the gates' cdc_no_critical) and, after synthesis, the structural CDC check
    (flow/cdc_structure.py, as the gate post_synth_cdc_structure_clean)."""
    if ctx.scope == "rtl":
        return _not_run("report_cdc needs a synthesised design (scope synth or route)")
    p = ctx.report("cdc")
    c = _parse_cdc(p)
    if c is None:
        return _not_run(ctx.not_run_reason("cdc"))
    fs = [{"tool": "vivado", "code": r["rule"], "severity": r["severity"], "where": f"{p.name}@{GATE_STAGE[ctx.scope]}",
           "key": f"vivado:{r['rule']}@{GATE_STAGE[ctx.scope]}", "message": f"{r['description']} (x{r['count']})",
           "count": r["count"], "blocking": r["severity"] == "Critical"} for r in c["rules"]]
    parts = {"report_cdc": "ran"}
    recs = [p]
    if ctx.scope == "synth":
        from flow import gates as G
        if (ctx.build / "cdc_paths_synth.rpt").is_file():
            try:
                s = G._cdc_structure(ctx.build, None)
                for u in s["unsafe"]:
                    fs.append({"tool": "cdc_structure", "code": u["rule"], "severity": "error", "where": u["cell"],
                               "key": f"cdc_structure:{u['rule']} {u['cell']}", "message": u["why"][:240],
                               "blocking": True})
                parts["structure"] = "ran"
                recs.append(ctx.build / "cdc_paths_synth.rpt")
            except ValueError as e:
                fs.append({"tool": "cdc_structure", "code": "U0", "severity": "error", "where": "cdc_paths_synth.rpt",
                           "message": f"unreadable: {e}", "blocking": True})
        else:
            parts["structure"] = "not run: the build has no cdc_paths_synth.rpt"
    return _result(fs, parts, recs)


def _gate_backed(kind: str):
    """exceptions and io: flow/gates.py's own helpers (the same functions the stage gates call, so the verdict is the
    gate's)."""
    def run(ctx: Ctx) -> dict[str, Any]:
        if ctx.scope == "rtl":
            return _not_run(f"the {kind} check reads the synthesised or routed timing database (scope synth or route)")
        from flow import gates as G
        stage = "synth" if ctx.scope == "synth" else "route"
        g: dict[str, bool] = {}
        strict = (ctx.build / "run.json").exists()
        try:
            r = (G._exceptions if kind == "exceptions" else G._io)(ctx.build, stage, strict, g, "x")
        except (OSError, ValueError, KeyError) as e:
            return _not_run(f"{type(e).__name__}: {e}")
        ri, gi = None, {}
        if kind == "io" and stage == "route":
            # brief 129: the I/O-block packing of every marked register (flow/iob_check.py), with the cell and the reason
            try:
                prep = json.loads((ctx.build / "prepare.json").read_text()) if (ctx.build / "prepare.json").exists() else {}
                ri = G._iob_packing(ctx.build, prep, strict, gi)
            except (OSError, ValueError, KeyError):
                ri = None
        if r is None and "x" not in g and ri is None:
            return _not_run(f"the build has no {kind} reports for {stage}")
        fs = []
        for f in (r or {}).get("failures") or []:
            where = f"{f['file']}:{f['line']}" if f.get("file") else (f"position {f['position']}" if f.get("position") else stage)
            fs.append({"tool": kind, "code": f["rule"], "severity": "error", "where": where,
                       "key": f"{kind}:{f['rule']} {where}", "message": (f.get("message") or f.get("text") or "")[:240],
                       "blocking": True})
        if g.get("x") is False and not fs:
            fs.append({"tool": kind, "code": "EXC-NO-PATH" if kind == "exceptions" else "IO-NO-PATH", "severity": "error",
                       "where": stage, "message": (r or {}).get("error", "the gate failed with no listed finding"),
                       "blocking": True})
        verdict = g.get("x")
        if ri is not None:
            for f in ri.get("findings") or []:
                fs.append({"tool": kind, "code": f["code"], "severity": "error" if f["blocking"] else "advisory", "where": f["where"],
                           "key": f"io:{f['code']} {f['where']}", "message": f["message"][:300], "blocking": f["blocking"]})
            if gi.get("iob_packed") is False:
                verdict = False
            elif verdict is None and "iob_packed" in gi:
                verdict = True
        return {**_result(fs), "verdict": verdict}
    return run


def _clocking(ctx: Ctx) -> dict[str, Any]:
    """CLKC methodology rows (AMD) and the MMCM/PLL VCO and PFD range check (flow/cmt_check.tcl, ours: no AMD report
    rejects a hand-instantiated MMCM outside its range)."""
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    import re
    fs, parts, recs = [], {}, []
    m = ctx.report("methodology")
    rows = _parse_rules(m)
    if rows is not None:
        fs += [_vrow(r, ctx, m.name, _crit(r["severity"])) for r in rows if r["rule"].startswith("CLKC-")]
        parts["methodology"] = "ran"
        recs.append(m)
    else:
        parts["methodology"] = "not run: " + ctx.not_run_reason("methodology")
    c = ctx.report("cmt")
    if c:
        for line in c.read_text(errors="replace").splitlines():
            if "VIOLATION" in line:
                cell = line.split()[1] if len(line.split()) > 1 else "?"
                fs.append({"tool": "clocking", "code": "CMT-RANGE-01", "severity": "error", "where": cell,
                           "key": f"clocking:CMT-RANGE-01 {cell}", "message": line.strip()[:240], "blocking": True})
        parts["cmt"] = "ran"
        recs.append(c)
    else:
        parts["cmt"] = "not run: " + ctx.not_run_reason("cmt")
    del re
    return _result(fs, parts, recs)



def _clock_mux(ctx: Ctx) -> dict[str, Any]:
    """Brief 208: clock multiplexers (flow/clock_mux_check.py on flow/clock_mux_dump.tcl's netlist scan, with the
    clock-interaction report): a LUT on a clock path, a mux whose modes are still timed against each other, clock groups on
    the mux's source clocks while paths join a source tree and the mux fanout (they hide real paths), and advisories for a
    case-analysed select, a CE-pin select, an external clock with IGNORE tied, and a deep BUFGCTRL cascade."""
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised netlist (scope synth or route)")
    p = ctx.report("clock_mux")
    if p is None:
        return _not_run(ctx.not_run_reason("clock_mux"))
    from flow import clock_mux_check as CM
    from flow.constraint_gates import parse_clock_pairs
    ci = ctx.report("clock_interaction")
    pairs = parse_clock_pairs(ci.read_text(errors="replace")) if ci else None
    fs = [{"tool": "clock_mux", "code": f["code"], "severity": "error" if f["blocking"] else "advisory", "where": f["where"],
           "key": f"clock_mux:{f['code']} {f['where']}", "message": f["message"], "blocking": f["blocking"]}
          for f in CM.findings(CM.parse_dump(p.read_text(errors="replace")), pairs)]
    parts = {"clock_mux": "ran", "clock_interaction": "ran" if ci else "not run: " + ctx.not_run_reason("clock_interaction")}
    return _result(fs, parts, [p, ci])


def _dsp_ram(ctx: Ctx) -> dict[str, Any]:
    """DSP and block-RAM mapping: AMD's DPIP/DPOP pipelining rows and SYNTH rows (methodology), RBOR and REQP RAM rows
    (DRC), and the utilisation of DSP and RAM. Critical rows fail; the rest are advice."""
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    import fnmatch
    fs, parts, recs = [], {}, []
    for rep, pats in (("methodology", ("DPIP-*", "DPOP-*", "SYNTH-*", "DPIR-*", "RMIR-*", "RMOR-*", "RROR-*")),
                      ("drc", ("DPIP-*", "DPOP-*", "DPIR-*", "DPOR-*", "RBOR-*"))):
        p = ctx.report(rep)
        rows = _parse_rules(p)
        if rows is None:
            parts[rep] = "not run: " + ctx.not_run_reason(rep)
            continue
        fs += [_vrow(r, ctx, p.name, _crit(r["severity"])) for r in rows if any(fnmatch.fnmatchcase(r["rule"], x) for x in pats)]
        parts[rep] = "ran"
        recs.append(p)
    u = ctx.report("utilization")
    parts["utilization"] = "ran" if u else "not run: " + ctx.not_run_reason("utilization")
    if u:
        from flow.gates import parse_utilization
        used = parse_utilization(u.read_text(errors="replace"))
        ctx.cache["dsp_ram_util"] = {k: v for k, v in used.items() if any(x in k.upper() for x in ("DSP", "RAMB", "BLOCK RAM"))}
        recs.append(u)
    return _result(fs, parts, recs)


def _dsp_regs_applies(design: Path) -> str | None:
    """Only builds that recorded their DSP cells (flow/build.tcl since brief 185): an older build, or no build, has nothing to read."""
    if not any(design.glob("build/*/dsp_cells*.txt")):
        return "no dsp_cells*.txt in the build (made by flow/build.tcl since brief 185)"
    return None


def _dsp_regs(ctx: Ctx) -> dict[str, Any]:
    """Advisory (brief 185): a DSP slice without the multiplier or output register at a period the measurements say it cannot meet, and Vivado's own
    DPIP/DPOP rows. The limits are flow/dsp_regs_limits.json (regenerated from results/185_dsp_slices by tools/dsp_regs_limits.py)."""
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    import re
    from flow import dsp_regs_check as D
    cells = ctx.report("dsp_cells")
    if cells is None:
        return _not_run(ctx.not_run_reason("dsp_cells"))
    ts = ctx.report("timing_summary")
    period = None
    if ts is not None:
        rows = re.findall(r"^\s*\S+\s+\{[^}]*\}\s+([\d.]+)\s+[\d.]+", ts.read_text(errors="replace"), re.M)
        period = min(float(x) for x in rows) if rows else None
    drc = ctx.report("drc")
    fs = []
    if period is None:
        parts = {"registers": "not run: no clock period in the timing summary"}
    else:
        parts = {"registers": "ran"}
    for f in D.check(D.parse_cells(cells.read_text(errors="replace")) if period is not None else [], period or 0.0, drc.read_text(errors="replace") if drc else None):
        fs.append({"tool": "dsp_regs", "code": f["code"], "severity": "advisory", "where": f["where"], "key": f"dsp_regs:{f['code']} {f['where']}",
                   "message": f["message"], "blocking": False})
    return _result(fs, parts, [cells])


def _init_values(ctx: Ctx) -> dict[str, Any]:
    """Initial values that cost a hard block's register (brief 206, flow/checks/init_values.py): the session's netlist scan
    (init_scan) for INIT = 1 registers wired to a DSP, RAM or FIFO, and the build log for UltraRAM refused for initial
    contents (Synth 8-12183). Advisory only."""
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    from flow.checks import init_values as I
    fs, parts, recs = [], {}, []
    scan = ctx.report("init_scan")
    if scan:
        fs += [{**f, "key": f"init_values:{f['code']} {f['where']}", "blocking": False} for f in I.scan_findings(I.read_scan(scan))]
        parts["netlist"] = "ran"
        recs.append(scan)
    else:
        parts["netlist"] = "not run: " + ctx.not_run_reason("init_scan")
    log = ctx.build / "vivado.log"
    if log.is_file():
        fs += [{**f, "key": f"init_values:{f['code']} {f['where']}", "blocking": False}
               for f in I.log_findings(log.read_text(errors="replace"))]
        parts["log"] = "ran"
        recs.append(log)
    else:
        parts["log"] = "not run: no build/<variant>/vivado.log"
    return _result(fs, parts, recs)


def _control_sets(ctx: Ctx) -> dict[str, Any]:
    """report_control_sets (AMD): the number of unique control sets, and AMD's ULMTCS rows from report_methodology."""
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    import re
    p = ctx.report("control_sets")
    if p is None:
        return _not_run(ctx.not_run_reason("control_sets"))
    t = p.read_text(errors="replace")
    m = re.search(r"Total control sets\s*\|\s*(\d+)", t) or re.search(r"Number of unique control sets\s*\|\s*(\d+)", t)
    ctx.cache["control_sets"] = int(m.group(1)) if m else None
    fs = []
    mp = ctx.report("methodology")
    for r in _parse_rules(mp) or []:
        if r["rule"].startswith("ULMTCS-"):
            fs.append(_vrow(r, ctx, mp.name, _crit(r["severity"])))
    parts = {"report_control_sets": "ran", "methodology": "ran" if mp else "not run: " + ctx.not_run_reason("methodology")}
    # brief 204a: UG949 Table 17 (p.265): the bands against the device's capacity (CLB registers / 8)
    from flow import report_gates as R
    ut, _up, why = _txt(ctx, "utilization")
    if ut is not None:
        fs += R.control_set_findings(ctx.cache["control_sets"], G_parse_util(ut).get("ff_available"))
        parts["utilization"] = "ran"
    else:
        parts["utilization"] = "not run: " + why
    return _result(fs, parts, records=[p])


# ---- brief 204a: report-driven checks (flow/report_gates.py) ------------------------------------------------------------
def _txt(ctx: Ctx, name: str) -> tuple[str | None, Path | None, str]:
    """(text, path, why): the report's text, or None and the reason it is missing."""
    p = ctx.report(name)
    if p is None:
        return None, None, ctx.not_run_reason(name)
    return p.read_text(errors="replace"), p, ""


def _timing_texts(ctx: Ctx) -> list[tuple[str, str]]:
    """The timing-path reports of this scope: (file name, text)."""
    names = ["timing_summary_synth.rpt"] if ctx.scope == "synth" else ["timing_summary.rpt", "timing_worst_setup.rpt", "timing_worst_hold.rpt"]
    return [(n, (ctx.build / n).read_text(errors="replace")) for n in names if (ctx.build / n).is_file()]


def _logic_levels(ctx: Ctx) -> dict[str, Any]:
    """RPT-LL-01 (advisory): the logic-level distribution against each clock's requirement; RPT-LL-02 (gate): a setup path of the
    post-synthesis timing report that still fails with its net delay taken out."""
    from flow import report_gates as R
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    fs, parts, recs = [], {}, []
    t, p, why = _txt(ctx, "logic_levels")
    if t is not None:
        fs += R.logic_level_findings(R.parse_logic_levels(t))
        parts["logic_levels"] = "ran"
        recs.append(p)
    else:
        parts["logic_levels"] = "not run: " + why
    ts = ctx.build / "timing_summary_synth.rpt"
    if ts.is_file():
        fs += R.zero_net_delay_findings(ts.read_text(errors="replace"))
        parts["zero_net_delay"] = "ran"
        recs.append(ts)
    else:
        parts["zero_net_delay"] = "not run: no timing_summary_synth.rpt"
    return _result(fs, parts, recs)


def _clock_tree(ctx: Ctx) -> dict[str, Any]:
    """RPT-CLK-01 (advisory): cascaded global buffers and local clocks; RPT-CLK-02 (advisory): uncertainty and skew over the guide's
    review thresholds, on the timing paths of the scope."""
    from flow import report_gates as R
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    fs, parts, recs = [], {}, []
    u, up, why = _txt(ctx, "clock_utilization")
    util = R.parse_clock_utilization(u) if u is not None else None
    parts["clock_utilization"] = "ran" if u is not None else "not run: " + why
    n, np_, why2 = _txt(ctx, "clock_networks")
    nets = R.parse_clock_networks(n) if n is not None else None
    parts["clock_networks"] = "ran" if n is not None else "not run: " + why2
    fs += R.clock_tree_findings(util, nets)
    recs += [x for x in (up, np_) if x]
    tt = _timing_texts(ctx)
    parts["timing_paths"] = "ran" if tt else "not run: no timing report for this scope"
    for name, text in tt:
        fs += R.path_clock_findings(R.T.parse_paths(text), name)
        recs.append(ctx.build / name)
    return _result(fs, parts, recs)


def _fanout(ctx: Ctx) -> dict[str, Any]:
    """RPT-FO-01 (advisory): a high-fanout net against the clock frequency (UG949 p.75), with the guide's fixes."""
    from flow import report_gates as R
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    t, p, why = _txt(ctx, "high_fanout")
    if t is None:
        return _not_run(why)
    ts = ctx.build / "timing_summary_synth.rpt"
    clocks = R.parse_clock_summary(ts.read_text(errors="replace")) if ts.is_file() else []
    parts = {"high_fanout": "ran", "clock_summary": "ran" if clocks else "not run: no Clock Summary (fastest clock unknown)"}
    return _result(R.fanout_findings(R.parse_high_fanout(t), clocks), parts, [p])


def _synth_log(ctx: Ctx) -> dict[str, Any]:
    """RPT-LOG-01 / RPT-LOG-02 (advisory): the build's log (the flow's own vivado.log)."""
    from flow import report_gates as R
    log = ctx.build / "vivado.log"
    if ctx.scope == "rtl" or not log.is_file():
        return _not_run("no vivado.log for this build" if ctx.scope != "rtl" else "needs a build log (scope synth or route)")
    inp = ctx.build / "inputs.tcl"
    gens = R.build_generics(inp.read_text(errors="replace")) if inp.is_file() else None   # None: unknown, so every unused generic counts
    return _result(R.log_findings(log.read_text(errors="replace"), generics=gens), {"vivado.log": "ran"}, [log])


def _congestion(ctx: Ctx) -> dict[str, Any]:
    """RPT-CONG-01 / RPT-CONG-02 (advisory): congestion tables in the log and report_design_analysis -congestion, and the
    utilisation the guide ties to hard placement."""
    from flow import report_gates as R
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    fs, parts, recs = [], {}, []
    log = ctx.build / "vivado.log"
    tables = R.parse_placer_congestion(log.read_text(errors="replace")) if log.is_file() else []
    parts["vivado.log"] = "ran" if log.is_file() else "not run: no vivado.log"
    wins: list[dict[str, Any]] = []
    t, p, why = _txt(ctx, "congestion") if ctx.scope == "route" else (None, None, "congestion is read after place and route")
    if t is not None:
        wins = R.parse_congestion_report(t)
        recs.append(p)
    parts["congestion_report"] = "ran" if t is not None else "not run: " + why
    fs += R.congestion_findings(tables, wins)
    u, up, why2 = _txt(ctx, "utilization")
    parts["utilization"] = "ran" if u is not None else "not run: " + why2
    if u is not None:
        fs += R.utilization_findings(G_parse_util(u))
        recs.append(up)
    return _result(fs, parts, recs)


def G_parse_util(text: str) -> dict[str, Any]:
    from flow.gates import parse_utilization
    return parse_utilization(text)


def _ip_status(ctx: Ctx) -> dict[str, Any]:
    """RPT-IP-01 (gate): report_ip_status after synthesis, written by flow/build.tcl for a build whose session holds IP."""
    from flow import report_gates as R
    if ctx.scope == "rtl":
        return _not_run("needs a synthesised design (scope synth or route)")
    f = ctx.build / "ip_status_synth.rpt"
    if not f.is_file():
        return _not_run("no ip_status_synth.rpt (the build holds no IP, or predates brief 204a)")
    return _result(R.ip_status_findings(R.parse_ip_status(f.read_text(errors="replace"))), {"report_ip_status": "ran"}, [f])


def _ip_applies(design: Path) -> str | None:
    b = design / "build"
    if b.is_dir() and any(b.glob("*/ip_status_synth.rpt")):
        return None
    return "no IP status report in the build (the design has no IP, or its build predates brief 204a)"


def _fsm(ctx: Ctx) -> dict[str, Any]:
    """flow/fsm_coverage.py on the simulation traces (verif/fsm.yaml and the VCDs under build/verif/sim)."""
    from flow import fsm_coverage as F
    vcds = sorted((ctx.design / "build" / "verif").rglob("*.vcd")) if (ctx.design / "build" / "verif").is_dir() else []
    if not vcds:
        return _not_run("no VCD under build/verif (run the tests with FDA_FSM_VCD=1)")
    try:
        rep = F.evaluate(ctx.design, vcds)
    except (OSError, ValueError, KeyError) as e:
        return _not_run(f"{type(e).__name__}: {e}")
    fs = []
    for m in rep.get("fsms") or []:
        for s in m.get("unvisited_states") or []:
            fs.append({"tool": "fsm", "code": "FSM-STATE", "severity": "error", "where": f"{m.get('name')}:{s}",
                       "message": f"state {s} never visited", "blocking": True})
        for t in m.get("untaken_transitions") or []:
            fs.append({"tool": "fsm", "code": "FSM-TRANS", "severity": "error", "where": f"{m.get('name')}:{t}",
                       "message": f"transition {t} never taken", "blocking": True})
        for t in m.get("unlisted_transitions") or []:
            fs.append({"tool": "fsm", "code": "FSM-UNLISTED", "severity": "error", "where": f"{m.get('name')}:{t}",
                       "message": f"transition {t} taken but not in the state table", "blocking": True})
    if not rep.get("pass", True) and not fs:
        fs.append({"tool": "fsm", "code": "FSM-STATE", "severity": "error", "where": "verif/fsm.yaml",
                   "message": "FSM coverage failed (see the record)", "blocking": True})
    return _result(fs)


def _axi(ctx: Ctx) -> dict[str, Any]:
    """AMD AXI4-Lite IP next to our register blocks (flow/amd_ip_notes.py, brief 69): one warning per IP found, with
    the measured differences. Advice, not a failure. The missing-response rule (RESP_LOST) is raised in simulation by
    the protocol monitor axi_tx/rtl/axil_resp_rules.sv, not here."""
    from flow import amd_ip_notes as N
    r = N.scan([ctx.design])
    fs = []
    for name, info in sorted((r.get("ips") or {}).items()):
        fs.append({"tool": "axi", "code": "AXI-AMD-IP", "severity": "warning", "where": ", ".join(info.get("files", [])[:2]) or name,
                   "key": f"axi:AXI-AMD-IP {name}", "message": f"{info.get('ip', name)}: " + "; ".join(info.get("notes", [])[:3])[:300],
                   "blocking": False})
    return _result(fs)


def _axi_profile(ctx: Ctx) -> dict[str, Any]:
    """Every generated AXI4-Lite register block has the interface profile its design declares and behaves as it says
    (flow/checks/axi_profile.py, brief 73): the block's source map is resolved under the design's `interfaces:`, the RTL
    regenerated and compared with the file."""
    from flow.checks import axi_profile as AP
    from flow import sources
    fs = AP.run_checks(ctx.design, ctx.root)
    parts: dict[str, str] = {}
    ifs, _ = AP.interfaces(ctx.design)
    unread = sources.no_reader(sources.vhdl_files(build_sources(ctx.design, ctx.root)), {"sv"}, "axi_profile (generated register blocks)") if ifs is not None else None
    if unread:                                          # the generator emits SystemVerilog only, so a VHDL register block has no claim to compare
        parts = {"generated_sv_blocks": "ran", "vhdl_register_logic": "not run: " + unread}
    return _result(fs, parts, records=[p for p in (ctx.design / "spec.yaml",) if p.is_file()])


def _axi_profile_applies(design: Path) -> str | None:
    from flow.checks import axi_profile as AP
    return AP.applies(design, ROOT)


def _link(design: Path) -> tuple[dict[str, Any] | None, str]:
    """The design's link section: spec.yaml ``link:`` (agent designs) or link_spec.yaml (hand-built, brief 56A)."""
    for name in ("spec.yaml", "link_spec.yaml"):
        try:
            spec = yaml.safe_load((design / name).read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(spec, dict) and isinstance(spec.get("link"), dict):
            return spec["link"], name
    return None, "no link: section in spec.yaml or link_spec.yaml (no transceiver link)"


def _gt(ctx: Ctx) -> dict[str, Any]:
    """The transceiver link plan (flow/gt_plan.py, brief 56A): every reason the design's link cannot be built."""
    from flow import gt_plan as gp
    link, src = _link(ctx.design)
    if link is None:
        return _not_run(src)
    try:
        build = yaml.safe_load((ctx.design / "build.yaml").read_text()) or {}
        board = yaml.safe_load((ctx.root / "boards" / str(build.get("board") or "kr260") / "board.yaml").read_text())
    except (OSError, yaml.YAMLError) as e:
        return _not_run(f"board: {e}")
    r = gp.plan(link, board, board.get("part"))
    fs = [{"tool": "gt", "code": "GT-PLAN", "severity": "error", "where": f"{src} link", "key": f"gt:GT-PLAN {i}",
           "message": str(p)[:300], "blocking": True} for i, p in enumerate(r.get("problems") or [])]
    return _result(fs, records=[ctx.design / src])


def _gt_applies(design: Path) -> str | None:
    return None if _link(design)[0] is not None else _link(design)[1]


def _doc(ctx: Ctx) -> dict[str, Any]:
    """The DOC gate (brief 68 part C, agent/graph/document.py ``doc_gate``): flow.handover's problems and stale claims,
    required gaps, unwritten prose, over-claims and contradictions. The DOC step calls this check, so the gate and the
    tool agree. Without the agent package (a bare flow checkout) it falls back to flow.handover.problems."""
    try:
        from agent.graph.document import doc_gate
        probs = doc_gate(ctx.design, ctx.cache.get("doc_required", []))
    except ImportError:
        from flow import handover as H
        p, st = H.problems(ctx.design)
        probs = p + st
    fs = [{"tool": "doc", "code": "DOC-PROBLEM", "severity": "error", "where": "handover.yaml", "key": f"doc:DOC-PROBLEM {i}",
           "message": p, "blocking": True} for i, p in enumerate(probs)]
    return _result(fs, records=[ctx.design / "handover.yaml"])


def _doc_applies(design: Path) -> str | None:
    return None if (design / "handover.yaml").is_file() else "no handover.yaml (the DOC step writes it at the end of a run)"


def _fsm_applies(design: Path) -> str | None:
    return None if (design / "verif" / "fsm.yaml").is_file() else "no verif/fsm.yaml (the design declares no state machine to cover)"


def _constants(ctx: Ctx) -> dict[str, Any]:
    """The derived-constants gate (brief 106, flow/derived_constants.py): the shell design ID derived from the spec's quoted
    string, spec identity words, and the board clock period, each checked against the RTL and the XDC."""
    from flow import derived_constants as DC
    t = DC.derive(ctx.design, ctx.root)
    out = ctx.design / "build" / "derived_constants.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(t, indent=1) + "\n")
    fs = [{"tool": "constants", "code": f["code"], "severity": f["severity"], "where": f["where"], "key": f"constants:{f['code']} {f['where']}",
           "message": f["message"], "blocking": f["blocking"]} for f in t["findings"]]
    parts = {"design_id": "not run: " + "; ".join(t["not_read"][:2])} if t.get("not_read") else {}
    if parts:
        parts["spec_literals_and_clock"] = "ran"
    return _result(fs, parts, records=[out])


def _stale(ctx: Ctx) -> dict[str, Any]:
    """The stale-data check (brief 106, flow/stale_check.py): a build or simulation result whose inputs changed since, and a
    document that cites a build that is not the current one. A design with no build and no stamp has nothing to compare."""
    from flow import stale_check as SC
    fs = [{"tool": "stale", "code": f["code"], "severity": f["severity"], "where": f["where"], "key": f"stale:{f['code']} {f['where']}",
           "message": f["message"], "blocking": f["blocking"]} for f in SC.findings(ctx.design, ctx.root)]
    return _result(fs, records=[ctx.design / "build" / "lineage.json"])


ALL = ("rtl", "synth", "route")
POST = ("synth", "route")
register(Check("lint", "source", ALL, {"verilator": ("*",)},
               "Verilator --lint-only -Wall (in a session: the lint tool, with Icarus elaboration and the top-port rules)", _lint))
register(Check("standards", "source", ALL, {"standards": ("*",)},
               "the design-standards checker (flow/standards_check.py; post-synthesis rules at synth/route)", _standards))
register(Check("resets", "vivado", ALL, {"resets": ("RST-ASYNC-01", "RST-POL-01", "RST-POL-02", "RST-DSPRAM-01", "RST-CDC-01",
                                                    "RST-LUT-01", "RST-IP-01"),
                                         "vivado": ("LUTAR-1", "DPIR-1", "DPIR-2", "DPIR-3", "DPOR-1", "DPOR-2", "DPOR-3", "REQP-1840",
                                                    "RMIR-1", "RMOR-1", "RROR-1", "ROAS-1", "CDC-7", "CDC-8")},
               "the house reset rules: AMD's LUTAR/DPIR/DPOR/RMIR/RMOR/RROR/ROAS and report_cdc reset rows, plus our source "
               "scan and netlist scan (flow/checks/resets.py)", _resets, reports=("methodology", "drc", "cdc", "reset_scan"),
               waivable=False))
register(Check("cdc", "records", POST, {"vivado": ("CDC-*",), "cdc_structure": ("U*",)},
               "report_cdc (Critical rows fail) and the structural CDC check after synthesis (flow/cdc_structure.py)", _cdc,
               reports=("cdc",), amd=True, gate_mirror=True))
register(Check("methodology", "records", ALL, {"vivado": ("*",)},
               "report_methodology: Critical Warnings fail (as the stage gates), Warnings listed",
               _rows_check("methodology", None, _crit), reports=("methodology",), amd=True, gate_mirror=True))
register(Check("drc", "records", POST, {"vivado": ("*",)},
               "report_drc: Errors and Critical Warnings fail (as the stage gates); CFGBVS-1/2 also fail on a board whose configuration voltage is "
               "confirmed (brief 105A)", _drc, reports=("drc",), amd=True, gate_mirror=True))
register(Check("exceptions", "records", POST, {"exceptions": ("EXC-*",)},
               "timing exceptions (flow/exceptions_check.py: ignored, covering no path, dropped by an XDC message)",
               _gate_backed("exceptions"), gate_mirror=True))
register(Check("io", "records", POST, {"io": ("IO-*", "IOB-*")},
               "I/O timing constraints (flow/io_check.py: invented delays, -min/-max from the data sheet, IOB packing) and the I/O-block "
               "packing of every marked register with Vivado's reason (flow/iob_check.py, brief 129)",
               _gate_backed("io"), gate_mirror=True))
register(Check("clocking", "vivado", POST, {"vivado": ("CLKC-*",), "clocking": ("CMT-RANGE-01",)},
               "AMD's CLKC methodology rows and the MMCM/PLL VCO and PFD range check (flow/cmt_check.tcl)", _clocking,
               reports=("methodology", "cmt")))
register(Check("clock_mux", "vivado", POST, {"clock_mux": ("CLKMUX-LUT", "CLKMUX-NO-GROUPS", "CLKMUX-SRC-GROUPED", "CLKMUX-CASE",
                                                       "CLKMUX-CE-SELECT", "CLKMUX-STOP", "CLKMUX-CASCADE", "CLKMUX-UNTRACED")},
               "clock multiplexers (brief 208, flow/clock_mux_check.py): a LUT on a clock path, mux modes timed against each other, "
               "clock groups on the source clocks that hide real paths, and advisories (case-analysed select, CE select, stoppable "
               "input with IGNORE tied, deep cascade)", _clock_mux, reports=("clock_mux", "clock_interaction")))
register(Check("xpm_sim", "source", ALL, {"xpm_sim": ("XPM-SIM-01",)},
               "advisory: an xpm_cdc instance whose SIM_ASSERT_CHK is not 1, which turns off the macro's own simulation warnings "
               "(flow/constraint_gates.py, brief 105A)", _xpm_sim))
register(Check("fastpath", "source", ALL, {"fastpath": ("FAST-SHIFT-01", "FAST-INDEX-01")},
               "advisory (brief 190): a data-dependent shift or index of a wide vector (a barrel shifter) in a module declared fast-path "
               "(flow/checks/wide_index.py)", _fastpath))
register(Check("constraint_scope", "records", ("route",), {"constraint_scope": ("XDC-ASYNC-PATHS", "XDC-ASYNC-ALL")},
               "advisory flag for owner review: set_clock_groups -asynchronous over clock pairs with paths between them, or over every clock "
               "(flow/constraint_gates.py, brief 105A); never blocks", _async_groups, reports=("clock_interaction",)))
register(Check("cdc_margin", "records", ("route",), {"cdc_margin": ("CDCM-SKEW-VIOL", "CDCM-SKEW-MISSING", "CDCM-DPO-LOOSE",
                                                                  "CDCM-MTBF-MISSING", "CDCM-MTBF-LOW", "CDCM-UNC-HIGH")},
               "clock-crossing intent constrained and met (flow/cdc_margin.py, brief 207): a set_bus_skew violation blocks (gate "
               "post_route_bus_skew_met); missing bus skew, a loose datapath-only value, MTBF (UltraScale+) and user uncertainty are advisory",
               _cdc_margin, gate_mirror=True))
register(Check("dsp_ram_mapping", "records", POST, {"vivado": ("DPIP-*", "DPOP-*", "SYNTH-*", "RBOR-*", "DPIR-*", "DPOR-*",
                                                              "RMIR-*", "RMOR-*", "RROR-*")},
               "DSP and block-RAM mapping advice (AMD DPIP/DPOP/SYNTH/RBOR rows) and their utilisation", _dsp_ram,
               reports=("methodology", "drc", "utilization"), amd=True))
register(Check("dsp_regs", "records", POST, {"dsp_regs": ("DSPREG-01", "DSPREG-02", "DSPREG-03", "DSPREG-04")},
               "advisory (brief 185): a DSP slice with no multiplier or output register at a period the measured limits say it cannot meet, a period "
               "below the slice's own minimum, and AMD's DPIP/DPOP rows (flow/dsp_regs_check.py)", _dsp_regs, reports=("timing_summary", "drc"), applies=_dsp_regs_applies))   # dsp_cells is written by flow/build.tcl, never by the Vivado session
register(Check("init_values", "vivado", POST, {"init_values": ("INIT-HB-01", "INIT-URAM-01")},
               "initial values that cost a hard block's register on AMD parts (brief 206): INIT = 1 registers wired to a DSP, "
               "RAM or FIFO (our netlist scan) and UltraRAM refused for initial contents (Synth 8-12183); advisory "
               "(flow/checks/init_values.py)", _init_values, reports=("init_scan",)))
register(Check("control_sets", "vivado", POST, {"vivado": ("ULMTCS-*",), "control_sets": ("RPT-CS-01", "RPT-CS-02")},
               "report_control_sets (count of unique control sets), AMD's ULMTCS rows and the three bands of UG949 Table 17 (7.5 % and 15 % of "
               "CLB registers / 8: reduction recommended, then required; brief 204a)", _control_sets,
               reports=("control_sets", "methodology", "utilization"), amd=True))
register(Check("logic_levels", "records", POST, {"logic_levels": ("RPT-LL-01", "RPT-LL-02")},
               "logic levels against the clock period (advisory, UG949 p.75/p.234) and a setup path that fails even with no net delay "
               "(gate, UG949 p.200); flow/report_gates.py, brief 204a", _logic_levels, reports=("logic_levels",), amd=True))
register(Check("clock_tree", "records", POST, {"clock_tree": ("RPT-CLK-01", "RPT-CLK-02")},
               "cascaded global buffers and local clocks (UG949 p.111/p.139) and clock uncertainty and skew over the review thresholds "
               "(p.232/p.248); advisory; brief 204a", _clock_tree, reports=("clock_utilization", "clock_networks"), amd=True))
register(Check("fanout", "records", POST, {"fanout": ("RPT-FO-01",)},
               "high-fanout nets against the clock frequency (UG949 p.75 table), with the guide's fixes; advisory; brief 204a", _fanout,
               reports=("high_fanout",), amd=True))
register(Check("synth_log", "records", POST, {"synth_log": ("RPT-LOG-01", "RPT-LOG-02", "RPT-LOG-03")},
               "synthesis messages that say logic was dropped, messages the tool switched off at its 100-message limit (UG949 p.198) "
               "(advisory), and a generic the build sets that the top does not have (gate, brief 203); brief 204a", _synth_log))
register(Check("congestion", "records", POST, {"congestion": ("RPT-CONG-01", "RPT-CONG-02")},
               "placer and router congestion level 4 or above, short-interconnect share, and utilisation the guide ties to hard placement "
               "(UG949 p.240/p.273, UG1292 p.6); advisory; brief 204a", _congestion, reports=("congestion", "utilization"), amd=True))
register(Check("ip_status", "records", POST, {"ip_status": ("RPT-IP-01",)},
               "report_ip_status: IP locked or not up to date fails (UG949 p.49); brief 204a", _ip_status, applies=_ip_applies, amd=True))
register(Check("fsm", "records", ALL, {"fsm": ("FSM-STATE", "FSM-TRANS", "FSM-UNLISTED")},
               "FSM state and transition coverage from the simulation traces (flow/fsm_coverage.py)", _fsm, applies=_fsm_applies))
register(Check("axi", "source", ALL, {"axi": ("AXI-AMD-IP",)},
               "AMD AXI4-Lite IP beside our register blocks: the measured differences (flow/amd_ip_notes.py, brief 69)", _axi))
register(Check("axi_profile", "source", ALL, {"axi_profile": ("AXI-PROFILE-SPEC", "AXI-PROFILE-MISMATCH", "AXI-PROFILE-DRIFT", "AXI-PROFILE-MIX",
                                                         "AXI-PROFILE-STALE", "AXI-PROFILE-NOSRC", "AXI-PROFILE-OVERRIDE",
                                                         "AXI-PROFILE-AMD-STRICT")},
               "AXI4-Lite interface profiles (brief 73): each generated register block is what its map generates under the "
               "design's declared profile; mixed profiles and AMD IP behind a strict region are flagged",
               _axi_profile, applies=_axi_profile_applies))
register(Check("gt_plan", "source", ALL, {"gt": ("GT-PLAN",)},
               "the transceiver link plan (flow/gt_plan.py, brief 56A): every reason the link cannot be built", _gt,
               applies=_gt_applies))
register(Check("constants", "source", ALL, {"constants": ("CONST-ID-01", "CONST-ID-02", "CONST-LIT-01", "CONST-CLK-01")},
               "constants derived by code from the spec and the board file (design ID, identity words, clock period) against the RTL and XDC "
               "(flow/derived_constants.py, brief 106)", _constants))
register(Check("stale", "records", POST, {"stale": ("STALE-EVID-01", "STALE-CLAIM-01")},
               "build and simulation evidence whose inputs changed since it was made, and documents citing a build that is not current "
               "(flow/stale_check.py, brief 106)", _stale, waivable=False))
register(Check("doc", "records", ALL, {"doc": ("DOC-PROBLEM",)},
               "the DOC gate (brief 68: flow/handover.py problems, required gaps, over-claims)", _doc, applies=_doc_applies,
               waivable=False))

#: the Vivado-session reports each check may need (the ones the build does not write)
SESSION_ONLY = ("reset_scan", "cmt", "control_sets", "qor_suggestions", "init_scan", "logic_levels", "clock_utilization", "clock_networks", "congestion", "clock_mux")


# ---- the runner ----------------------------------------------------------------------------------------------------
def latest_scope(design: Path, variant: str = "base") -> str:
    b = design / "build" / variant
    if (b / "timing_summary.rpt").is_file():
        return "route"
    if (b / "timing_summary_synth.rpt").is_file():
        return "synth"
    return "rtl"


def select(names: list[str] | str, scope: str, design: Path) -> tuple[list[str], dict[str, str]]:
    """(checks to run, {check: why skipped}). ``all``: every check whose scopes include ``scope`` and that applies."""
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]
    skipped: dict[str, str] = {}
    if not names or names == ["all"]:
        chosen = [n for n, c in CHECKS.items() if scope in c.scopes]
        for n in list(chosen):
            why = CHECKS[n].applies(design) if CHECKS[n].applies else None
            if why:
                chosen.remove(n)
                skipped[n] = why
        return chosen, skipped
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        raise KeyError(f"unknown check(s) {unknown}; known: {sorted(CHECKS)}")
    return list(dict.fromkeys(names)), skipped


def _finish(name: str, raw: dict[str, Any], rs: dict[str, Any], waivers: list[dict[str, Any]], bad_waivers: list[str]) -> dict[str, Any]:
    from flow.lint_ruleset import rule_for
    from flow.traceability import match_item
    if not CHECKS[name].waivable:
        waivers = []
    by_id = {r["id"]: r for r in rs["rules"]}
    if raw.get("status") == "not_run":
        return {"check": name, **raw}
    fs = []
    for f in raw["findings"]:
        rid = f.get("rule") or rule_for(rs, f["tool"], f["code"])
        rule = by_id.get(rid, {})
        key = f.get("key") or f"{f['tool']}:{f['code']} {f.get('where', '')}"
        w = next((w for w in waivers if w["rule"] == rid and match_item(key, str(w["match"]))), None)
        fs.append({"rule": rid, "tool": f["tool"], "code": f["code"], "severity": f.get("severity", ""),
                   "where": f.get("where", ""), "key": key, "message": f.get("message", ""),
                   "fix": f.get("fix") or rule.get("fix", ""), "skill": rule.get("skill", ""),
                   "blocking": bool(f.get("blocking", True)), "count": f.get("count", 1),
                   **({"cost": f["cost"]} if f.get("cost") else {}),
                   **({"waived": {"reason": w["reason"], "owner": w["owner"], "date": str(w["date"])}} if w else {})})
    open_ = [f for f in fs if f["blocking"] and ("waived" not in f or CHECKS[name].gate_mirror)]
    for f in fs:
        if CHECKS[name].gate_mirror and f["blocking"] and "waived" in f:
            f["waived"]["note"] = "the stage gate still fails on it"
    parts = raw.get("parts") or {}
    incomplete = [k for k, v in parts.items() if v != "ran"]
    verdict = raw.get("verdict")
    status = "fail" if open_ or verdict is False else "pass"
    if status == "pass" and parts and not any(v == "ran" for v in parts.values()):
        status = "not_run"
    return {"check": name, "status": status, "incomplete": incomplete, "parts": parts, "findings": fs,
            "records": raw.get("records", []), "why": raw.get("why", "")}


def doc_gate(design: Path, required: list[str]) -> list[str]:
    """The DOC gate through the registry (agent/graph/document.py's DOC step calls this): the problem texts, unchanged."""
    r = run_one("doc", design, "rtl", required=required)
    if r["status"] == "not_run":
        return [r.get("why") or "the doc check did not run"]
    return [f["message"] for f in r["findings"] if f["blocking"]]


def run_one(name: str, design: Path, scope: str, variant: str = "base", root: Path = ROOT,
            required: list[str] | None = None) -> dict[str, Any]:
    """One check's finished result, with no Vivado session and no report file: what a sign-off gate calls (flow/gates.py
    post_synth_resets_clean, the DOC gate), so a finding means the same at sign-off as in the Designer's loop."""
    from flow.lint_ruleset import load_waivers
    design = Path(design).resolve()
    ctx = Ctx(design, scope, variant, root)
    if required is not None:
        ctx.cache["doc_required"] = list(required)
    waivers, bad = load_waivers(design)
    try:
        raw = CHECKS[name].run(ctx)
    except Exception as e:
        raw = _not_run(f"internal error: {type(e).__name__}: {e}")
    return _finish(name, raw, rules(), waivers, bad)


def run(design: Path, names: list[str] | str = "all", scope: str = "auto", level: str = "summary", variant: str = "base",
        root: Path = ROOT, lint: Callable[[], dict[str, Any]] | None = None,
        vivado: Callable[[Path, Path, list[str]], tuple[int, str]] | None = None,
        cmd: Callable[[str, list[str], int], int] | None = None) -> dict[str, Any]:
    """Run the named checks; write the full result to ``build/checks/<variant>/<scope>.json``; return it with the
    digest text under ``digest``."""
    from flow.lint_ruleset import load_waivers
    design = Path(design).resolve()
    t0 = time.monotonic()
    if scope == "auto":
        scope = latest_scope(design, variant)
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES} or auto")
    if level not in LEVELS:
        raise ValueError(f"level must be one of {tuple(LEVELS)}")
    ctx = Ctx(design, scope, variant, root, level, lint, vivado, cmd)
    chosen, skipped = select(names, scope, design)
    # one Vivado session for every report the chosen checks need and the build did not write
    need = sorted({r for n in chosen for r in CHECKS[n].reports if ctx.report(r) is None and
                   (r in SESSION_ONLY or r in BUILD_FILES)}) if scope != "rtl" else []
    vivado_ran = None
    if need:
        dcp = ctx.build / DCP[scope]
        if vivado is None:
            ctx.cache["vivado_why"] = f"needs Vivado ({', '.join(need)}) and Vivado may not run here (--vivado never or no session hook)"
        elif not dcp.is_file():
            ctx.cache["vivado_why"] = f"no checkpoint {dcp.relative_to(design)} (build until={'synth' if scope == 'synth' else 'route'} first)"
        else:
            ctx.out.mkdir(parents=True, exist_ok=True)
            for r in need:                                  # never mix a new session's files with an old one's
                for ext in ("rpt", "tsv", "not_run.txt"):
                    (ctx.out / f"{r}.{ext}").unlink(missing_ok=True)
            rc, text = vivado(dcp, ctx.out, need)
            vivado_ran = {"reports": need, "rc": rc, "tail": text[-400:]}
            if rc != 0:
                ctx.cache["vivado_why"] = f"the Vivado session failed (rc {rc}): {text.strip()[-200:]}"
    rs = rules()
    waivers, bad = load_waivers(design)
    source = [n for n in chosen if CHECKS[n].kind == "source"]
    others = [n for n in chosen if n not in source]
    results: dict[str, dict[str, Any]] = {}

    def one(n: str) -> tuple[str, dict[str, Any]]:
        try:
            raw = CHECKS[n].run(ctx)
        except Exception as e:                    # a checker bug is reported as not run, never as a pass
            if type(e).__name__ == "SecurityError":           # a session refusal (agent.core.security) stays a refusal
                raise
            raw = _not_run(f"internal error: {type(e).__name__}: {e}")
        return n, _finish(n, raw, rs, waivers, bad)
    with ThreadPoolExecutor(max_workers=4) as ex:            # source checks are independent: run them concurrently
        for n, r in ex.map(one, source):
            results[n] = r
    for n in others:
        results[n] = one(n)[1]
    for r in results.values():                    # record paths relative to the design (the report is portable)
        r["records"] = [_relp(Path(x), design) for x in r.get("records") or []]
    order = [n for n in chosen]
    rep = {"design": design.name, "scope": scope, "variant": variant, "level": level, "standard": rs["standard"],
           "version": rs["version"], "checks": [results[n] for n in order], "skipped": skipped, "vivado": vivado_ran,
           "bad_waivers": bad, "seconds": round(time.monotonic() - t0, 2),
           "extra": {k: ctx.cache[k] for k in ("control_sets", "dsp_ram_util") if k in ctx.cache}}
    rep["pass"] = all(r["status"] == "pass" and not r.get("incomplete") for r in rep["checks"]) and not bad
    out = design / "build" / "checks" / variant / f"{scope}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str) + "\n")
    try:
        rep["report_path"] = out.relative_to(design).as_posix()
    except ValueError:
        rep["report_path"] = str(out)
    rep["digest"] = digest(rep, level)
    return rep


def _relp(p: Path, design: Path) -> str:
    try:
        return p.resolve().relative_to(design).as_posix()
    except ValueError:
        try:
            return p.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return p.name


def digest(rep: dict[str, Any], level: str = "summary") -> str:
    """The compact text the caller sees: a verdict line, one line per check, then up to LEVELS[level] findings per check."""
    n = LEVELS[level]
    cs = rep["checks"]
    cnt = {s: sum(1 for c in cs if c["status"] == s) for s in ("pass", "fail", "not_run")}
    part = sum(1 for c in cs if c["status"] == "pass" and c.get("incomplete"))
    head = (f"checks {'PASS' if rep['pass'] else 'FAIL' if cnt['fail'] else 'INCOMPLETE'} at scope {rep['scope']} "
            f"({rep['variant']}): {cnt['pass'] - part} pass, {part} partial, {cnt['fail']} fail, {cnt['not_run']} not run. "
            f"Full report: {rep.get('report_path', '')}")
    lines = [head]
    for c in cs:
        fs = c.get("findings") or []
        blocking = [f for f in fs if f["blocking"] and "waived" not in f]
        rules_ = sorted({f["rule"] for f in blocking})
        extra = ""
        if c["status"] == "not_run":
            extra = f": {c.get('why', '')[:160]}"
        else:
            bits = []
            if blocking:
                bits.append(f"{len(blocking)} blocking ({', '.join(rules_[:4])})")
            adv = len([f for f in fs if not f["blocking"]])
            if adv:
                bits.append(f"{adv} advisory")
            w = len([f for f in fs if "waived" in f])
            if w:
                bits.append(f"{w} waived")
            if c.get("incomplete"):
                bits.append("not run: " + "; ".join(f"{k} ({c['parts'][k][9:130] if c['parts'][k].startswith('not run: ') else c['parts'][k]})"
                                                    for k in c["incomplete"]))
            extra = (": " + "; ".join(bits)) if bits else ""
        label = "PARTIAL" if c["status"] == "pass" and c.get("incomplete") else c["status"].upper()
        lines.append(f"{label:8} {c['check']}{extra}")
        if n:
            shown = sorted(fs, key=lambda f: (not f["blocking"], "waived" in f))[:n]
            for f in shown:
                tag = "waived" if "waived" in f else ("" if f["blocking"] else "advisory")
                lines.append(f"  {f['rule']} {f['code']} {f['where'][:70]}{' [' + tag + ']' if tag else ''}: {f['message'][:160]}"
                             + (f" | fix: {f['fix'][:140]}" if f.get("fix") and f["blocking"] else "")
                             + (f" | {f['cost'][:150]}" if f.get("cost") and f["blocking"] else "")
                             + (f" | skill: {f['skill']}" if f.get("skill") else ""))
            if len(fs) > n:
                lines.append(f"  ... {len(fs) - n} more in the full report")
    if rep.get("skipped"):
        lines.append("not applicable: " + "; ".join(f"{k} ({v[:60]})" for k, v in rep["skipped"].items()))
    for b in rep.get("bad_waivers") or []:
        lines.append(f"BAD waiver: {b}")
    return "\n".join(lines)


def cli_vivado(dcp: Path, out: Path, names: list[str]) -> tuple[int, str]:
    import subprocess
    r = subprocess.run([str(ROOT / "flow" / "checks" / "run_vivado_checks.sh"), str(dcp), str(out), ",".join(names)],
                       capture_output=True, text=True, timeout=3600)
    return r.returncode, (r.stdout or "") + (r.stderr or "")
