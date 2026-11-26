"""Brief 230: every top port and every clock-generating primitive is accounted for BEFORE synthesis, and the flow writes the
constraints it already knows.

The post-synthesis gate (``flow/gates.py``, Vivado ``check_timing``) finds an unconstrained port or an unclocked register pin only
after a full synthesis; the Vivado run then optimised the miss unconstrained. This module reads the same facts from the files
(top module ports, spec.yaml, board.yaml, the RTL's primitive instances, the XDC text) and answers in seconds:

1. ``port_classes``: each top port gets one class (clock, reset, timed input, timed output, slow or asynchronous, transceiver
   serial pad, transceiver reference clock, forwarded clock, ...) and says whether the XDC covers it. A port nothing covers is
   ``FDA-CON-14``.
2. ``block_findings``: each clock-generating or hard-IP primitive instantiated in the RTL (``HARD_BLOCKS``) either has an automatic
   derivation or an XDC line; one without is ``FDA-CON-15`` with the exact line to add.
3. ``known_pre_xdc`` / ``known_post_xdc``: what the flow already knows and writes itself (``<build>/known_pre.xdc`` before the design's XDC, ``known_post.xdc`` after it): the false
   paths of the board's ``slow_ports`` (and the spec's ``async: true`` ports) and each supplied or primitive block's own clock
   (the BSCANE2 TCK inside ``jtag_bus``; the USR_ACCESSE2 configuration clock). The model writes only the timed-interface
   delays and the design's own exceptions.
4. ``explain_unconstrained``: for a post-synthesis ``check_timing`` list, each endpoint with its class and the line to add.

Everything here is deterministic text processing; nothing calls a model or Vivado. What Vivado itself reports on an elaborated
design is measured in ``results/230_constraints_complete`` and recorded in ``HARD_BLOCKS``' ``evidence`` fields.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

import yaml

# ---- hard blocks: what each needs, who supplies it, and how we know ------------------------------------------------------------------
#: ``prims``: primitive or module names that identify the block in the RTL. ``kind``: what the block adds to the timing
#: picture. ``line``: the XDC the flow writes (``{i}`` = hierarchical instance path) or None. ``evidence``: ``measured`` (a result
#: file) or ``document`` (read in the AMD guide only; not measured by us).
HARD_BLOCKS: dict[str, dict[str, Any]] = {
    "bscane2": {
        "prims": ["BSCANE2"], "kind": "clock source",
        "needs": "a create_clock on the TCK output (INTERNAL_TCK pin), at most 30 MHz on the JTAG cable; its crossings go through xpm_cdc macros, which carry their own constraints",
        "supplier": "flow (known_pre.xdc) for jtag_bus; the design for its own BSCANE2",
        "line": "create_clock -name jtag_tck -period 33.333 [get_pins {i}/INTERNAL_TCK]",
        "evidence": "measured (Vivado 2026.1, xck26): results/230_constraints_complete/elab_probe: the fixture's TCK registers are unclocked in report_clocks at elaboration and in check_timing no_clock after synthesis; 224 p5 run 1 listed 193 u_jtag registers; designs/b96_kr260_10g/design.xdc uses this line and closes",
    },
    "usr_accesse2": {
        "prims": ["USR_ACCESSE2"], "kind": "clock source (configuration clock)",
        "needs": "a clock on the CCLK pin (the primitive is a clocked cell with an internal clock); the DATA word is constant after configuration, but whether paths from the clock need a cut depends on where DATA goes (an xpm_cdc macro already cuts them: a second false path is reported EXC-IGNORED, measured), so the crossing is the design's",
        "supplier": "flow (known_pre.xdc)",
        "line": "create_clock -name usr_cclk -period 10.000 [get_pins {i}/CCLK]",
        "evidence": "measured (Vivado 2026.1, xck26): after synthesis check_timing no_clock lists u_usr/CCLK (fixture and 224 p5 run 1); at elaboration the CCLK pin is NOT among the registers' clock pins, so only the static primitive check sees it; 209 and 224 designs that closed define a clock on CCLK",
    },
    "startupe3": {
        "prims": ["STARTUPE3", "STARTUPE2"], "kind": "dedicated pins",
        "needs": "nothing for the USRCCLKO/USRDONE pins in fabric timing unless the design drives the flash clock (then a create_generated_clock on USRCCLKO is the design's, brief 20 handling)",
        "supplier": "document only",
        "line": None, "evidence": "document: UG570 (configuration), UG949; not measured",
    },
    "icape": {
        "prims": ["ICAPE3", "ICAPE2"], "kind": "clocked by the design",
        "needs": "its CLK is an ordinary fabric clock (no extra constraint); the configuration port is not a package pin",
        "supplier": "document only", "line": None, "evidence": "document: UG570; not measured",
    },
    "sysmon": {
        "prims": ["SYSMONE1", "SYSMONE4", "XADC"], "kind": "analog inputs and a DCLK",
        "needs": "DCLK is an ordinary fabric clock (1 to 5.2 MHz ADC clock after the internal divider); VP/VN and VAUXP/N are dedicated analog pins: no XDC delay, no I/O standard",
        "supplier": "document only", "line": None, "evidence": "document: UG580, DS925 table 127; not measured",
    },
    "bufgce_div": {
        "prims": ["BUFGCE_DIV"], "kind": "derived clock",
        "needs": "Vivado derives the divided clock from the input clock automatically when the input has a clock; a divider fed by an unclocked pin leaves the output unclocked",
        "supplier": "Vivado (automatic derivation)", "line": None,
        "evidence": "measured (Vivado 2026.1, xck26): the fixture's BUFGCE_DIV output is an auto-derived generated clock (P,G,A, divide by 2) in report_clocks at elaboration and after synthesis, with no constraint of ours",
    },
    "mmcm_pll": {
        "prims": ["MMCME2_ADV", "MMCME3_ADV", "MMCME4_ADV", "PLLE2_ADV", "PLLE3_ADV", "PLLE4_ADV", "MMCME2_BASE", "PLLE2_BASE"],
        "kind": "derived clock",
        "needs": "outputs are derived automatically from the input clock (create_clock on the input only); feedback needs nothing",
        "supplier": "Vivado (automatic derivation)", "line": None,
        "evidence": "measured (Vivado 2026.1, xck26): the fixture's MMCME4_ADV CLKOUT0 and CLKFBOUT are auto-derived (P,G,A) at elaboration and after synthesis; so are clk_u and fb in designs/b96_kr260_10g",
    },
    "gt_channel": {
        "prims": ["GTHE4_CHANNEL", "GTHE3_CHANNEL", "GTYE4_CHANNEL", "GTYE3_CHANNEL", "GTPE2_CHANNEL", "GTXE2_CHANNEL", "GTHE4_COMMON", "GTHE3_COMMON"],
        "kind": "transceiver (serial pads, reference clock, user clocks)",
        "needs": "TXP/TXN/RXP/RXN go to the GT pads: no fabric timing and no XDC delay (placement is the GT site, LOC on the channel); the reference clock port needs a create_clock at its frequency; TXOUTCLK/RXOUTCLK are derived by Vivado through the PLL and the BUFG_GT dividers from that reference clock",
        "supplier": "the design (create_clock on the reference clock port); the board file lists the lane pins and the frequency",
        "line": None,
        "evidence": "measured (Vivado 2026.1, xck26, designs/b96_kr260_10g): after synthesis check_timing is zero in every check, with the four serial pad ports in the top and only the reference clock constrained; the channel and QPLL clocks (TXOUTCLK, RXOUTCLK, QPLL0OUTCLK) are auto-derived (P,G,A) in report_clocks, at elaboration as well",
    },
    "gt_refclk": {
        "prims": ["IBUFDS_GTE4", "IBUFDS_GTE3", "IBUFDS_GTE2", "IBUFDS_GTE5", "IBUFDS_GTHE2"],
        "kind": "transceiver reference clock input",
        "needs": "PACKAGE_PIN on both pins of the pair (the board lane's MGTREFCLK pins) and a create_clock on the P pin at the reference frequency (the N pin takes none)",
        "supplier": "flow (known_pre.xdc) when the board file lists exactly one lane with a reference clock and the design names neither; otherwise the design",
        "line": None, "evidence": "measured (Vivado 2026.1, xck26): 224 p5 run 1 replay: a reference clock with a create_clock but no PACKAGE_PIN on its ports left AVAL-324 (hard block needs LOC), AVAL-326, NSTD-1 and UCIO-1 open; designs/b96_kr260_10g/design.xdc places Y6/Y5 and clocks the P port. The flow now writes the board's pins and frequency",
    },
    "ps8": {
        "prims": ["zynq_ultra_ps_e", "PS8", "zynq_ultra_ps_e_0"],
        "kind": "processor system (Zynq UltraScale+ PS)",
        "needs": "MIO and PS DDR pins are fixed by the PS and take no XDC; PL clocks pl_clk0..3 take their period from the PS IP's own constraints; EMIO routed to PL pins is ordinary fabric I/O and gets an ordinary class; PS-PL AXI crossings follow the IP's clocks",
        "supplier": "the AMD IP (its own XDC, generated with the IP)",
        "line": None, "evidence": "measured (Vivado 2026.1, xck26, designs/b191_ps_axi_lat elaborated): report_clocks lists the PS IP's own pl_clk0 clocks with no XDC of ours for them, and the PS has no top ports (MIO and DDR are fixed by the PS); EMIO through PL pins is not in that design (not measured)",
    },
    "ip_with_xdc": {
        "prims": ["ddr4", "mig", "pcie", "cmac", "xxv_ethernet", "xdma", "axi_ethernet", "gig_ethernet_pcs_pma"],
        "kind": "AMD IP that ships its own XDC (memory controller, PCIe, CMAC, other GT-based IP)",
        "needs": "the IP's pins, clocks and exceptions come from the XDC it generates; our XDC must not duplicate or override them, and the build must read it",
        "supplier": "the AMD IP (ip_tcl generates it with its constraints)",
        "line": None, "evidence": "document: PG150, PG213, PG203; not measured (no such design in this repository)",
    },
}

#: input port names that are resets and what the usual treatment is
_RESET_RX = re.compile(r"(^|_)(a?rst|reset|aresetn?|rstn|resetn|rst_n|reset_n)(_|$|\d)|^a?rst|^a?reset", re.I)
_REFCLK_PRIMS = set(HARD_BLOCKS["gt_refclk"]["prims"])
_GT_PRIMS = set(HARD_BLOCKS["gt_channel"]["prims"])
_GT_PAD_RX = re.compile(r"(^|_)(gt[hxyp]?_?)?(rx|tx)_?[pn]($|_|\d)|(^|_)(rx|tx)[pn]\d*$|^(gt[hxyp]?|mgt)_(rx|tx)", re.I)
_CMD = re.compile(r"^\s*(create_clock|create_generated_clock|set_input_delay|set_output_delay|set_false_path|set_max_delay|set_min_delay|"
                  r"set_clock_groups|set_multicycle_path|set_clock_latency|set_clock_uncertainty|set_case_analysis|set_disable_timing)\b", re.I)


# ---- the design's facts -------------------------------------------------------------------------------------------------------------
def _load_modules(design: Path, cfg: dict, root: Path) -> list[Any]:
    """The modules of the build's sources (SystemVerilog and Verilog; a VHDL entity gives no instances here)."""
    import glob
    try:
        from flow import srcorder
        from flow.standards_check import parse_modules
    except ImportError:                 # run as a script (flow/prepare.py): flow/ itself is on sys.path
        import srcorder  # type: ignore[no-redef]
        from standards_check import parse_modules  # type: ignore[no-redef]
    mods: list[Any] = []
    for pat in cfg.get("sources", []):
        for f in sorted(glob.glob(str(root / pat))):
            if srcorder.is_shell_source(f) or not f.lower().endswith((".sv", ".v", ".svh", ".vh")):
                continue
            try:
                mods += parse_modules(Path(f).read_text(errors="replace"), Path(f).name)
            except OSError:
                pass
    return mods


