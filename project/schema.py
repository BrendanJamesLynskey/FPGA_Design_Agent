#!/usr/bin/env python3
"""Checkers for the project files (brief 27 Part B, P0): ``design.yaml``, ``modules/<m>/contract.yaml`` and
``system/requirements.yaml``. Formats: ``docs/project_layer.md``.

Three levels, each a pure function that returns a list of problems (empty: the file can be read):

1. :func:`check_contract` - one contract on its own: parameters, clocks, resets, ports, interfaces (AXI4-Stream,
   AXI4-Lite, the test shell's register window), registers, data formats, latency and throughput, and that every
   interface's ports are in the port list with the right direction and width;
2. :func:`check_design` - ``design.yaml`` on its own: the clock and reset plan, the module list, the shell, the
   connections and board ports as references;
3. :func:`check_project` - the two together and the board: each module's clocks and resets bound to the plan, both
   ends of every connection compatible (protocol, widths, ``tuser`` and ``tlast`` meaning, back-pressure, gaps), a
   CDC primitive at every crossing and only there, the register window without overlaps, board port names against
   the board's master XDC with their widths, and the requirements' module references.

    python3 -m project check <dir> [--json OUT]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent.graph.spec_schema import PROOF_METHODS, requirement_errors
from flow.architecture import CDC_PRIMITIVES, PROTOCOLS
from project.expr import ExprError, evaluate, names

ROOT = Path(__file__).resolve().parents[1]
DESIGN_SCHEMA = "fpga-design-agent/project/v1"
CONTRACT_SCHEMA = "fpga-design-agent/contract/v1"
REQUIREMENTS_SCHEMA = "fpga-design-agent/requirements/v1"

KINDS = ("rtl", "ipgen", "lib")              # module kinds; only rtl needs a contract.yaml in P0
ACCESS = ("RW", "RO", "WO", "W1C")
POLARITY = ("active_high", "active_low")
RESET_STYLE = ("sync", "async")
CLOCK_SOURCES = ("board", "mmcm", "pll")
DRIVES = ("push-pull", "open-drain", "pulled-up", "input")
ROLES = ("master", "slave")
WINDOW_WORDS = 0x80                          # the shell's design window, 0x80-0xFF (shell/PROTOCOL.md)
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FORMAT = re.compile(r"^(?P<s>[us])(?P<i>\d+)(?:\.(?P<f>\d+))?$")
_BUS = re.compile(r"^(?P<n>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<hi>\d+)(?::(?P<lo>\d+))?\])?$")

#: the AXI4-Lite signals and which side drives them (from flow/standards_check.py's STD-AXI-01 rule)
AXIL_SIGNALS = ("awaddr", "awvalid", "awready", "wdata", "wstrb", "wvalid", "wready", "bresp", "bvalid", "bready",
                "araddr", "arvalid", "arready", "rdata", "rresp", "rvalid", "rready")
AXIL_SLAVE_OUT = {"awready", "wready", "bresp", "bvalid", "arready", "rdata", "rresp", "rvalid"}


# ---- helpers ------------------------------------------------------------------------------------------------------
def load_yaml(p: Path) -> tuple[Any, str | None]:
    if not p.is_file():
        return None, f"{p.name} does not exist"
    try:
        return yaml.safe_load(p.read_text()), None
    except yaml.YAMLError as e:
        return None, f"{p.name} is not valid YAML: {' '.join(str(e).split())}"


def fmt_width(fmt: str) -> int | None:
    """``u8`` -> 8, ``s16`` -> 16, ``s1.15`` -> 16 (Q format: integer bits including the sign, then fraction bits)."""
    m = _FORMAT.match(str(fmt))
    return None if not m else int(m["i"]) + int(m["f"] or 0)


def _bits(v: Any) -> tuple[int, int] | None:
    if (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in v)
            and v[0] >= v[1] >= 0):
        return v[0], v[1]
    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
        return v, v
    return None


def params_of(contract: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, int]:
    """The parameter values: each default, then the design's overrides."""
    out = {p["name"]: p.get("default") for p in contract.get("parameters") or [] if isinstance(p, dict) and "name" in p}
    out.update(overrides or {})
    return {k: v for k, v in out.items() if isinstance(v, int) and not isinstance(v, bool)}


def port_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in contract.get("ports") or [] if isinstance(p, dict) and p.get("name")}


def iface_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["name"]: f for f in contract.get("interfaces") or [] if isinstance(f, dict) and f.get("name")}


