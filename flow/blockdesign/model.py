"""Elaborate a block design: read it, resolve every instance, run the automations and the checks.

``elaborate(path)`` returns an :class:`Elab`: the boxes (one per instance, as the rest of the design sees it), the
bit-level connections, the bus links, the domains, the address map and the diagnostics. Generation, the viewer and the
checks all read this one model, so they cannot disagree.

The order (each step can add diagnostics; later steps still run so one pass reports as much as it can):

1. schema (JSON Schema, with the path of the bad key);
2. instances: the component or the hierarchy (elaborated recursively, in the parent's clock domain), the variant, the
   given parameters against the entry's declared space;
3. clock-frequency propagation: parameters a component derives from its clock (the shell's baud divider);
4. connections: endpoints, directions, slices; width propagation (a sink whose width follows a parameter that was not
   set takes the driver's width);
5. connection automation: one AXI4-Lite crossbar per ``interconnect`` entry; the address editor assigns the map;
6. clock and reset automation: every unconnected clock and reset input is tied to its domain's clock and to the
   domain's synchronised reset, in the polarity the input needs (one reset synchroniser per domain);
7. checks: unconnected inputs and bus interfaces, multiple drivers, interface type and width mismatches, clock and
   reset domain crossings without a synchroniser, parameters outside the declared space, address overlaps and holes.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

from flow.blockdesign import components as C
from flow.blockdesign import hdl

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = Path(__file__).with_name("blockdesign.schema.json")
SCHEMA_ID = "fpga-design-agent/blockdesign/v1"
BUS = ("axi4", "axi4lite", "axis", "window")


@dataclass
class Diag:
    code: str
    severity: str          # error, warning, info
    where: str
    msg: str
    hint: str = ""

    def text(self) -> str:
        return f"{self.severity.upper()} {self.code} {self.where}: {self.msg}" + (f" ({self.hint})" if self.hint else "")


@dataclass
class BPort:
    name: str
    dir: str               # in / out, as seen from outside the box
    width: int
    kind: str = "data"     # data, clock, reset, interrupt
    polarity: str | None = None
    async_ok: bool = False
    signed: bool = False


@dataclass
class BIface:
    name: str
    kind: str
    role: str
    ports: dict            # signal -> box port name
    addr_w: int = 0
    data_w: int = 0
    id_w: int = 0


@dataclass
class Box:
    name: str
    kind: str              # component, wrapped, hierarchy, interconnect, reset_sync
    comp: C.Component | None
    module: str
    params: dict = field(default_factory=dict)
    origin: dict = field(default_factory=dict)     # param -> given / default / derived / propagated ... / variant
    given: dict = field(default_factory=dict)
    ports: dict = field(default_factory=dict)      # name -> BPort
    ifaces: dict = field(default_factory=dict)     # name -> BIface
    domain: str | None = None
    variant: str | None = None
    sub: "Elab | None" = None
    wrap: dict | None = None                       # the axi_lite wrapper spec, resolved
    generated: bool = False                        # added by automation, not written in the design
    note: str = ""


@dataclass
class Seg:
    """``width`` bits from a source (box output, design input or constant) into a sink (box input or design output)."""
    dst: tuple             # ("box", inst, port) or ("ext", port)
    dst_lsb: int
    width: int
    src: tuple | None      # ("box", inst, port) / ("ext", port); None for a constant
    src_lsb: int = 0
    const: int = 0
    invert: bool = False
    auto: str = ""         # "clock" / "reset" when block automation made it
    where: str = ""


@dataclass
class Link:
    """A bus connection between a master interface and a slave interface."""
    name: str
    kind: str
    master: tuple          # (box name, iface name); box name "" is this design's own boundary (a hierarchy export)
    slave: tuple
    xbar: str | None = None
    index: int = 0         # the port index on the crossbar side
    where: str = ""


@dataclass
class Domain:
    name: str
    clk: str               # the clock net: an input port of this design
    freq_mhz: float | None
    reset_port: str | None
    reset_net: str = ""    # the synchronised active-high reset net
    async_reset_polarity: str = "low"


@dataclass
class Range:
    slave: str             # endpoint text inst.iface
    box: str
    iface: str
    base: int
    size: int
    fixed: bool
    xbar: str = ""
    index: int = 0


@dataclass
class Elab:
    path: Path
    data: dict
    name: str
    kind: str
    top: str
    ports: dict = field(default_factory=dict)      # design boundary ports: name -> BPort (dir as seen from outside)
    port_meta: dict = field(default_factory=dict)  # name -> the YAML entry
    domains: dict = field(default_factory=dict)
    boxes: dict = field(default_factory=dict)
    segs: list = field(default_factory=list)
    links: list = field(default_factory=list)
    exports: dict = field(default_factory=dict)    # hierarchy: boundary iface -> (inst, iface)
    ranges: list = field(default_factory=list)
    holes: list = field(default_factory=list)
    diags: list = field(default_factory=list)
    top_params: list = field(default_factory=list) # (path list, param, value)
    parent_domain: Domain | None = None
    mprefix: str = ""
    attempted: set = field(default_factory=set)   # sinks of connections already reported as wrong
    modules: dict = field(default_factory=dict)    # generated module name -> what it is

    def errors(self) -> list[Diag]:
        return [d for d in self.all_diags() if d.severity == "error"]

    def all_diags(self) -> list[Diag]:
        out = list(self.diags)
        for b in self.boxes.values():
            if b.sub is not None:
                out += [Diag(d.code, d.severity, f"{b.name}/{d.where}", d.msg, d.hint) for d in b.sub.all_diags()]
        return out

    def err(self, code, where, msg, hint=""):
        self.diags.append(Diag(code, "error", where, msg, hint))

    def warn(self, code, where, msg, hint=""):
        self.diags.append(Diag(code, "warning", where, msg, hint))

    def info(self, code, where, msg, hint=""):
        self.diags.append(Diag(code, "info", where, msg, hint))


# ---------------------------------------------------------------------------------------------------------------- read
def schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text())


def schema_errors(data) -> list[Diag]:
    v = jsonschema.Draft202012Validator(schema())
    out = []
    for e in sorted(v.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "(top)"
        msg = e.message
        if e.validator == "oneOf" and isinstance(e.instance, dict):
            msg = f"must have exactly one of the alternatives ({', '.join(sorted(_one_of_keys(e.validator_value)))}); it has {sorted(e.instance)}"
        elif e.validator == "additionalProperties":
            msg = f"{msg}; allowed: {', '.join(sorted((e.schema.get('properties') or {}).keys()))}"
        out.append(Diag("BD-SCHEMA", "error", where, msg))
    return out


def _one_of_keys(alts) -> set:
    ks = set()
    for a in alts:
        ks.update(a.get("required", []))
    return ks


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(Path(path).read_text()) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: not valid YAML: {' '.join(str(e).split())}") from None


# ----------------------------------------------------------------------------------------------------------- elaborate
def elaborate(path: Path, parent_domain: Domain | None = None, _stack: tuple = (), mprefix: str | None = None) -> Elab:
    """``mprefix``: the prefix of the modules generated for this design (the root design's name, then each hierarchy's)."""
    path = Path(path).resolve()
    data = load_yaml(path)
    kind = data.get("kind", "top") if isinstance(data, dict) else "top"
    name = data.get("name", path.stem) if isinstance(data, dict) else path.stem
    E = Elab(path=path, data=data, name=name, kind=kind, top=(data.get("top") if isinstance(data, dict) else None) or f"{name}_top",
             parent_domain=parent_domain)
    E.mprefix = mprefix or name
    E.diags += schema_errors(data)
    if E.errors():
        return E                       # nothing below can be trusted on a malformed file
    if path in _stack:
        E.err("BD-HIER-02", "design", f"{path.name} includes itself through {' -> '.join(p.name for p in _stack)}")
        return E
    _ports(E)
    _domains(E)
    for iname, spec in data["instances"].items():
        _instance(E, iname, spec, _stack + (path,))
    _connections(E)
    _exports(E)
    _interconnects(E)
    _clock_reset(E)
    _top_params(E)
    _check(E)
    return E


def _ports(E: Elab):
    for p in E.data.get("ports") or []:
        E.ports[p["name"]] = BPort(p["name"], p["dir"], p.get("width", 1), p.get("kind", "data"), p.get("polarity"),
                                   bool(p.get("async")))
        E.port_meta[p["name"]] = p
    if E.kind == "hierarchy":          # a hierarchy's own clock and reset (from the parent's domain)
        for n, k in (("clk", "clock"), ("rst", "reset")):
            if n in E.ports:
                E.err("BD-HIER-03", f"ports/{n}", f"a hierarchy gets {n} from its parent's domain; do not declare it")
            E.ports[n] = BPort(n, "in", 1, k, "high" if k == "reset" else None)
            E.port_meta[n] = {"name": n, "dir": "in", "kind": k}


def _domains(E: Elab):
    if E.kind == "hierarchy":
        pd = E.parent_domain
        E.domains["clk"] = Domain("clk", "clk", pd.freq_mhz if pd else None, None, reset_net="rst")
        if E.data.get("clocks"):
            E.err("BD-HIER-01", "clocks", "a hierarchy has one clock domain, its parent's (several domains in one hierarchy are not supported yet)")
        return
    for c in E.data.get("clocks") or []:
        p = E.ports.get(c["port"])
        w = f"clocks/{c['name']}"
        if p is None or p.dir != "in":
            E.err("BD-CLK-02", w, f"clock port {c['port']} is not an input port of the design")
            continue
        if p.kind != "clock":
            E.err("BD-CLK-01", w, f"port {c['port']} is not declared kind: clock")
        f = c.get("freq_mhz", E.port_meta[c["port"]].get("freq_mhz"))
        if f is None:
            E.warn("BD-CLK-04", w, "no frequency given; parameters derived from the clock cannot be set",
                   "add freq_mhz to the clock or its port")
        d = Domain(c["name"], c["port"], f, c.get("reset"))
        if d.reset_port:
            rp = E.ports.get(d.reset_port)
            if rp is None or rp.dir != "in" or rp.kind != "reset":
                E.err("BD-RST-03", w, f"reset {d.reset_port} is not an input port of kind: reset")
            else:
                d.async_reset_polarity = rp.polarity or "low"
            d.reset_net = f"rst_{c['name']}"
        E.domains[c["name"]] = d
    if not E.domains and E.kind == "top":
        E.err("BD-CLK-03", "clocks", "a top design needs at least one clock domain")


def _given_params(spec: dict) -> dict:
    return dict(spec.get("params") or {})


def _instance(E: Elab, iname: str, spec: dict, stack: tuple):
    w = f"instances/{iname}"
    if iname in E.ports:
        E.err("BD-REF-02", w, f"instance name {iname} is also a port name of the design")
    dom = spec.get("domain")
    if dom is None:
        dom = next(iter(E.domains)) if len(E.domains) == 1 else None
        if dom is None and E.domains:
            E.err("BD-CLK-03", w, f"several clock domains ({', '.join(E.domains)}); say which one with domain:")
    elif dom not in E.domains:
        E.err("BD-CLK-02", w, f"domain {dom} is not a clock domain of the design ({', '.join(E.domains) or 'none'})")
        dom = None
    if "design" in spec:
        sub_path = (E.path.parent / spec["design"]).resolve()
        if not sub_path.is_file():
            E.err("BD-HIER-01", w, f"hierarchy file {spec['design']} does not exist")
            return
        sub_name = (load_yaml(sub_path) or {}).get("name", sub_path.stem)
        S = elaborate(sub_path, E.domains.get(dom) if dom else None, stack, f"{E.mprefix}_{sub_name}")
        if S.kind != "hierarchy":
            E.err("BD-HIER-01", w, f"{spec['design']} is not kind: hierarchy")
        b = Box(iname, "hierarchy", None, S.mprefix, domain=dom, sub=S)
        for p in S.ports.values():
            b.ports[p.name] = BPort(p.name, p.dir, p.width, p.kind, p.polarity, False)
        for ifn, (inst, ifc) in S.exports.items():
            ib = S.boxes[inst].ifaces[ifc]
            ports = {sig: f"{ifn}_{sig}" for sig in ib.ports}
            for sig, pn in ports.items():
                src = S.boxes[inst].ports[ib.ports[sig]]
                b.ports[pn] = BPort(pn, src.dir, src.width, "data")
            b.ifaces[ifn] = BIface(ifn, ib.kind, ib.role, ports, ib.addr_w, ib.data_w, ib.id_w)
        if "params" in spec or "variant" in spec or "axi_lite" in spec:
            E.err("BD-HIER-01", w, "a hierarchy instance takes no params, variant or axi_lite (set them inside the hierarchy file)")
        E.boxes[iname] = b
        return
    try:
        comp = C.load(spec["component"])
    except (C.ComponentError, KeyError, hdl.HdlError) as e:
        E.err("BD-COMP-01", w, str(e).strip("'"),
              "ip_lib entries: " + ", ".join(sorted(p.parent.name for p in C.IP.glob("*/ip.yaml"))))
        return
    given = _given_params(spec)
    b = Box(iname, "component", comp, comp.top, domain=dom, given=dict(given))
    if spec.get("variant") is not None:
        if not comp.variant_param:
            E.err("BD-COMP-02", w, f"{comp.name} has no variants")
        elif spec["variant"] not in comp.variants:
            E.err("BD-COMP-02", w, f"{comp.name} has no variant {spec['variant']!r} (it has {', '.join(comp.variants)})")
        else:
            if comp.variant_param in given and given[comp.variant_param] != spec["variant"]:
                E.err("BD-PARAM-02", w, f"variant {spec['variant']} and {comp.variant_param}={given[comp.variant_param]} disagree")
            given[comp.variant_param] = spec["variant"]
            b.variant = spec["variant"]
    names = {p.name for p in comp.module.params}
    for k in list(given):
        if k not in names:
            E.err("BD-PARAM-01", w, f"{comp.name} has no parameter {k} (it has {', '.join(sorted(names)) or 'none'})")
            del given[k]
    b.given = dict(given)
    b.origin = {k: "given" for k in given}
    if b.variant:
        b.origin[comp.variant_param] = "variant"
    elif comp.variant_param:
        b.variant = str(hdl.resolve_params(comp.module, given).get(comp.variant_param))
    _derive(E, b, w)
    _resolve(b)
    if spec.get("axi_lite"):
        _wrap(E, b, spec["axi_lite"], w)
    E.boxes[iname] = b


def _derive(E: Elab, b: Box, w: str):
    """Clock-frequency propagation: parameters the component derives from its domain's clock."""
    if not b.comp.derive:
        return
    d = E.domains.get(b.domain) if b.domain else None
    if d is None or not d.freq_mhz:
        E.warn("BD-PARAM-03", w, f"{b.comp.name} derives {', '.join(b.comp.derive)} from its clock, whose frequency is unknown")
        return
    hz = int(round(d.freq_mhz * 1e6))
    for k, expr in b.comp.derive.items():
        v = int(eval(expr, {"__builtins__": {}, "round": round}, {"clk_hz": hz}))   # noqa: S307 (repo-owned overlay text)
        if k in b.given and int(b.given[k]) != v:
            E.err("BD-PARAM-02", w, f"{k}={b.given[k]} is given, but the {d.name} clock ({d.freq_mhz:g} MHz) gives {k}={v} ({expr})",
                  f"remove {k} to let it follow the clock")
            continue
        b.given[k] = v
        b.origin[k] = f"derived from the {d.name} clock ({d.freq_mhz:g} MHz): {expr}"