def hierarchy(mods: list[Any], top: str) -> dict[str, list[str]]:
    """Instance type -> hierarchical paths from the top (``u_jtag/u_bscan``), following instances of modules in ``mods``. A
    library primitive (not a module in ``mods``) is a leaf. Depth-limited (16) so a recursive description cannot loop."""
    by = {m.name: m for m in mods}
    out: dict[str, list[str]] = {}

    def walk(mod: Any, prefix: str, depth: int) -> None:
        for inst in mod.instances:
            path = f"{prefix}{inst['name']}"
            out.setdefault(inst["type"], []).append(path)
            if inst["type"] in by and depth < 16:
                walk(by[inst["type"]], path + "/", depth + 1)

    if top in by:
        walk(by[top], "", 0)
    return out


def _bits(width: str) -> bool:
    return bool(width and width.strip())


def top_port_table(mods: list[Any], top: str) -> dict[str, dict[str, Any]]:
    """Top module ports: name -> {dir (input/output/inout), bus (bool)}."""
    for m in mods:
        if m.name == top:
            return {n: {"dir": p.get("dir") or "input", "bus": _bits(p.get("width", ""))} for n, p in m.ports.items()}
    return {}


def _port_patterns(arg: str) -> list[str]:
    """The names inside the first ``get_ports`` argument of an XDC line: braced lists, bare names, quoted names."""
    out: list[str] = []
    for m in re.finditer(r"get_ports\s+(?:-quiet\s+)?(?:\{([^}]*)\}|\"([^\"]*)\"|([^\s\]]+))", arg):
        out += (m.group(1) or m.group(2) or m.group(3) or "").split()
    return out