def iface_ports(f: dict[str, Any]) -> dict[str, tuple[str, Any]]:
    """{port name: (direction, width expression)} an interface needs, from its protocol, role and prefix."""
    pre, proto, role = f.get("prefix", ""), f.get("protocol"), f.get("role")
    out: dict[str, tuple[str, Any]] = {}
    if proto == "axi4-stream":
        src = "out" if role == "master" else "in"
        snk = "in" if role == "master" else "out"
        out[f"{pre}_tvalid"] = (src, 1)
        out[f"{pre}_tready"] = (snk, 1)
        out[f"{pre}_tdata"] = (src, (f.get("tdata") or {}).get("width"))
        if f.get("tuser"):
            out[f"{pre}_tuser"] = (src, (f.get("tuser_width") or (max(int(b.get("bit", 0)) for b in f["tuser"]) + 1)))
        if f.get("tlast"):
            out[f"{pre}_tlast"] = (src, 1)
    elif proto == "axi4-lite":
        aw, dw = f.get("addr_width"), f.get("data_width", 32)
        widths = {"awaddr": aw, "araddr": aw, "wdata": dw, "rdata": dw, "wstrb": (dw // 8 if isinstance(dw, int) else None),
                  "bresp": 2, "rresp": 2}
        for s in AXIL_SIGNALS:
            slave_out = s in AXIL_SLAVE_OUT
            d = ("out" if slave_out else "in") if role == "slave" else ("in" if slave_out else "out")
            out[f"{pre}_{s}"] = (d, widths.get(s, 1))
    elif proto == "simple" and f.get("kind") == "shell-window":
        out.update({f"{pre}_addr": ("in", 7), f"{pre}_wr": ("in", 1), f"{pre}_rd": ("in", 1),
                    f"{pre}_wdata": ("in", 32), f"{pre}_rdata": ("out", 32)})
    return out


# ---- contract.yaml ------------------------------------------------------------------------------------------------
def check_contract(c: Any, module: str | None = None) -> list[str]:
    """Problems with one contract (empty list: it can be read and is consistent with itself)."""
    if not isinstance(c, dict):
        return ["contract.yaml must be a YAML mapping at the top level"]
    e: list[str] = []
    if c.get("schema") != CONTRACT_SCHEMA:
        e.append(f"schema must be {CONTRACT_SCHEMA!r} (got {c.get('schema')!r})")
    if not c.get("module") or not _ID.match(str(c.get("module"))):
        e.append("'module' must be the module's name (an identifier)")
    elif module and c["module"] != module:
        e.append(f"module = {c['module']!r} but the directory is modules/{module}")

    # parameters
    pnames: set[str] = set()
    for i, p in enumerate(c.get("parameters") or []):
        if not isinstance(p, dict) or not p.get("name") or not _ID.match(str(p["name"])):
            e.append(f"parameters[{i}] must be a mapping with a 'name'")
            continue
        n = p["name"]
        if n in pnames:
            e.append(f"parameter {n} is declared twice")
        pnames.add(n)
        d = p.get("default")
        if not isinstance(d, int) or isinstance(d, bool):
            e.append(f"parameter {n}: 'default' must be an integer")
            continue
        if "values" in p and (not isinstance(p["values"], list) or d not in p["values"]):
            e.append(f"parameter {n}: 'values' must be a list that contains the default")
        lo, hi = p.get("min"), p.get("max")
        if lo is not None and hi is not None and not (isinstance(lo, int) and isinstance(hi, int) and lo <= d <= hi):
            e.append(f"parameter {n}: need integers min <= default <= max")
    params = params_of(c)

    def width_ok(w: Any, where: str) -> int | None:
        try:
            v = evaluate(w, params)
        except ExprError as x:
            e.append(f"{where}: width {x}")
            return None
        if v < 1:
            e.append(f"{where}: width must be at least 1 (got {v})")
            return None
        return v

    # clocks and resets
    clocks = {}
    for i, k in enumerate(c.get("clocks") or []):
        if not isinstance(k, dict) or not k.get("name") or not k.get("port"):
            e.append(f"clocks[{i}] must be a mapping with 'name' and 'port' (and max_mhz, the rate it must close at)")
            continue
        clocks[k["name"]] = k
        mhz = k.get("max_mhz")
        if mhz is not None and (not isinstance(mhz, (int, float)) or isinstance(mhz, bool) or mhz <= 0):
            e.append(f"clock {k['name']}: max_mhz must be a positive number")
    if not clocks:
        e.append("'clocks' must list at least one clock: {name, port, max_mhz}")
    resets = {}
    for i, r in enumerate(c.get("resets") or []):
        if not isinstance(r, dict) or not r.get("name") or not r.get("port"):
            e.append(f"resets[{i}] must be a mapping with 'name', 'port', 'clock', 'polarity', 'style'")
            continue
        resets[r["name"]] = r
        if r.get("clock") not in clocks:
            e.append(f"reset {r['name']}: clock {r.get('clock')!r} is not one of the contract's clocks")
        if r.get("polarity") not in POLARITY:
            e.append(f"reset {r['name']}: polarity must be one of {', '.join(POLARITY)}")
        if r.get("style") not in RESET_STYLE:
            e.append(f"reset {r['name']}: style must be one of {', '.join(RESET_STYLE)}")

    # ports
    ports = port_map(c)
    if len(ports) != len(c.get("ports") or []):
        seen: set[str] = set()
        for p in c.get("ports") or []:
            n = p.get("name") if isinstance(p, dict) else None
            if not n:
                e.append("every port must be a mapping with a 'name'")
            elif n in seen:
                e.append(f"port {n} is declared twice")
            seen.add(n) if n else None
    clock_ports = {k["port"] for k in clocks.values()}
    reset_ports = {r["port"]: r for r in resets.values()}
    widths: dict[str, int] = {}
    for n, p in ports.items():
        if p.get("dir") not in ("in", "out"):
            e.append(f"port {n}: dir must be 'in' or 'out'")
        w = width_ok(p.get("width", 1), f"port {n}")
        if w:
            widths[n] = w
        if n in clock_ports or n in reset_ports:
            if p.get("dir") != "in" or widths.get(n) != 1:
                e.append(f"port {n}: a clock or reset port is a 1-bit input")
            continue
        ck = p.get("clock")
        if ck != "async" and ck not in clocks:
            e.append(f"port {n}: clock {ck!r} is not one of the contract's clocks (or 'async')")
        rv = p.get("reset_value")
        if rv is not None:
            if p.get("dir") != "out":
                e.append(f"port {n}: reset_value is for outputs only")
            elif not isinstance(rv, int) or isinstance(rv, bool) or rv < 0 or (n in widths and rv >= 1 << widths[n]):
                e.append(f"port {n}: reset_value must be an integer that fits in the port")
    for k in clocks.values():
        if k["port"] not in ports:
            e.append(f"clock {k['name']}: port {k['port']} is not in the port list")
    for r in resets.values():
        if r["port"] not in ports:
            e.append(f"reset {r['name']}: port {r['port']} is not in the port list")

    # data formats
    formats: dict[str, int] = {}
    for i, d in enumerate(c.get("data_formats") or []):
        if not isinstance(d, dict) or not d.get("name") or not d.get("format"):
            e.append(f"data_formats[{i}] must be a mapping with 'name' and 'format' (u8, s16, s1.15 ...) and 'packing'")
            continue
        w = fmt_width(d["format"])
        if w is None:
            e.append(f"data format {d['name']}: format {d['format']!r} is not u<N>, s<N> or s<I>.<F> / u<I>.<F>")
        else:
            formats[d["name"]] = w

    def field_width(fmt: Any) -> int | None:
        return formats.get(str(fmt), fmt_width(str(fmt)))

    # interfaces
    ifaces = iface_map(c)
    for i, f in enumerate(c.get("interfaces") or []):
        if not isinstance(f, dict) or not f.get("name"):
            e.append(f"interfaces[{i}] must be a mapping with a 'name'")
            continue
        n = f["name"]
        where = f"interface {n}"
        if f.get("protocol") not in PROTOCOLS:
            e.append(f"{where}: protocol must be one of {', '.join(PROTOCOLS)}")
            continue
        if f.get("role") not in ROLES:
            e.append(f"{where}: role must be master or slave")
        if not f.get("prefix") or not _ID.match(str(f.get("prefix"))):
            e.append(f"{where}: needs a port 'prefix' (s_axis_video, s_axil, win ...)")
            continue
        if f.get("clock") not in clocks:
            e.append(f"{where}: clock {f.get('clock')!r} is not one of the contract's clocks")
        if f.get("reset") is not None and f["reset"] not in resets:
            e.append(f"{where}: reset {f['reset']!r} is not one of the contract's resets")
        if f["protocol"] == "axi4-stream":
            td = f.get("tdata")
            tw = width_ok(td.get("width"), f"{where}.tdata") if isinstance(td, dict) else None
            if not isinstance(td, dict):
                e.append(f"{where}: an AXI4-Stream interface needs tdata: {{width, fields}}")
            elif tw:
                used = 0
                for fl in td.get("fields") or []:
                    b = _bits(fl.get("bits")) if isinstance(fl, dict) else None
                    if not b or not fl.get("name"):
                        e.append(f"{where}.tdata: each field needs a 'name' and 'bits: [hi, lo]'")
                        continue
                    if b[0] >= tw:
                        e.append(f"{where}.tdata.{fl['name']}: bits {list(b)} outside the {tw}-bit tdata")
                    m = ((1 << (b[0] + 1)) - 1) ^ ((1 << b[1]) - 1)
                    if used & m:
                        e.append(f"{where}.tdata.{fl['name']}: bits {list(b)} overlap another field")
                    used |= m
                    if fl.get("format") is not None:
                        fw = field_width(fl["format"])
                        if fw is None:
                            e.append(f"{where}.tdata.{fl['name']}: format {fl['format']!r} is neither a data_formats "
                                     "name nor u<N>/s<N>/s<I>.<F>")
                        elif fw != b[0] - b[1] + 1:
                            e.append(f"{where}.tdata.{fl['name']}: format {fl['format']} is {fw} bits but the field "
                                     f"is {b[0] - b[1] + 1}")
            tu = f.get("tuser")
            if tu is not None:
                if not isinstance(tu, list) or not all(isinstance(b, dict) and isinstance(b.get("bit"), int)
                                                       and b.get("name") for b in tu):
                    e.append(f"{where}: tuser must be a list of {{bit, name, meaning}}")
                elif len({b["bit"] for b in tu}) != len(tu) or len({b["name"] for b in tu}) != len(tu):
                    e.append(f"{where}: tuser bits and names must be unique")
            if f.get("tlast") is not None and not isinstance(f["tlast"], str):
                e.append(f"{where}: tlast is the meaning of the last beat, as text (omit it if there is no tlast)")
            if "packet_beats" in f:
                if not f.get("tlast"):
                    e.append(f"{where}: packet_beats needs a tlast")
                try:
                    evaluate(f["packet_beats"], params)
                except ExprError as x:
                    e.append(f"{where}.packet_beats: {x}")
            for k in ("backpressure", "source_gaps"):
                if not isinstance(f.get(k), bool):
                    e.append(f"{where}: '{k}' must be true or false (backpressure: the sink may hold tready low; "
                             "source_gaps: the source may leave tvalid low between beats)")
        elif f["protocol"] == "axi4-lite":
            if not isinstance(f.get("addr_width"), int) or f["addr_width"] < 2:
                e.append(f"{where}: an AXI4-Lite interface needs addr_width (an integer >= 2)")
            if f.get("data_width", 32) not in (32, 64):
                e.append(f"{where}: data_width must be 32 or 64")
        elif f["protocol"] == "simple" and f.get("kind") == "shell-window":
            if f.get("role") != "slave":
                e.append(f"{where}: a shell window is always the slave side")
        for pn, (d, w) in iface_ports(f).items():
            if pn not in ports:
                e.append(f"{where}: port {pn} is missing from the port list")
                continue
            if ports[pn].get("dir") != d:
                e.append(f"{where}: port {pn} must be dir {d} for a {f.get('role')}")
            try:
                want = evaluate(w, params) if w is not None else None
            except ExprError:
                want = None
            if want is not None and widths.get(pn) not in (None, want):
                e.append(f"{where}: port {pn} is {widths[pn]} bits; the interface needs {want}")
            if ports[pn].get("clock") not in (f.get("clock"), None):
                e.append(f"{where}: port {pn} is on clock {ports[pn].get('clock')}, the interface on {f.get('clock')}")

    # registers
    regs = c.get("registers")
    if regs is not None:
        if not isinstance(regs, dict) or not isinstance(regs.get("map"), list):
            e.append("registers must be {bus: top | <interface>, map: [{name, offset, access, reset, fields}]}")
        else:
            bus = regs.get("bus")
            bus_if = ifaces.get(bus)
            if bus != "top" and not (bus_if and (bus_if.get("protocol") == "axi4-lite" or bus_if.get("kind") == "shell-window")):
                e.append(f"registers.bus = {bus!r}: 'top' (the generated top decodes the shell window) or the name of an "
                         "axi4-lite or shell-window interface of this contract")
            dw = (bus_if or {}).get("data_width", 32)
            step = dw // 8 if bus_if and bus_if.get("protocol") == "axi4-lite" else 1
            offs: dict[int, str] = {}
            rnames: set[str] = set()
            for i, r in enumerate(regs["map"]):
                if not isinstance(r, dict) or not r.get("name") or not isinstance(r.get("offset"), int):
                    e.append(f"registers.map[{i}] must be a mapping with 'name' and an integer 'offset'")
                    continue
                rn = r["name"]
                where = f"register {rn}"
                if rn in rnames:
                    e.append(f"{where} is declared twice")
                rnames.add(rn)
                if r["offset"] in offs:
                    e.append(f"{where}: offset {r['offset']:#x} is also {offs[r['offset']]}")
                offs[r["offset"]] = rn
                if r["offset"] % step:
                    e.append(f"{where}: offset {r['offset']:#x} is not aligned to {step} bytes")
                if bus_if and bus_if.get("protocol") == "axi4-lite" and r["offset"] >= 1 << bus_if.get("addr_width", 0):
                    e.append(f"{where}: offset {r['offset']:#x} does not fit addr_width {bus_if.get('addr_width')}")
                if bus == "top" or (bus_if and bus_if.get("kind") == "shell-window"):
                    if r["offset"] >= WINDOW_WORDS:
                        e.append(f"{where}: offset {r['offset']:#x} is outside the shell window (0x00-0x7f)")
                if r.get("access") not in ACCESS:
                    e.append(f"{where}: access must be one of {', '.join(ACCESS)}")
                width = r.get("width", dw)
                rv = r.get("reset", 0)
                if not isinstance(rv, int) or isinstance(rv, bool) or rv < 0 or rv >= 1 << width:
                    e.append(f"{where}: reset must be an integer that fits in {width} bits")
                used = 0
                for fl in r.get("fields") or []:
                    b = _bits(fl.get("bits")) if isinstance(fl, dict) else None
                    if not b or not fl.get("name"):
                        e.append(f"{where}: each field needs 'name' and 'bits: [hi, lo]'")
                        continue
                    m = ((1 << (b[0] + 1)) - 1) ^ ((1 << b[1]) - 1)
                    if b[0] >= width:
                        e.append(f"{where}.{fl['name']}: bits {list(b)} outside the {width}-bit register")
                    if used & m:
                        e.append(f"{where}.{fl['name']}: bits overlap another field")
                    used |= m
                    pn = fl.get("port")
                    if bus == "top":
                        if not pn:
                            e.append(f"{where}.{fl['name']}: with bus top every field names the module 'port' it "
                                     "drives (RW, WO) or is read from (RO)")
                        elif pn not in ports:
                            e.append(f"{where}.{fl['name']}: port {pn} is not in the port list")
                        else:
                            want = "out" if r.get("access") == "RO" else "in"
                            if ports[pn].get("dir") != want:
                                e.append(f"{where}.{fl['name']}: port {pn} must be dir {want} for access {r.get('access')}")
                            if widths.get(pn) not in (None, b[0] - b[1] + 1):
                                e.append(f"{where}.{fl['name']}: port {pn} is {widths[pn]} bits, the field "
                                         f"{b[0] - b[1] + 1}")

    # latency and throughput
    for i, L in enumerate(c.get("latency") or []):
        if not isinstance(L, dict) or L.get("from") not in ifaces or L.get("to") not in ifaces:
            e.append(f"latency[{i}] must be {{from: <interface>, to: <interface>, cycles: N | [lo, hi] | expression}}")
            continue
        cy = L.get("cycles")
        try:
            if isinstance(cy, list):
                if len(cy) != 2 or evaluate(cy[0], params) > evaluate(cy[1], params):
                    e.append(f"latency[{i}].cycles: a range is [lo, hi] with lo <= hi")
            elif evaluate(cy, params) < 0:
                e.append(f"latency[{i}].cycles must not be negative")
        except ExprError as x:
            e.append(f"latency[{i}].cycles: {x}")
    for i, t in enumerate(c.get("throughput") or []):
        if not isinstance(t, dict) or t.get("interface") not in ifaces:
            e.append(f"throughput[{i}] must be {{interface, beats_per_cycle, (from, out_per_in)}}")
            continue
        bpc = t.get("beats_per_cycle")
        if not isinstance(bpc, (int, float)) or isinstance(bpc, bool) or not 0 < bpc <= 1:
            e.append(f"throughput[{i}].beats_per_cycle must be in (0, 1]")
        if ("from" in t) != ("out_per_in" in t) or ("from" in t and t["from"] not in ifaces):
            e.append(f"throughput[{i}]: 'from' (an interface) and 'out_per_in' (output beats per input beat) go together")
    for n in sorted(set().union(*[names(p.get("width", 1)) for p in ports.values()]) - pnames) if ports else []:
        e.append(f"port widths use {n}, which is not a declared parameter")
    return e


# ---- design.yaml --------------------------------------------------------------------------------------------------
def check_design(d: Any) -> list[str]:
    """Problems with ``design.yaml`` on its own (references to contracts and the board: :func:`check_project`)."""
    if not isinstance(d, dict):
        return ["design.yaml must be a YAML mapping at the top level"]
    e: list[str] = []
    if d.get("schema") != DESIGN_SCHEMA:
        e.append(f"schema must be {DESIGN_SCHEMA!r} (got {d.get('schema')!r})")
    for k in ("name", "board"):
        if not d.get(k) or not _ID.match(str(d.get(k))):
            e.append(f"'{k}' must be an identifier")
    clocks: dict[str, dict[str, Any]] = {}
    for i, k in enumerate(d.get("clocks") or []):
        if not isinstance(k, dict) or not k.get("name") or k.get("source") not in CLOCK_SOURCES:
            e.append(f"clocks[{i}] must be {{name, source: {'|'.join(CLOCK_SOURCES)}, mhz, port (board) | from (mmcm, pll)}}")
            continue
        if k["name"] in clocks:
            e.append(f"clock {k['name']} is declared twice")
        clocks[k["name"]] = k
        if not isinstance(k.get("mhz"), (int, float)) or isinstance(k.get("mhz"), bool) or k["mhz"] <= 0:
            e.append(f"clock {k['name']}: mhz must be a positive number")
        if k["source"] == "board" and not k.get("port"):
            e.append(f"clock {k['name']}: a board clock names its board 'port'")
    for k in clocks.values():
        if k["source"] != "board" and k.get("from") not in clocks:
            e.append(f"clock {k['name']}: 'from' must be another declared clock (the MMCM or PLL input)")
    if not clocks:
        e.append("'clocks' must declare at least one clock")
    resets: dict[str, dict[str, Any]] = {}
    for i, r in enumerate(d.get("resets") or []):
        if not isinstance(r, dict) or not r.get("name"):
            e.append(f"resets[{i}] must be {{name, domain, polarity, style, from, via}}")
            continue
        resets[r["name"]] = r
        if r.get("domain") not in clocks:
            e.append(f"reset {r['name']}: domain {r.get('domain')!r} is not a declared clock")
        if r.get("polarity") not in POLARITY:
            e.append(f"reset {r['name']}: polarity must be one of {', '.join(POLARITY)}")
        if r.get("style") not in RESET_STYLE:
            e.append(f"reset {r['name']}: style must be one of {', '.join(RESET_STYLE)}")
        if r.get("via") is not None and r["via"] not in CDC_PRIMITIVES:
            e.append(f"reset {r['name']}: via {r['via']!r} is not a CDC primitive ({', '.join(CDC_PRIMITIVES)})")
    for r in resets.values():
        src = r.get("from")
        if src in resets and resets[src].get("domain") != r.get("domain") and not r.get("via"):
            e.append(f"reset {r['name']}: derived from {src} in another domain, so it needs 'via' (reset_sync, "
                     "xpm_cdc_async_rst)")
    mods: dict[str, dict[str, Any]] = {}
    for i, m in enumerate(d.get("modules") or []):
        if not isinstance(m, dict) or not m.get("name") or not _ID.match(str(m["name"])):
            e.append(f"modules[{i}] must be a mapping with a 'name'")
            continue
        if m["name"] in mods or m["name"] in ("shell", "top"):
            e.append(f"module name {m['name']} is used twice or reserved (shell, top)")
        mods[m["name"]] = m
        if m.get("kind") not in KINDS:
            e.append(f"module {m['name']}: kind must be one of {', '.join(KINDS)}")
        for k, plan in (("clocks", clocks), ("resets", resets)):
            b = m.get(k)
            if not isinstance(b, dict) or not b:
                e.append(f"module {m['name']}: '{k}' maps each contract {k[:-1]} to a design {k[:-1]}")
                continue
            for local, glob in b.items():
                if glob not in plan:
                    e.append(f"module {m['name']}: {k}.{local} -> {glob!r} is not a declared design {k[:-1]}")
        if m.get("params") is not None and not isinstance(m["params"], dict):
            e.append(f"module {m['name']}: params is a mapping {{NAME: value}}")
    if not mods:
        e.append("'modules' must list at least one module")
    sh = d.get("shell")
    if sh is not None:
        if not isinstance(sh, dict):
            e.append("shell must be {design_id, clock, reset}")
        else:
            if not isinstance(sh.get("design_id"), str) or len(sh["design_id"]) != 4 or not sh["design_id"].isascii():
                e.append("shell.design_id must be four ASCII characters")
            if sh.get("clock") not in clocks:
                e.append(f"shell.clock {sh.get('clock')!r} is not a declared clock")
            if sh.get("reset") not in resets:
                e.append(f"shell.reset {sh.get('reset')!r} is not a declared reset")
    for i, x in enumerate(d.get("connections") or []):
        if not isinstance(x, dict) or not all(isinstance(x.get(k), str) and x[k].count(".") == 1 for k in ("from", "to")):
            e.append(f"connections[{i}] must be {{from: <module>.<interface>, to: <module>.<interface>, crossing?}}")
            continue
        for k in ("from", "to"):
            if x[k].split(".")[0] not in mods:
                e.append(f"connections[{i}].{k}: module {x[k].split('.')[0]!r} is not in 'modules'")
        cr = x.get("crossing")
        if cr is not None and (not isinstance(cr, dict) or cr.get("primitive") not in CDC_PRIMITIVES):
            e.append(f"connections[{i}].crossing must be {{primitive: one of {', '.join(CDC_PRIMITIVES)}}}")
    for i, p in enumerate(d.get("board_ports") or []):
        if not isinstance(p, dict) or not p.get("name") or not _BUS.match(str(p["name"])):
            e.append(f"board_ports[{i}] must be {{name: NAME or NAME[hi:lo], dir, drive, from | to}}")
            continue
        if p.get("dir") not in ("in", "out"):
            e.append(f"board port {p['name']}: dir must be in or out")
        elif (p["dir"] == "in") != ("to" in p) or ("from" in p) == ("to" in p):
            e.append(f"board port {p['name']}: an input names what it drives ('to'), an output what drives it ('from')")
        if p.get("drive") not in DRIVES:
            e.append(f"board port {p['name']}: drive (electrical type) must be one of {', '.join(DRIVES)}")
    for g in d.get("owned") or []:
        if not isinstance(g, str) or g.startswith("/") or ".." in Path(g).parts:
            e.append(f"owned: {g!r} must be a path or glob inside the project")
    aids: set[str] = set()
    for i, a in enumerate(d.get("assumptions") or []):
        if not isinstance(a, dict) or not re.match(r"^A-\d+$", str(a.get("id", ""))) or not a.get("text"):
            e.append(f"assumptions[{i}] must be {{id: A-<n>, text, default, reason, affects: [...], status: open|resolved}}")
            continue
        if a["id"] in aids:
            e.append(f"assumption {a['id']} is declared twice")
        aids.add(a["id"])
        if a.get("status", "open") not in ("open", "resolved"):
            e.append(f"assumption {a['id']}: status must be open or resolved")
    return e


# ---- the project --------------------------------------------------------------------------------------------------
def xdc_ports(xdc: Path) -> set[str]:
    """Every port name of a master XDC, commented or not (``LED[0]``, ``CLK100MHZ`` ...)."""
    return set(re.findall(r"get_ports\s*\{\s*([^\s}]+)\s*\}", xdc.read_text(errors="replace")))


def board_dir(board: str) -> Path:
    return ROOT / "boards" / board


def bus_bits(name: str) -> tuple[str, list[int]] | None:
    """``VGA_R[3:0]`` -> ("VGA_R", [3, 2, 1, 0]); ``LED[0]`` -> ("LED", [0]); ``VGA_HS`` -> ("VGA_HS", [])."""
    m = _BUS.match(name)
    if not m:
        return None
    if m["hi"] is None:
        return m["n"], []
    hi, lo = int(m["hi"]), int(m["lo"] if m["lo"] is not None else m["hi"])
    return (m["n"], list(range(hi, lo - 1, -1))) if hi >= lo else None


@dataclass
class Project:
    """A loaded project: the files as read, and every problem found."""
    root: Path
    design: dict[str, Any] = field(default_factory=dict)
    contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
    requirements: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def module(self, name: str) -> dict[str, Any]:
        return next(m for m in self.design.get("modules") or [] if isinstance(m, dict) and m.get("name") == name)

    def params(self, name: str) -> dict[str, int]:
        return params_of(self.contracts.get(name, {}), self.module(name).get("params"))

    def iface(self, ref: str) -> dict[str, Any] | None:
        m, _, i = ref.partition(".")
        return iface_map(self.contracts.get(m, {})).get(i)

    def domain(self, ref: str) -> str | None:
        """The design clock an interface ``<module>.<iface>`` runs on (through the module's clock binding)."""
        f = self.iface(ref)
        if not f:
            return None
        return (self.module(ref.split(".")[0]).get("clocks") or {}).get(f.get("clock"))

    def modules(self) -> list[str]:
        return [m["name"] for m in self.design.get("modules") or [] if isinstance(m, dict) and m.get("name")]


def _width(p: Project, mod: str, w: Any) -> int | None:
    try:
        return evaluate(w, p.params(mod))
    except ExprError:
        return None


def _ref_width(p: Project, ref: str) -> tuple[int | None, str | None]:
    """The width of a board-port binding, or why it cannot be resolved. Forms: ``<clock>``, ``<reset>``,
    ``<clock>.locked`` (an MMCM's lock), ``shell.uart_rx`` / ``shell.uart_tx``, ``<module>.<port>``,
    ``<module>.<iface>.tuser.<name>``, ``<module>.<iface>.<signal>[hi:lo]``."""
    d = p.design
    clocks = {k.get("name"): k for k in d.get("clocks") or [] if isinstance(k, dict)}
    resets = {r.get("name") for r in d.get("resets") or [] if isinstance(r, dict)}
    if ref in clocks or ref in resets:
        return 1, None
    parts = ref.split(".")
    if len(parts) == 2 and parts[0] in clocks and parts[1] == "locked":
        return (1, None) if clocks[parts[0]].get("source") in ("mmcm", "pll") else (None, f"{parts[0]} has no lock")
    if parts[0] == "shell":
        if not d.get("shell"):
            return None, "the design has no shell"
        return (1, None) if ref in ("shell.uart_rx", "shell.uart_tx") else (None, f"{ref}: the shell has uart_rx, uart_tx")
    if parts[0] not in p.contracts:
        return None, f"{ref}: {parts[0]} is not a module with a contract"
    c = p.contracts[parts[0]]
    if len(parts) == 2:
        pt = port_map(c).get(parts[1])
        return (_width(p, parts[0], pt.get("width", 1)), None) if pt else (None, f"{ref}: no such port")
    f = iface_map(c).get(parts[1])
    if not f:
        return None, f"{ref}: {parts[1]} is not an interface of {parts[0]}"
    if len(parts) == 4 and parts[2] == "tuser":
        ok = any(b.get("name") == parts[3] for b in f.get("tuser") or [])
        return (1, None) if ok else (None, f"{ref}: tuser has no bit named {parts[3]}")
    if len(parts) == 3:
        m = _BUS.match(parts[2])
        if not m:
            return None, f"{ref}: cannot read the signal"
        pn = f"{f.get('prefix')}_{m['n']}"
        pt = port_map(c).get(pn)
        if not pt:
            return None, f"{ref}: port {pn} does not exist"
        full = _width(p, parts[0], pt.get("width", 1))
        if m["hi"] is None:
            return full, None
        hi, lo = int(m["hi"]), int(m["lo"] if m["lo"] is not None else m["hi"])
        if full is not None and not (full > hi >= lo):
            return None, f"{ref}: slice outside the {full}-bit {pn}"
        return hi - lo + 1, None
    return None, f"{ref}: cannot read the reference"


def _check_connection(p: Project, i: int, x: dict[str, Any]) -> list[str]:
    e: list[str] = []
    a, b = p.iface(x["from"]), p.iface(x["to"])
    w = f"connection {x['from']} -> {x['to']}"
    for ref, f in ((x["from"], a), (x["to"], b)):
        if f is None:
            e.append(f"{w}: {ref} is not an interface in that module's contract")
    if a is None or b is None:
        return e
    if a.get("role") != "master" or b.get("role") != "slave":
        e.append(f"{w}: 'from' must be a master and 'to' a slave (got {a.get('role')} -> {b.get('role')})")
    if a.get("protocol") != b.get("protocol"):
        e.append(f"{w}: protocols differ ({a.get('protocol')} -> {b.get('protocol')})")
        return e
    ma, mb = x["from"].split(".")[0], x["to"].split(".")[0]
    if a["protocol"] == "axi4-stream":
        wa = _width(p, ma, (a.get("tdata") or {}).get("width"))
        wb = _width(p, mb, (b.get("tdata") or {}).get("width"))
        if wa != wb:
            e.append(f"{w}: tdata is {wa} bits on one side and {wb} on the other")
        fa = [(f.get("name"), f.get("bits"), f.get("format")) for f in (a.get("tdata") or {}).get("fields") or []]
        fb = [(f.get("name"), f.get("bits"), f.get("format")) for f in (b.get("tdata") or {}).get("fields") or []]
        if fa and fb and sorted(map(str, fa)) != sorted(map(str, fb)):
            e.append(f"{w}: the tdata fields differ ({fa} against {fb})")
        ua = {u["bit"]: u["name"] for u in a.get("tuser") or []}
        ub = {u["bit"]: u["name"] for u in b.get("tuser") or []}
        if ua != ub:
            e.append(f"{w}: tuser bits differ ({ua} against {ub})")
        if bool(a.get("tlast")) != bool(b.get("tlast")):
            e.append(f"{w}: one side has tlast and the other does not")
        if "packet_beats" in a and "packet_beats" in b:
            pa, pb = _width(p, ma, a["packet_beats"]), _width(p, mb, b["packet_beats"])
            if pa != pb:
                e.append(f"{w}: packet_beats {pa} against {pb} (check both modules' parameters)")
        if b.get("backpressure") and not a.get("backpressure"):
            e.append(f"{w}: the sink may hold tready low but the source cannot be stalled (backpressure)")
        if a.get("source_gaps") and not b.get("source_gaps"):
            e.append(f"{w}: the source may leave gaps but the sink needs a beat every cycle (source_gaps)")
    elif a["protocol"] == "axi4-lite":
        if (a.get("addr_width"), a.get("data_width", 32)) != (b.get("addr_width"), b.get("data_width", 32)):
            e.append(f"{w}: AXI4-Lite address or data widths differ")
    da, db = p.domain(x["from"]), p.domain(x["to"])
    if da != db and not x.get("crossing"):
        e.append(f"{w}: crosses from {da} to {db} but declares no crossing (crossing: {{primitive: ...}})")
    if da == db and x.get("crossing"):
        e.append(f"{w}: declares a crossing but both ends are on {da}")
    return e


def check_project(root: Path) -> Project:
    """Load and check a whole project directory."""
    root = Path(root)
    p = Project(root=root)
    d, err = load_yaml(root / "design.yaml")
    if err:
        p.errors.append(err)
        return p
    p.design = d if isinstance(d, dict) else {}
    p.errors += [f"design.yaml: {x}" for x in check_design(d)]
    if not isinstance(d, dict):
        return p
    for m in d.get("modules") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        cpath = root / "modules" / m["name"] / "contract.yaml"
        if m.get("kind") != "rtl" and not cpath.is_file():
            p.warnings.append(f"module {m['name']} ({m.get('kind')}): no contract.yaml; P0 checks rtl modules only")
            continue
        c, err = load_yaml(cpath)
        if err:
            p.errors.append(f"modules/{m['name']}: {err}")
            continue
        errs = check_contract(c, m["name"])
        p.errors += [f"modules/{m['name']}/contract.yaml: {x}" for x in errs]
        if not isinstance(c, dict):
            continue
        p.contracts[m["name"]] = c
        # bindings against the contract
        cclk = {k.get("name"): k for k in c.get("clocks") or [] if isinstance(k, dict)}
        crst = {r.get("name"): r for r in c.get("resets") or [] if isinstance(r, dict)}
        dclk = {k.get("name"): k for k in d.get("clocks") or [] if isinstance(k, dict)}
        drst = {r.get("name"): r for r in d.get("resets") or [] if isinstance(r, dict)}
        for local in sorted(set(cclk) - set(m.get("clocks") or {})):
            p.errors.append(f"module {m['name']}: contract clock {local} is not bound to a design clock (clocks:)")
        for local in sorted(set(crst) - set(m.get("resets") or {})):
            p.errors.append(f"module {m['name']}: contract reset {local} is not bound to a design reset (resets:)")
        for local, glob in (m.get("clocks") or {}).items():
            if local not in cclk:
                p.errors.append(f"module {m['name']}: clocks.{local} is not a clock of its contract")
            elif glob in dclk and isinstance(cclk[local].get("max_mhz"), (int, float)):
                if dclk[glob].get("mhz", 0) > cclk[local]["max_mhz"]:
                    p.errors.append(f"module {m['name']}: {local} runs at {dclk[glob]['mhz']} MHz ({glob}), above the "
                                    f"contract's max_mhz {cclk[local]['max_mhz']}")
        for local, glob in (m.get("resets") or {}).items():
            if local not in crst:
                p.errors.append(f"module {m['name']}: resets.{local} is not a reset of its contract")
                continue
            if glob not in drst:
                continue
            for k in ("polarity", "style"):
                if crst[local].get(k) != drst[glob].get(k):
                    p.errors.append(f"module {m['name']}: reset {local} is {crst[local].get(k)} but {glob} is "
                                    f"{drst[glob].get(k)}")
            if (m.get("clocks") or {}).get(crst[local].get("clock")) != drst[glob].get("domain"):
                p.errors.append(f"module {m['name']}: reset {local} is bound to {glob} in domain {drst[glob].get('domain')}, "
                                f"but its clock {crst[local].get('clock')} is bound to "
                                f"{(m.get('clocks') or {}).get(crst[local].get('clock'))}")
        pnames = {x.get("name") for x in c.get("parameters") or [] if isinstance(x, dict)}
        for k, v in (m.get("params") or {}).items():
            if k not in pnames:
                p.errors.append(f"module {m['name']}: params.{k} is not a parameter of its contract")
                continue
            spec = next(x for x in c["parameters"] if x.get("name") == k)
            if not isinstance(v, int) or isinstance(v, bool):
                p.errors.append(f"module {m['name']}: params.{k} must be an integer")
            elif ("values" in spec and v not in spec["values"]) or (
                    spec.get("min") is not None and v < spec["min"]) or (spec.get("max") is not None and v > spec["max"]):
                p.errors.append(f"module {m['name']}: params.{k} = {v} is outside the contract's allowed values")
    if p.errors and not p.contracts:
        return p

    # connections
    connected: set[str] = set()
    for i, x in enumerate(d.get("connections") or []):
        if not isinstance(x, dict) or not isinstance(x.get("from"), str) or not isinstance(x.get("to"), str):
            continue
        if x["from"].split(".")[0] not in p.contracts or x["to"].split(".")[0] not in p.contracts:
            continue
        p.errors += _check_connection(p, i, x)
        for k in ("from", "to"):
            if x[k] in connected:
                p.errors.append(f"interface {x[k]} is connected twice (point-to-point links only in P0)")
            connected.add(x[k])
    for mname, c in p.contracts.items():
        regs = c.get("registers") or {}
        bus = regs.get("bus") if isinstance(regs, dict) else None
        for f in c.get("interfaces") or []:
            ref = f"{mname}.{f.get('name')}"
            if ref in connected or f.get("name") == bus:
                continue
            if f.get("role") == "slave" and not f.get("optional"):
                p.errors.append(f"interface {ref} (slave) is not connected")
            elif ref not in {b.get("from", "") for b in d.get("board_ports") or [] if isinstance(b, dict)} and not any(
                    str(b.get("from", "")).startswith(ref + ".") for b in d.get("board_ports") or [] if isinstance(b, dict)):
                p.warnings.append(f"interface {ref} ({f.get('role')}) is not connected and drives no board port")

    # the shell window: module register maps placed in it without overlap; crossings for register ports
    sh = d.get("shell") if isinstance(d.get("shell"), dict) else None
    used: dict[int, str] = {}
    for mname, c in p.contracts.items():
        regs = c.get("registers")
        if not isinstance(regs, dict) or regs.get("bus") != "top":
            continue
        m = p.module(mname)
        if not sh:
            p.errors.append(f"module {mname}: registers on bus top need a shell in design.yaml")
            continue
        base = m.get("window_base")
        if not isinstance(base, int) or base < 0:
            p.errors.append(f"module {mname}: registers on bus top need window_base (an offset in the shell window)")
            continue
        ports = port_map(c)
        xs = m.get("register_crossings") or {}
        for r in regs.get("map") or []:
            if not isinstance(r, dict) or not isinstance(r.get("offset"), int):
                continue
            a = base + r["offset"]
            if a >= WINDOW_WORDS:
                p.errors.append(f"register {mname}.{r.get('name')}: window offset {a:#x} is past 0x7f")
            if a in used:
                p.errors.append(f"register {mname}.{r.get('name')}: window offset {a:#x} is also {used[a]}")
            used[a] = f"{mname}.{r.get('name')}"
            doms = {(m.get("clocks") or {}).get(ports.get(fl.get("port"), {}).get("clock"))
                    for fl in r.get("fields") or [] if isinstance(fl, dict) and fl.get("port") in ports}
            cross = any(dm != sh.get("clock") for dm in doms)
            prim = xs.get(r.get("name"))
            if cross and prim not in CDC_PRIMITIVES:
                p.errors.append(f"register {mname}.{r.get('name')}: its ports are on {', '.join(sorted(map(str, doms)))}, "
                                f"the shell on {sh.get('clock')}; register_crossings.{r.get('name')} must name a CDC "
                                "primitive")
            elif not cross and prim:
                p.errors.append(f"register {mname}.{r.get('name')}: register_crossings given but there is no crossing")

    # board ports against the master XDC
    bd = board_dir(str(d.get("board")))
    bcfg, _ = load_yaml(bd / "board.yaml")
    xdc = bd / str((bcfg or {}).get("master_xdc", "")) if isinstance(bcfg, dict) else None
    have = xdc_ports(xdc) if xdc and xdc.is_file() else None
    if have is None:
        p.errors.append(f"board {d.get('board')}: no boards/{d.get('board')}/board.yaml with a master_xdc to check ports against")
    bound_inputs: set[str] = set()
    for bp in d.get("board_ports") or []:
        if not isinstance(bp, dict) or not bp.get("name"):
            continue
        bb = bus_bits(str(bp["name"]))
        if not bb:
            continue
        base, bits = bb
        if have is not None:
            missing = [n for n in ([f"{base}[{b}]" for b in bits] if bits else [base]) if n not in have]
            if missing:
                p.errors.append(f"board port {bp['name']}: {', '.join(missing)} not in the board's master XDC")
        ref = bp.get("from") if bp.get("dir") == "out" else bp.get("to")
        if not isinstance(ref, str):
            continue
        bound_inputs.add(ref) if bp.get("dir") == "in" else None
        wref, why = _ref_width(p, ref)
        if why:
            p.errors.append(f"board port {bp['name']}: {why}")
        elif wref != max(len(bits), 1):
            p.errors.append(f"board port {bp['name']}: {max(len(bits), 1)} bits, but {ref} is {wref}")
        dclk = {k.get("name"): k for k in d.get("clocks") or [] if isinstance(k, dict)}
        if bp.get("dir") == "in" and ref in dclk and dclk[ref].get("port") != base:
            p.errors.append(f"board port {bp['name']} drives clock {ref}, whose port is {dclk[ref].get('port')}")
    for k in d.get("clocks") or []:
        if isinstance(k, dict) and k.get("source") == "board" and k.get("name") not in bound_inputs:
            p.errors.append(f"clock {k.get('name')}: no board port drives it (board_ports: {{name: {k.get('port')}, "
                            f"dir: in, to: {k.get('name')}}})")
    for r in d.get("resets") or []:
        if isinstance(r, dict) and r.get("from") not in {x.get("name") for x in d.get("resets") or [] if isinstance(x, dict)}:
            if r.get("name") not in bound_inputs:
                p.errors.append(f"reset {r.get('name')}: comes from the board ({r.get('from')}) but no board port drives it")
    if sh:
        for need in ("shell.uart_rx", "shell.uart_tx"):
            if not any(isinstance(b, dict) and need in (b.get("from"), b.get("to")) for b in d.get("board_ports") or []):
                p.errors.append(f"the shell's {need.split('.')[1]} is not on a board port")

    # requirements
    rq_path = root / "system" / "requirements.yaml"
    if rq_path.is_file():
        rq, err = load_yaml(rq_path)
        p.requirements = rq if isinstance(rq, dict) else None
        if err or not isinstance(rq, dict):
            p.errors.append(f"system/requirements.yaml: {err or 'must be a mapping'}")
        else:
            p.errors += [f"system/requirements.yaml: {x}" for x in check_requirements(rq, p.modules())]
    return p


def check_requirements(rq: dict[str, Any], modules: list[str]) -> list[str]:
    e: list[str] = []
    if rq.get("schema") != REQUIREMENTS_SCHEMA:
        e.append(f"schema must be {REQUIREMENTS_SCHEMA!r}")
    if not isinstance(rq.get("requirements"), list) or not rq["requirements"]:
        return e + ["'requirements' must be a non-empty list of {id: S-<n>, text, proof, modules}"]
    e += requirement_errors(rq, need_proof=True)
    for r in rq["requirements"]:
        if not isinstance(r, dict):
            continue
        if not re.match(r"^S-\d+$", str(r.get("id", ""))):
            e.append(f"requirement {r.get('id')!r}: system requirement ids are S-<n>")
        ms = r.get("modules")
        if not isinstance(ms, list):
            e.append(f"requirement {r.get('id')}: 'modules' lists the modules it touches ('top' for the integrated design)")
            continue
        for m in ms:
            if m not in modules and m != "top":
                e.append(f"requirement {r.get('id')}: module {m!r} is not in design.yaml")
    return e


__all__ = ["PROOF_METHODS", "Project", "check_contract", "check_design", "check_project", "check_requirements"]
