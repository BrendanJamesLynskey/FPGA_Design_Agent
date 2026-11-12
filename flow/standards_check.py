#!/usr/bin/env python3
"""Design-standards checker (brief 05d, Taylor addition 3): docs/design_standards.md v1.0, rule by rule.

    python3 flow/standards_check.py designs/<name> [--variant base] [--json OUT]

Every rule has an id, a stage (``rtl`` runs on the sources, ``post_synth`` on the Vivado reports) and a status:

    pass         checked, no finding
    fail         checked, findings listed (file, line, message)
    not_run      a checkable rule whose tool is missing here (Verilator, Yosys) or whose report is absent;
                 counts as a failure (an unchecked rule is not a pass)
    review_only  cannot be checked by a program; listed so the human reviewer sees it

Exit status 0 only if no checkable rule failed or went unchecked. A finding may be waived on its line (or the line
above) by ``// std-waive: <RULE> <reason>``; a waiver without a reason is itself a finding (STD-WAIVE-01).

The static rules read the SystemVerilog with a small scanner (comments and strings removed, modules, ports, always
blocks, assigns, instances), not a full parser; the latch and loop rules use Verilator's warnings and Yosys's
``proc`` and ``check``. Raw findings only: no fix hints (the harness stays neutral).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    from flow import architecture as arch_mod
except ImportError:                     # run as a script: flow/ itself is on sys.path
    import architecture as arch_mod     # type: ignore[no-redef]

try:
    from flow import srcorder
except ImportError:
    import srcorder                     # type: ignore[no-redef]

try:
    from flow import vhdl
except ImportError:
    import vhdl                         # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0"

#: id -> (stage, title, how it is checked)
RULES: dict[str, tuple[str, str, str]] = {
    "STD-ARCH-00": ("rtl", "architecture.yaml exists and has the shape the checker reads",
                    "flow/architecture.py check_architecture"),
    "STD-CLK-01": ("rtl", "no derived or gated clocks: every clock a register uses is a clock input, an alias of one, "
                          "or the output of a clock-network primitive (MMCM, PLL, BUFG)",
                   "static scan: edge signals of every always block against ports, assigns and instance outputs; "
                   "clock-gating primitives (BUFGCE, BUFGMUX, BUFHCE) refused"),
    "STD-CLK-02": ("rtl", "every clock of the top module is declared in architecture.yaml clock_domains",
                   "static scan against architecture.yaml"),
    "STD-CLK-03": ("post_synth", "every clock source in the synthesised design's clock network is a declared domain",
                   "clock-net scan of report_clock_networks (clock_networks_synth.rpt) against architecture.yaml"),
    "STD-RST-01": ("rtl", "synchronous reset: a reset is not in a sensitivity list (the bank's reset-strategy skill: "
                          "follow the spec; FPGA default synchronous), except in a declared reset synchroniser",
                   "static scan of sensitivity lists; architecture.yaml reset.synchronisers or a waiver"),
    "STD-LATCH-01": ("rtl", "no latches", "Verilator -Wall LATCH warnings; Yosys proc (a $dlatch cell)"),
    "STD-LOOP-01": ("rtl", "no combinational loops", "Verilator UNOPTFLAT warnings; Yosys check (logic loop)"),
    "STD-INIT-01": ("rtl", "no initial blocks in synthesisable RTL except ROM initialisation ($readmemh/$readmemb)",
                    "static scan; // synthesis translate_off regions are skipped"),
    "STD-CDC-01": ("rtl", "every clock-domain crossing is a named CDC primitive from the bank, listed in "
                          "architecture.yaml crossings, and instantiated; no module mixes two clocks outside one",
                   "architecture.yaml crossings against the instances in the RTL; static scan of clocks per module"),
    "STD-CDC-02": ("post_synth", "report_cdc on the synthesised netlist has no Critical row",
                   "Vivado report_cdc (cdc_synth.rpt), gate post_synth_cdc_no_critical"),
    "STD-METH-01": ("post_synth", "report_methodology on the synthesised netlist has no Critical Warning",
                    "Vivado report_methodology, gate post_synth_methodology_no_critical"),
    "STD-AXI-01": ("rtl", "a new block interface is AXI4-Lite or AXI4-Stream with AMBA port names (prefix_awvalid, "
                          "prefix_tdata ...) and the right direction",
                   "architecture.yaml interfaces against the module's ports"),
    "STD-AXI-02": ("rtl", "ports named like an AXI interface belong to a declared interface",
                   "port-name pattern scan"),
    "STD-WAIVE-01": ("rtl", "every waiver states a reason", "static scan of std-waive comments"),
    "STD-REV-01": ("review", "a multi-bit crossing uses Gray code, a handshake or an asynchronous FIFO, never a bit-by-bit "
                             "synchroniser", "review only: the data type of a crossing is not in the netlist"),
    "STD-REV-02": ("review", "AXI protocol semantics: valid is not withdrawn before ready, no combinational "
                             "ready-to-valid loop", "review only (a formal property is the way to check it)"),
    "STD-REV-03": ("review", "reset values and enables follow the spec and the bank's reset-strategy skill",
                   "review only"),
}
CLOCK_PRIMS = re.compile(r"^(MMCM\w*|PLL\w*|BUFG(?!CE|MUX)\w*|BUFH|BUFR|BUFIO|IBUFDS?|IBUF|BUFGCTRL|DCM\w*)$")
GATING_PRIMS = re.compile(r"^(BUFGCE\w*|BUFGMUX\w*|BUFHCE|BUFMRCE)$")
_WAIVE = re.compile(r"//\s*std-waive:\s*(STD-[A-Z]+-\d+)\s*(.*)")
_KEYWORDS = {"if", "else", "begin", "end", "case", "casez", "casex", "endcase", "for", "while", "assign", "always",
             "always_ff", "always_comb", "always_latch", "initial", "module", "endmodule", "generate", "endgenerate",
             "function", "endfunction", "task", "endtask", "parameter", "localparam", "wire", "reg", "logic", "input",
             "output", "inout", "genvar", "integer", "int", "typedef", "enum", "struct", "return", "default", "posedge",
             "negedge", "or", "and", "not", "import", "package", "interface", "modport", "bit", "byte", "shortint",
             "longint", "signed", "unsigned", "var", "automatic", "static", "assert", "assume", "cover", "property",
             "sequence", "disable", "fork", "join"}


@dataclass
class Finding:
    file: str
    line: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "message": self.message}


@dataclass
class Module:
    name: str
    file: str
    line: int
    body: str                               # comment-free text, line structure kept
    body_line0: int                         # line number of the first body character
    ports: dict[str, dict[str, Any]] = field(default_factory=dict)      # name -> {dir, width}
    always: list[dict[str, Any]] = field(default_factory=list)
    assigns: dict[str, tuple[str, int]] = field(default_factory=dict)  # lhs identifier -> (rhs text, line)
    instances: list[dict[str, Any]] = field(default_factory=list)


# ---- scanner ---------------------------------------------------------------------------------------------
def strip_comments(text: str) -> tuple[str, dict[int, tuple[str, str]]]:
    """Comments and strings blanked (newlines kept, so line numbers match); waivers by line number."""
    waivers: dict[int, tuple[str, str]] = {}
    for i, line in enumerate(text.splitlines(), 1):
        m = _WAIVE.search(line)
        if m:
            waivers[i] = (m.group(1), m.group(2).strip())
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append('"' + " " * (j - i - 1) + '"')
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out), waivers


def drop_translate_off(raw: str) -> str:
    """Remove ``// synthesis translate_off`` ... ``translate_on`` regions (also ``pragma``), keeping newlines."""
    out, off = [], False
    for line in raw.splitlines():
        low = line.lower()
        if re.search(r"//\s*(synopsys|synthesis|pragma)\s+translate_off", low):
            off = True
        out.append("" if off else line)
        if re.search(r"//\s*(synopsys|synthesis|pragma)\s+translate_on", low):
            off = False
    return "\n".join(out)


