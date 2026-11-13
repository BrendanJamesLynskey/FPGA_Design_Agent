"""Read a SystemVerilog module header: parameters and ANSI ports, with widths evaluated at a parameter point.

Only the header is read (``module NAME #( ... ) ( ... );``). That is all the block design needs: the names, directions
and widths of the ports, which the generator wires and the validator compares. The parser covers the forms the
library uses (``input logic [W-1:0] a, b,`` and ``output logic signed [...] x``, ``wire``, untyped string
parameters, ``parameter int``, ``parameter logic [..]``); anything else raises ``HdlError`` naming the file and text.
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


class HdlError(ValueError):
    pass


@dataclass
class Param:
    name: str
    default: str            # the default as written (an expression or a string literal with quotes)
    kind: str               # "int", "string", "logic"


@dataclass
class Port:
    name: str
    dir: str                # "in" or "out"
    msb: str | None         # width expression parts as written, or None for one bit
    lsb: str | None
    signed: bool = False
    comment: str = ""


@dataclass
class Module:
    name: str
    file: str
    params: list[Param] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)

    def port(self, name: str) -> Port:
        for p in self.ports:
            if p.name == name:
                return p
        raise KeyError(name)


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _split_top(s: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside brackets and braces."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _balanced(text: str, start: int) -> int:
    """Index just past the parenthesis that closes the one at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    raise HdlError("unbalanced parentheses")


def read_module(path: Path, name: str) -> Module:
    raw = Path(path).read_text()
    text = _strip_comments(raw)
    m = re.search(rf"\bmodule\s+{re.escape(name)}\b", text)
    if not m:
        raise HdlError(f"{path}: module {name} not found")
    i = m.end()
    while text[i].isspace():
        i += 1
    mod = Module(name=name, file=str(path))
    if text[i] == "#":
        j = text.index("(", i)
        k = _balanced(text, j)
        for item in _split_top(text[j + 1:k - 1]):
            item = " ".join(item.split())
            if not item:
                continue
            pm = re.match(r"^(?:parameter\s+)?(int|integer|string|logic\s*(?:\[[^\]]*\])?|bit\s*(?:\[[^\]]*\])?)?\s*(\w+)\s*=\s*(.+)$",
                          item)
            if not pm:
                raise HdlError(f"{path}: cannot read parameter {item!r}")
            kind = (pm.group(1) or "").split("[")[0].strip() or ("string" if pm.group(3).strip().startswith('"') else "int")
            mod.params.append(Param(pm.group(2), pm.group(3).strip(), "int" if kind in ("int", "integer") else kind))
        i = k
        while text[i].isspace():
            i += 1
    if text[i] != "(":
        raise HdlError(f"{path}: module {name} has no ANSI port list")
    k = _balanced(text, i)
    cur_dir, cur_rng, cur_signed = None, (None, None), False
    for item in _split_top(text[i + 1:k - 1]):
        item = " ".join(item.split())
        if not item:
            continue
        pm = re.match(r"^(input|output|inout)?\s*(?:(logic|wire|reg|bit)\s+)?(signed\s+)?(\[[^\]]+\]\s*)?(\w+)$", item)
        if not pm:
            raise HdlError(f"{path}: cannot read port {item!r}")
        if pm.group(1):
            if pm.group(1) == "inout":
                raise HdlError(f"{path}: inout port {pm.group(5)} is not supported by the block design")
            cur_dir = "in" if pm.group(1) == "input" else "out"
            cur_signed = bool(pm.group(3))
            cur_rng = (None, None)
            if pm.group(4):
                a, b = pm.group(4).strip()[1:-1].split(":")
                cur_rng = (a.strip(), b.strip())
        elif pm.group(4):                       # a new range without a direction keeps the direction
            a, b = pm.group(4).strip()[1:-1].split(":")
            cur_rng = (a.strip(), b.strip())
        if cur_dir is None:
            raise HdlError(f"{path}: port {pm.group(5)} has no direction")
        mod.ports.append(Port(pm.group(5), cur_dir, cur_rng[0], cur_rng[1], cur_signed))
    return mod


