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
#: the shell's own synchroniser, exempt by its file (not by its module name: review round 2)
SHELL_SYNCS = ("shell/rtl/reset_sync.sv",)
_UNIT = re.compile(r"\b(module|macromodule|interface|program)\s+(?:automatic\s+|static\s+)?(\w+)")
_ALWAYS = re.compile(r"\balways(_ff|_comb|_latch)?\b\s*(@\s*)?")
_PRIM = re.compile(r"\b(FDCE|FDPE|LDCE|LDPE)\b\s*(?:#\s*\([^;]*?\)\s*)?(\w+)\s*\(")
_RSTNAME = re.compile(r"(?i)rst|reset|clr|clear")
_INCLUDE = re.compile(r'`include\s+"([^"]+)"')
#: a reset test in an if: (neg?) name (cmp value)?, with any number of parentheses around it
_TEST = re.compile(r"^\(*\s*(!|~)?\s*\(*\s*(\w+)\s*\)*\s*(?:(==|!=|===|!==)\s*(?:1'[bB])?([01])\s*)?\)*$")


def _paren(text: str, k: int) -> tuple[str, int] | None:
    """The balanced (...) starting at text[k] == '(': (inside, index after it), or None."""
    if k >= len(text) or text[k] != "(":
        return None
    depth = 0
    for i in range(k, min(len(text), k + 4000)):
        depth += text[i] == "("
        depth -= text[i] == ")"
        if depth == 0:
            return text[k + 1:i], i + 1
    return None


def _expand_includes(text: str, f: Path, dirs: list[Path], depth: int = 0) -> tuple[str, list[str]]:
    """Inline `include "x" from the file's folder or the source folders; the names that could not be found."""
    missing: list[str] = []

    def sub(m):
        name = m.group(1)
        for d in [f.parent, *dirs]:
            q = d / name
            if q.is_file() and depth < 8:
                t, mm = _expand_includes(q.read_text(errors="replace"), q, dirs, depth + 1)
                missing.extend(mm)
                return t.replace("\n", " ")              # inlined on one line, so the file's line numbers hold
        missing.append(name)
        return " "
    return _INCLUDE.sub(sub, text), missing


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _test_of(cond: str, aliases: dict[str, tuple[str, int]]) -> tuple[str, int] | None:
    """(root reset signal, active_low) for a simple reset test, through `assign a = ~b` aliases; None otherwise."""
    m = _TEST.match(cond.strip())
    if not m:
        return None
    neg, sig, op, bit = m.groups()
    low = bool(neg)
    if op in ("==", "===") and bit == "0" or op in ("!=", "!==") and bit == "1":
        low = not low
    inv = 0
    seen = 0
    while sig in aliases and seen < 8:
        sig, i_ = aliases[sig]
        inv ^= i_
        seen += 1
    return sig, int(low) ^ inv


