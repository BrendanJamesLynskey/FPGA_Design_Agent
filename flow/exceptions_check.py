#!/usr/bin/env python3
"""The timing-exception check of the flow gates (brief 20): is every exception in the XDC applied, used, and not one
that Vivado's methodology checks call wrong?

    python3 flow/exceptions_check.py <build dir> [--stage synth|route]

Reads, for one stage (``synth`` after synthesis, ``route`` after routing), the reports ``flow/build.tcl`` writes:

    exceptions_<stage>.rpt           report_exceptions            every exception, by position
    exceptions_ignored_<stage>.rpt   report_exceptions -ignored   exceptions Vivado drops (overridden, no path)
    exceptions_coverage_<stage>.rpt  report_exceptions -coverage  the endpoints each exception covers
    methodology_<stage>.rpt          report_methodology           (methodology_synth.rpt / methodology.rpt)

``mcp_paths_<stage>.txt`` (flow/mcp_paths.tcl: each multicycle exception's registers and their clock enables), and the build
log (``vivado.log``) for constraint messages raised while reading the XDC. It fails on:

    EXC-IGNORED     an exception in report_exceptions -ignored (overridden by a higher-priority one, or no path)
    EXC-NO-PATH     an exception that covers no endpoint (report_exceptions -coverage: Endpoints 0)
    EXC-XDC-MSG     a CRITICAL WARNING or ERROR from reading an XDC exception line (an empty object list drops the
                    exception: brief 20 E6, Vivado 12-4739)
    TIMING-29/46/47 the methodology rules for an inconsistent multicycle pair, a multicycle with tied CE pins, and a
                    false path / clock group / datapath-only max delay between synchronous clocks (Warnings in
                    Vivado 2025.2; gate failures here)
    TIMING-24       a datapath-only max delay overridden (by a clock group: brief 20 E7; also EXC-IGNORED)
    EXC-MCP-ENABLE  a multicycle exception whose registers do not share a clock enable (mcp_paths_<stage>.txt from
                    flow/mcp_paths.tcl): on one clock, every register it names must have a CE that is not tied and one
                    register must be in the fan-in of all those CEs; between clocks, the registers on the faster clock
                    must have such a CE (UG903's slow-to-fast case), and -start/-end must count the faster
                    clock's edges (brief 20 E8b: -start on a 100 -> 200 MHz path gave 15 ns, not 10). Vivado 2025.2 raised no TIMING-46 for a
                    multicycle on tied-CE registers (brief 20 E3, after synthesis and after routing)
    XDCH-1          a -setup multicycle with no -hold multicycle (a Warning; brief 20 E2 measured it, and the hold check
                    then fails by about N-1 periods)

Each failure names the exception's XDC file and line where it can be found: report_exceptions numbers exceptions by
``Position``, the order in which timing constraints were read (``xdc_positions``, checked against the fixtures of
brief 20), and the log names file and line for its messages. Raw tool text only, no fix hints.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Timing constraint commands: each takes the next report_exceptions Position when read (Vivado 2025.2, measured on the
# brief 20 fixtures: create_clock and create_generated_clock take positions too). Physical (set_property) lines do not.
TIMING_COMMANDS = ("create_clock", "create_generated_clock", "set_input_delay", "set_output_delay", "set_false_path",
                   "set_multicycle_path", "set_max_delay", "set_min_delay", "set_clock_groups", "set_clock_latency",
                   "set_clock_uncertainty", "set_input_jitter", "set_system_jitter", "set_case_analysis",
                   "set_disable_timing", "set_bus_skew", "set_max_time_borrow", "group_path", "set_clock_sense",
                   "set_data_check", "set_external_delay", "set_propagated_clock")
EXCEPTION_COMMANDS = ("set_false_path", "set_multicycle_path", "set_max_delay", "set_min_delay", "set_clock_groups")
METHODOLOGY_RULES = ("TIMING-24", "TIMING-29", "TIMING-46", "TIMING-47", "XDCH-1")


def _table(text: str) -> list[dict[str, str]]:
    """The rows of a report_exceptions table: the header line starting ``Position`` and its dashed rule give the
    column spans; a row is a line whose first column is a number."""
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.startswith("Position") and set(lines[i + 1].strip()) <= {"-", " "} and lines[i + 1].strip():
            rule = lines[i + 1]
            spans = [(m.start(), m.end()) for m in re.finditer(r"-+", rule)]
            names = [line[a:b + 1].strip() or line[a:].split()[0] for a, b in spans]
            rows = []
            for row in lines[i + 2:]:
                if not row.strip():
                    if rows:
                        break
                    continue
                if not re.match(r"\d+\s", row):
                    if rows and row.startswith(" "):      # a wrapped continuation: append to the last row's columns
                        for (a, b), n in zip(spans, names):
                            extra = row[a:b + 1].strip()
                            if extra:
                                rows[-1][n] = (rows[-1][n] + " " + extra).strip()
                        continue
                    break
                cells = []
                for k, (a, b) in enumerate(spans):
                    end = spans[k + 1][0] if k + 1 < len(spans) else len(row)
                    cells.append(row[a:end].strip())
                rows.append(dict(zip(names, cells)))
            return rows
    return []


def parse_exceptions(text: str) -> list[dict[str, Any]]:
    """report_exceptions (plain or -ignored): Position, From, Through, To, Setup, Hold, Status."""
    if "Exceptions Report" not in text:
        raise ValueError("not a report_exceptions report")
    return [{**r, "position": int(r["Position"])} for r in _table(text)]


def parse_coverage(text: str) -> list[dict[str, Any]]:
    """report_exceptions -coverage: Position, Type, Setup, Hold, From, Through, To, Endpoints and the percentages."""
    if "Exceptions Report" not in text:
        raise ValueError("not a report_exceptions -coverage report")
    out = []
    for r in _table(text):
        ep = r.get("Endpoints", "")
        out.append({**r, "position": int(r["Position"]), "endpoints": int(ep) if ep.isdigit() else None})
    return out


def xdc_positions(xdc_files: list[Path]) -> dict[int, dict[str, Any]]:
    """Position -> {file, line, text}: the timing constraint commands of the XDC files, in read order."""
    out: dict[int, dict[str, Any]] = {}
    pos = 0
    for f in xdc_files:
        try:
            lines = Path(f).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for n, raw in enumerate(lines, 1):
            code = raw.split("#", 1)[0]
            for stmt in (s.strip() for s in code.split(";")):
                if stmt and stmt.split()[0] in TIMING_COMMANDS:
                    pos += 1
                    out[pos] = {"file": Path(f).name, "line": n, "text": raw.strip()}
    return out


# "CRITICAL WARNING: [Vivado 12-4739] set_multicycle_path:No valid object(s) found for '-to [get_cells p_rgx[*]]'.
#  [/path/tex_e6.xdc:3]"
_LOG_MSG = re.compile(r"^(CRITICAL WARNING|ERROR): \[([^\]]+)\] (.*?)\s*\[([^\[\]]+\.xdc):(\d+)\]\s*$", re.M)


def xdc_messages(log_text: str) -> list[dict[str, Any]]:
    """CRITICAL WARNING / ERROR messages the log ties to an XDC line (file and line as Vivado prints them)."""
    out, seen = [], set()
    for sev, mid, msg, f, n in _LOG_MSG.findall(log_text):
        key = (mid, Path(f).name, int(n))
        if key not in seen:                     # Vivado repeats a message (the log and the end-of-command summary)
            seen.add(key)
            out.append({"severity": sev, "id": mid, "message": msg, "file": Path(f).name, "line": int(n)})
    return out


def _rule_rows(methodology_text: str) -> list[dict[str, Any]]:
    """TIMING-29/46/47 detail entries of a report_methodology report (rule, severity, the detail text)."""
    out = []
    for rule in METHODOLOGY_RULES:
        for m in re.finditer(rf"^({rule})#(\d+)\s+(\w[\w ]*?)\s*\n(.*?)(?=^\S+#\d+\s|\Z)", methodology_text, re.M | re.S):
            body = " ".join(l.strip() for l in m.group(4).splitlines() if l.strip() and not set(l.strip()) <= {"-"})
            loc = re.search(r"(\S+\.xdc) \(Line: (\d+)\)", body)
            pos = re.search(r"constraint position (\d+)", body)
            out.append({"rule": rule, "index": int(m.group(2)), "severity": m.group(3).strip(), "detail": body[:600],
                        "position": int(pos.group(1)) if pos else None,
                        "file": Path(loc.group(1)).name if loc else None, "line": int(loc.group(2)) if loc else None})
    return out


def parse_mcp_dump(text: str) -> dict[str, Any]:
    """flow/mcp_paths.tcl's dump: clocks, multicycle exceptions, and the clock and CE cone of each register they name."""
    if "# end" not in text:
        raise ValueError("mcp_paths dump truncated (no '# end')")
    out: dict[str, Any] = {"clocks": {}, "exceptions": {}, "errors": []}
    for line in text.splitlines():
        f = line.split("|")
        if f[0] == "CLOCK" and len(f) >= 3:
            out["clocks"][f[1]] = float(f[2])
        elif f[0] == "EXC" and len(f) >= 7:
            out["exceptions"][int(f[1])] = {"kind": f[2], "n": int(f[3]), "edge": f[4], "from": f[5], "to": f[6],
                                            "cells": {"from": [], "to": []}, "other": []}
        elif f[0] == "CELL" and len(f) >= 7:
            e = out["exceptions"].get(int(f[1]))
            if e is None:
                continue
            if f[3].startswith("<"):
                e["other"].append(f"{f[2]} {f[3]}")
            else:
                e["cells"][f[2]].append({"cell": f[3], "clock": f[4], "tied": f[5], "fanin": [x for x in f[6].split(",") if x]})
        elif f[0] == "ERROR":
            out["errors"].append(line)
    return out