def _resolve(b: Box):
    """Ports and interfaces of a component box at its current parameters (run again after propagation)."""
    c = b.comp
    b.params = hdl.resolve_params(c.module, b.given)
    for p in c.module.params:
        b.origin.setdefault(p.name, "default")
    old = b.ports
    b.ports = {}
    for p in c.module.ports:
        ifc = c.iface_of_port(p.name)
        kind = ifc.kind if ifc and ifc.kind in ("clock", "reset", "interrupt") else "data"
        b.ports[p.name] = BPort(p.name, p.dir, hdl.width(p, b.params), kind,
                                ifc.polarity if ifc and ifc.kind == "reset" else None, p.name in c.async_inputs, p.signed)
    b.ifaces = {}
    for i in c.interfaces:
        bi = BIface(i.name, i.kind, i.role, dict(i.ports))
        if i.kind in ("axi4", "axi4lite"):
            bi.addr_w = b.ports[i.ports["awaddr"]].width
            bi.data_w = b.ports[i.ports["wdata"]].width
            bi.id_w = b.ports[i.ports["awid"]].width if "awid" in i.ports else 0
        elif i.kind == "axis":
            bi.data_w = b.ports[i.ports["tdata"]].width
        b.ifaces[i.name] = bi
    if b.wrap:
        _apply_wrap(b)
    return old