def source_findings(design: Path, files: list[Path], cfg: dict[str, Any], root: Path | None = None,
                    top: str | None = None, parts: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The source part (review round 2: a raw-text scan that fails closed). Each module, macromodule, interface and
    program of the SystemVerilog sources (with `include files inlined): every edge signal of a sensitivity list except the
    clock is an asynchronous reset; a list it cannot read (a macro, iff, nested parentheses) is reported as unread
    (``parts['source_unread']``); direct FDCE/FDPE/LDCE/LDPE instances and always_latch blocks with a reset test count as
    asynchronous resets. ``reset.async_inputs`` exempt only edges on the top module's own ports. VHDL files are not
    scanned (``parts['source_vhdl']``), but an entity named like a recognised synchroniser is still reported."""
    from flow.standards_check import strip_comments
    parts = parts if parts is not None else {}
    root = root or Path(__file__).resolve().parents[2]
    out: list[dict[str, Any]] = []
    unread: list[str] = []
    vhdl: list[str] = []
    dirs = sorted({f.parent for f in files})
    shell = {(root / x).resolve() for x in SHELL_SYNCS}
    declared = cfg.get("declared", set())
    for f in files:
        rel = _rel(f, design)
        try:
            raw = f.read_text(errors="replace")
        except OSError:
            unread.append(f"{rel}: unreadable")
            continue
        if f.suffix.lower() in (".vhd", ".vhdl"):
            vhdl.append(rel)
            for m in re.finditer(r"(?im)^\s*entity\s+(\w+)\s+is", raw):
                if (m.group(1) in RECOGNISED or XPM.match(m.group(1))) and m.group(1) not in declared:
                    cfg.setdefault("impostors", set()).add(m.group(1))
                    out.append(_f(rel, _line(raw, m.start()), "RST-ASYNC-01", f"VHDL entity {m.group(1)} takes the name of a "
                                  "recognised synchroniser or XPM macro, and VHDL is not scanned here: rename it, or declare it "
                                  "in architecture.yaml reset.synchronisers"))
            continue
        if f.suffix.lower() not in (".sv", ".v", ".svh", ".vh"):
            continue
        is_shell = f.resolve() in shell
        text, missing = _expand_includes(raw, f, dirs)
        text, _ = strip_comments(text)
        unread += [f"{rel}: `include \"{n}\" not found" for n in missing]
        units = [(m.start(), m.group(1), m.group(2)) for m in _UNIT.finditer(text)]
        for n, (u0, kind, name) in enumerate(units):
            u1 = units[n + 1][0] if n + 1 < len(units) else len(text)
            body = text[u0:u1]
            exempt = (name in cfg["synchronisers"] and (name in declared or is_shell))
            if not is_shell and (name in RECOGNISED or XPM.match(name)) and name not in declared:
                cfg.setdefault("impostors", set()).add(name)
                out.append(_f(rel, _line(text, u0), "RST-ASYNC-01", f"{kind} {name} takes the name of a recognised "
                              "synchroniser or XPM macro; the netlist rules would exempt it: rename it, or declare it in "
                              "architecture.yaml reset.synchronisers"))
            if name in declared and "ASYNC_REG" not in body and "xpm_cdc_" not in body:
                out.append(_f(rel, _line(text, u0), "RST-ASYNC-01", f"{kind} {name} is declared a reset synchroniser but has "
                              "no ASYNC_REG register and no xpm_cdc instance: a synchroniser exempts its whole subtree, so "
                              "it must be one"))
            ports = set(re.findall(r"\b(\w+)\s*[,)]", (_paren(body, body.find("(")) or ("", 0))[0])) if name == top else set()
            aliases = {a: (b, int(bool(neg))) for a, neg, b in
                       re.findall(r"(?:\bassign\s+|\bwire\s+(?:logic\s+)?)(\w+)\s*=\s*(!|~)?\s*(\w+)\s*;", body)}
            for pm in _PRIM.finditer(body):
                if not exempt:
                    out.append(_f(rel, _line(text, u0 + pm.start()), "RST-ASYNC-01", f"{kind} {name}: a {pm.group(1)} primitive "
                                  f"({pm.group(2)}) has an asynchronous clear or preset"))
            alw = list(_ALWAYS.finditer(body))
            pol: dict[str, dict[int, int]] = {}
            for k, a in enumerate(alw):
                blk_end = alw[k + 1].start() if k + 1 < len(alw) else len(body)
                ln = _line(text, u0 + a.start())
                kind_a = a.group(1) or ""
                sens = None
                after = a.end()
                if a.group(2):
                    ps = _paren(body, after)
                    if ps is None:
                        if body[after:after + 1] != "*":
                            unread.append(f"{rel}:{ln}: sensitivity list not read")
                        continue
                    sens, after = ps
                blk = body[after:blk_end]
                tests = [c for c in (_paren(blk, mm.end() - 1) for mm in re.finditer(r"\bif\s*\(", blk)) if c]
                if kind_a == "_latch":
                    t0 = _test_of(tests[0][0], aliases) if tests else None
                    if t0 and _RSTNAME.search(t0[0]) and not exempt:
                        out.append(_f(rel, ln, "RST-ASYNC-01", f"{kind} {name}: always_latch with a reset test on {t0[0]}: "
                                      "a latch with an asynchronous reset"))
                    continue
                if sens is None:
                    continue
                if "`" in sens or re.search(r"\biff\b|\(", sens) or not re.fullmatch(
                        r"\s*(?:(?:posedge|negedge)\s+\w+(?:\s*\[\s*\d+\s*\])?|\*|\w+)(?:\s*(?:or|,)\s*(?:(?:posedge|negedge)\s+\w+"
                        r"(?:\s*\[\s*\d+\s*\])?|\w+))*\s*", sens):
                    unread.append(f"{rel}:{ln}: sensitivity list '{' '.join(sens.split())[:60]}' not read")
                    continue
                edges = re.findall(r"(posedge|negedge)\s+(\w+)", sens)
                if not edges:
                    continue
                first = _test_of(tests[0][0], aliases) if tests else None
                tested = first[0] if first else None
                if len(edges) > 1 and not exempt:
                    clk_sig = next((s_ for _, s_ in edges if s_ != tested), edges[0][1])
                    for e, sig in edges:
                        if sig == clk_sig:
                            continue
                        if sig in cfg["async_inputs"] and name == top and sig in ports:
                            continue
                        out.append(_f(rel, ln, "RST-ASYNC-01", f"{kind} {name}: {e} {sig} in the sensitivity list: an "
                                      "asynchronous reset outside a recognised synchroniser"))
                for cond, _ in tests:
                    t = _test_of(cond, aliases)
                    if t and _RSTNAME.search(t[0]):
                        pol.setdefault(t[0], {})[t[1]] = ln
            for sig, p in pol.items():
                if len(p) == 2 and not exempt:
                    out.append(_f(rel, p[1], "RST-POL-02", f"{kind} {name}: {sig} is tested active high (line {p[0]}) "
                                                            f"and active low (line {p[1]})"))
    parts["source_unread"] = ("not run: " + "; ".join(unread[:4]) + (f"; {len(unread) - 4} more" if len(unread) > 4 else "")) \
        if unread else "ran"
    if vhdl:
        parts["source_vhdl"] = "not run: VHDL is not scanned by the source part (" + ", ".join(vhdl[:3]) + "); the netlist part covers it"
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
    return any((XPM.match(p) and p not in RECOGNISED) or p in ip_names for p in parts)   # exact names (review round 2)


def _clocks(s: str) -> set[str]:
    return {c for c in (s or "").split(",") if c}


def netlist_findings(rows: list[dict[str, str]], cfg: dict[str, Any], ip_names: set[str] = frozenset()) -> list[dict[str, Any]]:
    """Group the scan's rows into findings (one per rule and root/module, with a register count)."""
    syncs = cfg["synchronisers"] - cfg.get("impostors", set())     # a user module or entity named like one is not one
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