def _split_statements(line: str) -> list[str]:
    """Split on ``;`` outside braces and brackets."""
    out, depth, cur = [], 0, ""
    for ch in line:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if ch == ";" and depth <= 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return out + [cur]


def _arg_after(stmt: str, pos: int) -> tuple[str, int]:
    """The Tcl word starting at ``pos`` (after whitespace): a balanced ``[...]`` or ``{...}``, or a bare token."""
    while pos < len(stmt) and stmt[pos].isspace():
        pos += 1
    if pos >= len(stmt):
        return "", pos
    opener = stmt[pos]
    if opener in "[{":
        close, depth, i = {"[": "]", "{": "}"}[opener], 0, pos
        while i < len(stmt):
            if stmt[i] == opener:
                depth += 1
            elif stmt[i] == close:
                depth -= 1
                if depth == 0:
                    return stmt[pos:i + 1], i + 1
            i += 1
        return stmt[pos:], len(stmt)
    j = pos
    while j < len(stmt) and not stmt[j].isspace():
        j += 1
    return stmt[pos:j], j


def xdc_commands(text: str) -> list[dict[str, Any]]:
    """Timing commands of an XDC text (continuation lines joined): command, the text, the port patterns each option names."""
    out: list[dict[str, Any]] = []
    cur = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0]
        if cur:
            line = cur + " " + line.strip()
            cur = ""
        if line.rstrip().endswith("\\"):
            cur = line.rstrip()[:-1]
            continue
        for stmt in [x for x in _split_statements(line) if x.strip()]:
            m = _CMD.match(stmt)
            if not m:
                continue
            opts: dict[str, list[str]] = {}
            for om in re.finditer(r"-(from|to|through)\b", stmt):
                arg, _ = _arg_after(stmt, om.end())
                lst = opts.setdefault(om.group(1), [])
                lst += _port_patterns(arg)
                if "all_inputs" in arg:
                    lst.append("@inputs")
                if "all_outputs" in arg:
                    lst.append("@outputs")
            out.append({"cmd": m.group(1).lower(), "text": stmt.strip(), "opts": opts, "ports": _port_patterns(stmt),
                        "all_in": "all_inputs" in stmt, "all_out": "all_outputs" in stmt})
    return out


def _match(pattern: str, port: str) -> bool:
    """XDC port pattern against a top port name (a bus port matches ``name[*]``, ``name[0]`` or ``name``)."""
    return fnmatch.fnmatchcase(port, re.sub(r"\[[^\]]*\]$", "", pattern.strip()))