# -------------------------------------------------------------------------------------------- axi_lite wrapper
AXIL_PORTS = [("awaddr", "in"), ("awprot", "in"), ("awvalid", "in"), ("awready", "out"), ("wdata", "in"), ("wstrb", "in"),
              ("wvalid", "in"), ("wready", "out"), ("bresp", "out"), ("bvalid", "out"), ("bready", "in"), ("araddr", "in"),
              ("arprot", "in"), ("arvalid", "in"), ("arready", "out"), ("rdata", "out"), ("rresp", "out"), ("rvalid", "out"),
              ("rready", "in")]
AXIL_W = {"awaddr": "A", "araddr": "A", "awprot": 3, "arprot": 3, "wdata": 32, "rdata": 32, "wstrb": 4, "bresp": 2, "rresp": 2}
WRAP_ADDR_W = 12          # every generated wrapper decodes 4 KB; the address editor never assigns less


def _wrap(E: Elab, b: Box, spec: dict, w: str):
    c = b.comp
    if "s_axil" in b.ports or any(p.startswith("s_axil_") for p in b.ports):
        E.err("BD-WRAP-01", w, f"{c.name} already has s_axil ports; it needs no axi_lite wrapper")
        return
    wr = {"kind": "window" if "window" in spec else "registers", "consumed": [], "observed": [], "control": [], "status": [],
          "tick": None}
    if "window" in spec:
        ifn = spec["window"]
        if ifn not in b.ifaces or b.ifaces[ifn].kind != "window" or b.ifaces[ifn].role != "slave":
            E.err("BD-WRAP-01", w, f"{c.name} has no register-window slave interface {ifn!r}",
                  "the window is the five ports win_addr, win_wr, win_rd, win_wdata, win_rdata")
            return
        wr["window"] = ifn
        wr["consumed"] = list(b.ifaces[ifn].ports.values())
        wr["registered"] = c.window_registered
    else:
        R = spec["registers"]
        regs_seen = set()
        for kind in ("control", "status"):
            for r in R.get(kind) or []:
                if r["name"] in regs_seen:
                    E.err("BD-WRAP-02", f"{w}/axi_lite", f"register {r['name']} is defined twice")
                regs_seen.add(r["name"])
                fields = r.get("fields") or ([{"port": r["port"], "lsb": 0}] if r.get("port") else [])
                fl = []
                for f in fields:
                    p = b.ports.get(f["port"])
                    want = "in" if kind == "control" else "out"
                    if p is None or p.dir != want or p.kind != "data":
                        E.err("BD-WRAP-02", f"{w}/axi_lite/{r['name']}",
                              f"{f['port']} is not a data {'input' if want == 'in' else 'output'} of {c.name}",
                              f"its {'inputs' if want == 'in' else 'outputs'}: " + ", ".join(
                                  n for n, q in b.ports.items() if q.dir == want and q.kind == "data"))
                        continue
                    if f["lsb"] + p.width > 32:
                        E.err("BD-WIDTH-04", f"{w}/axi_lite/{r['name']}",
                              f"{f['port']} ({p.width} bits) at bit {f['lsb']} does not fit a 32-bit register")
                    if kind == "control":         # a control register drives the input; a status register only reads an output
                        if f["port"] in wr["consumed"]:
                            E.err("BD-DRV-01", f"{w}/axi_lite/{r['name']}", f"{f['port']} is driven by two registers")
                        wr["consumed"].append(f["port"])
                    else:
                        wr["observed"].append(f["port"])
                    fl.append({"port": f["port"], "lsb": f["lsb"], "width": p.width, "signed": p.signed})
                wr[kind].append({"name": r["name"], "fields": fl, "reset": r.get("reset", 0), "doc": r.get("doc", "")})
        if not wr["status"]:
            wr["status"].append({"name": "ID", "fields": [], "reset": 0, "doc": "reads 0 (the bank needs one status word)"})
        if not wr["control"]:
            wr["control"].append({"name": "SCRATCH", "fields": [], "reset": 0, "doc": "scratch register (no block input)"})
        if R.get("tick"):
            t = R["tick"]
            if t["div_reg"] not in [r["name"] for r in wr["control"]]:
                E.err("BD-WRAP-02", f"{w}/axi_lite/tick", f"div_reg {t['div_reg']} is not a control register")
            p = b.ports.get(t["to"])
            if p is None or p.dir != "in" or p.width != 1:
                E.err("BD-WRAP-02", f"{w}/axi_lite/tick", f"{t['to']} is not a one-bit input of {c.name}")
            else:
                wr["tick"] = {"div_reg": t["div_reg"], "to": t["to"]}
                wr["consumed"].append(t["to"])
    b.wrap = wr
    b.kind = "wrapped"
    b.module = f"{E.mprefix}_{b.name}_wrap"
    _apply_wrap(b)


