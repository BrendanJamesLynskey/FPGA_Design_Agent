"""Components a block design can instantiate, and the interfaces inferred from their ports.

A component is an ``ip_lib`` entry (``ip_lib/<name>/ip.yaml`` plus its RTL top) or a flow component described in
``flow/blockdesign/components/<name>.yaml`` (the test shell, the reset and signal synchronisers, the block-design
support RTL). A file of the same name there for an ``ip_lib`` entry is an overlay: it adds what ip.yaml does not say
in a machine-readable form (inputs that carry their own synchroniser, parameters derived from the clock).

Interfaces are inferred from port names, the way a packager groups ports into bus interfaces:

- AXI4-Lite / AXI4: ``<p>_awaddr``, ``<p>_wdata``, ``<p>_araddr`` ... (``<p>_awlen`` or ``<p>_awid`` makes it AXI4);
  slave when ``awaddr`` is an input;
- AXI4-Stream: ``<p>_tdata`` and ``<p>_tvalid``; master when ``tdata`` is an output;
- the test shell's register window: ``win_addr``, ``win_wr``, ``win_rd``, ``win_wdata``, ``win_rdata``;
- clock and reset: the ports ip.yaml lists under ``clocks`` and ``resets`` (with the reset's polarity);
- interrupt: a one-bit output named ``irq``, ``interrupt`` or ``*_irq``;
- every other port is a one-port conduit of its own name.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from flow.blockdesign import hdl

ROOT = Path(__file__).resolve().parents[2]
IP = ROOT / "ip_lib"
COMP = Path(__file__).resolve().parent / "components"

AXI_LITE = ("awaddr", "awprot", "awvalid", "awready", "wdata", "wstrb", "wvalid", "wready", "bresp", "bvalid", "bready",
            "araddr", "arprot", "arvalid", "arready", "rdata", "rresp", "rvalid", "rready")
AXI_FULL_EXTRA = ("awid", "awlen", "awsize", "awburst", "awlock", "awcache", "awqos", "wlast", "bid", "arid", "arlen",
                  "arsize", "arburst", "arlock", "arcache", "arqos", "rid", "rlast")
AXIS = ("tdata", "tvalid", "tready", "tlast", "tkeep", "tstrb", "tuser", "tid", "tdest")
WINDOW = ("win_addr", "win_wr", "win_rd", "win_wdata", "win_rdata")
#: signals driven by the master side of each bus (the rest are driven by the slave)
MASTER_DRIVES = {"awaddr", "awprot", "awvalid", "wdata", "wstrb", "wvalid", "bready", "araddr", "arprot", "arvalid",
                 "rready", "awid", "awlen", "awsize", "awburst", "awlock", "awcache", "awqos", "wlast", "arid", "arlen",
                 "arsize", "arburst", "arlock", "arcache", "arqos", "tdata", "tvalid", "tlast", "tkeep", "tstrb",
                 "tuser", "tid", "tdest", "win_addr", "win_wr", "win_rd", "win_wdata"}
#: what a missing optional signal is tied to on the side that has it as an input
TIE = {"awprot": "0", "arprot": "0", "wstrb": "ones", "tkeep": "ones", "tstrb": "ones", "tlast": "1", "tuser": "0",
       "bresp": "0", "rresp": "0", "tready": "1"}
KINDS = ("axi4", "axi4lite", "axis", "clock", "reset", "interrupt", "conduit", "window")


class ComponentError(ValueError):
    pass


@dataclass
class Iface:
    name: str
    kind: str                      # one of KINDS
    role: str                      # master / slave (buses), source / sink (clock, reset, interrupt, conduit)
    ports: dict = field(default_factory=dict)     # signal role -> port name (a conduit: {"data": port})
    polarity: str | None = None    # resets: "high" or "low"


@dataclass
class Component:
    name: str
    source: str                    # "ip_lib" or "flow"
    top: str
    rtl: list[str]                 # repo-relative files
    module: hdl.Module
    summary: str = ""
    version: str = ""
    clocks: list[str] = field(default_factory=list)
    resets: dict = field(default_factory=dict)          # port -> "high" | "low"
    async_inputs: set = field(default_factory=set)      # inputs with their own synchroniser inside
    derive: dict = field(default_factory=dict)          # parameter -> expression over clk_hz
    variant_param: str | None = None
    variants: list[str] = field(default_factory=list)
    param_space: dict = field(default_factory=dict)     # ip.yaml parameters (range / set / default)
    cdc: bool = False                                   # a synchroniser: its async inputs may come from any domain
    window_registered: bool = True
    note: str = ""
    interfaces: list[Iface] = field(default_factory=list)

    def iface(self, name: str) -> Iface:
        for i in self.interfaces:
            if i.name == name:
                return i
        raise KeyError(name)

    def iface_of_port(self, port: str) -> Iface | None:
        for i in self.interfaces:
            if port in i.ports.values():
                return i
        return None


def component_dirs() -> list[Path]:
    """Where flow components are described: flow/blockdesign/components, then each directory in $FDA_BD_COMPONENTS
    (the tests' stub components with AXI4, AXI4-Stream and interrupt ports)."""
    import os
    extra = [Path(p) for p in os.environ.get("FDA_BD_COMPONENTS", "").split(os.pathsep) if p]
    return [COMP, *extra]


def _rtl_files(base: Path, files: list[str]) -> list[str]:
    return [str((base / f).resolve().relative_to(ROOT)) for f in files]


@functools.lru_cache(maxsize=None)
def load(name: str) -> Component:
    """The component called ``name``: an ip_lib entry (with an optional overlay) or a flow component."""
    ipy = IP / name / "ip.yaml"
    flowy = next((d / f"{name}.yaml" for d in component_dirs() if (d / f"{name}.yaml").is_file()), COMP / f"{name}.yaml")
    over = yaml.safe_load(flowy.read_text()) if flowy.is_file() else {}
    if ipy.is_file():
        y = yaml.safe_load(ipy.read_text())
        rtl = _rtl_files(IP / name, y.get("rtl") or [])
        top = y["top"]
        mfile = next((ROOT / f for f in rtl if re.search(rf"\bmodule\s+{top}\b", (ROOT / f).read_text())), None)
        if mfile is None:
            raise ComponentError(f"{name}: top module {top} is in none of its rtl files")
        c = Component(name=name, source="ip_lib", top=top, rtl=rtl, module=hdl.read_module(mfile, top),
                      summary=" ".join(str(y.get("summary", "")).split()), version=str(y.get("version", "")),
                      clocks=[c["name"] for c in y.get("clocks") or []],
                      resets={r["name"]: r.get("polarity", "high") for r in y.get("resets") or []},
                      variant_param=y.get("variant_param"), variants=list((y.get("variants") or {}).keys()),
                      param_space=y.get("parameters") or {})
        for d in y.get("depends") or []:          # an entry's own sub-blocks from other entries
            c.rtl += load(d).rtl
    elif over:
        rtl = [str(Path(f)) for f in over["rtl"]]
        top = over["top"]
        first = ROOT / rtl[0] if (ROOT / rtl[0]).is_file() else flowy.parent / rtl[0]
        c = Component(name=name, source="flow", top=top, rtl=rtl, module=hdl.read_module(first, top),
                      summary=" ".join(str(over.get("summary", "")).split()), version=str(over.get("version", "")),
                      clocks=list(over.get("clocks") or []), resets=dict(over.get("resets") or {}),
                      param_space=over.get("parameters") or {})
    else:
        raise ComponentError(f"no component {name!r}: not an ip_lib entry and no flow/blockdesign/components/{name}.yaml")
    c.async_inputs = set(over.get("async_inputs") or [])
    c.derive = dict(over.get("derive") or {})
    c.cdc = bool(over.get("cdc", False))
    c.note = " ".join(str(over.get("note", "")).split())
    c.window_registered = bool(over.get("window_registered", True))
    for p in c.async_inputs:
        c.module.port(p)                         # KeyError if the overlay names a port that does not exist
    c.interfaces = infer(c.module, c.clocks, c.resets)
    return c


def infer(mod: hdl.Module, clocks: list[str], resets: dict) -> list[Iface]:
    names = {p.name: p for p in mod.ports}
    used: set[str] = set()
    out: list[Iface] = []
    for p in mod.ports:                                            # clocks and resets first
        if p.name in clocks:
            out.append(Iface(p.name, "clock", "sink" if p.dir == "in" else "source", {"clk": p.name}))
            used.add(p.name)
        elif p.name in resets:
            out.append(Iface(p.name, "reset", "sink" if p.dir == "in" else "source", {"rst": p.name},
                             polarity=resets[p.name]))
            used.add(p.name)
    prefixes = []
    for p in mod.ports:
        m = re.fullmatch(r"(\w+?)_(awaddr|tdata)", p.name)
        if m and m.group(1) not in prefixes:
            prefixes.append(m.group(1))
    for pre in prefixes:
        if f"{pre}_awaddr" in names:
            sig = {s: f"{pre}_{s}" for s in AXI_LITE + AXI_FULL_EXTRA if f"{pre}_{s}" in names}
            kind = "axi4" if ("awlen" in sig or "awid" in sig) else "axi4lite"
            role = "slave" if names[f"{pre}_awaddr"].dir == "in" else "master"
        else:
            if f"{pre}_tvalid" not in names:
                continue
            sig = {s: f"{pre}_{s}" for s in AXIS if f"{pre}_{s}" in names}
            kind = "axis"
            role = "master" if names[f"{pre}_tdata"].dir == "out" else "slave"
        out.append(Iface(pre, kind, role, sig))
        used.update(sig.values())
    if all(w in names for w in WINDOW):
        role = "slave" if names["win_addr"].dir == "in" else "master"
        out.append(Iface("window", "window", role, {w: w for w in WINDOW}))
        used.update(WINDOW)
    for p in mod.ports:
        if p.name in used:
            continue
        if p.dir == "out" and p.msb is None and re.fullmatch(r"irq|interrupt|\w+_irq", p.name):
            out.append(Iface(p.name, "interrupt", "source", {"irq": p.name}))
        elif p.dir == "in" and p.msb is None and re.fullmatch(r"irq|interrupt|\w+_irq", p.name):
            out.append(Iface(p.name, "interrupt", "sink", {"irq": p.name}))
        else:
            out.append(Iface(p.name, "conduit", "source" if p.dir == "out" else "sink", {"data": p.name}))
    return out


def driven_by_master(sig: str) -> bool:
    return sig in MASTER_DRIVES
