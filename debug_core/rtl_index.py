"""A small, deterministic index of a design's SystemVerilog: modules, ports, signals, registers, instances and clocks.

Used by the debug front end (brief 50A) to turn a signal name from a request into something the ILA can probe:

    idx = RtlIndex.from_design(Path("designs/t1_dimmer_counter"))
    r = idx.resolve("count")            # -> Resolution(kind="register", path="u_dut.count", width=16,
                                        #                pins="u_dut/count_reg[*]/Q", clock="CLK100MHZ", ...)

It is not a full SystemVerilog front end. It reads ANSI port lists, ``logic``/``reg``/``wire``/``bit`` and enum
declarations, parameters (with ``$clog2`` and instance overrides), named-port instances of modules in the source list,
``always_ff`` (and ``always @(posedge ...)``) left-hand sides, and ``assign`` aliases. Generate blocks, interfaces and
structs are not elaborated (a name inside them is reported as unresolved, never guessed).

Probe pins follow the flow's rule (flow/debug.tcl, designs/*/probes.yaml): probe **register output pins**, because cell
names survive synthesis and net names do not. A register ``x`` of instance path ``a.b`` is ``a/b/x_reg[*]/Q`` (``x_reg/Q`` for
one bit; ``x_reg[k][*]/Q`` for element ``k`` of an unpacked array). A signal that is not a register is traced to the
register (or top-level pin) that drives it through port connections and plain ``assign`` aliases; a combinational signal is
an error with the registers it is computed from as suggestions. The insertion step checks every pin again after synthesis
(flow/debug.tcl stops with close matches if a pattern does not match exactly).
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

_KEYWORDS = {"module", "endmodule", "input", "output", "inout", "logic", "wire", "reg", "bit", "int", "integer",
             "parameter", "localparam", "assign", "always", "always_ff", "always_comb", "always_latch", "begin", "end",
             "if", "else", "case", "endcase", "default", "for", "generate", "endgenerate", "genvar", "typedef", "enum",
             "posedge", "negedge", "or", "and", "not", "signed", "unsigned", "function", "endfunction", "task",
             "endtask", "initial", "struct", "packed", "unique", "priority", "return", "automatic", "import", "export",
             "package", "endpackage", "interface", "endinterface", "modport", "var", "const", "string", "real"}


# --- text helpers ------------------------------------------------------------------------------------------------------------

def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"\(\*.*?\*\)", " ", text, flags=re.S)       # attributes
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


def _matching(text: str, i: int, open_c: str = "(", close_c: str = ")") -> int:
    """Index of the bracket that closes the one at ``text[i]``."""
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("unbalanced brackets")


def _split_top(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside (), [] and {}."""
    out, depth, cur = [], 0, []
    for c in text:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if "".join(cur).strip():
        out.append("".join(cur))
    return [x.strip() for x in out if x.strip()]


def _sv_number(m: re.Match) -> str:
    base = (m.group(2) or "d").lower()
    digits = m.group(3).replace("_", "")
    if re.search(r"[xz?]", digits, re.I):
        return "0"
    return str(int(digits, {"h": 16, "d": 10, "b": 2, "o": 8}[base]))


def eval_expr(expr: str, env: dict[str, int]) -> int | None:
    """Evaluate a constant SystemVerilog expression (parameters, numbers, + - * / % << >> ** and $clog2). None if it
    names something that is not a known parameter."""
    e = expr.strip()
    if not e:
        return None
    e = re.sub(r"(\d+)?\s*'\s*[sS]?([hHdDbBoO])\s*([0-9a-fA-FxXzZ?_]+)", _sv_number, e)
    e = re.sub(r"'([01])\b", r"\1", e)                    # '0 / '1 fill literals: their value as a width is not needed
    e = re.sub(r"(\d)_(?=\d)", r"\1", e)
    e = re.sub(r"\b\w+'\(", "(", e)                       # casts: PW'(x), int'(x)
    e = e.replace("$clog2", "clog2").replace("/", "//")
    for name in re.findall(r"[A-Za-z_]\w*", e):
        if name != "clog2" and name not in env:
            return None
    try:
        v = eval(e, {"__builtins__": {}}, {"clog2": lambda x: 0 if x <= 1 else math.ceil(math.log2(x)), **env})  # noqa: S307
    except Exception:                                      # anything odd: unknown, never a guess
        return None
    return int(v) if isinstance(v, (int, bool)) else None