def _apply_wrap(b: Box):
    wr = b.wrap
    for p in wr["consumed"]:
        b.ports.pop(p, None)
    for ifn in [k for k, i in b.ifaces.items() if any(p in wr["consumed"] for p in i.ports.values())]:
        del b.ifaces[ifn]
    ports = {}
    for sig, d in AXIL_PORTS:
        wd = AXIL_W.get(sig, 1)
        pn = f"s_axil_{sig}"
        b.ports[pn] = BPort(pn, d, WRAP_ADDR_W if wd == "A" else wd)
        ports[sig] = pn
    b.ifaces["s_axil"] = BIface("s_axil", "axi4lite", "slave", ports, WRAP_ADDR_W, 32)
    if wr.get("tick"):
        b.ports[wr["tick"]["to"]] = BPort(wr["tick"]["to"], "out", 1)


# ------------------------------------------------------------------------------------------------- connections
def _endpoint(E: Elab, text: str, where: str):
    """('box', inst, port|iface) / ('ext', port) / None, and whether it names an interface."""
    if "." in text:
        inst, item = text.split(".", 1)
        b = E.boxes.get(inst)
        if b is None:
            if inst in E.data["instances"]:
                return None, False          # the instance failed to elaborate; already reported
            E.err("BD-REF-01", where, f"no instance {inst} (instances: {', '.join(E.boxes)})")
            return None, False
        if item in b.ifaces and not (item in b.ports):
            return ("box", inst, item), True
        if item in b.ports:
            return ("box", inst, item), False
        E.err("BD-REF-01", where, f"{inst} has no port or interface {item}",
              f"ports: {', '.join(sorted(b.ports))}; interfaces: {', '.join(sorted(b.ifaces)) or 'none'}")
        return None, False
    if text in E.ports:
        return ("ext", text), False
    if text in E.exports or text in [x["name"] for x in E.data.get("interfaces") or []]:
        return ("hif", text), True
    E.err("BD-REF-01", where, f"{text} is not a port of the design (ports: {', '.join(E.ports) or 'none'})")
    return None, False


