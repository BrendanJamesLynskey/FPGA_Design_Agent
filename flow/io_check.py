#!/usr/bin/env python3
"""The I/O-timing check of the flow gates (brief 20 part B): are the input and output delays real, complete and relative
to the right clock, and is the clock uncertainty recorded?

    python3 flow/io_check.py <build dir> [--stage synth|route] [--interfaces io.yaml] [--xdc f.xdc ...]

Reads the XDC files (the delay lines themselves, with the comments above them), ``io_paths_<stage>.txt``
(flow/io_paths.tcl: the clocks, each port's IOB register and synchroniser, the worst setup and hold path of each port,
the worst internal paths) and, after routing, ``timing_worst_setup.rpt`` / ``timing_worst_hold.rpt`` for the
uncertainty breakdown. The design's I/O interfaces come from ``io_interfaces:`` in its spec.yaml or build.yaml (see
``INTERFACE_KEYS``); ports the board lists as slow (``board.yaml`` ``slow_ports``) or the spec marks ``async: true``
are asynchronous or slow. Fails on:

    IO-INVENTED       a non-zero delay on an asynchronous or slow port (button, switch, LED, UART...): these have no
                      timing relationship; the right constraint is a 0 ns placeholder and a commented false path
                      (brief 20 part A: the agent gave such ports made-up and negative delays)
    IO-NO-FORMULA     a non-zero delay with no comment above it naming the data-sheet terms it comes from (tCO, tSU,
                      tH, trace, skew, data valid)
    IO-MIN-GT-MAX     -min larger than -max on the same port, clock and edge (fixture I3: Vivado says nothing)
    IO-REPLACED       a delay that a later line on the same ports and clock replaces because that line has no -add_delay
                      (I5b: the falling-edge lines of a DDR input written without -add_delay dropped the rising-edge ones)
    IO-MISSING-MINMAX a port of a synchronous interface without both -max and -min for each edge it uses (I2: with
                      -max only Vivado has no hold path from the port, and check_timing reports partial_input_delay)
    IO-PLACEHOLDER    a 0 ns placeholder, or a false path, on a port of a synchronous interface (I8)
    IO-VALUE          a delay that differs from the interface's data-sheet formula (I3b, I4b: a wrong sign on -min)
    IO-CLOCK          a delay relative to a clock other than the interface's, or a clock whose period differs from the
                      interface's (I7b, V2a, V5)
    IO-ASYNC-CLOCK    a delay on a port of an asynchronous interface (its device has its own oscillator) that has no
                      synchroniser: no fixed phase, so the delay means nothing (V6)
    IO-NO-PATH        a port of a synchronous interface with no setup or no hold path in Vivado's analysis
    IO-IOB            an interface register that should be in the IOB (``iob: true``) and is not
    IO-DDR-REQUIREMENT a DDR interface whose setup or hold requirement in Vivado's analysis is not the intended edge
                      pairing's (a full-period setup requirement: the wrong edges are paired), or that declares nothing
                      to check it against
    IO-FWD-SOURCE     an interface timed against a clock the FPGA forwards (``forwarded_clock_source``: the pin the
                      generated clock must be defined from, e.g. the forwarding ODDR's C) whose create_generated_clock is
                      missing or names another -source (brief 63D: a forwarded clock defined from the wrong pin passes
                      the clock-name check while its latency is modelled wrongly)
    IO-DDR-UNDECLARED a DDR port (a DDR primitive next to the pin, or delays on both clock edges) that is not in a
                      declared DDR interface with data-sheet values: the pairing check would otherwise be skipped
    IO-VCLK-UNRELATED a virtual clock whose period is neither equal to nor an integer ratio of a design clock, with no
                      comment above its create_clock saying why
    IO-DUMP           flow/io_paths.tcl could not run, or its dump is truncated

A virtual clock used before it is defined is a CRITICAL WARNING (Vivado 12-4739) that drops the delay: the exception
check (flow/exceptions_check.py, EXC-XDC-MSG) already fails it (fixture V4). Raw findings only, no fix hints.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

INTERFACE_KEYS = ("name", "kind", "direction", "ports", "clock", "clock_period_ns", "ddr", "iob", "data_sheet",
                  "forwarded_phase_deg", "forwarded_clock_source")
KINDS = ("system_synchronous", "source_synchronous", "forwarded_clock", "asynchronous")
# board slow_ports default (when board.yaml has none): the Nexys A7 user I/O that has no timing relationship
DEFAULT_SLOW = (r"BTN[CUDLR]", r"CPU_RESETN", r"SW\[\d+\]", r"LED\[\d+\]", r"LED1[67]_[RGB]", r"AN\[\d+\]",
                r"C[A-G]", r"DP", r"UART_\w+")
_FORMULA = re.compile(r"(t_?co|t_?su|t_?h\b|\bth\b|tsu|tco|trace|skew|dv_|data[- ]valid|valid (before|after)|setup|hold|"
                      r"data ?sheet|propagation)", re.I)
_DELAY = re.compile(r"^\s*(set_input_delay|set_output_delay)\b(.*)$")
_CLOCKDEF = re.compile(r"^\s*create_clock\b(.*)$")
_TOL = 0.0051


# --- XDC text -------------------------------------------------------------------------------------------------------

def _ports_in(arg: str, vars_: dict[str, list[str]]) -> list[str]:
    """Port patterns of a delay line's object argument: [get_ports {a b}], [get_ports a], $VAR, [all_inputs] ..."""
    out: list[str] = []
    for m in re.finditer(r"\[\s*get_ports\s+(\{[^}]*\}|\S+?)\s*\]", arg):
        out += m.group(1).strip("{}").split()
    for m in re.finditer(r"\$(\w+)", arg):
        out += vars_.get(m.group(1), [])
    if re.search(r"\[\s*all_inputs\s*\]", arg):
        out.append("<all_inputs>")
    if re.search(r"\[\s*all_outputs\s*\]", arg):
        out.append("<all_outputs>")
    return out