def _dims(text: str) -> list[tuple[str, str]]:
    """'[15:0][3:0]' -> [('15', '0'), ('3', '0')]; an unpacked size '[7]' -> ('0', '(7)-1')."""
    out = []
    for inner in re.findall(r"\[([^\]]+)\]", text):
        if ":" in inner:
            a, b = inner.split(":", 1)
            out.append((a.strip(), b.strip()))
        else:
            out.append(("0", f"({inner.strip()})-1"))
    return out


# --- parsed structures --------------------------------------------------------------------------------------------------------

@dataclass
class Signal:
    name: str
    packed: list[tuple[str, str]] = field(default_factory=list)     # [(msb expr, lsb expr)]
    unpacked: list[tuple[str, str]] = field(default_factory=list)
    direction: str | None = None                                     # input / output / inout for ports
    enum_type: str | None = None
    init_expr: str | None = None                                     # wire x = <expr>


@dataclass
class Instance:
    module: str
    name: str
    params: dict[str, str]          # child parameter -> expression in the parent's scope ("#0", "#1" positional)
    conns: dict[str, str]           # child port -> expression in the parent's scope


@dataclass
class Module:
    name: str
    file: str
    params: list[tuple[str, str]] = field(default_factory=list)          # header parameters in order: (name, default)
    localparams: list[tuple[str, str]] = field(default_factory=list)
    signals: dict[str, Signal] = field(default_factory=dict)
    ports: list[str] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    regs: dict[str, str] = field(default_factory=dict)                     # register name -> clock signal name
    aliases: dict[str, str] = field(default_factory=dict)                  # assign a = b
    comb: dict[str, str] = field(default_factory=dict)                     # a = <expression> (not a plain alias)
    enums: dict[str, tuple[str, str] | None] = field(default_factory=dict) # enum type -> packed range


def _parse_params(text: str) -> list[tuple[str, str]]:
    out = []
    for item in _split_top(text):
        item = re.sub(r"^\s*(parameter|localparam)\b", "", item).strip()
        m = re.match(r"(?:.*?\s)?([A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*=\s*(.+)$", item, re.S)
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


def _parse_decl_names(rest: str) -> list[tuple[str, list[tuple[str, str]], str | None]]:
    """'a, b [0:3], c = x' -> [(name, unpacked dims, init expr)]"""
    out = []
    for item in _split_top(rest):
        m = re.match(r"([A-Za-z_]\w*)\s*((?:\[[^\]]*\]\s*)*)(?:=\s*(.+))?$", item, re.S)
        if m:
            out.append((m.group(1), _dims(m.group(2) or ""), m.group(3).strip() if m.group(3) else None))
    return out


_TYPE_RE = r"(?:logic|reg|wire|bit|var\s+logic|wire\s+logic)"