def port_of(E: Elab, ref: tuple) -> BPort | None:
    if ref[0] == "box":
        return E.boxes[ref[1]].ports.get(ref[2])
    return E.ports.get(ref[1])


def drives(E: Elab, ref: tuple) -> bool:
    """Can this endpoint drive a net? A box output, or one of this design's inputs."""
    p = port_of(E, ref)
    return p is not None and ((ref[0] == "box" and p.dir == "out") or (ref[0] == "ext" and p.dir == "in"))


def ref_text(ref: tuple) -> str:
    return f"{ref[1]}.{ref[2]}" if ref[0] == "box" else ref[1]


def _connections(E: Elab):
    pending = []
    for i, c in enumerate(E.data.get("connections") or []):
        w = f"connections/{i}"
        tos = c["to"] if isinstance(c["to"], list) else [c["to"]]
        if "const" in c:
            for t in tos:
                d, isif = _endpoint(E, t, w)
                if d is None:
                    continue
                if isif:
                    E.err("BD-IF-03", w, f"a constant cannot drive the interface {t}")
                    continue
                pending.append((w, None, None, c, d))
            continue
        s, s_if = _endpoint(E, c["from"], w)
        if s is None:
            continue
        for t in tos:
            d, d_if = _endpoint(E, t, w)
            if d is None:
                continue
            if s_if or d_if:
                _iface_link(E, w, s, s_if, d, d_if, c)
            else:
                pending.append((w, s, None, c, d))
    # width propagation: a sink port whose width follows an unset parameter takes the driver's width
    for _ in range(4):
        changed = False
        for (w, s, _, c, d) in pending:
            if s is None or "to_bits" in c or d[0] != "box":
                continue
            b = E.boxes[d[1]]
            if b.comp is None or b.kind not in ("component", "wrapped"):
                continue
            mp = next((p for p in b.comp.module.ports if p.name == d[2]), None)
            sp = port_of(E, s)
            if mp is None or sp is None:
                continue
            want = (c["bits"][0] - c["bits"][1] + 1) if "bits" in c else sp.width
            par = hdl.width_param(mp)
            if par and par not in b.given and b.ports[d[2]].width != want and want > 0:
                b.given[par] = want
                b.origin[par] = f"propagated from {ref_text(s)} ({want} bits)"
                _resolve(b)
                changed = True
        if not changed:
            break
    for (w, s, _, c, d) in pending:
        _segment(E, w, s, c, d)


def _segment(E: Elab, w: str, s, c: dict, d):
    dp = port_of(E, d)
    if dp is None:
        return
    if d[0] == "box" and dp.dir != "in":
        E.err("BD-DRV-02", w, f"{ref_text(d)} is an output of {d[1]}; it cannot be driven")
        return
    if d[0] == "ext" and dp.dir != "out":
        E.err("BD-DRV-02", w, f"{d[1]} is an input of the design; it cannot be driven")
        return
    dl, dw = 0, dp.width
    if "to_bits" in c:
        hi, lo = c["to_bits"]
        if hi < lo or hi >= dp.width:
            E.err("BD-WIDTH-03", w, f"to_bits [{hi}:{lo}] is outside {ref_text(d)} ({dp.width} bits)")
            return
        dl, dw = lo, hi - lo + 1
    if s is None:
        if c["const"] >= (1 << dw):
            E.err("BD-WIDTH-01", w, f"constant {c['const']} does not fit {dw} bits of {ref_text(d)}")
            return
        E.segs.append(Seg(d, dl, dw, None, const=c["const"], where=w))
        return
    sp = port_of(E, s)
    if not drives(E, s):
        E.err("BD-DRV-02", w, f"{ref_text(s)} is {'an input of ' + s[1] if s[0] == 'box' else 'an output of the design'}; it cannot drive a net",
              "connections go from an output to inputs")
        return
    sl, sw = 0, sp.width
    if "bits" in c:
        hi, lo = c["bits"]
        if hi < lo or hi >= sp.width:
            E.err("BD-WIDTH-03", w, f"bits [{hi}:{lo}] is outside {ref_text(s)} ({sp.width} bits)")
            return
        sl, sw = lo, hi - lo + 1
    if sw != dw:
        par = None
        if d[0] == "box" and E.boxes[d[1]].comp is not None:
            mp = next((p for p in E.boxes[d[1]].comp.module.ports if p.name == d[2]), None)
            par = hdl.width_param(mp) if mp else None
        hint = (f"{d[1]}.{par}={E.boxes[d[1]].params.get(par)} is set in the design; remove it to let the width propagate, or set it to {sw}"
                if par and par in E.boxes[d[1]].given and not str(E.boxes[d[1]].origin.get(par, "")).startswith("propagated")
                else "use bits / to_bits to connect part of a port")
        E.err("BD-WIDTH-01", w, f"{ref_text(s)} gives {sw} bits but {ref_text(d)} takes {dw}", hint)
        E.attempted.add(d)                 # reported here; not again as undriven
        return
    for kind_s, kind_d in ((sp.kind, dp.kind),):
        if kind_d == "clock" and kind_s != "clock":
            E.err("BD-CLK-01", w, f"{ref_text(d)} is a clock input, driven by {ref_text(s)}, which is not a clock")
        if kind_d == "interrupt" and kind_s != "interrupt":
            E.err("BD-IF-01", w, f"{ref_text(d)} is an interrupt input, driven by {ref_text(s)}, which is not an interrupt")
        if kind_s == "interrupt" and kind_d not in ("interrupt",) and not (d[0] == "ext"):
            E.err("BD-IF-01", w, f"interrupt {ref_text(s)} drives {ref_text(d)}, which is not an interrupt input")
        if kind_d == "reset" and kind_s == "reset":
            pol_s = sp.polarity or "high"
            pol_d = dp.polarity or "high"
            if (pol_s != pol_d) != bool(c.get("invert")):
                E.err("BD-RST-01", w, f"{ref_text(s)} is active {pol_s}, {ref_text(d)} is active {pol_d}",
                      "add invert: true, or leave the reset unconnected and let reset automation tie it")
    E.segs.append(Seg(d, dl, dw, s, sl, invert=bool(c.get("invert")), where=w))