def covers(cmds: list[dict[str, Any]], port: str, direction: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(strong, weak): the commands that cover ``port``. Strong: create_clock, set_input_delay (input), set_output_delay (output).
    Weak: a false path or max/min delay naming it (``-from`` for an input, ``-to`` for an output, ``-through`` either). A weak
    cover alone does not satisfy Vivado's check_timing: it lists the port as "no output delay but user has a false path
    constraint" and the post-synthesis gate counts it (measured: p5 arm run 1, led[0] and led[1])."""
    strong: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    for c in cmds:
        cmd = c["cmd"]
        names = c["ports"]
        in_all = c["all_in"] and direction in ("input", "inout")
        out_all = c["all_out"] and direction in ("output", "inout")
        named = any(_match(p, port) for p in names)
        if cmd in ("create_clock", "create_generated_clock") and named:         # a forwarded clock output carries a generated clock (brief 20)
            strong.append(c)
        elif cmd == "set_input_delay" and direction in ("input", "inout") and (named or in_all):
            strong.append(c)
        elif cmd == "set_output_delay" and direction in ("output", "inout") and (named or out_all):
            strong.append(c)
        elif cmd in ("set_false_path", "set_max_delay", "set_min_delay", "set_disable_timing"):
            f = c["opts"].get("from", [])
            t = c["opts"].get("to", [])
            th = c["opts"].get("through", [])
            if direction in ("input", "inout") and (any(_match(p, port) for p in f + th) or ("@inputs" in f + th)):
                weak.append(c)
            elif direction in ("output", "inout") and (any(_match(p, port) for p in t + th) or ("@outputs" in t + th)):
                weak.append(c)
    return strong, weak


# ---- the context ---------------------------------------------------------------------------------------------------------------------
class Ctx:
    """Everything the checks read, loaded once: build.yaml's top and sources, the board file, the spec's async ports."""

    def __init__(self, design: Path, root: Path, board: str | None = None, cfg: dict | None = None):
        self.design, self.root = Path(design), Path(root)
        self.cfg = cfg if cfg is not None else (yaml.safe_load((self.design / "build.yaml").read_text()) if (self.design / "build.yaml").is_file() else {})
        self.top = str(self.cfg.get("top", ""))
        self.board_name = board or self.cfg.get("board") or self._board_from_spec_or_part()
        bf = self.root / "boards" / str(self.board_name) / "board.yaml" if self.board_name else None
        self.board: dict[str, Any] = (yaml.safe_load(bf.read_text()) or {}) if bf and bf.is_file() else {}
        self.mods = _load_modules(self.design, self.cfg, self.root)
        self.ports = top_port_table(self.mods, self.top)
        self.tree = hierarchy(self.mods, self.top)
        self.slow_rx = [re.compile(p) for p in (self.board.get("slow_ports") or [])]
        spec: dict[str, Any] = {}
        if (self.design / "spec.yaml").is_file():
            try:
                spec = yaml.safe_load((self.design / "spec.yaml").read_text()) or {}
            except yaml.YAMLError:
                spec = {}
        self.spec = spec if isinstance(spec, dict) else {}
        self.async_ports: dict[str, str] = {}      # port -> reason ("" when the spec gives none)
        for p in self.spec.get("ports") or []:
            if isinstance(p, dict) and p.get("async") and p.get("name"):
                self.async_ports[str(p["name"])] = str(p.get("reason") or p.get("async_reason") or p.get("why") or "")

    def _board_from_spec_or_part(self) -> str | None:
        """build.yaml often has no ``board``: take spec.yaml's, else the one board whose part matches build.yaml's."""
        try:
            spec = yaml.safe_load((self.design / "spec.yaml").read_text()) if (self.design / "spec.yaml").is_file() else None
        except yaml.YAMLError:
            spec = None
        if isinstance(spec, dict) and spec.get("board") and (self.root / "boards" / str(spec["board"]) / "board.yaml").is_file():
            return str(spec["board"])
        hits = [b.parent.name for b in sorted((self.root / "boards").glob("*/board.yaml"))
                if (yaml.safe_load(b.read_text()) or {}).get("part") == self.cfg.get("part")]
        return hits[0] if len(hits) == 1 else None

    def board_slow(self, port: str) -> bool:
        return any(r.fullmatch(port) or r.fullmatch(f"{port}[0]") for r in self.slow_rx)

    def instances_of(self, prims: list[str]) -> list[tuple[str, str]]:
        """(type, hierarchical path) of every instance of a listed primitive or module."""
        want = {p.lower() for p in prims}
        return [(t, p) for t, paths in self.tree.items() if t.lower() in want for p in paths]

    def refclk_pairs(self) -> list[dict[str, Any]]:
        """Top-level differential reference-clock pairs: (P port, N port) wired to an ``IBUFDS_GTE*`` (its ``I`` and ``IB``), with the
        board's pins and frequency when the board file lists exactly one transceiver lane with a reference clock."""
        lanes = [v for v in ((self.board.get("gt") or {}).values()) if isinstance(v, dict) and isinstance(v.get("refclk"), dict)]
        out = []
        for m in self.mods:
            if m.name != self.top:
                continue
            for inst in m.instances:
                if inst["type"] in _REFCLK_PRIMS:
                    c = inst["conns"] or {}
                    pp = re.findall(r"[A-Za-z_]\w*", str(c.get("I", "")))
                    nn = re.findall(r"[A-Za-z_]\w*", str(c.get("IB", "")))
                    if pp and nn and pp[0] in self.ports and nn[0] in self.ports:
                        row: dict[str, Any] = {"p": pp[0], "n": nn[0], "inst": inst["name"], "pins": None, "mhz": None}
                        if len(lanes) == 1:
                            rc = lanes[0]["refclk"]
                            if rc.get("p") and rc.get("n"):
                                row["pins"] = (str(rc["p"]), str(rc["n"]))
                            row["mhz"] = rc.get("mhz")
                        out.append(row)
        return out

    def top_connections(self, prims: set[str]) -> dict[str, str]:
        """Top port -> primitive type for ports wired straight into an instance of ``prims`` in the top module."""
        out: dict[str, str] = {}
        for m in self.mods:
            if m.name != self.top:
                continue
            for inst in m.instances:
                if inst["type"] in prims:
                    for expr in (inst["conns"] or {}).values():
                        for ident in re.findall(r"[A-Za-z_]\w*", str(expr)):
                            if ident in self.ports:
                                out[ident] = inst["type"]
        return out


def constraint_text(design: Path, cfg: dict, root: Path) -> list[tuple[str, str]]:
    """(file name, text) of the design's XDC files from build.yaml ``constraints``."""
    import glob
    out = []
    for pat in cfg.get("constraints", []):
        for f in sorted(glob.glob(str(root / pat))):
            try:
                out.append((Path(f).name, Path(f).read_text(errors="replace")))
            except OSError:
                pass
    return out


# ---- classification ------------------------------------------------------------------------------------------------------------------
def classify(ctx: Ctx, port: str, info: dict[str, Any], clock_ports: set[str], gt_pads: set[str], gt_refs: dict[str, str], fwd_ports: set[str] = frozenset()) -> tuple[str, str]:
    """(class, why) of one top port. Classes: clock, fwd_clock, gt_refclk, gt_serial, reset, slow, async, input, output."""
    d = info["dir"]
    if port in gt_refs:
        return "gt_refclk", f"feeds {gt_refs[port]}"
    if port in clock_ports:
        return "clock", "create_clock names it"
    if port in fwd_ports:
        return "fwd_clock", "create_generated_clock names it (a forwarded clock, brief 20)"
    if port in gt_pads:
        return "gt_serial", "wired to a transceiver channel's serial pad"
    if _GT_PAD_RX.search(port) and not ctx.board_slow(port):
        return "gt_serial", "name is a transceiver serial pad (rx/tx p/n)"
    if port in ctx.async_ports:
        return "async", ctx.async_ports[port] or "spec.yaml marks the port async: true (no reason given)"
    if ctx.board_slow(port):
        return "slow", "board.yaml slow_ports"
    if d in ("input", "inout") and _RESET_RX.search(port):
        return "reset", "name is a reset"
    return ("input" if d == "input" else "output" if d == "output" else "inout"), "timed data"


def port_classes(ctx: Ctx, xdc: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """One row per top port: name, dir, class, why, covered (the commands that cover it), and what to add when it is not."""
    cmds: list[dict[str, Any]] = []
    for _, t in xdc:
        cmds += xdc_commands(t)
    clock_ports = {p for p in ctx.ports for c in cmds if c["cmd"] == "create_clock" and any(_match(x, p) for x in c["ports"])}
    fwd_ports = {p for p in ctx.ports for c in cmds if c["cmd"] == "create_generated_clock" and any(_match(x, p) for x in c["ports"])}
    gt_pads = set(ctx.top_connections(_GT_PRIMS))
    gt_refs = ctx.top_connections(_REFCLK_PRIMS)
    rows = []
    for port, info in ctx.ports.items():
        cls, why = classify(ctx, port, info, clock_ports, gt_pads, gt_refs, fwd_ports)
        strong, weak = covers(cmds, port, info["dir"])
        ref = f"{port}[*]" if info["bus"] else port
        rows.append({"port": port, "dir": info["dir"], "class": cls, "why": why, "covered": bool(strong) or cls == "gt_serial",
                     "false_path_only": bool(weak) and not strong, "by": [h["text"][:90] for h in (strong or weak)[:2]], "ref": ref})
    # a differential refclk: the N port takes no clock of its own when the P port has one
    byname = {r["port"]: r for r in rows}
    for r in rows:
        if r["class"] == "gt_refclk" and not r["covered"]:
            m = re.match(r"(.*?)(_?)n$", r["port"], re.I)
            peer = (m.group(1) + m.group(2) + ("p" if r["port"][-1] == "n" else "P")) if m else None
            if peer and peer in byname and byname[peer]["covered"] and byname[peer]["class"] == "gt_refclk":
                r["covered"] = True
                r["by"] = [f"the P port {peer} has the clock"]
    return rows


def _fix_for(row: dict[str, Any], ctx: Ctx) -> str:
    port, ref, cls, d = row["port"], row["ref"], row["class"], row["dir"]
    gp = f"[get_ports {{{ref}}}]"
    if cls == "gt_refclk":
        mhz = None
        for lane in ((ctx.board.get("gt") or {}).values()):
            mhz = ((lane or {}).get("refclk") or {}).get("mhz") or mhz
        per = f"{1000.0 / float(mhz):.3f}" if mhz else "<period from the board file or the spec>"
        return f"create_clock -name {port.rsplit('_', 1)[0] if port.lower().endswith(('_p', '_n')) else port} -period {per} [get_ports {{{port}}}]   (the transceiver reference clock, P pin)"
    if cls == "clock":
        return f"create_clock -name {port} -period <period> {gp}"
    if cls in ("slow", "async"):
        reason = "board.yaml slow_ports" if cls == "slow" else (row["why"] or "state the reason")
        side, dl = ("-from", "set_input_delay") if d == "input" else ("-to", "set_output_delay")
        return (f"# {reason}: no timing relation to any clock\n{dl} -clock <board clock> 0.000 {gp}\nset_false_path {side} {gp}"
                f"   (the flow writes both itself: known_post.xdc)")
    if row.get("false_path_only"):
        dl = "set_input_delay" if d == "input" else "set_output_delay"
        return (f"{dl} -clock <clk> 0.000 {gp} next to the existing false path, as a placeholder (check_timing still lists a port "
                f"that has a false path and no delay); a real delay only with the data-sheet terms in a comment above it")
    if cls == "reset":
        return (f"# asynchronous reset into a synchroniser (state which): set_false_path -from {gp}\n"
                f"   or, if the reset is synchronous and timed: set_input_delay -clock <clk> -max <tSU+trace> {gp} and -min <tH+trace>")
    if d == "input":
        return f"set_input_delay -clock <clk> -max <tCO_max+trace_max> {gp}; set_input_delay -clock <clk> -min <tCO_min+trace_min> {gp}   (numbers from the interface's data sheet)"
    if d == "output":
        return f"set_output_delay -clock <clk> -max <tSU+trace_max> {gp}; set_output_delay -clock <clk> -min <-tH+trace_min> {gp}   (numbers from the interface's data sheet), or set_false_path -to {gp} with the reason if the output is quasi-static"
    return f"set_input_delay and set_output_delay on {gp}, or a commented set_false_path"


def block_findings(ctx: Ctx, xdc: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """FDA-CON-15: a clock-generating primitive with no clock and no automatic derivation, from the RTL's instances."""
    text = "\n".join(t for _, t in xdc)
    known = known_items(ctx)
    out = []
    for item in known["blocks"]:
        if item["line"] is None:
            continue
        clk = item["clock"]
        if re.search(rf"create_clock[^\n]*{re.escape(item['pin'])}", text) or re.search(rf"create_clock[^\n]*-name\s+{clk}\b", text) \
                or item["written_by_flow"]:
            continue
        out.append({"file": "rtl", "rule": "FDA-CON-15", "line": 0, "text": f"{item['type']} {item['path']}",
                    "message": f"{item['type']} instance {item['path']} is a clock source Vivado cannot derive: {item['needs']}. Add: {item['line']}"})
    return out


# ---- what the flow writes ------------------------------------------------------------------------------------------------------------
def known_items(ctx: Ctx) -> dict[str, list[dict[str, Any]]]:
    """The constraints the flow knows without a model: ``blocks`` (a primitive's clock) and ``slow`` (false paths)."""
    blocks: list[dict[str, Any]] = []
    for key in ("bscane2", "usr_accesse2"):
        hb = HARD_BLOCKS[key]
        for typ, path in ctx.instances_of(hb["prims"]):
            pin = f"{path}/{'INTERNAL_TCK' if key == 'bscane2' else 'CCLK'}"
            blocks.append({"type": typ, "path": path, "pin": pin, "clock": "jtag_tck" if key == "bscane2" else "usr_cclk",
                           "line": hb["line"].replace("{i}", path), "needs": hb["needs"], "written_by_flow": True, "key": key})
    # only the first instance of each kind gets the named clock (a second one would need its own name and period: left to the design)
    seen: set[str] = set()
    uniq = []
    for b in blocks:
        if b["key"] in seen:
            b["clock"] = f"{b['clock']}_{len([x for x in uniq if x['key'] == b['key']])}"
            b["line"] = re.sub(r"-name \S+", f"-name {b['clock']}", b["line"])
        seen.add(b["key"])
        uniq.append(b)
    slow = []
    for port, info in ctx.ports.items():
        if info["dir"] not in ("input", "output", "inout"):
            continue
        reason = None
        if ctx.board_slow(port):
            reason = "board.yaml slow_ports: user I/O with no timing relation to any clock"
        elif port in ctx.async_ports:
            reason = "spec.yaml async: true" + (f": {ctx.async_ports[port]}" if ctx.async_ports[port] else " (no reason given: add one to the spec)")
        if reason:
            slow.append({"port": port, "dir": info["dir"], "ref": f"{port}[*]" if info["bus"] else port, "reason": reason})
    return {"blocks": uniq, "slow": slow}


def known_pre_xdc(ctx: Ctx, xdc: list[tuple[str, str]] | None = None) -> str:
    """The text of ``<build>/known_pre.xdc``, read before the design's XDC: the clocks of primitives Vivado cannot derive (empty
    string when there are none). A create_clock of the design's own on the same pin replaces ours."""
    k = known_items(ctx)
    text = "\n".join(t for _, t in (xdc or []))
    # a clock the design's XDC already defines on that pin is the design's: write nothing for it (a second create_clock would replace it,
    # and the false path below names OUR clock)
    k["blocks"] = [b for b in k["blocks"] if not re.search(rf"create_clock[^\n]*{re.escape(b['pin'])}", text)]
    lines: list[str] = []
    refs = []
    if len(ctx.refclk_pairs()) == 1:        # one reference clock, one board lane: the board file's pins and frequency are the facts; several: the design says
        r = ctx.refclk_pairs()[0]
        has_pin = lambda port: re.search(rf"PACKAGE_PIN[^\n]*\b{re.escape(port)}\b", text) is not None          # noqa: E731
        has_clk = re.search(rf"create_clock[^\n]*\b{re.escape(r['p'])}\b", text) is not None
        if r["pins"] and not (has_pin(r["p"]) or has_pin(r["n"])):
            refs.append(f"# {r['p']}/{r['n']}: the transceiver reference clock pair of the board lane (board.yaml gt refclk p/n): placement")
            refs.append(f"set_property PACKAGE_PIN {r['pins'][0]} [get_ports {{{r['p']}}}]")
            refs.append(f"set_property PACKAGE_PIN {r['pins'][1]} [get_ports {{{r['n']}}}]")
        if r["mhz"] and not has_clk:
            refs.append(f"# {r['p']}: reference clock {r['mhz']} MHz (board.yaml gt refclk mhz)")
            refs.append(f"create_clock -name {re.sub(r'_[pP]$', '', r['p'])} -period {1000.0 / float(r['mhz']):.3f} [get_ports {{{r['p']}}}]")
    bf = ctx.board.get("clock") or {}
    bc = board_clock_port(ctx, xdc) if bf.get("freq_mhz") else None
    if bc and not re.search(rf"create_clock[^\n]*\b{re.escape(bc)}\b", text):
        refs.append(f"# {bc}: the board's clock input (board.yaml clock: pin {bf.get('pin')}, {bf['freq_mhz']} MHz)")
        refs.append(f"create_clock -name {bc} -period {1000.0 / float(bf['freq_mhz']):.3f} [get_ports {{{bc}}}]")
    if refs:
        lines.append("# Clock inputs the board file defines (flow/known_constraints.py, brief 230): the board clock, and the transceiver reference clock's pins and frequency.")
        lines += refs
    if k["blocks"]:
        lines.append("# Clocks of the primitives in this design that Vivado cannot derive (flow/known_constraints.py, brief 230).")
        lines.append("# Read before design.xdc: a create_clock of your own on the same pin replaces these.")
    for b in k["blocks"]:
        lines.append(f"# {b['type']} {b['path']}: {b['needs']}")
        lines.append(b["line"])
    return "\n".join(lines) + "\n" if lines else ""


def board_clock_port(ctx: Ctx, xdc: list[tuple[str, str]]) -> str | None:
    """The top port that carries the board's clock: the port whose PACKAGE_PIN is board.yaml's clock pin, else the first top input
    with a create_clock that is not a transceiver reference clock."""
    text = "\n".join(t for _, t in xdc)
    pin = str((ctx.board.get("clock") or {}).get("pin") or "").strip()
    if pin:
        for m in re.finditer(r"PACKAGE_PIN\s+(\w+)[^\n]*?get_ports\s+\{?\s*([A-Za-z_]\w*)", text):
            if m.group(1) == pin and m.group(2) in ctx.ports:
                return m.group(2)
    refs = ctx.top_connections(_REFCLK_PRIMS)
    for c in xdc_commands(text):
        if c["cmd"] == "create_clock":
            for p in c["ports"]:
                base = re.sub(r"\[[^\]]*\]$", "", p)
                if base in ctx.ports and base not in refs:
                    return base
    return None


def known_post_xdc(ctx: Ctx, xdc: list[tuple[str, str]]) -> str:
    """The text of ``<build>/known_post.xdc``, read after the design's XDC: for each slow or asynchronous port the design's XDC does
    not already cover, the 0 ns placeholder delay (Vivado's check_timing lists a port with only a false path as having no delay) and
    the commented false path, as flow/io_check.py FDA-CON-11 requires and designs/b96_kr260_10g does by hand."""
    k = known_items(ctx)
    if not k["slow"]:
        return ""
    cmds: list[dict[str, Any]] = []
    for _, t in xdc:
        cmds += xdc_commands(t)
    clk = board_clock_port(ctx, xdc)
    lines = ["# False paths and 0 ns placeholder delays of ports with no timing relation to any clock (board slow_ports, or the spec's async: true).",
             "# flow/known_constraints.py, brief 230. Read after design.xdc; a port the design's XDC already constrains is left alone.",
             "# One command per kind: Vivado reports a false path whose every object carries no path (a constant output) as EXC-IGNORED, so the",
             "# ports are listed together and one live port keeps the command in use."]
    delays: dict[str, list[str]] = {"set_input_delay": [], "set_output_delay": []}
    fps: dict[str, list[str]] = {"-from": [], "-to": []}
    for s in k["slow"]:
        sides = [("set_input_delay", "-from"), ("set_output_delay", "-to")] if s["dir"] == "inout" else \
            [("set_input_delay", "-from") if s["dir"] == "input" else ("set_output_delay", "-to")]
        wrote = False
        for dl, side in sides:
            has_delay = any(c["cmd"] == dl and any(_match(p, s["port"]) for p in c["ports"]) for c in cmds)
            has_fp = bool([c for c in cmds if c["cmd"] == "set_false_path" and any(_match(p, s["port"]) for p in c["opts"].get(side[1:], []))])
            if has_delay and has_fp:
                continue
            if not wrote:
                lines.append(f"# {s['port']}: {s['reason']}")
                wrote = True
            if not has_delay and clk:
                delays[dl].append(s["ref"])
            elif not has_delay:
                lines.append(f"# no board clock port found in the design's XDC: no placeholder delay written for {s['port']}")
            if not has_fp:
                fps[side].append(s["ref"])
    for dl, refs in delays.items():
        if refs:
            lines.append(f"{dl} -clock [get_clocks -of_objects [get_ports {{{clk}}}]] 0.000 [get_ports {{{' '.join(refs)}}}]")
    for side, refs in fps.items():
        if refs:
            lines.append(f"set_false_path {side} [get_ports {{{' '.join(refs)}}}]")
    wrote_any = any(delays.values()) or any(fps.values())
    return "\n".join(lines) + "\n" if wrote_any else ""


# ---- the pre-synthesis findings --------------------------------------------------------------------------------------------------------
def findings(design: Path, root: Path, cfg: dict | None = None, board: str | None = None, extra_xdc: bool = True) -> list[dict[str, Any]]:
    """FDA-CON-14 (a top port no constraint covers) and FDA-CON-15 (a clock source nothing clocks), before synthesis. Empty while
    the top module's source does not exist yet or the build has no XDC yet."""
    ctx = Ctx(design, root, board=board, cfg=cfg)
    if not ctx.ports:
        return []
    xdc = constraint_text(ctx.design, ctx.cfg, ctx.root)
    if not xdc:
        return []
    uncertain = any(re.search(r"\bforeach\b|\bfor\b\s*\{|\$\w", re.sub(r"(?m)#.*$", "", t)) for _, t in xdc)
    kx = (known_pre_xdc(ctx, xdc) + known_post_xdc(ctx, xdc)) if extra_xdc else ""
    rows = port_classes(ctx, xdc + ([("known.xdc", kx)] if kx else []))
    out = []
    for r in ([] if uncertain else rows):       # an XDC that builds its port lists in Tcl (variables, loops) cannot be read as text: no port finding
        if r["covered"]:
            continue
        out.append({"file": "rtl", "rule": "FDA-CON-14", "line": 0, "text": f"port {r['port']} ({r['dir']}, class {r['class']})",
                    "message": f"top port {r['port']} is a {r['class']} port ({r['why']}) and no constraint covers it. Every top port needs one "
                               f"class and a line before synthesis. Add: {_fix_for(r, ctx)}"})
    out += block_findings(ctx, xdc)
    return out


def info_lines(ctx: Ctx, xdc: list[tuple[str, str]] | None = None) -> list[str]:
    """What the flow writes itself, for the tool outputs: one line per primitive clock, one line for the slow-port constraints."""
    xdc = xdc if xdc is not None else constraint_text(ctx.design, ctx.cfg, ctx.root)
    out = [f"written by the flow (known_pre.xdc, before design.xdc): {ln}" for ln in known_pre_xdc(ctx, xdc).splitlines() if ln and not ln.startswith("#")]
    ports = re.findall(r"(?m)^# (\S+): ", known_post_xdc(ctx, xdc))
    if ports:
        out.append(f"written by the flow (known_post.xdc, after design.xdc): a 0 ns placeholder delay and a false path on {', '.join(ports)} "
                   f"(board slow_ports or spec async: true: no timing relation to any clock)")
    return out


# ---- the repair note -----------------------------------------------------------------------------------------------------------------
def explain_unconstrained(ports: dict[str, list[str]], ctx: Ctx) -> list[str]:
    """For a post-synthesis check_timing list (``parse_check_timing_ports``): each endpoint group with its class and the line to
    add, or the question when the class is unknown. Replaces the raw report in the repair note."""
    k = known_items(ctx)
    block_by_prefix = {b["path"]: b for b in k["blocks"]}
    rows = {r["port"]: r for r in port_classes(ctx, constraint_text(ctx.design, ctx.cfg, ctx.root))} if ctx.ports else {}
    lines: list[str] = []

    def base(n: str) -> str:
        return re.sub(r"\[[^\]]*\]$", "", n)

    # unclocked register pins, grouped by the instance path they sit under
    groups: dict[str, list[str]] = {}
    for name in ports.get("no_clock", []) + ports.get("unconstrained_internal_endpoints", []):
        groups.setdefault(name.split("/")[0] if "/" in name else name, []).append(name)
    for head, names in groups.items():
        owner = None
        for path, b in block_by_prefix.items():
            if head == path.split("/")[0]:
                owner = b
        if owner:
            lines.append(f"{len(names)} pin(s) under {head} (e.g. {names[0]}): {owner['type']} {owner['path']} has no clock. "
                         f"Cause: {owner['needs']}. Line: {owner['line']}")
            continue
        jt = next((b for b in k["blocks"] if b["key"] == "bscane2"), None)
        if jt and head.split("/")[0] == jt["path"].split("/")[0]:
            lines.append(f"{len(names)} pin(s) under {head} (e.g. {names[0]}): registers in the JTAG TCK domain. Line: {jt['line']}")
            continue
        lines.append(f"{len(names)} pin(s) under {head} (e.g. {names[0]}): no clock reaches them and the class of their clock source is unknown. "
                     f"Question: which port, primitive or generated clock should clock {head}? Constrain that source (create_clock on its port or pin; "
                     f"a generated clock needs create_generated_clock with -source).")
    for key, what in (("no_input_delay", "input"), ("no_output_delay", "output")):
        by_base: dict[str, list[str]] = {}
        for n in ports.get(key, []):
            by_base.setdefault(base(n), []).append(n)
        for b, names in by_base.items():
            r = rows.get(b)
            shown = names[0] if len(names) == 1 else f"{b} ({len(names)} bits: {', '.join(names[:4])}{', ...' if len(names) > 4 else ''})"
            if r is None:
                lines.append(f"{what} port {shown}: not a top port of the RTL I can read; question: what drives or loads it?")
            else:
                lines.append(f"{what} port {shown}: class {r['class']} ({r['why']}). Add: {_fix_for(r, ctx)}")
    return lines