# ---- expressions ----------------------------------------------------------------------------------------------------
_FUNCS = {"clog2": lambda n: max(0, math.ceil(math.log2(n))) if n > 0 else 0}
_OK = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Add, ast.Sub, ast.Mult,
       ast.Div, ast.FloorDiv, ast.Mod, ast.USub, ast.UAdd, ast.Call, ast.IfExp, ast.Compare, ast.Gt, ast.Lt, ast.GtE,
       ast.LtE, ast.Eq, ast.NotEq, ast.LShift, ast.RShift)


def sv_int(text: str):
    """A SystemVerilog integer literal (``32'h4000_0000``, ``8'd12``, ``100_000``) as int, or None."""
    t = text.strip().replace("_", "")
    m = re.fullmatch(r"(\d+)?'([sS])?([hHdDbBoO])([0-9a-fA-FxXzZ]+)", t)
    if m:
        base = {"h": 16, "d": 10, "b": 2, "o": 8}[m.group(3).lower()]
        return int(m.group(4), base)
    if re.fullmatch(r"\d+", t):
        return int(t)
    return None


def eval_expr(expr: str, params: dict):
    """An integer expression of a header (a width or a parameter default) at a parameter point."""
    lit = sv_int(expr)
    if lit is not None:
        return lit
    t = expr.strip()
    if re.search(r"\b0[xXoObB]", t):
        raise HdlError(f"expression {expr!r}: write a Verilog literal (32'h10), not a C or Python one (0x10)")
    t = re.sub(r"\$clog2\s*\(", "clog2(", t)
    t = re.sub(r"(\d+)?'([hHdDbB])([0-9a-fA-F_]+)", lambda m: str(sv_int(m.group(0))), t)
    t = t.replace("/", "//")
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        raise HdlError(f"expression {expr!r} cannot be evaluated") from None
    for n in ast.walk(tree):
        if not isinstance(n, _OK):
            raise HdlError(f"expression {expr!r}: {type(n).__name__} is not supported")
        if isinstance(n, ast.Constant) and (not isinstance(n.value, int) or isinstance(n.value, bool)):
            raise HdlError(f"expression {expr!r}: {n.value!r} is not an integer")
        if isinstance(n, ast.Name) and n.id not in params and n.id not in _FUNCS:
            raise HdlError(f"expression {expr!r}: unknown parameter {n.id}")
    vals = {k: v for k, v in params.items() if isinstance(v, int) and not isinstance(v, bool)}
    return int(eval(compile(tree, "<hdl>", "eval"), {"__builtins__": {}}, {**_FUNCS, **vals}))   # noqa: S307 (checked)


def resolve_params(mod: Module, given: dict) -> dict:
    """Every parameter's value: ``given`` first, else the header default evaluated in order. Strings stay strings."""
    out: dict = {}
    for p in mod.params:
        if p.name in given:
            out[p.name] = given[p.name]
            continue
        d = p.default
        if d.startswith('"'):
            out[p.name] = d.strip('"')
        elif d.startswith("{") or d == "'0" or "'" in d and sv_int(d) is None:
            out[p.name] = d                    # a replication or fill literal: kept as written
        else:
            try:
                out[p.name] = eval_expr(d, out)
            except HdlError:
                out[p.name] = d
    return out


def width(port: Port, params: dict) -> int:
    if port.msb is None:
        return 1
    return abs(eval_expr(port.msb, params) - eval_expr(port.lsb, params)) + 1


def width_param(port: Port) -> str | None:
    """The parameter a port's width follows directly (``[NAME-1:0]``), so a connection can set it; else None."""
    if port.msb is None or port.lsb.strip() != "0":
        return None
    m = re.fullmatch(r"\s*(\w+)\s*-\s*1\s*", port.msb)
    return m.group(1) if m and not m.group(1).isdigit() else None