def _comments_above(lines: list[str], n: int) -> list[str]:
    return [l for l in lines[max(0, n - 9):n - 1] if l.lstrip().startswith("#")]


def parse_xdc_delays(files: list[Path] | list[tuple[str, str]]) -> dict[str, Any]:
    """The delay lines, clock definitions and port false paths of the XDC files (paths, or (name, text) pairs), in
    read order."""
    delays, clocks, false_paths = [], [], []
    order = 0
    for f in files:
        if isinstance(f, tuple):
            f, text = Path(f[0]), f[1]
        else:
            try:
                text = Path(f).read_text(errors="replace")
            except OSError:
                continue
        lines = text.splitlines()
        vars_: dict[str, list[str]] = {}
        for n, raw in enumerate(lines, 1):
            code = raw.split("#", 1)[0] if not raw.lstrip().startswith("#") else ""
            for stmt in (s.strip() for s in code.split(";") if s.strip()):
                order += 1
                mv = re.match(r"set\s+(\w+)\s+(\[.*\])\s*$", stmt)
                if mv:
                    vars_[mv.group(1)] = _ports_in(mv.group(2), vars_)
                    continue
                md = _DELAY.match(stmt)
                if md:
                    rest = md.group(2)
                    ck = re.search(r"-clock\s+(\[get_clocks\s+(\{[^}]*\}|\S+?)\s*\]|\{[^}]*\}|\S+)", rest)
                    clock = ck.group(2) if ck and ck.group(2) else (ck.group(1) if ck else None)
                    clock = clock.strip("{} ") if clock else None
                    body = re.sub(r"\[[^\]]*\]|\$\w+|-clock\s+\S+", " ", rest)
                    nums = re.findall(r"(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])", body)
                    kinds = [k for k in ("max", "min") if re.search(rf"-{k}\b", rest)] or ["max", "min"]
                    delays.append({"file": Path(f).name, "line": n, "text": raw.strip(), "order": order,
                                   "dir": "in" if md.group(1) == "set_input_delay" else "out", "clock": clock,
                                   "kinds": kinds, "fall": bool(re.search(r"-clock_fall\b", rest)),
                                   "add": bool(re.search(r"-add_delay\b", rest)),
                                   "value": float(nums[0]) if nums else None, "ports": _ports_in(rest, vars_),
                                   "comments": _comments_above(lines, n)})
                    continue
                mc = _CLOCKDEF.match(stmt)
                if mc:
                    nm = re.search(r"-name\s+(\S+)", mc.group(1))
                    per = re.search(r"-period\s+([\d.]+)", mc.group(1))
                    clocks.append({"file": Path(f).name, "line": n, "order": order, "name": nm.group(1) if nm else None,
                                   "period": float(per.group(1)) if per else None,
                                   "virtual": not re.search(r"get_ports|get_pins|get_nets", mc.group(1)),
                                   "comments": _comments_above(lines, n)})
                    continue
                if re.match(r"set_false_path\b", stmt):
                    for side in ("from", "to"):
                        m = re.search(rf"-{side}\s+(\[get_ports[^\]]*\]|\$\w+)", stmt)
                        if m:
                            false_paths.append({"file": Path(f).name, "line": n, "ports": _ports_in(m.group(1), vars_)})
    # a delay written without -add_delay replaces the earlier ones of the same kind (-max/-min) on the same ports and clock,
    # whatever their clock edge (fixture I5b: falling-edge lines without -add_delay left only falling-edge launches timed)
    for i, x in enumerate(delays):
        if x["add"]:
            continue
        for y in delays[:i]:
            if (y.get("replaced_by") is None and y["dir"] == x["dir"] and y["clock"] == x["clock"]
                    and sorted(y["ports"]) == sorted(x["ports"]) and set(y["kinds"]) & set(x["kinds"])):
                y["replaced_by"] = x["line"]
    return {"delays": delays, "clocks": clocks, "false_paths": false_paths}


