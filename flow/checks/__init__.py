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
}
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
        for ext in ("rpt", "tsv"):
            p = self.out / f"{name}.{ext}"
            if p.is_file():
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
    import glob
    try:
        b = yaml.safe_load((design / "build.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return sorted(design.glob("rtl/*.sv")) + sorted(design.glob("rtl/*.v"))
    return [Path(f) for g in b.get("sources") or [] for f in sorted(glob.glob(str(root / g)))]


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
    from flow.lint_ruleset import verilator_findings
    vf, note = verilator_findings(ctx.design)
    if vf is None:
        return _not_run(note)
    fs = [{"tool": "verilator", "code": f["code"], "severity": f["severity"], "where": f["key"].split(" ", 1)[-1],
           "key": f["key"], "message": f["message"], "blocking": True} for f in vf]
    return _result(fs)


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
    return _result(fs, records=[out])


def _resets(ctx: Ctx) -> dict[str, Any]:
    from flow.checks import resets as R
    cfg = R.reset_config(ctx.design)
    parts: dict[str, str] = {}
    fs = []
    srcs = [p for p in build_sources(ctx.design, ctx.root) if p.suffix in (".sv", ".v")]
    if srcs:
        fs += R.source_findings(ctx.design, srcs, cfg)
        parts["source"] = "ran"
    else:
        parts["source"] = "not run: no SystemVerilog sources (a VHDL design is checked by the netlist part)"
    records = []
    if ctx.scope == "rtl":
        parts["amd"] = parts["netlist"] = "not run: scope rtl (needs a synthesised design)"
    else:
        meth, drc, cdc = ctx.report("methodology"), ctx.report("drc"), ctx.report("cdc")
        if meth or drc or cdc:
            for r in R.amd_findings(_parse_rules(meth), _parse_rules(drc), _parse_cdc(cdc), GATE_STAGE[ctx.scope]):
                rule = r["code"]
                fs.append({**r, "key": f"vivado:{rule}@{GATE_STAGE[ctx.scope]}",
                           "blocking": r["severity"].lower() not in ("advisory", "info")})
            parts["amd"] = "ran"
            records += [meth, drc, cdc]
        else:
            parts["amd"] = "not run: " + ctx.not_run_reason("methodology")
        scan = ctx.report("reset_scan")
        if scan:
            ips = {p.stem for p in (ctx.build / "ip").glob("*") if p.is_dir()} if (ctx.build / "ip").is_dir() else set()
            fs += [{**f, "key": f"resets:{f['code']} {f['where']}", "blocking": True}
                   for f in R.netlist_findings(R.read_scan(scan), cfg, ips)]
            parts["netlist"] = "ran"
            records.append(scan)
        else:
            parts["netlist"] = "not run: " + ctx.not_run_reason("reset_scan")
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
        if r is None and "x" not in g:
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
        return {**_result(fs), "verdict": g.get("x")}
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
    if u:
        from flow.gates import parse_utilization
        used = parse_utilization(u.read_text(errors="replace"))
        ctx.cache["dsp_ram_util"] = {k: v for k, v in used.items() if any(x in k.upper() for x in ("DSP", "RAMB", "BLOCK RAM"))}
        recs.append(u)
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
    return _result(fs, records=[p])


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
    for name, info in sorted((r.get("found") or {}).items()):
        fs.append({"tool": "axi", "code": "AXI-AMD-IP", "severity": "warning", "where": ", ".join(info.get("files", [])[:2]) or name,
                   "key": f"axi:AXI-AMD-IP {name}", "message": f"{info.get('ip', name)}: " + "; ".join(info.get("notes", [])[:3])[:300],
                   "blocking": False})
    return _result(fs)


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


ALL = ("rtl", "synth", "route")
POST = ("synth", "route")
register(Check("lint", "source", ALL, {"verilator": ("*",)},
               "Verilator --lint-only -Wall (in a session: the lint tool, with Icarus elaboration and the top-port rules)", _lint))
register(Check("standards", "source", ALL, {"standards": ("*",)},
               "the design-standards checker (flow/standards_check.py; post-synthesis rules at synth/route)", _standards))
register(Check("resets", "vivado", ALL, {"resets": ("RST-ASYNC-01", "RST-POL-01", "RST-POL-02", "RST-DSPRAM-01", "RST-CDC-01",
                                                    "RST-LUT-01"),
                                         "vivado": ("LUTAR-1", "DPIR-1", "DPIR-2", "DPIR-3", "DPOR-1", "DPOR-2", "DPOR-3",
                                                    "RMIR-1", "RMOR-1", "RROR-1", "ROAS-1", "CDC-7", "CDC-8")},
               "the house reset rules: AMD's LUTAR/DPIR/DPOR/RMIR/RMOR/RROR/ROAS and report_cdc reset rows, plus our source "
               "scan and netlist scan (flow/checks/resets.py)", _resets, reports=("methodology", "drc", "cdc", "reset_scan"),
               waivable=False))
register(Check("cdc", "records", POST, {"vivado": ("CDC-*",), "cdc_structure": ("U*",)},
               "report_cdc (Critical rows fail) and the structural CDC check after synthesis (flow/cdc_structure.py)", _cdc,
               reports=("cdc",), amd=True))
register(Check("methodology", "records", ALL, {"vivado": ("*",)},
               "report_methodology: Critical Warnings fail (as the stage gates), Warnings listed",
               _rows_check("methodology", None, _crit), reports=("methodology",), amd=True))
register(Check("drc", "records", POST, {"vivado": ("*",)}, "report_drc: Errors and Critical Warnings fail (as the stage gates)",
               _rows_check("drc", None, _err_or_crit), reports=("drc",), amd=True))
register(Check("exceptions", "records", POST, {"exceptions": ("EXC-*",)},
               "timing exceptions (flow/exceptions_check.py: ignored, covering no path, dropped by an XDC message)",
               _gate_backed("exceptions")))
register(Check("io", "records", POST, {"io": ("IO-*",)},
               "I/O timing constraints (flow/io_check.py: invented delays, -min/-max from the data sheet, IOB packing)",
               _gate_backed("io")))
register(Check("clocking", "vivado", POST, {"vivado": ("CLKC-*",), "clocking": ("CMT-RANGE-01",)},
               "AMD's CLKC methodology rows and the MMCM/PLL VCO and PFD range check (flow/cmt_check.tcl)", _clocking,
               reports=("methodology", "cmt")))
register(Check("dsp_ram_mapping", "records", POST, {"vivado": ("DPIP-*", "DPOP-*", "SYNTH-*", "RBOR-*", "DPIR-*", "DPOR-*",
                                                              "RMIR-*", "RMOR-*", "RROR-*")},
               "DSP and block-RAM mapping advice (AMD DPIP/DPOP/SYNTH/RBOR rows) and their utilisation", _dsp_ram,
               reports=("methodology", "drc", "utilization"), amd=True))
register(Check("control_sets", "vivado", POST, {"vivado": ("ULMTCS-*",)},
               "report_control_sets (count of unique control sets) and AMD's ULMTCS rows", _control_sets,
               reports=("control_sets", "methodology"), amd=True))
register(Check("fsm", "records", ALL, {"fsm": ("FSM-STATE", "FSM-TRANS", "FSM-UNLISTED")},
               "FSM state and transition coverage from the simulation traces (flow/fsm_coverage.py)", _fsm, applies=_fsm_applies))
register(Check("axi", "source", ALL, {"axi": ("AXI-AMD-IP",)},
               "AMD AXI4-Lite IP beside our register blocks: the measured differences (flow/amd_ip_notes.py, brief 69)", _axi))
register(Check("gt_plan", "source", ALL, {"gt": ("GT-PLAN",)},
               "the transceiver link plan (flow/gt_plan.py, brief 56A): every reason the link cannot be built", _gt,
               applies=_gt_applies))
register(Check("doc", "records", ALL, {"doc": ("DOC-PROBLEM",)},
               "the DOC gate (brief 68: flow/handover.py problems, required gaps, over-claims)", _doc, applies=_doc_applies,
               waivable=False))

#: the Vivado-session reports each check may need (the ones the build does not write)
SESSION_ONLY = ("reset_scan", "cmt", "control_sets", "qor_suggestions")


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
                   **({"waived": {"reason": w["reason"], "owner": w["owner"], "date": str(w["date"])}} if w else {})})
    open_ = [f for f in fs if f["blocking"] and "waived" not in f]
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