def _iface_link(E: Elab, w, s, s_if, d, d_if, c):
    if not (s_if and d_if):
        one = ref_text(s) if s_if else ref_text(d)
        other = ref_text(d) if s_if else ref_text(s)
        E.err("BD-IF-03", w, f"{one} is an interface, {other} is a port: connect an interface to an interface")
        return
    if "bits" in c or "to_bits" in c or c.get("invert"):
        E.err("BD-IF-03", w, "bits, to_bits and invert apply to ports, not interfaces")
    a = _iface(E, s)
    b = _iface(E, d)
    if a is None or b is None:
        return
    if a.kind != b.kind:
        E.err("BD-IF-01", w, f"{ref_text(s)} is {a.kind} but {ref_text(d)} is {b.kind}: interface types differ")
        return
    if s[0] == "hif" or d[0] == "hif":
        E.err("BD-IF-03", w, "connect a hierarchy's boundary interface with interfaces: (export), not connections")
        return
    roles = {a.role, b.role}
    if roles != {"master", "slave"}:
        E.err("BD-IF-02", w, f"{ref_text(s)} and {ref_text(d)} are both {a.role}s: a link joins one master to one slave")
        return
    m, sl = (s, d) if a.role == "master" else (d, s)
    _check_link_widths(E, w, m, sl)
    E.links.append(Link(f"{m[1]}_{m[2]}", a.kind, (m[1], m[2]), (sl[1], sl[2]), where=w))


def _iface(E: Elab, ref) -> BIface | None:
    if ref[0] != "box":
        return None
    return E.boxes[ref[1]].ifaces.get(ref[2])


def _check_link_widths(E: Elab, w, m, s):
    a, b = _iface(E, m), _iface(E, s)
    if a.data_w != b.data_w:
        E.err("BD-WIDTH-02", w, f"{ref_text(m)} has {a.data_w}-bit data but {ref_text(s)} has {b.data_w}-bit data",
              "put a width converter between them")
    if a.kind == "axi4" and a.id_w > b.id_w:
        E.err("BD-WIDTH-02", w, f"{ref_text(m)} sends {a.id_w}-bit IDs but {ref_text(s)} takes {b.id_w}",
              "the slave's ID width must hold the master's")
    if a.kind in ("axi4", "axi4lite") and a.addr_w < b.addr_w:
        E.info("BD-WIDTH-05", w, f"{ref_text(m)} drives {a.addr_w} address bits into {b.addr_w}; the top bits are tied to 0")


def _exports(E: Elab):
    for i, x in enumerate(E.data.get("interfaces") or []):
        w = f"interfaces/{i}"
        if E.kind != "hierarchy":
            E.err("BD-HIER-01", w, "only a hierarchy exports interfaces")
            continue
        if "." not in x["export"]:
            E.err("BD-REF-01", w, f"export {x['export']} must be inst.interface")
            continue
        inst, ifc = x["export"].split(".", 1)
        if inst not in E.boxes or ifc not in E.boxes[inst].ifaces:
            E.err("BD-REF-01", w, f"{x['export']} is not an interface of an instance here")
            continue
        E.exports[x["name"]] = (inst, ifc)


# ---------------------------------------------------------------------------------------- connection automation
def _interconnects(E: Elab):
    from flow.blockdesign import addrmap
    used = set()
    for ix, spec in enumerate(E.data.get("interconnect") or []):
        w = f"interconnect/{spec['name']}"
        if spec["name"] in E.boxes:
            E.err("BD-REF-02", w, f"{spec['name']} is already an instance name")
            continue
        ms, ss = [], []
        for role, lst, out in (("master", spec["masters"], ms), ("slave", spec["slaves"], ss)):
            for t in lst:
                r, isif = _endpoint(E, t, w)
                if r is None:
                    continue
                f = _iface(E, r) if isif else None
                if f is None:
                    E.err("BD-IF-03", w, f"{t} is not an interface")
                    continue
                if f.kind != "axi4lite":
                    E.err("BD-IF-01", w, f"{t} is {f.kind}; the generated interconnect joins AXI4-Lite interfaces",
                          "AXI4 and AXI4-Stream interconnects are not generated yet")
                    continue
                if f.role != role:
                    E.err("BD-IF-02", w, f"{t} is a {f.role}, listed as a {role}")
                    continue
                if t in used:
                    E.err("BD-DRV-01", w, f"{t} is on more than one interconnect or listed twice")
                    continue
                used.add(t)
                out.append((r, f, t))
        if not ms or not ss:
            continue
        aws = {f.addr_w for (_, f, _) in ms}
        if len(aws) > 1:
            E.err("BD-WIDTH-02", w, f"the masters' address widths differ ({sorted(aws)}); the crossbar has one width")
        aw = max(aws)
        for (r, f, t) in ms + ss:
            if f.data_w != 32:
                E.err("BD-WIDTH-02", w, f"{t} has {f.data_w}-bit data; the crossbar is 32-bit")
        comp = C.load("axil_xbar")
        b = Box(spec["name"], "interconnect", comp, comp.top, domain=E.boxes[ms[0][0][1]].domain, generated=True,
                given={"N_M": len(ms), "N_S": len(ss), "ADDR_W": aw},
                note="connection automation: AXI4-Lite crossbar")
        b.origin = {"N_M": f"{len(ms)} masters", "N_S": f"{len(ss)} slaves", "ADDR_W": "propagated from the masters"}
        b.params = hdl.resolve_params(comp.module, b.given)
        b.ports = {"clk": BPort("clk", "in", 1, "clock"), "rst": BPort("rst", "in", 1, "reset", "high")}
        E.boxes[b.name] = b
        for i, (r, f, t) in enumerate(ms):
            E.links.append(Link(f"{b.name}_s{i}", "axi4lite", (r[1], r[2]), (b.name, f"s{i}"), xbar=b.name, index=i, where=w))
        for i, (r, f, t) in enumerate(ss):
            E.links.append(Link(f"{b.name}_m{i}", "axi4lite", (b.name, f"m{i}"), (r[1], r[2]), xbar=b.name, index=i, where=w))
        b.wrap = {"masters": [t for (_, _, t) in ms], "slaves": [t for (_, _, t) in ss], "addr_w": aw}
        # crossbar view: one interface per port, for the domain checks and the viewer
        for i, (r, f, t) in enumerate(ms):
            b.ifaces[f"s{i}"] = BIface(f"s{i}", "axi4lite", "slave", {}, aw, 32)
        for i, (r, f, t) in enumerate(ss):
            b.ifaces[f"m{i}"] = BIface(f"m{i}", "axi4lite", "master", {}, aw, 32)
    addrmap.assign(E)
    for x in E.data.get("interconnect") or []:
        b = E.boxes.get(x["name"])
        if b is None or b.kind != "interconnect":
            continue
        rs = sorted([r for r in E.ranges if r.xbar == b.name], key=lambda r: r.index)
        if len(rs) == b.params["N_S"]:
            aw = b.params["ADDR_W"]
            b.params["S_BASE"] = sum(r.base << (r.index * aw) for r in rs)
            b.params["S_BITS"] = sum(int(math.log2(r.size)) << (r.index * 8) for r in rs)
            b.origin["S_BASE"] = b.origin["S_BITS"] = "the address editor"