def port_match(pattern: str, name: str) -> bool:
    """Vivado get_ports pattern (``*`` and ``?`` wild, brackets literal) against a port name."""
    if pattern == "<all_inputs>" or pattern == "<all_outputs>":
        return False
    rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(rx, name) is not None


# --- the dump ---------------------------------------------------------------------------------------------------------

def parse_io_dump(text: str) -> dict[str, Any]:
    if "# end" not in text:
        raise ValueError("io_paths dump truncated (no '# end')")
    out: dict[str, Any] = {"clocks": {}, "ports": {}, "worst": {}, "errors": []}

    def num(x: str) -> float | None:
        try:
            return float(x)
        except ValueError:
            return None
    for line in text.splitlines():
        f = line.split("|")
        if f[0] == "CLOCK" and len(f) >= 7:
            out["clocks"][f[1]] = {"period": num(f[2]), "waveform": f[3], "virtual": f[4] == "1",
                                   "generated": f[5] == "1", "source": f[6], "input_jitter": num(f[7]) if len(f) > 7 else None}
        elif f[0] == "PORT" and len(f) >= 6:
            out["ports"][f[1]] = {"dir": f[2], "iob": f[3], "register": f[4], "sync": f[5] == "1",
                                  "prim": f[6] if len(f) > 6 else "", "paths": {}}
        elif f[0] == "IO" and len(f) >= 11 and f[1] in out["ports"]:
            out["ports"][f[1]]["paths"][f[3]] = {"slack": num(f[4]), "requirement": num(f[5]), "io_delay": num(f[6]),
                                                 "start_clock": f[7], "end_clock": f[8], "corner": f[9],
                                                 "uncertainty": num(f[10])}
        elif f[0] == "NOIO" and len(f) >= 4 and f[1] in out["ports"]:
            out["ports"][f[1]]["paths"][f[3]] = None
        elif f[0] == "WORST" and len(f) >= 9:
            out["worst"][f[1]] = {"slack": num(f[2]), "requirement": num(f[3]), "start_clock": f[4], "end_clock": f[5],
                                  "corner": f[6], "uncertainty": num(f[7]), "pessimism": num(f[8]),
                                  "from": f[9] if len(f) > 9 else "", "to": f[10] if len(f) > 10 else ""}
        elif f[0] == "ERROR":
            out["errors"].append(line)
    return out


_UNC = re.compile(r"Clock Uncertainty:\s*(-?[\d.]+)ns\s*(.*)$", re.M)
_UNC_PARTS = {"tsj_ns": r"Total System Jitter\s+\(TSJ\):\s*(-?[\d.]+)ns", "tij_ns": r"Total Input Jitter\s+\(TIJ\):\s*(-?[\d.]+)ns",
              "dj_ns": r"Discrete Jitter\s+\(DJ\):\s*(-?[\d.]+)ns", "pe_ns": r"Phase Error\s+\(PE\):\s*(-?[\d.]+)ns",
              "user_ns": r"User Uncertainty\s+\(UU\):\s*(-?[\d.]+)ns"}


def parse_uncertainty(report_text: str) -> dict[str, Any] | None:
    """The first path's Clock Uncertainty line of a report_timing report and its parts (TSJ, TIJ, DJ, PE, UU)."""
    m = _UNC.search(report_text)
    if not m:
        return None
    out: dict[str, Any] = {"total_ns": float(m.group(1)), "formula": m.group(2).strip()}
    tail = report_text[m.end():m.end() + 800]
    for k, rx in _UNC_PARTS.items():
        p = re.search(rx, tail)
        if p:
            out[k] = float(p.group(1))
    for k, rx in (("pessimism_ns", r"Clock Pessimism Removal \(CPR\):\s*(-?[\d.]+)ns"),
                  ("requirement_ns", r"Requirement:\s*(-?[\d.]+)ns"), ("slack_ns", r"^Slack \(\w+\)\s*:\s*(-?[\d.]+)ns")):
        p = re.search(rx, report_text, re.M)
        if p:
            out[k] = float(p.group(1))
    return out


