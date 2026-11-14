"""The reset check (brief 71): the house reset rules, from AMD's reports first and our own netlist scan for the rest.

House rule (owner, 2026-11-13; fpga_agent_house_rules.md): resets are synchronous. An asynchronous reset appears only in
a reset or CDC synchroniser (asynchronous assert, synchronous release, as XPM does) or where an external device's reset is
asynchronous. The rules, their rationale and the waiver policy are in ``flow/hdl_rules.yaml`` (HDL-RST-01 to HDL-RST-05);
the background and the fixes are in the KB skills ``reset-strategy`` and ``control-sets-resets-and-enables``.

Three parts, each reported separately (a part that cannot run says why; the check is never a pass on a part that did not
run):

- **source**: the SystemVerilog sources (build.yaml), read with the design-standards scanner. RST-ASYNC-01: an edge
  signal besides the clock in a sequential block, outside a recognised synchroniser module. RST-POL-02: one module tests
  the same reset signal in both polarities.
- **amd**: AMD's own rule rows from the stage's ``report_methodology``, ``report_drc`` and ``report_cdc`` (Vivado 2026.1
  ids, verified against ``get_methodology_checks``/``get_drc_checks``: results/71_check_suite/rule_catalogue_2026_1.tsv):
  LUTAR-1 (a LUT drives an asynchronous reset), DPIR-1/-2 and DPIR-3/DPOR-1..3 (asynchronous registers next to a DSP),
  RMIR-1, RMOR-1, RROR-1 (multiplier and RAM registers with an asynchronous reset; Advisory, so reported, not counted by
  the lint ruleset), ROAS-1 (both asynchronous set and reset), and report_cdc's asynchronous-reset rows.
- **netlist**: ``reset_scan.tsv`` (flow/checks/vivado_checks.tcl: one row per register with a reset pin that is not
  tied off, its root driver traced through buffers and LUT1 cells). RST-ASYNC-01 (an FDCE/FDPE outside a recognised
  synchroniser, not reset by a declared external asynchronous input), RST-POL-01 (one root reset used in both
  polarities), RST-DSPRAM-01 (an FDCE/FDPE whose D comes from, or whose Q feeds, a DSP or block RAM), RST-CDC-01 (a
  reset made by a register on one clock resets registers on another, or a device pin resets registers through no
  synchroniser), RST-LUT-01 (a LUT drives an asynchronous reset pin).

Recognised synchronisers: ``xpm_cdc_async_rst``, ``xpm_cdc_sync_rst``, the shell's ``reset_sync``, and the modules in
``architecture.yaml`` ``reset.synchronisers``. Declared external asynchronous inputs: ``architecture.yaml``
``reset.async_inputs`` (top-level port names). Vendor IP internals (cells under an IP core, a debug core or any
``xpm_`` macro other than the reset synchronisers) are not ours to change and are left out, except for RST-LUT-01 when
the LUT itself is outside the IP.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

RECOGNISED = ("xpm_cdc_async_rst", "xpm_cdc_sync_rst", "reset_sync")
#: vendor hierarchy: AMD's XPM macros by their exact names, and the build's IP cores (build/<variant>/ip/<name>, passed in as
#: ``ip_names``) and everything generated under them. A user module is never vendor by its name alone (review fix).
XPM = re.compile(r"^xpm_(cdc_(single|array_single|gray|handshake|pulse|sync_rst|async_rst|low_latency_handshake)|"
                 r"fifo_(sync|async|axis|axif|axil|base|rst|reg_bit|reg_vec|counter_updn)|memory_\w+)$")
#: the AMD rule ids the reset check reads (verified on Vivado 2026.1, see the module docstring)
AMD_METHODOLOGY = ("LUTAR-1", "DPIR-1", "DPIR-2", "RMIR-1", "RMOR-1", "RROR-1", "ROAS-1")
AMD_DRC = ("DPIR-3", "DPOR-1", "DPOR-2", "DPOR-3")
AMD_CDC = ("CDC-7", "CDC-8")
FIX = {
    "RST-ASYNC-01": "make the register's reset synchronous (if (rst) inside always_ff @(posedge clk)); keep asynchronous "
                    "resets only inside a reset synchroniser, or declare the external input in architecture.yaml reset.async_inputs",
    "RST-POL-01": "use one polarity for each reset inside the design (active high, inverted once at the port or synchroniser)",
    "RST-POL-02": "test the reset in one polarity only; invert it once where it enters the module",
    "RST-DSPRAM-01": "give the DSP or block-RAM registers a synchronous reset (or none), so they pack into the primitive",
    "RST-CDC-01": "synchronise the reset into each clock domain (xpm_cdc_async_rst or reset_sync per domain)",
    "RST-LUT-01": "drive asynchronous resets only from a register (a synchroniser output) or a pin, never from logic",
}
CODE_RULE = {"RST-ASYNC-01": "HDL-RST-01", "RST-POL-01": "HDL-RST-02", "RST-POL-02": "HDL-RST-02",
             "RST-DSPRAM-01": "HDL-RST-03", "RST-CDC-01": "HDL-RST-04", "RST-LUT-01": "HDL-RST-05"}
#: every code the reset check can raise, by the hdl_rules.yaml tool key it belongs to
CODES = {"resets": tuple(CODE_RULE), "vivado": AMD_METHODOLOGY + AMD_DRC + AMD_CDC}


def reset_config(design: Path) -> dict[str, Any]:
    import yaml
    try:
        arch = yaml.safe_load((design / "architecture.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        arch = {}
    r = arch.get("reset") or {}
    return {"synchronisers": set(RECOGNISED) | set(r.get("synchronisers") or []),
            "declared": set(r.get("synchronisers") or []), "async_inputs": set(r.get("async_inputs") or [])}


def _f(file: str, line: int, code: str, msg: str, where: str | None = None, count: int = 1) -> dict[str, Any]:
    return {"tool": "resets", "code": code, "rule": CODE_RULE[code], "severity": "error", "file": file, "line": line,
            "where": where or f"{file}:{line}", "message": msg, "count": count, "fix": FIX[code]}


# ---- source ------------------------------------------------------------------------------------------------------
_IF = re.compile(r"^\s*(?:begin\s*(?::\s*\w+)?\s*)?if\s*\(\s*(!|~)?\s*(\w+)\s*(?:(==|!=)\s*1'b([01])\s*)?\)")


def source_findings(design: Path, files: list[Path], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    from flow.standards_check import parse_modules, strip_comments
    out: list[dict[str, Any]] = []
    for f in files:
        if f.suffix not in (".sv", ".v"):
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        rel = _rel(f, design)
        shell = "shell/rtl/" in f.resolve().as_posix()
        for mod in parse_modules(text, str(f)):
            if not shell and (mod.name in RECOGNISED or XPM.match(mod.name)) and mod.name not in cfg.get("declared", set()):
                out.append(_f(rel, mod.line, "RST-ASYNC-01", f"module {mod.name} takes the name of a recognised synchroniser or "
                                                             f"XPM macro; the netlist rules would exempt it: rename it, or "
                                                             f"declare it in architecture.yaml reset.synchronisers"))
            body = mod.body
            pol: dict[str, dict[int, int]] = {}
            for a in mod.always:
                edges = a.get("edges") or []
                if len(edges) > 1 and mod.name not in cfg["synchronisers"]:
                    # the clock is the edge signal the block's first if does not test; every other edge is a reset
                    start0 = _offset_of_line(body, a["line"] - mod.body_line0)
                    seg0 = body[start0:start0 + 400]
                    k0 = seg0.find(")", seg0.find("@"))
                    m0 = _IF.match(seg0[k0 + 1:]) if k0 >= 0 else None
                    tested = m0.group(2) if m0 else None
                    clk_sig = next((s_ for _, s_ in edges if s_ != tested), edges[0][1])
                    for e, sig in edges:
                        if sig != clk_sig and sig not in cfg["async_inputs"]:
                            out.append(_f(rel, a["line"], "RST-ASYNC-01",
                                          f"module {mod.name}: {e} {sig} in the sensitivity list: an asynchronous reset "
                                          f"outside a recognised synchroniser"))
                if not edges:
                    continue
                # the first statement of the block: its if-condition is the reset test (clock-edge blocks only)
                start = _offset_of_line(body, a["line"] - mod.body_line0)
                seg = body[start:start + 400]
                k = seg.find(")", seg.find("@"))
                m = _IF.match(seg[k + 1:]) if k >= 0 else None
                if not m:
                    continue
                neg, sig, op, bit = m.groups()
                if not re.search(r"(?i)rst|reset", sig):
                    continue
                active_low = bool(neg) ^ (op == "==" and bit == "0") ^ (op == "!=" and bit == "1")
                pol.setdefault(sig, {})[int(active_low)] = a["line"]
            for sig, p in pol.items():
                if len(p) == 2 and sig not in cfg["synchronisers"]:
                    out.append(_f(rel, p[1], "RST-POL-02", f"module {mod.name}: {sig} is tested active high (line {p[0]}) "
                                                            f"and active low (line {p[1]})"))
    return out


def _offset_of_line(body: str, n: int) -> int:
    pos = 0
    for _ in range(max(n, 0)):
        nxt = body.find("\n", pos)
        if nxt < 0:
            break
        pos = nxt + 1
    return pos


def _rel(f: Path, design: Path) -> str:
    try:
        return f.resolve().relative_to(design.resolve()).as_posix()
    except ValueError:
        try:
            return f.resolve().relative_to(Path(__file__).resolve().parents[2]).as_posix()
        except ValueError:
            return f.name


# ---- netlist (reset_scan.tsv) -----------------------------------------------------------------------------------------
def read_scan(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _parts(hier: str) -> list[str]:
    return [p for p in (hier or "").split("/") if p]


def _in(hier: str, names: set[str]) -> bool:
    return any(p in names for p in _parts(hier))


def _vendor(hier: str, ip_names: set[str]) -> bool:
    parts = _parts(hier)
    return any((XPM.match(p) and p not in RECOGNISED) or p in ip_names for p in parts) or \
        any(p.startswith(n + "_") for p in parts for n in ip_names)        # the IP's own generated submodules


def _clocks(s: str) -> set[str]:
    return {c for c in (s or "").split(",") if c}


def netlist_findings(rows: list[dict[str, str]], cfg: dict[str, Any], ip_names: set[str] = frozenset()) -> list[dict[str, Any]]:
    """Group the scan's rows into findings (one per rule and root/module, with a register count)."""
    syncs = cfg["synchronisers"]
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    def add(code: str, key: str, where: str, msg: str, cell: str) -> None:
        g = groups.setdefault((code, key), {"where": where, "msg": msg, "cells": []})
        g["cells"].append(cell)

    pol: dict[str, dict[int, list[str]]] = {}
    unknown: set[str] = set()
    for r in rows:
        hier, cell, ref = r.get("hier", ""), r["cell"], r["ref"]
        is_async = ref in ("FDCE", "FDPE", "LDCE", "LDPE")
        vendor = _vendor(hier, ip_names)
        in_sync = _in(hier, syncs)
        root, kind, rref = r.get("root", ""), r.get("root_kind", ""), r.get("root_ref", "")
        mod = (_parts(hier) or ["<top>"])[0]
        if is_async and kind == "cell" and re.match(r"^LUT(?!1$)", rref) and not _vendor(r.get("root_hier", ""), ip_names):
            add("RST-LUT-01", root, root, f"{rref} {root} drives the {r['pin']} pin of registers", cell)
        if vendor:
            continue
        port_base = re.sub(r"\[\d+\]$", "", root)
        if is_async and not in_sync and not (kind == "port" and port_base in cfg["async_inputs"]):
            add("RST-ASYNC-01", f"{mod}|{root}", cell, f"asynchronous {r['pin']} from {kind} {root or '?'} on registers in "
                                                         f"{mod if mod != '<top>' else 'the top module'}", cell)
        if is_async and not in_sync and (re.match(r"^(DSP48|RAMB)", r.get("d_ref", "")) or
                                         re.search(r"(^|,)(DSP48|RAMB)", r.get("q_refs", ""))):
            add("RST-DSPRAM-01", f"{mod}|{root}", cell, f"registers next to a DSP or block RAM (D from {r.get('d_ref') or '-'}, "
                                                        f"Q to {r.get('q_refs') or '-'}) have an asynchronous {r['pin']}", cell)
        if not in_sync:
            rclk, clk = _clocks(r.get("root_clock", "")), _clocks(r.get("clock", ""))
            if kind == "cell" and rref.startswith("FD") and (not rclk or not clk):
                unknown.add(cell)
            if kind == "cell" and rref.startswith("FD") and rclk and clk and not (rclk & clk):
                add("RST-CDC-01", f"{root}|{','.join(sorted(clk))}", root,
                    f"reset made by {root} on {','.join(sorted(rclk))} resets registers on {','.join(sorted(clk))} "
                    f"without a synchroniser", cell)
            elif kind == "port" and "IBUF" in r.get("path", "") and not is_async:
                add("RST-CDC-01", f"{root}|pin", root, f"device pin {root} resets registers on {','.join(sorted(clk)) or '?'} "
                                                       f"without a synchroniser", cell)
        if kind in ("cell", "port"):
            eff = int(r.get("root_inverted", "0") in ("1", "true")) ^ int(r.get("pin_inverted", "0") in ("1", "true"))
            pol.setdefault(f"{kind}:{root}", {}).setdefault(eff, []).append(cell)
    for rid, p in pol.items():
        if len(p) == 2:
            add("RST-POL-01", rid, rid.split(":", 1)[1],
                f"reset {rid.split(':', 1)[1]} is used active high on {len(p[0])} and active low on {len(p[1])} registers "
                f"(two nets, two control sets)", p[1][0])
    out = []
    for (code, _), g in sorted(groups.items()):
        n = len(g["cells"])
        out.append({"tool": "resets", "code": code, "rule": CODE_RULE[code], "severity": "error", "where": g["where"],
                    "message": g["msg"] + f" ({n} register{'s' if n != 1 else ''}, e.g. {g['cells'][0]})", "count": n,
                    "fix": FIX[code], "file": None, "line": None})
    if unknown:              # not a finding, but the clock-domain rule could not be judged for these registers
        out.append({"tool": "resets", "code": "RST-CDC-01", "rule": CODE_RULE["RST-CDC-01"], "severity": "unknown",
                    "where": "netlist", "message": f"{len(unknown)} register(s) whose reset comes from a register with no "
                    f"timed clock on one side (e.g. {sorted(unknown)[0]}): the clock-domain rule was not judged; constrain "
                    "every clock", "count": len(unknown), "fix": "create_clock on every clock", "file": None, "line": None,
                    "incomplete": True})
    return out


def amd_findings(meth: list[dict[str, Any]] | None, drc: list[dict[str, Any]] | None,
                 cdc: dict[str, Any] | None, stage: str) -> list[dict[str, Any]]:
    """The reset-related rows of AMD's own reports (parsed by flow/gates.py's parsers)."""
    out = []
    for src, ids, rows in (("report_methodology", AMD_METHODOLOGY, meth), ("report_drc", AMD_DRC, drc),
                           ("report_cdc", AMD_CDC, (cdc or {}).get("rules"))):
        for r in rows or []:
            if r.get("rule") in ids:
                out.append({"tool": "vivado", "code": r["rule"], "severity": str(r.get("severity", "")),
                            "where": f"{src}@{stage}", "message": f"{r.get('description', '')} (x{r.get('count', 1)})",
                            "count": r.get("count", 1), "file": None, "line": None})
    return out