# ---------------------------------------------------------------------------------- clock and reset automation
def _clock_reset(E: Elab):
    drv = _driven_bits(E)
    for dname, d in E.domains.items():
        if E.kind == "top" and d.reset_port:
            comp = C.load("reset_sync")
            bn = f"rst_sync_{dname}"
            b = Box(bn, "reset_sync", comp, comp.top, domain=dname, generated=True,
                    note=f"block automation: reset synchroniser for the {dname} domain")
            b.params = hdl.resolve_params(comp.module, {})
            _resolve(b)
            E.boxes[bn] = b
            E.segs.append(Seg(("box", bn, "clk"), 0, 1, ("ext", d.clk), auto="clock", where="clock automation"))
            pol = d.async_reset_polarity
            E.segs.append(Seg(("box", bn, "rst_n_async"), 0, 1, ("ext", d.reset_port), invert=(pol == "high"),
                              auto="reset", where="reset automation"))
    for b in list(E.boxes.values()):
        if b.kind == "reset_sync":
            continue
        d = E.domains.get(b.domain) if b.domain else None
        for p in b.ports.values():
            if p.dir != "in" or p.kind not in ("clock", "reset") or ("box", b.name, p.name) in drv:
                continue
            if d is None:
                continue
            if p.kind == "clock":
                E.segs.append(Seg(("box", b.name, p.name), 0, 1, ("ext", d.clk), auto="clock", where="clock automation"))
            else:
                if E.kind == "top" and not d.reset_port:
                    continue                      # reported as unconnected
                src = ("ext", "rst") if E.kind == "hierarchy" else ("box", f"rst_sync_{d.name}", "rst")
                E.segs.append(Seg(("box", b.name, p.name), 0, 1, src, invert=(p.polarity == "low"), auto="reset",
                                  where="reset automation"))


def _driven_bits(E: Elab) -> set:
    return {s.dst for s in E.segs}


def _top_params(E: Elab):
    for t in E.data.get("top_params") or []:
        parts = t.split(".")
        cur, path = E, []
        ok = True
        for seg in parts[:-1]:
            b = cur.boxes.get(seg)
            if b is None:
                E.err("BD-REF-01", f"top_params/{t}", f"no instance {seg}")
                ok = False
                break
            path.append(seg)
            if b.sub is not None:
                cur = b.sub
        if not ok:
            continue
        b = cur.boxes.get(parts[-2]) if len(parts) >= 2 else None
        if b is None or b.comp is None or parts[-1] not in b.params:
            E.err("BD-REF-01", f"top_params/{t}", f"{t} is not a parameter of a component instance")
            continue
        E.top_params.append((parts[:-1], parts[-1], b.params[parts[-1]]))