# --- interfaces ---------------------------------------------------------------------------------------------------------

def load_interfaces(*yaml_files: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """``io_interfaces`` from the given spec.yaml / build.yaml files (first that has any), the spec's async ports, and the
    problems found reading them."""
    ifs: list[dict[str, Any]] = []
    async_ports: list[str] = []
    errs: list[str] = []
    for p in yaml_files:
        if not p or not Path(p).is_file():
            continue
        try:
            data = yaml.safe_load(Path(p).read_text()) or {}
        except yaml.YAMLError as e:
            errs.append(f"{Path(p).name}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        for port in data.get("ports") or []:
            if isinstance(port, dict) and port.get("async") and port.get("name"):
                async_ports.append(str(port["name"]))
        if not ifs and isinstance(data.get("io_interfaces"), list):
            for i in data["io_interfaces"]:
                if not isinstance(i, dict):
                    errs.append(f"{Path(p).name}: io_interfaces entry is not a mapping")
                    continue
                if i.get("kind") not in KINDS:
                    errs.append(f"{Path(p).name}: io_interfaces {i.get('name')!r}: kind must be one of {', '.join(KINDS)}")
                    continue
                ifs.append(i)
    return ifs, async_ports, errs


_DDR_PRIM = re.compile(r"^(IDDR|ODDR|IDDR_2CLK|IDDRE1|ODDRE1|ISERDESE[1-3]|OSERDESE[1-3])$")


def expected_delays(i: dict[str, Any]) -> dict[str, float] | None:
    """The -max and -min the interface's data sheet gives (None when it gives no numbers):
    input, SDR: max = tCO_max + trace_max, min = tCO_min + trace_min; output: max = tSU + trace_max, min = -tH + trace_min;
    input, DDR centre-aligned (data valid before/after each edge): max = T/2 - dv_before, min = dv_after;
    input, DDR edge-aligned (skew before/after each edge): max = skew_after, min = -skew_before;
    output, DDR edge-aligned with a forwarded clock: max = T/2 - skew_after, min = +skew_before (an output's hold
      required time is the clock edge minus -min, so a positive -min lets the data change that long before the edge;
      a negative one would demand it change after the edge). An optional board_skew_ns (clock-to-data trace skew on
      the board, either sign) narrows both sides: skew_after and skew_before each lose it."""
    ds = i.get("data_sheet") or {}
    if not ds:
        return None
    tr = float(ds.get("trace_ns", 0.0))
    tmin, tmax = float(ds.get("trace_min_ns", tr)), float(ds.get("trace_max_ns", tr))
    try:
        if i.get("direction") == "out" and "skew_after_ns" in ds:      # edge-aligned DDR output (forwarded clock)
            half = float(i["clock_period_ns"]) / 2
            b = float(ds.get("board_skew_ns", 0.0))
            return {"max": round(half - (float(ds["skew_after_ns"]) - b), 6),
                    "min": round(float(ds["skew_before_ns"]) - b, 6)}
        if i.get("direction") == "out":
            return {"max": float(ds["tsu_ns"]) + tmax, "min": -float(ds["th_ns"]) + tmin}
        if "dv_before_ns" in ds:
            half = float(i["clock_period_ns"]) / 2
            return {"max": half - float(ds["dv_before_ns"]), "min": float(ds["dv_after_ns"])}
        if "skew_before_ns" in ds:
            return {"max": float(ds["skew_after_ns"]), "min": -float(ds["skew_before_ns"])}
        return {"max": float(ds["tco_max_ns"]) + tmax, "min": float(ds["tco_min_ns"]) + tmin}
    except (KeyError, TypeError, ValueError):
        return None


def ddr_requirements(i: dict[str, Any]) -> dict[str, float] | None:
    """The setup (max) and hold (min) requirements Vivado must apply to a DDR interface's ports when its edges are
    paired as intended (None when the interface declares nothing to check):
    centre-aligned input (data_sheet dv_before/dv_after): each edge's data is captured by the next opposite edge, setup
      requirement T/2, and must hold past the same edge it was launched around, hold requirement 0;
    edge-aligned input or output (data_sheet skew_before/skew_after, the clock in phase): the same, T/2 and 0;
    output with a forwarded clock forwarded_phase_deg later than the data clock: the same-edge forwarded clock captures,
      setup requirement T * phase / 360, hold requirement that minus T/2.
    A full-period setup requirement means the exceptions keep the wrong edge pairs (the flow's B3 finding)."""
    if not i.get("ddr") or not i.get("clock_period_ns"):
        return None
    t = float(i["clock_period_ns"])
    ds = i.get("data_sheet") or {}
    if i.get("direction") != "out" and "dv_before_ns" in ds:
        return {"max": t / 2, "min": 0.0}
    if i.get("direction") != "out" and "skew_before_ns" in ds:       # edge-aligned input: the same pairing
        return {"max": t / 2, "min": 0.0}
    if i.get("direction") == "out" and "skew_after_ns" in ds:       # edge-aligned output: the opposite edge sets up,
        return {"max": t / 2, "min": 0.0}                           # the same edge holds
    if i.get("direction") == "out" and i.get("forwarded_phase_deg") is not None:
        ph = t * float(i["forwarded_phase_deg"]) / 360.0
        return {"max": ph, "min": ph - t / 2}
    return None


def _iface_ports(i: dict[str, Any], names: list[str]) -> list[str]:
    pats = i.get("ports") or []
    pats = [pats] if isinstance(pats, str) else pats
    return [n for n in names if any(port_match(str(p), n) or fnmatch.fnmatchcase(n, str(p)) for p in pats)]


def static_findings(xdc: list[tuple[str, str]], slow_ports: list[str] | None = None,
                    async_ports: list[str] | None = None) -> list[dict[str, Any]]:
    """The rules that need only the XDC text (no Vivado): IO-INVENTED, IO-NO-FORMULA, IO-MIN-GT-MAX, IO-REPLACED, and a clock used
    by a delay before its create_clock (IO-CLOCK-ORDER: Vivado drops the delay with CRITICAL WARNING 12-4739)."""
    r = evaluate(None, "synth", xdc, [], async_ports, slow_ports)       # type: ignore[arg-type]
    out = [f for f in r["failures"] if f["rule"] in ("IO-INVENTED", "IO-NO-FORMULA", "IO-MIN-GT-MAX", "IO-REPLACED",
                                                     "IO-VCLK-UNRELATED")]
    parsed = parse_xdc_delays(xdc)
    first = {}
    for c in parsed["clocks"]:
        first.setdefault(c["name"], c["order"])
    for x in parsed["delays"]:
        if x["clock"] and x["clock"] in first and first[x["clock"]] > x["order"]:
            out.append({"rule": "IO-CLOCK-ORDER", "file": x["file"], "line": x["line"], "text": x["text"],
                        "message": f"clock {x['clock']} is used here before its create_clock: Vivado drops the delay"})
    return out


# --- the check ---------------------------------------------------------------------------------------------------------

def evaluate(build_dir: Path | None, stage: str = "route", xdc_files: list[Path] | None = None,
             interfaces: list[dict[str, Any]] | None = None, async_ports: list[str] | None = None,
             slow_ports: list[str] | None = None, dump: Path | None = None) -> dict[str, Any]:
    d = Path(build_dir) if build_dir else None
    if xdc_files is None and d is not None:
        prep = json.loads((d / "prepare.json").read_text()) if (d / "prepare.json").exists() else {}
        root = Path(__file__).resolve().parents[1]
        xdc_files = [root / x for x in prep.get("files") or [] if str(x).endswith(".xdc")]
    xdc = parse_xdc_delays(xdc_files or [])
    interfaces = interfaces or []
    slow_rx = [re.compile(p) for p in (slow_ports if slow_ports is not None else DEFAULT_SLOW)]
    async_set = {re.sub(r"\[.*$", "", a) for a in (async_ports or [])}
    fails: list[dict[str, Any]] = []

    def fail(rule: str, where: dict[str, Any] | None, msg: str) -> None:
        w = where or {}
        fails.append({"rule": rule, "file": w.get("file"), "line": w.get("line"), "text": w.get("text"), "message": msg})

    dump_p = dump or (d / f"io_paths_{stage}.txt" if d else None)
    io: dict[str, Any] | None = None
    if dump_p is not None and dump_p.exists():
        try:
            io = parse_io_dump(dump_p.read_text(errors="replace"))
            for e in io["errors"][:3]:
                fail("IO-DUMP", None, f"flow/io_paths.tcl could not evaluate: {e[:200]}")
        except ValueError as e:
            fail("IO-DUMP", None, str(e))
    port_names = sorted(io["ports"]) if io else sorted({p for x in xdc["delays"] for p in x["ports"]
                                                        if not p.startswith("<")})

    def ports_of(x: dict[str, Any]) -> list[str]:
        if io:
            out = [n for n in port_names for p in x["ports"] if port_match(p, n)]
            if "<all_inputs>" in x["ports"]:
                out += [n for n, v in io["ports"].items() if v["dir"] == "in"]
            if "<all_outputs>" in x["ports"]:
                out += [n for n, v in io["ports"].items() if v["dir"] == "out"]
            return sorted(set(out)) or [p for p in x["ports"] if not p.startswith("<")]
        return [p for p in x["ports"] if not p.startswith("<")]

    iface_of: dict[str, dict[str, Any]] = {}
    for i in interfaces:
        for n in _iface_ports(i, port_names or [p for x in xdc["delays"] for p in ports_of(x)]):
            iface_of[n] = i

    # IO-FWD-SOURCE: the forwarded clock an interface is timed against is defined from the declared pin
    gens: dict[str, list[tuple[str | None, dict[str, Any]]]] = {}
    for f in xdc_files or []:
        name_, text_ = (f[0], f[1]) if isinstance(f, tuple) else (str(f), Path(f).read_text(errors="replace"))
        for n, raw in enumerate(text_.splitlines(), 1):
            code = raw.split("#", 1)[0]
            if re.match(r"\s*create_generated_clock\b", code):
                nm = re.search(r"-name\s+(\S+)", code)
                src = re.search(r"-source\s+\[\s*get_pins\s+(\{[^}]*\}|\S+?)\s*\]", code)
                if nm:
                    gens.setdefault(nm.group(1), []).append(
                        (src.group(1).strip("{} ") if src else None,
                         {"file": Path(name_).name, "line": n, "text": raw.strip()}))
    for i in interfaces:
        want = i.get("forwarded_clock_source")
        if not want:
            continue
        got = gens.get(i.get("clock") or "")
        if not got:
            fail("IO-FWD-SOURCE", None, f"interface {i.get('name')}: no create_generated_clock defines {i.get('clock')}")
            continue
        for src, where in got:
            if src != want:
                fail("IO-FWD-SOURCE", where, f"interface {i.get('name')}: {i.get('clock')} is generated from {src}, "
                     f"the interface declares {want}")

    # IO-DDR-UNDECLARED: every DDR data port must belong to a declared DDR interface with data-sheet values, so the
    # edge-pairing check (IO-DDR-REQUIREMENT) cannot be skipped by leaving the declaration out. A DDR port is one
    # whose register next to the pin is a DDR primitive (Vivado's dump), or that has delays on both clock edges; a
    # forwarded clock's own pin (a clock defined on the port) is not data.
    edges: dict[str, set[bool]] = {}
    for x in xdc["delays"]:
        for n in ports_of(x):
            edges.setdefault(n, set()).add(bool(x["fall"]))
    ddr_ports = {n for n, e in edges.items() if e == {True, False}}
    if io:
        ddr_ports |= {n for n, v in io["ports"].items() if _DDR_PRIM.match(v.get("prim") or "")}
        ddr_ports -= {c["source"] for c in io["clocks"].values()}
    undeclared = [n for n in sorted(ddr_ports)
                  if not (iface_of.get(n, {}).get("ddr") and iface_of.get(n, {}).get("data_sheet"))]
    if undeclared:
        fail("IO-DDR-UNDECLARED", None, f"{len(undeclared)} DDR port(s) not in a declared DDR interface with data-sheet "
             f"values (io_interfaces: ddr: true, data_sheet), so their edge pairing is unchecked: "
             f"{', '.join(undeclared[:6])}")

    def is_slow(n: str) -> bool:
        base = re.sub(r"\[.*$", "", n)
        i = iface_of.get(n)
        if i is not None:
            return False
        probe = n.replace("*", "0").replace("?", "0")     # a pattern (no dump): a representative name
        return base in async_set or n in async_set or any(r.fullmatch(probe) for r in slow_rx)

    # per delay line
    for x in xdc["delays"]:
        ps = ports_of(x)
        nonzero = x["value"] is not None and abs(x["value"]) > 1e-9
        if nonzero and ps and all(is_slow(p) for p in ps):
            fail("IO-INVENTED", x, f"{'input' if x['dir'] == 'in' else 'output'} delay {x['value']:g} ns on "
                 f"{', '.join(ps[:6])}, asynchronous or slow port(s) with no timing relationship")
        elif nonzero and not any(_FORMULA.search(c) for c in x["comments"]):
            fail("IO-NO-FORMULA", x, f"delay {x['value']:g} ns with no comment above naming the data-sheet terms "
                                     f"(tCO, tSU, tH, trace, skew, data valid) it is derived from")
    for x in xdc["delays"]:
        if x.get("replaced_by"):
            fail("IO-REPLACED", x, f"replaced by line {x['replaced_by']}, which has no -add_delay: Vivado keeps only the later "
                 f"{'/'.join('-' + k for k in x['kinds'])} delay on these ports and clock")
    # min > max on the same port set, clock and edge
    seen: dict[tuple, dict[str, Any]] = {}
    for x in xdc["delays"]:
        for k in x["kinds"]:
            seen.setdefault((x["dir"], tuple(sorted(x["ports"])), x["clock"], x["fall"]), {})[k] = x
    for key, kv in seen.items():
        if "max" in kv and "min" in kv and kv["min"]["value"] is not None and kv["max"]["value"] is not None \
                and kv["min"] is not kv["max"] and kv["min"]["value"] > kv["max"]["value"] + 1e-9:
            fail("IO-MIN-GT-MAX", kv["min"], f"-min {kv['min']['value']:g} ns is larger than -max {kv['max']['value']:g} ns "
                 f"(line {kv['max']['line']}) for the same ports, clock and edge")
    # virtual clocks with no related design clock
    clk_periods = [c["period"] for c in xdc["clocks"] if not c["virtual"] and c["period"]]
    if io:
        clk_periods += [v["period"] for v in io["clocks"].values() if not v["virtual"] and v["period"]]
    for c in xdc["clocks"]:
        if c["virtual"] and c["period"] and clk_periods and not c["comments"]:
            rel = any(abs(c["period"] / p - round(c["period"] / p)) < 1e-6 or abs(p / c["period"] - round(p / c["period"])) < 1e-6
                      for p in clk_periods)
            if not rel:
                fail("IO-VCLK-UNRELATED", {"file": c["file"], "line": c["line"], "text": f"create_clock -name {c['name']}"},
                     f"virtual clock {c['name']} ({c['period']:g} ns) has no design clock at the same or an integer-ratio "
                     f"period, and no comment above it")
    # per synchronous interface
    report: list[dict[str, Any]] = []
    for i in interfaces:
        ps = _iface_ports(i, port_names) or [str(p) for p in (i.get("ports") or [])]
        kind, name = i.get("kind"), i.get("name") or "?"
        mine = [x for x in xdc["delays"] if set(ports_of(x)) & set(ps) and not x.get("replaced_by")]
        fp = [f for f in xdc["false_paths"] if any(port_match(p, n) for p in f["ports"] for n in ps)]
        entry: dict[str, Any] = {"name": name, "kind": kind, "ports": ps, "clock": i.get("clock")}
        if kind == "asynchronous":
            nz = [x for x in mine if x["value"] and abs(x["value"]) > 1e-9]
            no_sync = [p for p in ps if not (io and io["ports"].get(p, {}).get("sync"))]
            if nz and no_sync:
                fail("IO-ASYNC-CLOCK", nz[0], f"interface {name}: its device has its own clock (asynchronous), so a delay "
                     f"relative to {nz[0]['clock']} has no fixed phase; {', '.join(no_sync[:4])} has no synchroniser")
            report.append(entry)
            continue
        edges = sorted({x["fall"] for x in mine}) or [False]
        for fall in edges:
            have = {k for x in mine if x["fall"] == fall for k in x["kinds"]}
            vals = [x for x in mine if x["fall"] == fall]
            if not vals:
                fail("IO-MISSING-MINMAX", None, f"interface {name}: no {'input' if i.get('direction') != 'out' else 'output'} "
                     f"delay on {', '.join(ps[:4])}")
            elif all(abs(x["value"] or 0) < 1e-9 for x in vals) and not any(re.search(r"-(max|min)\b", x["text"]) for x in vals):
                fail("IO-PLACEHOLDER", vals[0], f"interface {name} is synchronous: a 0 ns placeholder is not a delay")
            elif have != {"max", "min"}:
                fail("IO-MISSING-MINMAX", vals[0], f"interface {name}: {'falling' if fall else 'rising'}-edge delay has "
                     f"{'/'.join('-' + k for k in sorted(have))} only; both -max and -min are needed (the hold check uses -min)")
            exp = expected_delays(i)
            if exp and have == {"max", "min"}:
                for x in vals:
                    for k in x["kinds"]:
                        if x["value"] is not None and abs(x["value"] - exp[k]) > _TOL:
                            fail("IO-VALUE", x, f"interface {name}: -{k} {x['value']:g} ns, the data sheet gives "
                                 f"{exp[k]:g} ns")
        if i.get("ddr") and len(edges) < 2:
            fail("IO-MISSING-MINMAX", mine[0] if mine else None, f"interface {name} is DDR: delays are needed for both edges "
                 f"(-clock_fall -add_delay)")
        for x in mine:
            if i.get("clock") and x["clock"] != i["clock"]:
                fail("IO-CLOCK", x, f"interface {name}: delay relative to {x['clock']}, the interface's clock is {i['clock']}")
        for f in fp:
            fail("IO-PLACEHOLDER", {"file": f["file"], "line": f["line"], "text": "set_false_path"},
                 f"interface {name} is synchronous: a false path on its ports removes its timing")
        if io and i.get("clock") in io["clocks"] and i.get("clock_period_ns"):
            per = io["clocks"][i["clock"]]["period"]
            if per is not None and abs(per - float(i["clock_period_ns"])) > 1e-3:
                fail("IO-CLOCK", None, f"interface {name}: clock {i['clock']} has period {per:g} ns, the interface's is "
                     f"{float(i['clock_period_ns']):g} ns")
        if io and stage == "route":
            setup = [io["ports"][p]["paths"].get("max") for p in ps if p in io["ports"]]
            hold = [io["ports"][p]["paths"].get("min") for p in ps if p in io["ports"]]
            def timed(p: str, k: str) -> bool:      # a path object with no slack is an unconstrained path (V4)
                x = io["ports"][p]["paths"].get(k)
                return bool(x) and x.get("slack") is not None
            missing = [p for p in ps if p in io["ports"] and not (timed(p, "max") and timed(p, "min"))]
            if missing and not fp:
                kind_ = "setup" if any(not timed(p, "max") for p in missing) else "hold"
                fail("IO-NO-PATH", None, f"interface {name}: no timed {kind_} path in Vivado's analysis for "
                     f"{', '.join(missing[:4])}")
            s = [p["slack"] for p in setup if p and p["slack"] is not None]
            h = [p["slack"] for p in hold if p and p["slack"] is not None]
            entry.update({"setup_slack_ns": min(s) if s else None, "hold_slack_ns": min(h) if h else None})
            req = ddr_requirements(i)
            if i.get("ddr") and not req:
                fail("IO-DDR-REQUIREMENT", None, f"interface {name} is DDR but declares nothing its edge pairing can be "
                     f"checked against (data_sheet dv_before/dv_after or skew_before/skew_after, or forwarded_phase_deg)")
            if req:
                got = {"max": sorted({p["requirement"] for p in setup if p and p.get("requirement") is not None}),
                       "min": sorted({p["requirement"] for p in hold if p and p.get("requirement") is not None})}
                entry["requirements_ns"] = got
                for k, want in req.items():
                    off = [r for r in got[k] if abs(r - want) > 0.011]
                    if off:
                        fail("IO-DDR-REQUIREMENT", None, f"interface {name}: {'setup' if k == 'max' else 'hold'} "
                             f"requirement {', '.join(f'{r:g}' for r in off)} ns, the intended edge pairing gives "
                             f"{want:g} ns (a full-period setup requirement means the wrong edges are paired)")
            if i.get("iob"):
                bad = [p for p in ps if p in io["ports"] and io["ports"][p]["iob"] != "1"]
                entry["iob_packed"] = not bad
                if bad:
                    fail("IO-IOB", None, f"interface {name}: the register of {', '.join(bad[:4])} is not in the IOB")
        report.append(entry)
    out: dict[str, Any] = {"stage": stage, "pass": not fails, "interfaces": report, "failures": fails,
                           "delays": len(xdc["delays"])}
    if io:
        out["clocks"] = io["clocks"]
        out["worst"] = io["worst"]
    if d is not None and stage == "route":
        unc = {}
        for k, f in (("setup", "timing_worst_setup.rpt"), ("hold", "timing_worst_hold.rpt")):
            if (d / f).exists():
                unc[k] = parse_uncertainty((d / f).read_text(errors="replace"))
        out["uncertainty"] = unc
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("build_dir", type=Path)
    ap.add_argument("--stage", choices=["synth", "route"], default="route")
    ap.add_argument("--xdc", type=Path, nargs="*")
    ap.add_argument("--interfaces", type=Path, nargs="*", help="spec.yaml / build.yaml with io_interfaces")
    a = ap.parse_args(argv)
    ifs, asy, _ = load_interfaces(*(a.interfaces or []))
    r = evaluate(a.build_dir, a.stage, a.xdc, ifs, asy)
    print(json.dumps(r, indent=2))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