def _balanced(text: str, i: int, open_c: str = "(", close_c: str = ")") -> int:
    """Index just past the group opening at ``text[i]``."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == open_c:
            depth += 1
        elif text[j] == close_c:
            depth -= 1
            if depth == 0:
                return j + 1
    return len(text)


def _split_top(text: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for c in text:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def _line_of(text: str, pos: int, line0: int = 1) -> int:
    return line0 + text.count("\n", 0, pos)


def _parse_ports(header: str, body: str) -> dict[str, dict[str, Any]]:
    ports: dict[str, dict[str, Any]] = {}
    direction = None
    for item in _split_top(header):
        it = re.sub(r"\s+", " ", item.strip())
        if not it:
            continue
        m = re.match(r"(input|output|inout)\b", it)
        if m:
            direction = m.group(1)
        if direction is None:
            continue
        it = it.split("=")[0]
        width = " ".join(re.findall(r"\[[^\]]*\]", it)[:1])
        name = re.findall(r"[A-Za-z_]\w*", re.sub(r"\[[^\]]*\]", " ", it))
        if name:
            ports[name[-1]] = {"dir": direction, "width": width}
    for m in re.finditer(r"\b(input|output|inout)\b([^;]*);", body):          # non-ANSI declarations in the body
        for item in _split_top(m.group(2)):
            nm = re.findall(r"[A-Za-z_]\w*", re.sub(r"\[[^\]]*\]", " ", item))
            if nm and nm[-1] not in _KEYWORDS:
                ports.setdefault(nm[-1], {"dir": m.group(1), "width": " ".join(re.findall(r"\[[^\]]*\]", item)[:1])})
    return ports


def parse_modules(text: str, fname: str) -> list[Module]:
    clean, _ = strip_comments(text)
    mods = []
    for m in re.finditer(r"\bmodule\s+(?:automatic\s+|static\s+)?([A-Za-z_]\w*)", clean):
        i = m.end()
        j = i
        while j < len(clean) and clean[j].isspace():
            j += 1
        if clean[j:j + 1] == "#":                               # parameter port list
            k = clean.find("(", j)
            j = _balanced(clean, k) if k >= 0 else j
            while j < len(clean) and clean[j].isspace():
                j += 1
        header = ""
        if clean[j:j + 1] == "(":
            e = _balanced(clean, j)
            header = clean[j + 1:e - 1]
            j = e
        semi = clean.find(";", j)
        end = clean.find("endmodule", semi if semi >= 0 else j)
        body_start = (semi + 1) if semi >= 0 else j
        body = clean[body_start:end if end >= 0 else len(clean)]
        mod = Module(m.group(1), fname, _line_of(clean, m.start()), body, _line_of(clean, body_start))
        mod.ports = _parse_ports(header, body)
        _scan_body(mod)
        mods.append(mod)
    return mods


def _idents(expr: str) -> list[str]:
    return [x for x in re.findall(r"(?<![\w'$.])[A-Za-z_]\w*", expr) if x not in _KEYWORDS]


def _scan_body(mod: Module) -> None:
    b, l0 = mod.body, mod.body_line0
    for m in re.finditer(r"\balways(_ff|_comb|_latch)?\b\s*(@\s*(\*|\([^)]*\))?)?", b):
        kind = m.group(1) or ""
        sens = (m.group(3) or m.group(2) or "").strip()
        edges = [(e, s) for e, s in re.findall(r"\b(posedge|negedge)\s+([A-Za-z_][\w.]*)", sens)]
        mod.always.append({"kind": kind, "sens": sens, "edges": edges, "line": _line_of(b, m.start(), l0)})
    for m in re.finditer(r"\bassign\b\s+([^;=]+?)\s*=\s*([^;]+);", b):
        for lhs in _idents(m.group(1)):
            mod.assigns[lhs] = (m.group(2).strip(), _line_of(b, m.start(), l0))
    for m in re.finditer(r"\b(?:wire|logic)\b(?:\s*\[[^\]]*\])?\s+([A-Za-z_]\w*)\s*=\s*([^;]+);", b):   # wire x = expr;
        mod.assigns.setdefault(m.group(1), (m.group(2).strip(), _line_of(b, m.start(), l0)))
    for m in re.finditer(r"(?<![\w.])([A-Za-z_]\w*)\s*(?:#\s*\()?", b):
        typ = m.group(1)
        if typ in _KEYWORDS:
            continue
        j = m.end()
        if b[m.start():m.end()].rstrip().endswith("("):                # parameter override list
            j = _balanced(b, b.rfind("(", m.start(), m.end()))
        mm = re.match(r"\s*([A-Za-z_]\w*)\s*\(\s*(\.|\))", b[j:])
        if not mm and not b[m.start():m.end()].rstrip().endswith("("):
            mm = None
        if not mm or mm.group(1) in _KEYWORDS:
            continue
        k = j + b[j:].find("(", mm.start())
        e = _balanced(b, k)
        conns = {}
        for c in _split_top(b[k + 1:e - 1]):
            cm = re.match(r"\s*\.\s*([A-Za-z_]\w*)\s*\((.*)\)\s*$", c, re.S)
            if cm:
                conns[cm.group(1)] = cm.group(2).strip()
        mod.instances.append({"type": typ, "name": mm.group(1), "conns": conns, "line": _line_of(b, m.start(), l0)})


# ---- the rules -------------------------------------------------------------------------------------------
class Check:
    def __init__(self, design: Path, root: Path = ROOT, variant: str = "base", stage: str | None = None):
        self.design, self.root, self.variant = design.resolve(), root, variant
        self.findings: dict[str, list[Finding]] = {r: [] for r in RULES}
        self.notes: dict[str, str] = {}
        self.not_run: dict[str, str] = {}
        self.arch = arch_mod.load(self.design) if (self.design / "architecture.yaml").is_file() else {}
        self.rtl_files = sorted(glob.glob(str(self.design / "rtl" / "*.sv")) + glob.glob(str(self.design / "rtl" / "*.v")))
        self.vhdl_error: str | None = None
        if vhdl.design_language(self.design) == "vhdl":   # brief 55: the rules read the GHDL netlist of the VHDL
            self.rtl_files = self._vhdl_netlist()
        self.waivers: dict[str, dict[int, tuple[str, str]]] = {}
        self.texts: dict[str, str] = {}
        self.modules: list[Module] = []
        for f in self.rtl_files:
            text = Path(f).read_text(errors="replace")
            self.texts[f] = text
            _, self.waivers[f] = strip_comments(text)
            self.modules += parse_modules(drop_translate_off(text) if False else text, f)
        self.lib: dict[str, Module] = {}
        for f in sorted(glob.glob(str(self.root / "shell" / "rtl" / "*.sv"))):
            for m in parse_modules(Path(f).read_text(errors="replace"), f):
                self.lib[m.name] = m
        self.by_name = {**self.lib, **{m.name: m for m in self.modules}}

    def _vhdl_netlist(self) -> list[str]:
        """Brief 55: the design's VHDL as one Verilog netlist (GHDL synthesis, hierarchy kept, generics at their
        defaults), which the static rules read like SystemVerilog. GHDL turns every VHDL signal initial value into an
        ``initial`` assignment; those are configuration INIT values (VHDL has no initial blocks), so they are removed
        before STD-INIT-01 looks. On a GHDL failure the RTL rules report it as not run."""
        vh = sorted(p for p in (self.design / "rtl").glob("*") if vhdl.is_vhdl(p))
        top = self.top()
        if not vh or not top:
            return []
        try:
            net = vhdl.to_verilog(vh, vhdl.top_entity(vh, top), {}, self.design / "build" / "vhdl_std")
        except RuntimeError as e:
            self.vhdl_error = str(e)[:300]
            return []
        text = re.sub(r"^\s*initial\s*\n\s*[^;]*;\n", "", net.read_text(), flags=re.M)
        # a VHDL signal with an initial value comes out as `reg x; always @* x = y; // (isignal)`: a plain alias, so it is
        # written as `wire x; assign x = y;`, which the clock and reset rules follow (a clock alias is not a derived clock)
        alias = re.findall(r"^\s*always @\*\s*\n\s*(\w+) = ([^;]+); // \(isignal\)", text, flags=re.M)
        text = re.sub(r"^(\s*)always @\*\s*\n\s*(\w+) = ([^;]+); // \(isignal\)", r"\1assign \2 = \3;", text, flags=re.M)
        for name, _ in alias:
            text = re.sub(rf"^(\s*)reg((?:\s*\[[^\]]*\])?\s+{re.escape(name)};)", r"\1wire\2", text, flags=re.M)
        out = net.with_name(f"{top}_standards.v")
        out.write_text(text)
        self.notes["vhdl"] = f"VHDL design: the rules read the GHDL netlist {out.name}; line numbers are the netlist's"
        return [str(out)]

    # -- helpers
    def rel(self, f: str) -> str:
        try:
            return str(Path(f).resolve().relative_to(self.design))
        except ValueError:
            return Path(f).name

    def add(self, rule: str, mod_or_file: Module | str, line: int, message: str) -> None:
        f = mod_or_file.file if isinstance(mod_or_file, Module) else mod_or_file
        w = self.waivers.get(f, {})
        for ln in (line, line - 1):
            if ln in w and w[ln][0] == rule and w[ln][1]:
                return
        self.findings[rule].append(Finding(self.rel(f), line, message))

    def top(self) -> str | None:
        try:
            return yaml.safe_load((self.design / "build.yaml").read_text()).get("top")
        except (OSError, AttributeError, yaml.YAMLError):
            return None

    def resolve_alias(self, mod: Module, sig: str, depth: int = 0) -> str:
        """Follow ``assign a = b;`` where b is a plain identifier."""
        sig = sig.split(".")[0]
        if sig in mod.assigns and depth < 8:
            rhs = mod.assigns[sig][0]
            if re.fullmatch(r"\s*[A-Za-z_]\w*\s*", rhs):
                return self.resolve_alias(mod, rhs.strip(), depth + 1)
        return sig

    def clock_ports(self, mod: Module, memo: dict[str, set[str]] | None = None) -> set[str]:
        """Input ports of ``mod`` its registers (or children) use as a clock."""
        memo = memo if memo is not None else {}
        if mod.name in memo:
            return memo[mod.name]
        memo[mod.name] = set()
        out = set()
        for a in mod.always:
            if a["edges"]:
                s = self.resolve_alias(mod, a["edges"][0][1])
                if mod.ports.get(s, {}).get("dir") == "input":
                    out.add(s)
        for inst in mod.instances:
            child = self.by_name.get(inst["type"])
            cps = self.clock_ports(child, memo) if child else {p for p in inst["conns"] if re.search(r"clk|clock", p, re.I)}
            for p in cps:
                expr = inst["conns"].get(p)
                if expr and re.fullmatch(r"[A-Za-z_]\w*", expr):
                    s = self.resolve_alias(mod, expr)
                    if mod.ports.get(s, {}).get("dir") == "input":
                        out.add(s)
        memo[mod.name] = out
        return out

    # -- rules
    def rule_arch(self) -> None:
        p = self.design / "architecture.yaml"
        if not p.is_file():
            self.add("STD-ARCH-00", str(p), 1, "architecture.yaml does not exist")
            return
        try:
            data = yaml.safe_load(p.read_text())
        except yaml.YAMLError as e:
            self.add("STD-ARCH-00", str(p), 1, f"not valid YAML: {' '.join(str(e).split())}")
            return
        for e in arch_mod.check_architecture(data):
            self.add("STD-ARCH-00", str(p), 1, e)

    def rule_clocks(self) -> None:
        declared = arch_mod.declared_clocks(self.arch)
        memo: dict[str, set[str]] = {}
        for mod in self.modules:
            for a in mod.always:
                if not a["edges"]:
                    continue
                sig = a["edges"][0][1]
                root = self.resolve_alias(mod, sig)
                if mod.ports.get(root, {}).get("dir") == "input":
                    continue
                drv = self._driver(mod, root)
                if drv == "clock-primitive":
                    continue
                self.add("STD-CLK-01", mod, a["line"],
                         f"module {mod.name}: clock {sig} is driven inside the module ({drv}): a derived or gated "
                         f"clock; use a clock enable on the declared clock")
            for inst in mod.instances:
                if GATING_PRIMS.match(inst["type"]):
                    self.add("STD-CLK-01", mod, inst["line"], f"module {mod.name}: {inst['type']} gates a clock; use a "
                                                              f"clock enable instead")
                    continue
                child = self.by_name.get(inst["type"])
                cps = self.clock_ports(child, memo) if child else set()
                for p in cps:
                    expr = inst["conns"].get(p, "")
                    if not re.fullmatch(r"[A-Za-z_]\w*", expr or ""):
                        self.add("STD-CLK-01", mod, inst["line"], f"instance {inst['name']} ({inst['type']}): clock port "
                                                                  f"{p} is connected to an expression ({expr or 'nothing'}): a derived clock")
                        continue
                    root = self.resolve_alias(mod, expr)
                    if mod.ports.get(root, {}).get("dir") == "input" or self._driver(mod, root) == "clock-primitive":
                        continue
                    self.add("STD-CLK-01", mod, inst["line"], f"instance {inst['name']} ({inst['type']}): clock port {p} is "
                                                              f"connected to {expr}, which is driven inside {mod.name} "
                                                              f"({self._driver(mod, root)}): a derived clock")
        top = self.top()
        tm = next((m for m in self.modules if m.name == top), None)
        if tm is not None:
            for p in sorted(self.clock_ports(tm, memo)):
                if declared and p not in declared:
                    self.add("STD-CLK-02", tm, tm.line, f"top clock input {p} is not a clock in architecture.yaml "
                                                         f"clock_domains (declared: {', '.join(sorted(declared)) or 'none'})")
                elif not declared:
                    self.add("STD-CLK-02", tm, tm.line, f"top clock input {p}: architecture.yaml declares no clock domain")

    def _driver(self, mod: Module, sig: str) -> str:
        if sig in mod.assigns:
            return f"assign {sig} = {mod.assigns[sig][0][:60]}"
        for inst in mod.instances:
            for port, expr in inst["conns"].items():
                if re.fullmatch(rf"\s*{re.escape(sig)}\s*(\[[^\]]*\])?\s*", expr or ""):
                    child = self.by_name.get(inst["type"])
                    is_out = (child.ports.get(port, {}).get("dir") == "output") if child else bool(
                        re.match(r"(CLKOUT|CLKFBOUT|O|Q|CLK_OUT)", port))
                    if is_out and CLOCK_PRIMS.match(inst["type"]):
                        return "clock-primitive"
                    if is_out:
                        return f"output {port} of {inst['type']} {inst['name']}"
        for a in mod.always:
            if re.search(rf"\b{re.escape(sig)}\b\s*<=", mod.body):
                return f"register {sig} assigned in always block"
        return "driver not found"

    def rule_reset(self) -> None:
        syn = set((self.arch.get("reset") or {}).get("synchronisers") or [])
        for mod in self.modules:
            for a in mod.always:
                if len(a["edges"]) > 1 and mod.name not in syn:
                    extra = ", ".join(f"{e} {s}" for e, s in a["edges"][1:])
                    self.add("STD-RST-01", mod, a["line"], f"module {mod.name}: {extra} in the sensitivity list of a "
                                                           f"sequential block: an asynchronous reset")

    def rule_init(self) -> None:
        for f in self.rtl_files:
            text, _ = strip_comments(drop_translate_off(self.texts[f]))
            for m in re.finditer(r"\binitial\b", text):
                j = m.end()
                while j < len(text) and text[j].isspace():
                    j += 1
                if text.startswith("begin", j):
                    depth, k = 0, j
                    for t in re.finditer(r"\b(begin|end)\b", text[j:]):
                        depth += 1 if t.group(1) == "begin" else -1
                        k = j + t.end()
                        if depth == 0:
                            break
                    block = text[j:k]
                else:
                    k = text.find(";", j) + 1
                    block = text[j:k]
                stmts = [s.strip() for s in re.sub(r"\b(begin|end)\b", ";", block).split(";") if s.strip()]
                if stmts and all(re.match(r"\$readmem[hb]\b", s) for s in stmts):
                    continue                                         # ROM initialisation
                self.add("STD-INIT-01", f, _line_of(text, m.start()), "initial block in synthesisable RTL "
                                                                       "(only $readmemh/$readmemb ROM initialisation is allowed)")

    def rule_cdc(self) -> None:
        a = self.arch
        doms = [d for d in a.get("clock_domains") or [] if isinstance(d, dict)]
        xs = [x for x in a.get("crossings") or [] if isinstance(x, dict)]
        af = str(self.design / "architecture.yaml")
        names = {m.name for m in self.modules} | set(self.lib)
        types = {i["type"] for m in self.modules for i in m.instances}
        if len(doms) > 1 and not xs:
            self.add("STD-CDC-01", af, 1, f"{len(doms)} clock domains are declared and no crossing is listed")
        prim_modules = set()
        for i, x in enumerate(xs):
            prim = str(x.get("primitive", ""))
            where = x.get("inline_in")
            prim_modules.add(prim)
            if where:
                prim_modules.add(str(where))
            if where and str(where) not in self.by_name:        # the design's own modules and the test shell's
                self.add("STD-CDC-01", af, 1, f"crossings[{i}]: inline_in {where} is not a module of this design or the shell")
            elif not where and prim not in types and prim.lower() not in {t.lower() for t in types}:
                self.add("STD-CDC-01", af, 1, f"crossings[{i}]: primitive {prim} is listed but not instantiated in the RTL")
        for mod in self.modules:
            clocks = {self.resolve_alias(mod, e[0][1]) for a_ in mod.always for e in [a_["edges"]] if e}
            if len(clocks) > 1 and mod.name not in prim_modules:
                self.add("STD-CDC-01", mod, mod.line, f"module {mod.name} uses clocks {', '.join(sorted(clocks))}: a "
                                                      f"crossing that is not through a listed CDC primitive")

    def rule_axi(self) -> None:
        a = self.arch
        top = self.top()
        declared_prefix = set()
        lite = ["awaddr", "awvalid", "awready", "wdata", "wstrb", "wvalid", "wready", "bresp", "bvalid", "bready",
                "araddr", "arvalid", "arready", "rdata", "rresp", "rvalid", "rready"]
        stream = ["tdata", "tvalid", "tready"]
        out_s = {"awready", "wready", "bresp", "bvalid", "arready", "rdata", "rresp", "rvalid"}   # slave drives these
        for i, f in enumerate(a.get("interfaces") or []):
            if not isinstance(f, dict) or not str(f.get("protocol", "")).startswith("axi4"):
                continue
            pre = str(f.get("prefix", ""))
            declared_prefix.add(pre)
            modname = f.get("module") or top
            mod = next((m for m in self.modules if m.name == modname), None)
            if mod is None:
                self.add("STD-AXI-01", str(self.design / "architecture.yaml"), 1,
                         f"interface {f.get('name')}: module {modname} not found in the design RTL")
                continue
            ports = {k.lower(): v for k, v in mod.ports.items()}
            slave = pre.lower().startswith("s_")
            master = pre.lower().startswith("m_")
            need = lite if f["protocol"] == "axi4-lite" else stream
            for sig in need:
                nm = f"{pre}_{sig}".lower()
                if nm not in ports:
                    self.add("STD-AXI-01", mod, mod.line, f"interface {f.get('name')} ({f['protocol']}): port "
                                                          f"{pre}_{sig} is missing from {mod.name}")
                    continue
                d = ports[nm]["dir"]
                if f["protocol"] == "axi4-lite" and (slave or master):
                    want = ("output" if sig in out_s else "input") if slave else ("input" if sig in out_s else "output")
                else:
                    want = ("output" if sig == "tready" else "input") if slave else (
                        ("input" if sig == "tready" else "output") if master else d)
                if d != want:
                    self.add("STD-AXI-01", mod, mod.line, f"interface {f.get('name')}: port {pre}_{sig} is {d}, "
                                                          f"expected {want} for a {'slave' if slave else 'master'}")
        pat = re.compile(r"^(?P<p>[sm]_axis?\w*?)_(aw|w|b|ar|r)(addr|valid|ready|data|strb|resp|prot|last)$|"
                         r"^(?P<q>\w*?)_(tdata|tvalid|tready|tlast|tkeep)$", re.I)
        for mod in self.modules:
            for name in mod.ports:
                m = pat.match(name)
                if not m:
                    continue
                pre = m.group("p") or m.group("q")
                if pre not in declared_prefix:
                    self.add("STD-AXI-02", mod, mod.line, f"port {name} of {mod.name} looks like an AXI port but "
                                                          f"prefix {pre} is not a declared interface")

    def rule_waivers(self) -> None:
        for f, ws in self.waivers.items():
            for ln, (rule, reason) in sorted(ws.items()):
                if not reason:
                    self.add("STD-WAIVE-01", f, ln, f"waiver of {rule} has no reason")

    # -- tools (latches, loops)
    def _env(self) -> dict[str, str]:
        """The tools.yaml-aware environment the core's runner uses; plain os.environ if the core cannot be imported
        (the lint job installs no Python packages)."""
        try:
            sys.path.insert(0, str(ROOT))
            from agent.core import runner as rn
            return rn.scrubbed_env()
        except Exception:                                     # noqa: BLE001
            return dict(os.environ)
        finally:
            if sys.path and sys.path[0] == str(ROOT):
                sys.path.pop(0)

    def _tool(self, name: str) -> str | None:
        return shutil.which(name, path=self._env().get("PATH", os.defpath))

    def _sources(self) -> list[str]:
        cfg = yaml.safe_load((self.design / "build.yaml").read_text()) if (self.design / "build.yaml").is_file() else {}
        noshell = srcorder.no_shell(self.design)         # 07a2-prep: a UART-subject design has no test shell
        srcs = sorted({p for pat in (cfg or {}).get("sources", []) for p in glob.glob(str(self.root / pat))}) or \
            ([] if noshell else sorted(glob.glob(str(self.root / "shell" / "rtl" / "*.sv")))) + self.rtl_files
        if any(vhdl.is_vhdl(s) for s in srcs):            # brief 55: the VHDL is read as its netlist (self.rtl_files)
            srcs = [s for s in srcs if not vhdl.is_vhdl(s)] + self.rtl_files
        if noshell:
            srcs = [str(p) for p in srcorder.drop_shell(srcs)]
        srcs = [str(p) for p in srcorder.order_sv(srcs)]     # 07a2-prep: packages and interfaces first, not name order
        return srcs + sorted(glob.glob(str(self.design / "lint" / "*.sv")))

    def rule_latch_loop(self) -> None:
        top = self.top()
        srcs = self._sources()
        if not top or not srcs:
            for r in ("STD-LATCH-01", "STD-LOOP-01"):
                self.not_run[r] = "no build.yaml top or sources to check"
            return
        vl = self._tool("verilator")
        if vl:
            with tempfile.TemporaryDirectory() as td:
                p = subprocess.run([vl, "--cc", "--Wall", "-Wno-fatal", "--Mdir", td, "--top-module", top, *srcs],
                                   capture_output=True, text=True, env=self._env(), cwd=self.root, errors="replace")
            for m in re.finditer(r"%Warning-(LATCH|UNOPTFLAT|COMBDLY):\s*([^\n]*?):(\d+):(?:\d+:)?\s*([^\n]*)", p.stderr):
                kind, f, ln, msg = m.groups()
                if not str(Path(f if Path(f).is_absolute() else self.root / f).resolve()).startswith(str(self.design / "rtl")):
                    continue
                rule = {"LATCH": "STD-LATCH-01", "UNOPTFLAT": "STD-LOOP-01", "COMBDLY": None}[kind]
                if rule:
                    self.add(rule, str((self.root / f).resolve() if not Path(f).is_absolute() else f), int(ln),
                             f"Verilator {kind}: {msg.strip()[:200]}")
            if p.returncode not in (0, 1) and "%Error" in p.stderr:
                err = next((l for l in p.stderr.splitlines() if l.startswith("%Error")), "")
                for r in ("STD-LATCH-01", "STD-LOOP-01"):
                    self.not_run[r] = f"Verilator could not read the design: {err[:200]}"
        else:
            for r in ("STD-LATCH-01", "STD-LOOP-01"):
                self.not_run[r] = "Verilator not found (tools.yaml path)"
        ys = self._tool("yosys")
        if ys and not any(r in self.not_run for r in ("STD-LATCH-01",)):
            self._yosys(ys, top, srcs)

    def _yosys(self, ys: str, top: str, srcs: list[str]) -> None:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "d.json"
            cmd = f"read_verilog -sv {' '.join(srcs)}; hierarchy -top {top}; proc; check; write_json {js}"
            p = subprocess.run([ys, "-q", "-p", cmd], capture_output=True, text=True, env=self._env(), cwd=self.root,
                               errors="replace")
            self.notes["yosys"] = "ran" if p.returncode == 0 else f"could not read the design ({p.stderr.strip()[-120:]})"
            if p.returncode != 0 or not js.is_file():
                return                                       # Verilator already covered the rule; Yosys is a second reader
            data = json.loads(js.read_text())
            for mname, m in data.get("modules", {}).items():
                for cname, c in m.get("cells", {}).items():
                    if c.get("type") in ("$dlatch", "$adlatch", "$dlatchsr"):
                        self.findings["STD-LATCH-01"].append(Finding(f"yosys:{mname}", 0, f"Yosys proc inferred a latch ({cname})"))
            if re.search(r"found logic loop|Warning: found", p.stdout + p.stderr):
                for l in (p.stdout + p.stderr).splitlines():
                    if "logic loop" in l:
                        self.findings["STD-LOOP-01"].append(Finding("yosys", 0, "Yosys check: " + l.strip()[:200]))
                        break

    # -- post-synthesis rules from the Vivado reports
    def post_synth(self) -> None:
        bdir = self.design / "build" / self.variant
        gj = bdir / "gates.json"
        try:
            g = json.loads(gj.read_text()) if gj.is_file() else None
        except ValueError:
            g = None
        ps = ((g or {}).get("stages") or {}).get("post_synth") or {}
        if not ps.get("ran"):
            for r in ("STD-CLK-03", "STD-CDC-02", "STD-METH-01"):
                self.not_run[r] = f"no post-synthesis reports in build/{self.variant}"
            return
        gg = ps.get("gates") or {}
        if "post_synth_cdc_no_critical" not in gg:
            self.not_run["STD-CDC-02"] = "cdc_synth.rpt was not written (a build before brief 05d)"
        elif not gg["post_synth_cdc_no_critical"]:
            self.add("STD-CDC-02", str(bdir / "cdc_synth.rpt"), 1, "report_cdc has Critical rows: "
                     + ", ".join(f"{r['id']} x{r['count']}" for r in ((ps.get("cdc") or {}).get("rules") or [])
                                 if r.get("severity") == "Critical"))
        if gg.get("post_synth_methodology_no_critical") is False:
            self.add("STD-METH-01", str(bdir / "methodology_synth.rpt"), 1, "report_methodology has Critical Warnings: "
                     + ", ".join(f"{r.get('id', r.get('rule'))} x{r['count']}" for r in ((ps.get("methodology") or {}).get("rules") or [])
                                 if r.get("severity") == "Critical Warning"))
        cn = bdir / "clock_networks_synth.rpt"
        if not cn.is_file():
            self.not_run["STD-CLK-03"] = "clock_networks_synth.rpt is absent"
        else:
            declared = arch_mod.declared_clocks(self.arch)
            text = cn.read_text(errors="replace")
            for m in re.finditer(r"^Clock\s+(\S+)[^\n]*\n(Port|Net|Pin)\s+(\S+)", text, re.M):
                src = m.group(3)
                if declared and src not in declared and m.group(1) not in declared:
                    self.add("STD-CLK-03", str(cn), _line_of(text, m.start()),
                             f"clock {m.group(1)} from {m.group(2).lower()} {src} is not a declared clock domain")

    def run(self, stages: tuple[str, ...] = ("rtl", "post_synth")) -> dict[str, Any]:
        if self.vhdl_error:
            for r, (st, _, _) in RULES.items():
                if st == "rtl" and r != "STD-ARCH-00":
                    self.not_run[r] = f"GHDL could not synthesise the VHDL for the checker: {self.vhdl_error}"
        self.rule_arch()
        if "rtl" in stages:
            self.rule_clocks()
            self.rule_reset()
            self.rule_init()
            self.rule_cdc()
            self.rule_axi()
            self.rule_waivers()
            self.rule_latch_loop()
        if "post_synth" in stages:
            self.post_synth()
        rules = []
        for rid, (stage, title, how) in RULES.items():
            if stage == "review":
                status = "review_only"
            elif stage not in stages:
                status = "not_run" if False else "skipped"
            elif rid in self.not_run and not self.findings[rid]:
                status = "not_run"
            else:
                status = "fail" if self.findings[rid] else "pass"
            rules.append({"id": rid, "stage": stage, "title": title, "how": how, "status": status,
                          "findings": [f.as_dict() for f in self.findings[rid]],
                          **({"why_not_run": self.not_run[rid]} if status == "not_run" else {})})
        checked = [r for r in rules if r["status"] in ("pass", "fail", "not_run")]
        by_stage = {s: all(r["status"] == "pass" for r in checked if r["stage"] == s) for s in ("rtl", "post_synth")
                    if s in stages}
        return {"version": VERSION, "design": self.design.name, "variant": self.variant, "rules": rules,
                "stages": by_stage, "notes": self.notes,
                "pass": all(r["status"] == "pass" for r in checked)}


def evaluate(design: Path, root: Path = ROOT, variant: str = "base",
             stages: tuple[str, ...] = ("rtl", "post_synth")) -> dict[str, Any]:
    return Check(design, root, variant).run(stages)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("design", type=Path)
    ap.add_argument("--variant", default="base")
    ap.add_argument("--stage", choices=["rtl", "post_synth", "all"], default="all")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    stages = ("rtl", "post_synth") if a.stage == "all" else (a.stage,)
    try:
        res = evaluate(a.design, a.root, a.variant, stages)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:      # a failed gate, not a traceback
        res = {"version": VERSION, "design": a.design.name, "pass": False, "stages": {}, "rules": [{
            "id": "STD-ARCH-00", "stage": "rtl", "title": RULES["STD-ARCH-00"][1], "how": "", "status": "fail",
            "findings": [{"file": "", "line": 0, "message": f"the checker could not read the design: {type(e).__name__}: {e}"}]}]}
    for r in res["rules"]:
        tag = {"pass": "ok  ", "fail": "FAIL", "not_run": "NOT RUN", "review_only": "review", "skipped": "-"}[r["status"]]
        print(f"{tag:7} {r['id']}: {r['title']}")
        for f in r["findings"]:
            print(f"          {f['file']}:{f['line']}: {f['message']}")
        if r["status"] == "not_run":
            print(f"          not checked: {r.get('why_not_run')}")
    print(f"standards {VERSION}: {'PASS' if res['pass'] else 'FAIL'}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=1) + "\n")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