def enable_problems(dump: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    """EXC-MCP-ENABLE findings, one per multicycle exception at most: its registers do not share a real clock enable, or
    (between clocks) the register on the faster clock has none, or -start/-end counts the slower clock."""
    out = []
    clocks = dump["clocks"]
    for pos, e in sorted(dump["exceptions"].items()):
        cells = e["cells"]["from"] + e["cells"]["to"]
        if not cells:
            continue
        per = {c["clock"]: clocks.get(c["clock"]) for c in cells if c["clock"]}
        why = None
        if len(per) <= 1:
            bad = sorted({c["cell"] for c in cells if c["tied"] != "0"})
            common = None
            for c in cells:
                common = set(c["fanin"]) if common is None else common & set(c["fanin"])
            if bad:
                why = (f"{len(bad)} of {len({c['cell'] for c in cells})} named registers load on every clock (CE tied or "
                       f"absent), e.g. {', '.join(bad[:4])}")
            elif not common:
                why = "the named registers share no register in their clock-enable cones"
        else:
            fast = min(per, key=lambda k: per[k] or 1e9)
            bad = sorted({c["cell"] for c in cells if c["clock"] == fast and c["tied"] != "0"})
            src = {c["clock"] for c in e["cells"]["from"]}
            dst = {c["clock"] for c in e["cells"]["to"]}
            ps = max((clocks.get(k) or 0) for k in src) if src else None
            pe = max((clocks.get(k) or 0) for k in dst) if dst else None
            if bad:
                why = f"registers on the faster clock {fast} load on every clock, e.g. {', '.join(bad[:4])}"
            elif e["kind"] == "setup" and ps and pe and ps != pe and ((e["edge"] == "start") == (ps > pe)):
                why = (f"-{e['edge']} counts periods of the slower clock ({max(ps, pe):g} ns); UG903 counts the faster "
                       f"clock's edges (-end slow to fast, -start fast to slow)")
        if why:
            out.append({"position": pos, "exception": f"{e['kind']} {e['n']} -{e['edge']}", "why": why})
            if len(out) >= limit:
                break
    return out


def evaluate(build_dir: Path, stage: str = "synth", xdc_files: list[Path] | None = None) -> dict[str, Any]:
    """The exception check for one stage of a build. Missing reports raise FileNotFoundError (the caller decides
    whether a missing report fails: flow/gates.py fails it for a strict build)."""
    d = Path(build_dir)
    meth_name = "methodology_synth.rpt" if stage == "synth" else "methodology.rpt"
    exc = parse_exceptions((d / f"exceptions_{stage}.rpt").read_text(errors="replace"))
    ign = parse_exceptions((d / f"exceptions_ignored_{stage}.rpt").read_text(errors="replace"))
    cov = parse_coverage((d / f"exceptions_coverage_{stage}.rpt").read_text(errors="replace"))
    meth = (d / meth_name).read_text(errors="replace") if (d / meth_name).exists() else ""
    if xdc_files is None:
        prep = json.loads((d / "prepare.json").read_text()) if (d / "prepare.json").exists() else {}
        root = Path(__file__).resolve().parents[1]
        xdc_files = [root / x for x in prep.get("files") or [] if str(x).endswith(".xdc")]   # flow/prepare.py: read order
    where = xdc_positions(xdc_files)
    log = d / "vivado.log"
    msgs = xdc_messages(log.read_text(errors="replace")) if log.exists() else []
    fails: list[dict[str, Any]] = []

    def at(pos: int) -> dict[str, Any]:
        return where.get(pos, {"file": None, "line": None, "text": None})

    for r in ign:
        fails.append({"rule": "EXC-IGNORED", "position": r["position"], **at(r["position"]),
                      "vivado": {k: v for k, v in r.items() if k not in ("position",)}})
    ignored = {r["position"] for r in ign}
    for r in cov:
        if r["endpoints"] == 0 and r["position"] not in ignored:
            fails.append({"rule": "EXC-NO-PATH", "position": r["position"], **at(r["position"]),
                          "vivado": {k: v for k, v in r.items() if k not in ("position", "endpoints")}})
    by_name = {Path(f).name: Path(f) for f in xdc_files}

    def line_text(f: str | None, n: int | None) -> str | None:
        try:
            return by_name[f].read_text(errors="replace").splitlines()[n - 1].strip() if f in by_name and n else None
        except (OSError, IndexError):
            return None

    for m in msgs:
        fails.append({"rule": "EXC-XDC-MSG", "position": None, "file": m["file"], "line": m["line"],
                      "text": line_text(m["file"], m["line"]),
                      "vivado": {"severity": m["severity"], "id": m["id"], "message": m["message"]}})
    dump_p = d / f"mcp_paths_{stage}.txt"
    if dump_p.exists():
        try:
            for f in enable_problems(parse_mcp_dump(dump_p.read_text(errors="replace"))):
                w = at(f["position"])
                fails.append({"rule": "EXC-MCP-ENABLE", "position": f["position"], "file": w["file"], "line": w["line"],
                              "text": w["text"], "vivado": {"message": f"multicycle {f['exception']}: {f['why']}"}})
        except ValueError as e:
            fails.append({"rule": "EXC-MCP-ENABLE", "position": None, "file": None, "line": None, "text": None,
                          "vivado": {"message": str(e)}})
    for r in _rule_rows(meth):
        if r["file"] is None and r["position"] is not None:        # TIMING-47 names a position, XDCH-1 a file and line
            r.update({k: at(r["position"])[k] for k in ("file", "line")})
        fails.append({"rule": r["rule"], "position": r["position"], "file": r["file"], "line": r["line"],
                      "text": line_text(r["file"], r["line"]),
                      "vivado": {"severity": r["severity"], "detail": r["detail"]}})
    return {"stage": stage, "pass": not fails, "exceptions": len(exc), "ignored": len(ign),
            "covered": {r["position"]: r["endpoints"] for r in cov}, "failures": fails}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("build_dir", type=Path)
    ap.add_argument("--stage", choices=["synth", "route"], default="synth")
    ap.add_argument("--xdc", type=Path, nargs="*", help="the XDC files in read order (default: prepare.json)")
    a = ap.parse_args(argv)
    r = evaluate(a.build_dir, a.stage, a.xdc)
    print(json.dumps(r, indent=2))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