def parse_module(name: str, header_params: str, ports_text: str, body: str, file: str) -> Module:
    mod = Module(name=name, file=file)
    mod.params = _parse_params(header_params) if header_params else []
    # enum typedefs
    for m in re.finditer(r"typedef\s+enum\s+(?:" + _TYPE_RE + r")?\s*((?:\[[^\]]*\])?)\s*\{[^}]*\}\s*([A-Za-z_]\w*)\s*;", body):
        d = _dims(m.group(1))
        mod.enums[m.group(2)] = d[0] if d else None
    # ANSI ports
    direction, packed, enum_t = None, [], None
    for item in _split_top(ports_text):
        m = re.match(r"(input|output|inout)?\s*(" + _TYPE_RE + r"|[A-Za-z_]\w*_t)?\s*(signed|unsigned)?\s*((?:\[[^\]]*\]\s*)*)([A-Za-z_]\w*)\s*((?:\[[^\]]*\]\s*)*)$",
                     item.strip(), re.S)
        if not m:
            continue
        if m.group(1):
            direction, packed, enum_t = m.group(1), _dims(m.group(4) or ""), None
            t = m.group(2) or ""
            if t.endswith("_t"):
                enum_t = t
        elif m.group(4):
            packed = _dims(m.group(4))
        sig = Signal(m.group(5), list(packed), _dims(m.group(6) or ""), direction, enum_t)
        mod.signals[sig.name] = sig
        mod.ports.append(sig.name)
    # body parameters
    for m in re.finditer(r"\b(localparam|parameter)\b([^;]*);", body):
        mod.localparams += _parse_params(m.group(2))
    # declarations
    for m in re.finditer(r"(?:^|;|\bbegin\b|\bend\b)\s*(" + _TYPE_RE + r"|[A-Za-z_]\w*_t)\s+(signed\s+|unsigned\s+)?((?:\[[^\]]*\]\s*)*)([A-Za-z_][^;]*);",
                         body, re.M):
        t, packed_s, rest = m.group(1), m.group(3) or "", m.group(4)
        if t in _KEYWORDS - {"logic", "reg", "wire", "bit"}:
            continue
        enum_t = t if t.endswith("_t") else None
        if enum_t and enum_t not in mod.enums:
            continue
        for nm, unpacked, init in _parse_decl_names(rest):
            if nm in _KEYWORDS:
                continue
            mod.signals.setdefault(nm, Signal(nm, _dims(packed_s), unpacked, None, enum_t, init))
            if init is not None:
                ident = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*", init)
                (mod.aliases if ident else mod.comb)[nm] = ident.group(1) if ident else init
    # continuous assigns
    for m in re.finditer(r"\bassign\s+([^=;]+?)\s*=\s*([^;]+);", body):
        lhs, rhs = m.group(1).strip(), m.group(2).strip()
        if re.fullmatch(r"[A-Za-z_]\w*", lhs):
            ident = re.fullmatch(r"([A-Za-z_]\w*)", rhs)
            (mod.aliases if ident else mod.comb)[lhs] = rhs
    # always_comb assignments (combinational; recorded so a request for one is answered as such)
    for m in re.finditer(r"\balways_comb\b", body):
        blk = _block_after(body, m.end())
        for lhs in re.findall(r"(?:^|[;\s])([A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*=(?!=)", blk):
            mod.comb.setdefault(lhs, "always_comb")
    # clocked processes
    for m in re.finditer(r"\balways(?:_ff)?\s*@\s*\(\s*(posedge|negedge)\s+([A-Za-z_]\w*)[^)]*\)", body):
        blk = _block_after(body, m.end())
        for lhs in re.findall(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*<=", blk):
            if lhs not in _KEYWORDS:
                mod.regs.setdefault(lhs, m.group(2))
    return mod


def _block_after(body: str, i: int) -> str:
    """The statement after an always header: a begin...end block (nested) or one statement up to ';'."""
    m = re.compile(r"\s*").match(body, i)
    j = m.end() if m else i
    if body.startswith("begin", j):
        depth, k = 0, j
        for t in re.finditer(r"\b(begin|end|case|endcase)\b", body[j:]):
            w = t.group(1)
            depth += 1 if w in ("begin", "case") else -1
            if depth == 0:
                return body[j:j + t.end()]
            k = j + t.end()
        return body[j:k]
    end = body.find(";", j)
    return body[j:end + 1]


def parse_text(text: str, file: str = "") -> list[Module]:
    src = strip_comments(text)
    mods = []
    for m in re.finditer(r"\bmodule\s+([A-Za-z_]\w*)\s*", src):
        name, i = m.group(1), m.end()
        header = ""
        while i < len(src) and src[i] in " \t\r\n":
            i += 1
        if src.startswith("import", i):                    # module m import pkg::*; #(...)
            i = src.find(";", i) + 1
            while src[i] in " \t\r\n":
                i += 1
        if src[i] == "#":
            k = src.index("(", i)
            e = _matching(src, k)
            header, i = src[k + 1:e], e + 1
            while src[i] in " \t\r\n":
                i += 1
        ports = ""
        if src[i] == "(":
            e = _matching(src, i)
            ports, i = src[i + 1:e], e + 1
        endm = src.find("endmodule", i)
        body = src[src.find(";", i) + 1:endm]
        mod = parse_module(name, header, ports, body, file)
        mods.append(mod)
    return mods


def find_instances(mod: Module, body: str, known: set[str]) -> None:
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*(#\s*\()?", body):
        if m.group(1) not in known or m.group(1) == mod.name:
            continue
        i = m.end()
        params: dict[str, str] = {}
        if m.group(2):
            e = _matching(body, i - 1)
            for k, item in enumerate(_split_top(body[i:e])):
                pm = re.match(r"\.\s*([A-Za-z_]\w*)\s*\((.*)\)\s*$", item, re.S)
                if pm:
                    params[pm.group(1)] = pm.group(2).strip()
                else:
                    params[f"#{k}"] = item.strip()
            i = e + 1
        im = re.compile(r"\s*([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*\(").match(body, i)
        if not im:
            continue
        e = _matching(body, im.end() - 1)
        conns: dict[str, str] = {}
        for item in _split_top(body[im.end():e]):
            cm = re.match(r"\.\s*([A-Za-z_]\w*)\s*(?:\((.*)\))?\s*$", item, re.S)
            if cm:
                conns[cm.group(1)] = (cm.group(2) if cm.group(2) is not None else cm.group(1)).strip()
        mod.instances.append(Instance(m.group(1), im.group(1), params, conns))


# --- the elaborated design ----------------------------------------------------------------------------------------------------

@dataclass
class Resolution:
    query: str
    ok: bool
    kind: str = ""                 # register | top_input | top_output | constant | combinational | unresolved | ambiguous
    path: str = ""                 # dotted RTL path of the probed thing (instance path + signal)
    width: int | None = None
    pins: str = ""                 # post-synthesis pin pattern for flow/debug.tcl
    clock: str | None = None       # clock domain: the top-level port (or instance output) the register's clock comes from
    trace: list[str] = field(default_factory=list)       # how the name was followed to the register
    notes: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    source: str = "rtl"            # rtl | probes.yaml

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", [])} | {"ok": self.ok}


class RtlIndex:
    def __init__(self, modules: dict[str, Module], top: str, generics: dict[str, Any] | None = None,
                 aliases: dict[str, dict[str, Any]] | None = None) -> None:
        if top not in modules:
            raise ValueError(f"top module {top!r} is not in the sources")
        self.modules = modules
        self.top = top
        self.generics = dict(generics or {})
        self.probe_aliases = dict(aliases or {})          # probes.yaml name -> {pins, width}
        self.insts: dict[str, tuple[Module, dict[str, int], str | None, Instance | None]] = {}
        self._elaborate("", top, {}, None, None)

    # construction
    @classmethod
    def from_files(cls, files: list[Path], top: str, generics: dict[str, Any] | None = None,
                   aliases: dict[str, dict[str, Any]] | None = None) -> "RtlIndex":
        mods: dict[str, Module] = {}
        bodies: dict[str, str] = {}
        for f in files:
            if f.suffix not in (".sv", ".v", ".svh"):
                continue
            text = strip_comments(f.read_text(errors="replace"))
            for m in parse_text(text, str(f)):
                mods[m.name] = m
                s = re.search(r"\bmodule\s+" + re.escape(m.name) + r"\b", text)
                endm = text.find("endmodule", s.end()) if s else -1
                bodies[m.name] = text[s.end():endm] if s else ""
        known = set(mods)
        for name, m in mods.items():
            body = bodies[name]
            # instances are searched after the port list's closing ';'
            find_instances(m, body[body.find(";") + 1:] if ";" in body else body, known)
        return cls(mods, top, generics, aliases)

    @classmethod
    def from_design(cls, design: Path) -> "RtlIndex":
        design = design if design.is_absolute() else (ROOT / design)
        cfg = yaml.safe_load((design / "build.yaml").read_text())
        files: list[Path] = []
        for pat in cfg["sources"]:
            files += sorted(ROOT.glob(pat)) or sorted(design.glob(pat))
        aliases = {}
        if cfg.get("probes"):
            pf = ROOT / cfg["probes"]
            if pf.is_file():
                for p in (yaml.safe_load(pf.read_text()) or {}).get("probes", []):
                    aliases[p["name"]] = {"pins": p["pins"], "width": int(p["width"]), "why": p.get("why", "")}
        gen = {k: v for k, v in (cfg.get("generics") or {}).items()}
        return cls.from_files(files, cfg["top"], gen, aliases)

    def _env(self, mod: Module, overrides: dict[str, int]) -> dict[str, int]:
        env: dict[str, int] = {}
        for n, d in mod.params:
            env[n] = overrides[n] if n in overrides else (eval_expr(d, env) or 0)
        for n, d in mod.localparams:
            if n not in env:
                v = eval_expr(d, env)
                if v is not None:
                    env[n] = v
        return env

    def _elaborate(self, path: str, modname: str, overrides: dict[str, int], parent: str | None,
                   inst: Instance | None) -> None:
        mod = self.modules[modname]
        if not path:
            for k, v in self.generics.items():
                ev = eval_expr(str(v), {})
                if ev is not None:
                    overrides[k] = ev
        env = self._env(mod, overrides)
        self.insts[path] = (mod, env, parent, inst)
        for ch in mod.instances:
            if ch.module not in self.modules:
                continue
            cmod = self.modules[ch.module]
            ov: dict[str, int] = {}
            for k, e in ch.params.items():
                name = cmod.params[int(k[1:])][0] if k.startswith("#") and int(k[1:]) < len(cmod.params) else k
                v = eval_expr(e, env)
                if v is not None:
                    ov[name] = v
            self._elaborate(f"{path}.{ch.name}" if path else ch.name, ch.module, ov, path, ch)

    # queries
    def width_of(self, path: str, sig: Signal) -> int | None:
        mod, env, _, _ = self.insts[path]
        rng = sig.packed[0] if sig.packed else None
        if sig.enum_type and not rng:
            rng = mod.enums.get(sig.enum_type)
        if not rng:
            return 1
        a, b = eval_expr(rng[0], env), eval_expr(rng[1], env)
        if a is None or b is None:
            return None
        w = abs(a - b) + 1
        for extra in sig.packed[1:]:
            x, y = eval_expr(extra[0], env), eval_expr(extra[1], env)
            if x is None or y is None:
                return None
            w *= abs(x - y) + 1
        return w

    def all_names(self) -> list[str]:
        """Every dotted signal path in the design (instance path + signal), plus the probes.yaml names."""
        out = []
        for p, (mod, _, _, _) in self.insts.items():
            for s in mod.signals:
                out.append(f"{p}.{s}" if p else s)
        return sorted(set(out)) + sorted(self.probe_aliases)

    def registers(self) -> list[str]:
        out = []
        for p, (mod, _, _, _) in self.insts.items():
            for r in mod.regs:
                if r in mod.signals:
                    out.append(f"{p}.{r}" if p else r)
        return sorted(out)

    def clock_root(self, path: str, sig: str, seen: set | None = None) -> str | None:
        """Follow a clock signal up through ports and aliases to a top-level port (or an instance output)."""
        seen = seen or set()
        if (path, sig) in seen:
            return None
        seen.add((path, sig))
        mod, _, parent, inst = self.insts[path]
        if sig in mod.aliases:
            return self.clock_root(path, mod.aliases[sig], seen)
        s = mod.signals.get(sig)
        if s is not None and s.direction == "input":
            if parent is None:
                return sig
            e = inst.conns.get(sig, "") if inst else ""
            if re.fullmatch(r"[A-Za-z_]\w*", e):
                return self.clock_root(parent, e, seen)
            return None
        for ch in mod.instances:
            for port, e in ch.conns.items():
                if e == sig and ch.module in self.modules:
                    cp = f"{path}.{ch.name}" if path else ch.name
                    cs = self.modules[ch.module].signals.get(port)
                    if cs is not None and cs.direction == "output":
                        return f"{cp}.{port}"
        return None

    def _register(self, query: str, path: str, sig: str, index: str | None, trace: list[str]) -> Resolution:
        mod, _, _, _ = self.insts[path]
        s = mod.signals[sig]
        w = self.width_of(path, s)
        inst_pins = path.replace(".", "/")
        stem = f"{inst_pins}/{sig}_reg" if inst_pins else f"{sig}_reg"
        notes = []
        clock = self.clock_root(path, mod.regs[sig])
        if s.unpacked:
            if index is None:
                return Resolution(query, False, "unresolved", f"{path}.{sig}".lstrip("."), trace=trace,
                                  notes=[f"{sig} is an array; name one element, for example {sig}[0]"],
                                  suggestions=[f"{path}.{sig}[{eval_expr(s.unpacked[0][0], self.insts[path][1]) or 0}]".lstrip(".")])
            stem += f"[{index}]"
        elif index is not None:
            if w is not None and w > 1:
                return Resolution(query, True, "register", f"{path}.{sig}[{index}]".lstrip("."), 1,
                                  f"{stem}[{index}]/Q", clock, trace, ["one bit of a bus"])
        if s.enum_type:
            notes.append("an enumerated state register: synthesis may re-encode it (FSM extraction renames the cells to "
                         "FSM_*_" + sig + "_reg); if the pins are not found, build with fsm_encoding none on it or probe a "
                         "plain register")
        if w is None:
            return Resolution(query, False, "unresolved", f"{path}.{sig}".lstrip("."), trace=trace,
                              notes=[f"cannot work out the width of {sig} from its declaration"])
        pins = f"{stem}[*]/Q" if (w > 1 and not s.unpacked) or (s.unpacked and w > 1) else f"{stem}/Q"
        return Resolution(query, True, "register", f"{path}.{sig}".lstrip(".") + (f"[{index}]" if index else ""), w,
                          pins, clock, trace, notes)

    def _follow(self, query: str, path: str, sig: str, index: str | None, trace: list[str],
                seen: set) -> Resolution:
        if (path, sig) in seen:
            return Resolution(query, False, "unresolved", f"{path}.{sig}", trace=trace, notes=["a loop of aliases"])
        seen.add((path, sig))
        mod, _, parent, inst = self.insts[path]
        here = f"{path}.{sig}".lstrip(".")
        trace = trace + [here]
        if sig in mod.regs and sig in mod.signals:
            return self._register(query, path, sig, index, trace)
        if sig in mod.aliases:
            return self._follow(query, path, mod.aliases[sig], index, trace, seen)
        # driven by a child's output port
        for ch in mod.instances:
            for port, e in ch.conns.items():
                if e == sig and ch.module in self.modules:
                    cs = self.modules[ch.module].signals.get(port)
                    if cs is not None and cs.direction == "output":
                        return self._follow(query, f"{path}.{ch.name}".lstrip("."), port, index, trace, seen)
        s = mod.signals.get(sig)
        if s is not None and s.direction == "input":
            if parent is None:
                w = self.width_of(path, s)
                if w != 1:
                    return Resolution(query, False, "unresolved", here, w, trace=trace,
                                      notes=[f"{sig} is a {w}-bit top-level input: probe its synchronised register instead"],
                                      suggestions=self._readers(sig))
                return Resolution(query, True, "top_input", sig, 1, f"{sig}_IBUF_inst/O", None, trace,
                                  ["a top-level input pin (asynchronous unless it is in the ILA's clock domain); sampled "
                                   "by the ILA clock"])
            e = (inst.conns.get(sig) or "").strip() if inst else ""
            ident = re.fullmatch(r"([A-Za-z_]\w*)(?:\[(\d+)\])?", e)
            if ident:
                return self._follow(query, parent, ident.group(1), ident.group(2) or index, trace, seen)
            if re.fullmatch(r"[\d'hHbBdD_xXzZ]+", e or "x"):
                return Resolution(query, False, "constant", here, trace=trace, notes=[f"tied to the constant {e or '(open)'}"])
            return Resolution(query, False, "combinational", here, trace=trace,
                              notes=[f"driven by the expression '{e}' in {parent or self.top}"],
                              suggestions=self._regs_in(parent, e))
        if s is not None and s.direction == "output" and parent is None:
            w = self.width_of(path, s)
            if w == 1:
                return Resolution(query, True, "top_output", sig, 1, f"{sig}_OBUF_inst/I", None, trace,
                                  ["a top-level output pin, probed at its output buffer's input"])
        if sig in mod.comb:
            return Resolution(query, False, "combinational", here, trace=trace,
                              notes=[f"combinational ({mod.comb[sig]}); after synthesis it may not exist under this name"],
                              suggestions=self._regs_in(path, mod.comb[sig]))
        if s is None:
            return Resolution(query, False, "unresolved", here, trace=trace, notes=[f"no signal {sig} in {mod.name}"])
        return Resolution(query, False, "unresolved", here, trace=trace,
                          notes=[f"{sig} in {mod.name} has no register, alias or driver this index can follow"])

    def _regs_in(self, path: str | None, expr: str) -> list[str]:
        if path is None or path not in self.insts:
            return []
        mod = self.insts[path][0]
        out = []
        for name in dict.fromkeys(re.findall(r"[A-Za-z_]\w*", expr or "")):
            if name in mod.signals:
                r = self._follow(name, path, name, None, [], set())
                if r.ok:
                    out.append(r.path)
        return out

    def _readers(self, sig: str, path: str = "", depth: int = 0) -> list[str]:
        """The registers that first sample a signal: followed down through the input ports it is connected to (a
        top-level input's synchroniser, for example)."""
        if depth > 6 or path not in self.insts:
            return []
        mod = self.insts[path][0]
        out: list[str] = []
        for ch in mod.instances:
            if ch.module not in self.modules:
                continue
            cp = f"{path}.{ch.name}" if path else ch.name
            for port, e in ch.conns.items():
                if re.fullmatch(re.escape(sig) + r"(\[\d+(:\d+)?\])?", e.strip()):
                    sub = self._readers(port, cp, depth + 1)
                    cmod = self.modules[ch.module]
                    out += sub or [f"{cp}.{r}" for r in cmod.regs if r in cmod.signals][:2]
        return list(dict.fromkeys(out))[:4]

    def resolve(self, query: str) -> Resolution:
        if re.search(r"\s", query.strip()):
            # a phrase ("fifo overflow"): try it as one identifier, else suggest names that share its words
            r = self.resolve(re.sub(r"\s+", "_", query.strip()))
            if r.ok:
                r.query = query
                r.notes.append(f"the phrase was read as {re.sub(r'[ ]+', '_', query.strip())}")
                return r
            words = [w.lower() for w in re.findall(r"[A-Za-z]\w*", query) if len(w) > 2]
            names = self.all_names()
            sugg = [n for n in names if any(w in n.split(".")[-1].lower() for w in words)]
            sugg.sort(key=lambda n: (n not in set(self.registers()) | set(self.probe_aliases), len(n)))
            return Resolution(query, False, "unresolved", notes=[f"no signal named {query!r} in the design"],
                              suggestions=sugg[:6] or self.suggest(query.replace(" ", "_")))
        q = query.strip().replace("/", ".")
        q = re.sub(r"^" + re.escape(self.top) + r"\.", "", q)
        # probes.yaml names (vetted by an earlier build) are aliases
        if q in self.probe_aliases and "." not in q:
            a = self.probe_aliases[q]
            rtl = self._alias_rtl(a["pins"])
            res = Resolution(query, True, "register" if "_reg" in a["pins"] else "pin", rtl or q, a["width"], a["pins"],
                             None, [f"probes.yaml: {q}"], [a.get("why", "")] if a.get("why") else [], source="probes.yaml")
            if rtl:
                r2 = self.resolve(rtl)
                if r2.ok:
                    res.clock = r2.clock
            if res.clock is None:
                res.clock = self._default_clock()
            return res
        m = re.fullmatch(r"(.*?)([A-Za-z_]\w*)(?:\[(\d+)\])?", q)
        if not m:
            return Resolution(query, False, "unresolved", notes=["not a signal name"], suggestions=self.suggest(query))
        prefix, sig, index = m.group(1).rstrip("."), m.group(2), m.group(3)
        if prefix or "." in q:
            if prefix not in self.insts:
                return Resolution(query, False, "unresolved", q, notes=[f"no instance {prefix!r}"],
                                  suggestions=self.suggest(query))
            if sig not in self.insts[prefix][0].signals:
                return Resolution(query, False, "unresolved", q, notes=[f"no signal {sig!r} in {prefix}"],
                                  suggestions=self.suggest(query))
            return self._follow(query, prefix, sig, index, [], set())
        # a bare name: every instance that has it; equal if all of them reach the same register
        hits = [p for p, (mod, _, _, _) in self.insts.items() if sig in mod.signals]
        if not hits:
            return Resolution(query, False, "unresolved", notes=[f"no signal named {sig!r} in the design"],
                              suggestions=self.suggest(query))
        res = [self._follow(query, p, sig, index, [], set()) for p in hits]
        good = {r.pins: r for r in res if r.ok}
        if len(good) == 1:
            r = next(iter(good.values()))
            if len(hits) > 1:
                r.notes.append(f"the name appears in {len(hits)} places that all reach this register")
            return r
        if len(good) > 1:
            return Resolution(query, False, "ambiguous", notes=[f"{sig!r} names {len(good)} different registers; "
                                                                "give the instance path"],
                              candidates=sorted(r.path for r in good.values()))
        return res[0] if len(res) == 1 else Resolution(query, False, res[0].kind, res[0].path, notes=res[0].notes,
                                                       suggestions=sorted({s for r in res for s in r.suggestions}),
                                                       candidates=sorted(r.path for r in res))

    def _alias_rtl(self, pins: str) -> str | None:
        m = re.fullmatch(r"(.*?)([A-Za-z_]\w*)_reg((?:\[\d+\])?)(?:\[\*\])?/Q", pins)
        if not m:
            return None
        return (m.group(1).replace("/", ".") + m.group(2) + m.group(3)).lstrip(".")

    def _default_clock(self) -> str | None:
        roots = {self.clock_root(p, c) for p, (mod, _, _, _) in self.insts.items() for c in mod.regs.values()}
        roots.discard(None)
        return next(iter(roots)) if len(roots) == 1 else None

    def clock_domains(self) -> list[str]:
        return sorted({r for p, (mod, _, _, _) in self.insts.items() for c in mod.regs.values()
                       if (r := self.clock_root(p, c))})

    def suggest(self, query: str, n: int = 6) -> list[str]:
        names = self.all_names()
        q = query.strip().replace("/", ".")
        leaf = re.sub(r"\[\d+\]$", "", q.split(".")[-1]).lower()
        scored = difflib.get_close_matches(q, names, n=n, cutoff=0.5)
        leaves = {nm: nm.split(".")[-1].lower() for nm in names}
        close_leaf = difflib.get_close_matches(leaf, sorted(set(leaves.values())), n=n, cutoff=0.6)
        scored += [nm for nm in names if leaves[nm] in close_leaf]
        scored += [nm for nm in names if leaf and len(leaf) >= 3 and leaf in leaves[nm]]
        out = []
        for s in scored:
            if s not in out:
                out.append(s)
        regs = set(self.registers()) | set(self.probe_aliases)
        out.sort(key=lambda s: (s not in regs, ))
        return out[:n]