# --------------------------------------------------------------------------------------------------------- checks
def _check(E: Elab):
    # ---- parameters inside the declared space (after propagation)
    for b in E.boxes.values():
        if b.comp is None or b.generated:
            continue
        for k, sp in (b.comp.param_space or {}).items():
            v = b.params.get(k)
            if v is None:
                continue
            why = ""
            if "range" in sp and isinstance(v, int) and not (sp["range"][0] <= v <= sp["range"][1]):
                why = f"outside {sp['range'][0]}..{sp['range'][1]}"
            if "set" in sp and v not in sp["set"]:
                why = f"not one of {', '.join(map(str, sp['set']))}"
            if why:
                E.err("BD-PARAM-01", f"instances/{b.name}", f"{k}={v} ({b.origin.get(k, 'given')}) is {why} for {b.comp.name}")
    # ---- bit-level drivers: multiple drivers and undriven inputs
    bits: dict = {}
    for s in E.segs:
        for i in range(s.width):
            key = (s.dst, s.dst_lsb + i)
            if key in bits:
                prev = bits[key]
                E.err("BD-DRV-01", s.where, f"bit {s.dst_lsb + i} of {ref_text(s.dst)} has two drivers: "
                      f"{_seg_src(prev)} ({prev.where}) and {_seg_src(s)}")
            else:
                bits[key] = s
    for b in E.boxes.values():
        for p in b.ports.values():
            if p.dir != "in":
                continue
            if any(p.name in i.ports.values() for i in b.ifaces.values() if i.kind in BUS):
                continue
            missing = [i for i in range(p.width) if (("box", b.name, p.name), i) not in bits]
            if missing and ("box", b.name, p.name) not in E.attempted:
                what = "all" if len(missing) == p.width else f"bits {_ranges(missing)}"
                E.err("BD-UNCONN-01", f"instances/{b.name}", f"input {b.name}.{p.name} ({p.width} bits): {what} not driven",
                      "connect it, or tie it with const:" if p.kind == "data" else
                      ("give the design a clock domain" if p.kind == "clock" else "give the domain a reset port"))
    for p in E.ports.values():
        if p.dir == "out":
            missing = [i for i in range(p.width) if (("ext", p.name), i) not in bits]
            if missing:
                E.err("BD-UNCONN-03", f"ports/{p.name}", f"output {p.name}: {'all bits' if len(missing) == p.width else 'bits ' + _ranges(missing)} not driven",
                      "tie unused outputs with const:")
    used_src = {s.src for s in E.segs if s.src}
    for p in E.ports.values():
        if p.dir == "in" and ("ext", p.name) not in used_src and not any(d.clk == p.name or d.reset_port == p.name for d in E.domains.values()):
            E.warn("BD-OPEN-02", f"ports/{p.name}", f"input {p.name} is not used")
    for b in E.boxes.values():
        if b.kind == "interconnect":
            continue
        for p in b.ports.values():
            observed = b.wrap.get("observed", []) if b.wrap and b.kind == "wrapped" else []
            if p.dir == "out" and ("box", b.name, p.name) not in used_src and p.name not in observed and not any(
                    p.name in i.ports.values() for i in b.ifaces.values() if i.kind in BUS):
                E.info("BD-OPEN-01", f"instances/{b.name}", f"output {b.name}.{p.name} is left open")
    # ---- bus interfaces must be on a link
    linked = set()
    for L in E.links:
        linked.add(L.master)
        linked.add(L.slave)
    for (inst, ifc) in E.exports.values():
        linked.add((inst, ifc))
    for b in E.boxes.values():
        if b.kind == "interconnect":
            continue
        for i in b.ifaces.values():
            if i.kind in BUS and (b.name, i.name) not in linked:
                E.err("BD-UNCONN-02", f"instances/{b.name}", f"{i.kind} {i.role} interface {b.name}.{i.name} is not connected",
                      "connect it, or list it on an interconnect")
    for L in E.links:
        n = sum(1 for M in E.links if M.master == L.master)
        if n > 1 and E.boxes.get(L.master[0]) and E.boxes[L.master[0]].kind != "interconnect":
            E.err("BD-DRV-01", L.where, f"master {L.master[0]}.{L.master[1]} is on {n} links; use an interconnect")
            break
    for L in E.links:
        n = sum(1 for M in E.links if M.slave == L.slave)
        if n > 1:
            E.err("BD-DRV-01", L.where, f"slave {L.slave[0]}.{L.slave[1]} has {n} masters; use an interconnect")
            break
    # ---- clock and reset domain crossings
    for s in E.segs:
        if s.src is None or s.auto == "clock":
            continue
        sd = _src_domain(E, s.src)
        dd, async_ok = _dst_domain(E, s.dst)
        if s.auto == "reset":
            continue
        if sd == "async" and dd is not None and not async_ok:
            E.err("BD-CDC-02", s.where, f"{ref_text(s.src)} is asynchronous and drives {ref_text(s.dst)} in domain {dd} with no synchroniser",
                  "route it through a sync2 instance, or into an input that has its own synchroniser")
        elif sd and dd and sd != "async" and sd != dd and not async_ok:
            pk = port_of(E, s.src).kind if port_of(E, s.src) else "data"
            code = "BD-RST-02" if pk == "reset" else "BD-CDC-01"
            E.err(code, s.where, f"{ref_text(s.src)} (domain {sd}) drives {ref_text(s.dst)} (domain {dd}) with no synchroniser",
                  "add a synchroniser (sync2 for a level, a handshake or FIFO for data)")
    for L in E.links:
        a, b = E.boxes.get(L.master[0]), E.boxes.get(L.slave[0])
        if a and b and a.domain and b.domain and a.domain != b.domain:
            E.err("BD-CDC-03", L.where, f"bus link {L.master[0]}.{L.master[1]} (domain {a.domain}) to {L.slave[0]}.{L.slave[1]} "
                  f"(domain {b.domain}) crosses clock domains", "put the slave in the master's domain; a clock converter is not generated yet")


def _seg_src(s: Seg) -> str:
    return f"constant {s.const}" if s.src is None else ref_text(s.src)


def _ranges(ix: list) -> str:
    ix = sorted(ix)
    out, a = [], ix[0]
    for p, q in zip(ix, ix[1:] + [None]):
        if q != p + 1:
            out.append(f"{p}:{a}" if p != a else f"{a}")
            if q is not None:
                a = q
    return ", ".join(out)


def _src_domain(E: Elab, ref) -> str | None:
    if ref[0] == "ext":
        meta = E.port_meta.get(ref[1], {})
        if meta.get("async"):
            return "async"
        if meta.get("domain"):
            return meta["domain"]
        if E.kind == "hierarchy":
            return "clk"
        for d in E.domains.values():
            if d.clk == ref[1]:
                return None
        return "async" if not meta.get("domain") and len(E.domains) != 1 else next(iter(E.domains), None)
    b = E.boxes[ref[1]]
    return b.domain


def _dst_domain(E: Elab, ref):
    if ref[0] == "ext":
        meta = E.port_meta.get(ref[1], {})
        return meta.get("domain"), True          # a design output: no domain rule (the board or the parent)
    b = E.boxes[ref[1]]
    p = b.ports.get(ref[2])
    return b.domain, bool(p and p.async_ok)


def summary(E: Elab) -> dict:
    ds = E.all_diags()
    return {"errors": sum(d.severity == "error" for d in ds), "warnings": sum(d.severity == "warning" for d in ds),
            "info": sum(d.severity == "info" for d in ds)}
