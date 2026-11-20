"""A blind document cross-read (brief 114): check code against a vendor document without letting one reader see both.

The 96D lesson: the eye-scan driver, its fake board and its test stand-in were all written from one misreading of UG576 (five-word
masks on UltraScale+, where the guide says ten), so every test passed and the board counted nothing. An independent read of the source
found it. This tool makes that independent read a routine check:

1. a **reader model** sees only the document excerpt (never the code) and writes the facts the topic depends on as structured data
   (name, address, bit range, width, word count, reset value, steps, conditions), each with a page and a quotation;
2. **code** checks every quotation against the excerpt (a fact whose quotation is not in the document is marked, never trusted);
3. **code** reads the numbers out of the code files (Python by ``ast``, SystemVerilog declarations, C ``#define``), with a small safe
   evaluator for the expressions and the short pure helper functions that build tables;
4. **code** compares the two sides fact by fact: ``agree``, ``disagree``, ``not_in_code`` (and, listed apart, ``not_in_document``).

No model compares anything and no model scores anything. The reader is called through the model resolver (brief 108), purpose
``doc_crossread``. Nothing here writes to the design, builds, simulates or touches a board.

    python -m flow.doc_crossread --pdf UG576.pdf --pages 226-234,462-464 --code hw.py --code eyescan.py \
        --topic "GTHE4 eye scan masks and DRP addresses" --target "UltraScale+ GTHE4"
    python -m flow.doc_crossread --doc excerpt.txt --code regs.h --facts replies/run1.json     # re-compare a stored reader reply, no model call
    python -m flow.doc_crossread --code-only --code tb.sv                                        # what the code side reads

What the code side parses and what it does not is in ``docs/doc_crossread.md`` (and ``CODE_LIMITS`` below); ``Report.not_parsed`` lists,
per run, every assignment it could not evaluate.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import operator
import re
import subprocess
import sys
import time
import tokenize
from collections.abc import Callable
from pathlib import Path
from typing import Any

PURPOSE = "doc_crossread"
PROMPTS = {"system": "graph/doc_crossread/system", "user": "graph/doc_crossread/user", "repair": "graph/doc_crossread/repair"}
SCHEMA = "fda-doc-crossread/1"
KINDS = ("address", "word_count", "width_bits", "bit_range", "reset_value", "value", "step", "condition", "other")
NUMERIC_KINDS = ("address", "word_count", "width_bits", "bit_range", "reset_value", "value")
TEXT_KINDS = ("step", "condition", "other")
MAX_FACTS = 400

CODE_LIMITS = (
    "Python: module-level and class-level assignments (including tuple unpacking), evaluated with integers, strings, lists, tuples, dicts, "
    "comprehensions over range(), and calls to simple functions defined in the given files (docstring, if-raise, local assignments, return). "
    "Not parsed: constants inside function bodies, attributes of objects, anything that calls a library or does I/O.",
    "SystemVerilog: localparam and parameter declarations (with their declared width), `define, and enum members with explicit values. "
    "Not parsed: array literals, structs, functions, case-statement addresses, port widths, generate blocks, numbers written inline in always blocks.",
    "C: #define NAME <integer expression>. Not parsed: enums, const variables, function-like macros.",
    "Comments and strings are searched only for the names a text fact (step, condition) mentions; no number in a comment is read.",
)

# ---------------------------------------------------------------------------------------------------------------- names

#: tokens that say what an item is, not which one (removed before names are compared); the aspect tokens are handled on their own
STOP = frozenset({"A", "R", "W", "REG", "REGS", "REGISTER", "ADDR", "ADDRS", "ADDRESS", "ADDRESSES", "OFFSET", "BASE", "VALUE", "DEFAULT",
                  "RESET", "WIDTH", "SHIFT", "ACCESS", "OF", "THE"})
#: the last token of a code name that says what number it is
ASPECTS = {"OFFSET": "OFFSET", "ADDR": "OFFSET", "ADDRS": "OFFSET", "ADDRESS": "OFFSET", "RESET": "RESET", "WIDTH": "WIDTH", "SHIFT": "SHIFT",
           "ACCESS": "ACCESS", "DEFAULT": "RESET"}
ASPECT_OK = {"address": {None, "OFFSET"}, "reset_value": {"RESET"}, "width_bits": {"WIDTH"}, "bit_range": {None, "SHIFT", "WIDTH"},
             "value": {None, "OFFSET", "RESET", "WIDTH", "SHIFT"}, "word_count": {None, "OFFSET"}}


def tokens(name: str) -> list[str]:
    """Upper-case word tokens of an identifier or a register name: ``A_ES_QUALIFIER0`` -> [A, ES, QUALIFIER0]; ``Rx FIFO`` -> [RX, FIFO]."""
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(name))
    return [t for t in re.split(r"[^A-Za-z0-9]+", s.upper()) if t]


def strip_digits(t: str) -> str:
    return re.sub(r"\d+$", "", t) or t


def aspect_of(toks: list[str]) -> tuple[list[str], str | None]:
    if len(toks) > 1 and toks[-1] in ASPECTS:
        return toks[:-1], ASPECTS[toks[-1]]
    return toks, None


def abbreviations(toks: list[str]) -> set[str]:
    """``RX_FIFO`` -> RXF, RXFIFO; ``STATUS_REGISTER`` -> SR (so a code name RXF can match a document's Rx FIFO)."""
    toks = [t for t in toks if t not in STOP]
    out: set[str] = set()
    if len(toks) >= 2:
        out.add("".join(toks[:-1]) + toks[-1][0])
        out.add("".join(t[0] for t in toks))
        out.add("".join(toks))
    return out


def _core(toks: list[str], prefix: frozenset[str]) -> list[str]:
    return [t for t in toks if t not in STOP and t not in prefix and not t.isdigit()]


MIN_SCORE = 0.3


def name_score(doc_toks: list[str], code_toks: list[str], prefix: frozenset[str]) -> float:
    """How well a code name names a document item: 0 (no), or the share of tokens in common (best of three readings). The document tokens
    must all be in the code name, or the code name's tokens all in the document's and including the document name's last word (so DATA1 matches
    GPIO_DATA and QUALIFIER_ADDRS matches ES_QUALIFIER, but A_ES_CONTROL does not match es_control_status)."""
    d, c = _core(doc_toks, frozenset()), _core(code_toks, prefix)
    if not d or not c:
        return 0.0
    best = 0.0
    for dd, cc, w in ((d, c, 1.0), ([strip_digits(t) for t in d], [strip_digits(t) for t in c], 0.9)):
        sd, sc = set(dd), set(cc)
        if sd <= sc or (sc <= sd and dd[-1] in sc):
            best = max(best, len(sd & sc) / max(len(sd), len(sc)) * w)
    if best == 0.0 and len(c) == 1 and c[0] in abbreviations(doc_toks):
        best = 0.5
    return best if best >= MIN_SCORE else 0.0


# ---------------------------------------------------------------------------------------------------- a safe evaluator

class Unresolved(Exception):
    """An expression the evaluator will not or cannot evaluate; the message is short and goes into ``not_parsed``."""


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.LShift: operator.lshift, ast.RShift: operator.rshift, ast.BitAnd: operator.and_, ast.BitOr: operator.or_, ast.BitXor: operator.xor,
        ast.Pow: operator.pow, ast.Div: operator.truediv}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
_FUNCS: dict[str, Callable] = {"len": len, "sum": sum, "min": min, "max": max, "abs": abs, "int": int, "bool": bool, "list": list, "tuple": tuple,
                               "sorted": sorted, "range": range, "bytes": bytes}
MAX_ITEMS = 100_000
MAX_SHIFT = 4096


def _guard(v: Any) -> Any:
    if isinstance(v, int) and not isinstance(v, bool) and v.bit_length() > 8192:
        raise Unresolved("number too large")
    if isinstance(v, (list, tuple, range, str, bytes)) and len(v) > MAX_ITEMS:
        raise Unresolved("sequence too long")
    return v


class Evaluator:
    """Evaluates the AST of an expression against a namespace. It runs no code of its own: only arithmetic, comprehensions over range()
    and calls to the file's simple pure functions (``funcs``), within size and depth limits."""

    def __init__(self, ns: dict[str, Any], funcs: dict[str, ast.FunctionDef] | None = None, aliases: dict[str, dict[str, Any]] | None = None):
        self.ns, self.funcs, self.aliases = ns, funcs or {}, aliases or {}
        self.depth = 0
        self.steps = 0

    def ev(self, n: ast.AST, loc: dict[str, Any] | None = None) -> Any:
        self.steps += 1
        if self.steps > 400_000:
            raise Unresolved("too many steps")
        loc = loc or {}
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float, str, bool)) or n.value is None:
                return n.value
            raise Unresolved("constant")
        if isinstance(n, ast.Name):
            if n.id in loc:
                return loc[n.id]
            if n.id in self.ns:
                return self.ns[n.id]
            if n.id in ("True", "False", "None"):
                return {"True": True, "False": False, "None": None}[n.id]
            raise Unresolved(f"name {n.id}")
        if isinstance(n, ast.Attribute):
            if isinstance(n.value, ast.Name) and n.value.id in self.aliases and n.attr in self.aliases[n.value.id]:
                return self.aliases[n.value.id][n.attr]
            raise Unresolved(f"attribute {ast.unparse(n)[:40]}")
        if isinstance(n, ast.UnaryOp):
            v = self.ev(n.operand, loc)
            return {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert, ast.Not: operator.not_}[type(n.op)](v)
        if isinstance(n, ast.BinOp):
            a, b = self.ev(n.left, loc), self.ev(n.right, loc)
            f = _BIN.get(type(n.op))
            if f is None:
                raise Unresolved("operator")
            if isinstance(n.op, ast.LShift) and (not isinstance(b, int) or b > MAX_SHIFT):
                raise Unresolved("shift too large")
            if isinstance(n.op, ast.Pow) and (not isinstance(b, int) or b > 512):
                raise Unresolved("power too large")
            if isinstance(n.op, ast.Mult) and isinstance(a, (list, tuple, str)) and isinstance(b, int) and len(a) * max(b, 0) > MAX_ITEMS:
                raise Unresolved("sequence too long")
            try:
                return _guard(f(a, b))
            except (TypeError, ZeroDivisionError, ValueError) as e:
                raise Unresolved(type(e).__name__) from None
        if isinstance(n, ast.BoolOp):
            vals = [self.ev(v, loc) for v in n.values]
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.Compare):
            left = self.ev(n.left, loc)
            for op, c in zip(n.ops, n.comparators):
                right = self.ev(c, loc)
                if isinstance(op, ast.In):
                    ok = left in right
                elif isinstance(op, ast.NotIn):
                    ok = left not in right
                elif type(op) in _CMP:
                    ok = _CMP[type(op)](left, right)
                else:
                    raise Unresolved("comparison")
                if not ok:
                    return False
                left = right
            return True
        if isinstance(n, ast.IfExp):
            return self.ev(n.body, loc) if self.ev(n.test, loc) else self.ev(n.orelse, loc)
        if isinstance(n, (ast.List, ast.Tuple, ast.Set)):
            items = [self.ev(e, loc) for e in n.elts]
            return items if isinstance(n, ast.List) else (tuple(items) if isinstance(n, ast.Tuple) else set(items))
        if isinstance(n, ast.Dict):
            if any(k is None for k in n.keys):
                raise Unresolved("dict unpacking")
            return {self.ev(k, loc): self.ev(v, loc) for k, v in zip(n.keys, n.values)}
        if isinstance(n, ast.Subscript):
            v = self.ev(n.value, loc)
            if isinstance(n.slice, ast.Slice):
                lo = self.ev(n.slice.lower, loc) if n.slice.lower else None
                hi = self.ev(n.slice.upper, loc) if n.slice.upper else None
                return v[lo:hi]
            try:
                return v[self.ev(n.slice, loc)]
            except (KeyError, IndexError, TypeError):
                raise Unresolved("subscript") from None
        if isinstance(n, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            out: list[Any] = []

            def gen(i: int, scope: dict[str, Any]) -> None:
                if i == len(n.generators):
                    out.append(self.ev(n.elt, scope))
                    if len(out) > MAX_ITEMS:
                        raise Unresolved("sequence too long")
                    return
                g = n.generators[i]
                it = self.ev(g.iter, scope)
                if not isinstance(it, (list, tuple, range, set, dict, str)):
                    raise Unresolved("iteration")
                for x in it:
                    sc = dict(scope)
                    self._bind(g.target, x, sc)
                    if all(self.ev(c, sc) for c in g.ifs):
                        gen(i + 1, sc)
            gen(0, dict(loc))
            return set(out) if isinstance(n, ast.SetComp) else out
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.keywords and n.func.id not in self.funcs:
                raise Unresolved("call")
            args = [self.ev(a, loc) for a in n.args]
            if n.func.id in self.funcs:
                return self._call(self.funcs[n.func.id], args, {kw.arg: self.ev(kw.value, loc) for kw in n.keywords if kw.arg})
            if n.func.id in _FUNCS and n.func.id not in loc:
                try:
                    r = _FUNCS[n.func.id](*args)
                except (TypeError, ValueError) as e:
                    raise Unresolved(type(e).__name__) from None
                return list(r) if isinstance(r, range) else _guard(r)
            raise Unresolved(f"call {n.func.id}")
        raise Unresolved(type(n).__name__)

    def _bind(self, target: ast.AST, value: Any, scope: dict[str, Any]) -> None:
        if isinstance(target, ast.Name):
            scope[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            vals = list(value)
            if len(vals) != len(target.elts):
                raise Unresolved("unpack")
            for t, v in zip(target.elts, vals):
                self._bind(t, v, scope)
        else:
            raise Unresolved("target")

    def _call(self, fn: ast.FunctionDef, args: list[Any], kwargs: dict[str, Any]) -> Any:
        self.depth += 1
        try:
            if self.depth > 12:
                raise Unresolved("recursion")
            a = fn.args
            names = [p.arg for p in a.posonlyargs + a.args]
            if a.vararg or a.kwarg or a.kwonlyargs or len(args) > len(names):
                raise Unresolved("signature")
            scope = dict(zip(names, args))
            defaults = a.defaults
            for p, d in zip(names[len(names) - len(defaults):], defaults):
                scope.setdefault(p, self.ev(d, {}))
            scope.update(kwargs)
            if any(p not in scope for p in names):
                raise Unresolved("arguments")
            for st in fn.body:
                if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
                    continue
                if isinstance(st, ast.Assign) and len(st.targets) == 1:
                    self._bind(st.targets[0], self.ev(st.value, scope), scope)
                    continue
                if isinstance(st, ast.If) and not st.orelse and len(st.body) == 1 and isinstance(st.body[0], ast.Raise):
                    if self.ev(st.test, scope):
                        raise Unresolved("the function raises for these arguments")
                    continue
                if isinstance(st, ast.Return) and st.value is not None:
                    return self.ev(st.value, scope)
                raise Unresolved(f"statement {type(st).__name__}")
            raise Unresolved("no return")
        finally:
            self.depth -= 1


# --------------------------------------------------------------------------------------------------- code-side facts

def _fact(name: str, value: Any, path: str, line: int, how: str, **kw: Any) -> dict[str, Any]:
    toks, aspect = aspect_of(tokens(name))
    return {"name": name, "tokens": toks, "aspect": aspect, "value": value, "file": path, "line": line, "how": how,
            "cls": "list" if isinstance(value, (list, tuple)) else ("map" if isinstance(value, dict) else "scalar"), **kw}


def _ints(v: Any) -> list[int]:
    if isinstance(v, bool):
        return []
    if isinstance(v, int):
        return [v]
    if isinstance(v, (list, tuple, set)):
        return [x for e in v for x in _ints(e)]
    if isinstance(v, dict):
        return [x for e in list(v.keys()) + list(v.values()) for x in _ints(e)]
    return []


def _py_facts(path: Path, text: str, others: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Facts of one Python file; ``others`` maps the stem of every other given file to its namespace (for ``from pkg import module as tw``)."""
    facts: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [], [{"file": str(path), "line": e.lineno or 0, "name": "(file)", "why": "syntax error"}], {}
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    aliases: dict[str, dict[str, Any]] = {}
    ns: dict[str, Any] = {}
    for n in tree.body:
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name in others:
                    aliases[a.asname or a.name] = others[a.name]
                elif n.module and n.module.split(".")[-1] in others and a.name in others[n.module.split(".")[-1]]:
                    ns[a.asname or a.name] = others[n.module.split(".")[-1]][a.name]
        elif isinstance(n, ast.Import):
            for a in n.names:
                stem = a.name.split(".")[-1]
                if stem in others:
                    aliases[a.asname or stem] = others[stem]
    ev = Evaluator(ns, funcs, aliases)
    pending: list[tuple[str, ast.AST, int, str]] = []

    def collect(body: list[ast.stmt], prefix: str) -> None:
        for n in body:
            if isinstance(n, ast.ClassDef):
                collect(n.body, prefix + n.name + ".")
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if n.value is None:
                    continue
                for t in targets:
                    names = [t] if isinstance(t, ast.Name) else (list(t.elts) if isinstance(t, (ast.Tuple, ast.List)) else [])
                    if isinstance(t, ast.Name):
                        pending.append((prefix + t.id, n.value, n.lineno, t.id))
                    elif names and all(isinstance(x, ast.Name) for x in names):
                        if isinstance(n.value, (ast.Tuple, ast.List)) and len(n.value.elts) == len(names):
                            for x, v in zip(names, n.value.elts):
                                pending.append((prefix + x.id, v, n.lineno, x.id))      # type: ignore[attr-defined]
                        else:
                            pending.append((prefix + "(" + ",".join(x.id for x in names) + ")", n.value, n.lineno, ""))   # type: ignore[attr-defined]
    collect(tree.body, "")
    resolved: dict[str, tuple[Any, int]] = {}
    for _ in range(6):
        progress = False
        for full, node, line, plain in pending:
            if full in resolved:
                continue
            try:
                v = ev.ev(node)
            except (Unresolved, RecursionError, KeyError, TypeError, ValueError, OverflowError, MemoryError):
                continue
            if plain:
                resolved[full] = (v, line)
                ns[plain] = v
                ns[full] = v
                progress = True
        if not progress:
            break
    for full, node, line, plain in pending:
        if full in resolved:
            v, ln = resolved[full]
            if isinstance(v, (int, list, tuple, dict)) and not isinstance(v, bool) and (_ints(v) or isinstance(v, dict)):
                facts.append(_fact(full, v, str(path), ln, "python assignment"))
                if isinstance(v, dict):
                    for k, x in v.items():
                        if isinstance(k, str) and isinstance(x, int):
                            facts.append(_fact(k, x, str(path), ln, f"entry of {full}"))
                        elif isinstance(k, int) and isinstance(x, str):
                            facts.append(_fact(x, k, str(path), ln, f"entry of {full} (number to text)"))
            continue
        try:
            ev.ev(node)
        except Unresolved as e:
            why = str(e)
        except (RecursionError, KeyError, TypeError, ValueError, OverflowError, MemoryError):
            why = "evaluation error"
        else:
            why = "not evaluated"
        if not isinstance(node, (ast.Constant,)) or isinstance(node.value, (int,)):
            unparsed.append({"file": str(path), "line": line, "name": full, "why": why})
    return facts, unparsed, {k: v for k, v in ns.items() if isinstance(v, (int, list, tuple, dict, str))}


_SV_LIT = re.compile(r"(\d*)'[sS]?([bBoOdDhH])([0-9a-fA-FxXzZ_?]+)")
_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def _sv_expr(expr: str, ns: dict[str, Any]) -> tuple[Any, int | None]:
    """An SV constant expression -> (value, declared width of a lone sized literal). Raises Unresolved."""
    width: list[int | None] = [None]

    def lit(m: re.Match) -> str:
        digits = m.group(3).replace("_", "")
        if re.search(r"[xXzZ?]", digits):
            raise Unresolved("x or z in a literal")
        width[0] = int(m.group(1)) if m.group(1) else None
        return str(int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[m.group(2).lower()]))
    e = _SV_LIT.sub(lit, expr.strip())
    e = re.sub(r"\b(\d+)\s*(?:u|U|l|L)+\b", r"\1", e)
    e = re.sub(r"\$clog2", "clog2", e)
    if not re.fullmatch(r"[\w\s()+\-*/%<>&|^~.]*", e):
        raise Unresolved("syntax")
    try:
        tree = ast.parse(e.replace("**", "**"), mode="eval")
    except SyntaxError:
        raise Unresolved("syntax") from None
    v = Evaluator(ns).ev(tree.body)
    if not re.fullmatch(r"\s*[\w']+\s*", expr.strip()) and not _SV_LIT.fullmatch(expr.strip()):
        width[0] = None
    return v, width[0]


def _strip_comments(text: str) -> str:
    return _COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _split_top(s: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _sv_facts(path: Path, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    code = _strip_comments(text)
    facts: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    ns: dict[str, Any] = {}

    def line_of(pos: int) -> int:
        return code.count("\n", 0, pos) + 1

    for m in re.finditer(r"\b(localparam|parameter)\b([^;]*);", code):
        body = m.group(2)
        rng = re.match(r"\s*(?:(?:int|integer|logic|bit|reg|unsigned|signed|longint|shortint|byte)\s+)*(\[[^\]]*\])?", body)
        decl_w = None
        rest = body
        if rng:
            if rng.group(1):
                mm = re.fullmatch(r"\[\s*([^:\]]+?)\s*:\s*([^\]]+?)\s*\]", rng.group(1))
                if mm:
                    try:
                        hi, lo = _sv_expr(mm.group(1), ns)[0], _sv_expr(mm.group(2), ns)[0]
                        decl_w = abs(int(hi) - int(lo)) + 1
                    except (Unresolved, TypeError, ValueError):
                        decl_w = None
            rest = body[rng.end():] if rng.group(1) else re.sub(r"^\s*(?:(?:int|integer|logic|bit|reg|unsigned|signed|longint|shortint|byte)\s+)+", "", body)
        for part in _split_top(rest):
            mm = re.fullmatch(r"\s*(?:(?:int|integer|logic|bit|reg|unsigned|signed)\s+)*(?:\[[^\]]*\]\s*)?([A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*=\s*(.+?)\s*", part, re.S)
            if not mm:
                continue
            name, expr = mm.groups()
            if expr.lstrip().startswith(("'{", '"')):
                unparsed.append({"file": str(path), "line": line_of(m.start()), "name": name, "why": "array or string literal"})
                continue
            try:
                v, lw = _sv_expr(expr, ns)
            except (Unresolved, RecursionError, TypeError, ValueError, OverflowError, MemoryError) as e:
                unparsed.append({"file": str(path), "line": line_of(m.start()), "name": name, "why": str(e) or "expression"})
                continue
            if isinstance(v, bool) or not isinstance(v, int):
                continue
            ns[name] = v
            facts.append(_fact(name, v, str(path), line_of(m.start()), m.group(1), declared_width=lw or decl_w))
    for m in re.finditer(r"`define\s+([A-Za-z_]\w*)[ \t]+([^\n]+)", code):
        try:
            v, lw = _sv_expr(m.group(2), ns)
        except (Unresolved, RecursionError, TypeError, ValueError, OverflowError, MemoryError) as e:
            unparsed.append({"file": str(path), "line": line_of(m.start()), "name": m.group(1), "why": str(e) or "expression"})
            continue
        if isinstance(v, int) and not isinstance(v, bool):
            ns[m.group(1)] = v
            facts.append(_fact(m.group(1), v, str(path), line_of(m.start()), "`define", declared_width=lw))
    for m in re.finditer(r"\benum\b[^{;]*\{([^}]*)\}", code):
        nxt = 0
        for part in _split_top(m.group(1)):
            mm = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*(?:=\s*(.+?))?\s*", part, re.S)
            if not mm:
                continue
            try:
                v = _sv_expr(mm.group(2), ns)[0] if mm.group(2) else nxt
            except (Unresolved, TypeError, ValueError):
                unparsed.append({"file": str(path), "line": line_of(m.start()), "name": mm.group(1), "why": "enum value"})
                continue
            if isinstance(v, int):
                nxt = v + 1
                ns[mm.group(1)] = v
                facts.append(_fact(mm.group(1), v, str(path), line_of(m.start()), "enum member"))
    return facts, unparsed, ns


def _c_facts(path: Path, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    code = _strip_comments(text)
    facts: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    ns: dict[str, Any] = {}
    for m in re.finditer(r"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_]\w*)[ \t]+([^\n]+)$", code, re.M):
        name, expr = m.groups()
        line = code.count("\n", 0, m.start()) + 1
        e = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b", r"\1", expr.strip())
        try:
            tree = ast.parse(e, mode="eval")
            v = Evaluator(ns).ev(tree.body)
        except (SyntaxError, Unresolved, RecursionError, TypeError, ValueError, OverflowError, MemoryError) as ex:
            if not re.match(r"[\"A-Za-z_(]", expr.strip()) or not e.strip().startswith(("\"",)):
                unparsed.append({"file": str(path), "line": line, "name": name, "why": str(ex) if isinstance(ex, Unresolved) else "expression"})
            continue
        if isinstance(v, int) and not isinstance(v, bool):
            ns[name] = v
            facts.append(_fact(name, v, str(path), line, "#define"))
    return facts, unparsed, ns


def _mentions(path: Path, text: str) -> dict[str, str]:
    """Identifier-like words and where they occur: ``code`` or only in a ``comment``/string. Used for the text facts (steps, conditions)."""
    code_words: set[str] = set()
    other: set[str] = set()
    if path.suffix == ".py":
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.NAME:
                    code_words.add(tok.string.upper())
                elif tok.type in (tokenize.COMMENT, tokenize.STRING):
                    other.update(w.upper() for w in re.findall(r"[A-Za-z_]\w+", tok.string))
        except (tokenize.TokenError, IndentationError):
            code_words.update(w.upper() for w in re.findall(r"[A-Za-z_]\w+", text))
    else:
        stripped = _strip_comments(text)
        code_words.update(w.upper() for w in re.findall(r"[A-Za-z_]\w+", stripped))
        other.update(w.upper() for w in re.findall(r"[A-Za-z_]\w+", " ".join(_COMMENT.findall(text))))
    out = {w: "comment" for w in other}
    out.update({w: "code" for w in code_words})
    return out


def extract_code(paths: list[Path | str]) -> dict[str, Any]:
    """Read the number facts out of the code files. Returns {"files": [{path, sha256, lines}], "facts": [...], "not_parsed": [...], "mentions": {...}}."""
    ps = [Path(p) for p in paths]
    texts = {p: p.read_text(errors="replace") for p in ps}
    facts: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    mentions: dict[str, str] = {}
    others: dict[str, dict[str, Any]] = {}
    # Python files first in the order given; a file's namespace is visible to the ones after it, and a second pass lets the order not matter
    order = ps + [p for p in ps if p.suffix == ".py"]
    seen: dict[Path, tuple] = {}
    for p in order:
        suf = p.suffix.lower()
        if suf == ".py":
            f, u, ns = _py_facts(p, texts[p], others)
            others[p.stem] = ns
        elif suf in (".sv", ".v", ".svh", ".vh"):
            f, u, ns = _sv_facts(p, texts[p])
        elif suf in (".h", ".hpp", ".c"):
            f, u, ns = _c_facts(p, texts[p])
        else:
            f, u, ns = [], [{"file": str(p), "line": 0, "name": "(file)", "why": f"file type {suf or '(none)'} is not read"}], {}
        seen[p] = (f, u)
    for p in ps:
        f, u = seen[p]
        facts += f
        unparsed += u
        for w, where in _mentions(p, texts[p]).items():
            if mentions.get(w) != "code":
                mentions[w] = where
    names = [f["tokens"] for f in facts if f["cls"] != "map"]
    prefix: frozenset[str] = frozenset()
    if len(names) >= 6:
        cnt: dict[str, int] = {}
        for t in names:
            for x in set(t):
                cnt[x] = cnt.get(x, 0) + 1
        prefix = frozenset(x for x, c in cnt.items() if c >= 0.8 * len(names) and x not in STOP)
    uniq = {(f["file"], f["line"], f["name"], str(f["value"])): f for f in facts}
    return {"files": [{"path": str(p), "sha256": hashlib.sha256(texts[p].encode()).hexdigest(), "lines": texts[p].count("\n") + 1} for p in ps],
            "facts": list(uniq.values()), "not_parsed": unparsed, "mentions": mentions, "common_prefix": sorted(prefix)}


# ----------------------------------------------------------------------------------------------------- the document

def parse_pages(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def load_document(*, doc: Path | None = None, pdf: Path | None = None, pages: str | None = None, page_offset: int = 0) -> dict[str, Any]:
    """The document excerpt as text with ``[[page N]]`` markers (N = the printed page: PDF page index minus ``page_offset``)."""
    chunks: list[tuple[int, str]] = []
    if pdf is not None:
        if not pages:
            raise ValueError("--pdf needs --pages (the excerpt is a page range; whole documents are not sent)")
        for pg in parse_pages(pages):
            r = subprocess.run(["pdftotext", "-layout", "-f", str(pg), "-l", str(pg), str(pdf), "-"], capture_output=True, text=True)
            if r.returncode != 0:
                raise ValueError(f"pdftotext failed on page {pg}: {r.stderr.strip()[:200]}")
            chunks.append((pg - page_offset, r.stdout.replace("\f", "")))
        src = str(pdf)
    elif doc is not None:
        raw = Path(doc).read_text(errors="replace")
        parts = raw.split("\f")
        want = set(parse_pages(pages)) if pages else None
        for i, t in enumerate(parts, 1):
            if want is None or i in want:
                chunks.append((i - page_offset, t))
        src = str(doc)
    else:
        raise ValueError("give --doc or --pdf")
    text = "\n".join(f"[[page {n}]]\n{t.strip(chr(10))}\n" for n, t in chunks)
    return {"source": src, "pages": [n for n, _ in chunks], "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text),
            "page_text": {n: t for n, t in chunks}}


def _squash(s: str) -> str:
    s = s.replace("‐", "-").replace("‑", "-").replace("‒", "-").replace("–", "-").replace("—", "-").replace("’", "'")
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", "", s).casefold()


def _num(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        t = v.strip().replace("_", "")
        t = re.sub(r"(?<=[0-9a-fA-F])[hH]$", "", t) if re.fullmatch(r"[0-9a-fA-F]+[hH]", t) else t
        if re.fullmatch(r"[0-9a-fA-F]+", t) and re.search(r"[a-fA-F]", t) and not t.lower().startswith("0x"):
            t = "0x" + t if v.strip().lower().endswith("h") else t
        try:
            return int(t, 0)
        except ValueError:
            m = re.fullmatch(r"\d*'[hH]([0-9a-fA-F_]+)", v.strip())
            return int(m.group(1).replace("_", ""), 16) if m else None
    return None


def validate_facts(reply: Any, document: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Check a reader reply: the schema, and (by code) that every quotation is in the excerpt and on the page cited. Returns (facts, problems);
    a fact with a problem that makes it unusable is dropped and named in the problems; a missing quotation only marks the fact ``quote_ok: false``."""
    problems: list[str] = []
    if not isinstance(reply, dict) or not isinstance(reply.get("facts"), list):
        return [], ["the reply is not an object with a list called facts"]
    sq_all = _squash(document["text"])
    sq_pages = {n: _squash(t) for n, t in document["page_text"].items()}
    out: list[dict[str, Any]] = []
    for i, f in enumerate(reply["facts"][:MAX_FACTS]):
        tag = f"fact {f.get('id', i + 1) if isinstance(f, dict) else i + 1}"
        if not isinstance(f, dict):
            problems.append(f"{tag}: not an object")
            continue
        if f.get("kind") not in KINDS:
            problems.append(f"{tag}: kind {f.get('kind')!r} is not one of {', '.join(KINDS)}")
            continue
        if not isinstance(f.get("subject"), str) or not f["subject"].strip():
            problems.append(f"{tag}: no subject")
            continue
        g: dict[str, Any] = {"id": str(f.get("id") or f"F{i + 1}"), "subject": f["subject"].strip(), "field": (f.get("field") or None),
                             "aliases": [str(a) for a in (f.get("aliases") or []) if isinstance(a, (str, int))], "kind": f["kind"],
                             "unit": f.get("unit"), "applies_to": str(f.get("applies_to") or "all"), "for_target": f.get("for_target") is not False,
                             "statement": str(f.get("statement") or ""), "names": [str(a) for a in (f.get("names") or []) if isinstance(a, str)],
                             "ref": f.get("ref"), "quote": str(f.get("quote") or "")}
        if f["kind"] in NUMERIC_KINDS:
            vals = [_num(x) for x in (f.get("values") or [])]
            val = _num(f.get("value"))
            lo, hi = _num(f.get("lo")), _num(f.get("hi"))
            if any(v is None for v in vals):
                problems.append(f"{tag}: a value in values is not a number")
                vals = [v for v in vals if v is not None]
            if f["kind"] == "bit_range" and lo is None:
                problems.append(f"{tag}: a bit_range fact needs lo")
                continue
            if f["kind"] != "bit_range" and val is None and not vals:
                problems.append(f"{tag}: a {f['kind']} fact needs a numeric value")
                continue
            g.update({"value": val, "values": vals or None, "lo": lo, "hi": hi if hi is not None else lo})
        else:
            g.update({"value": f.get("value") if isinstance(f.get("value"), str) else None, "values": None, "lo": None, "hi": None})
        page = _num(f.get("page"))
        g["page"] = page
        q = _squash(g["quote"])
        g["quote_ok"] = bool(q) and q in sq_all
        g["page_ok"] = bool(q) and page in sq_pages and q in sq_pages[page]
        if g["quote_ok"] and not g["page_ok"]:
            g["found_on_pages"] = [n for n, t in sq_pages.items() if q in t]
        if not g["quote_ok"]:
            problems.append(f"{tag}: the quotation was not found in the excerpt")
        out.append(g)
    ids = [g["id"] for g in out]
    if len(set(ids)) != len(ids):
        problems.append("duplicate fact ids")
    return out, problems


def _json_of(text: str) -> Any:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            t = t[i:j + 1]
    return json.loads(t)


def _fill(tmpl: str, **kw: str) -> str:
    for k, v in kw.items():
        tmpl = tmpl.replace(f"<<{k}>>", v)
    return tmpl


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def read_document(document: dict[str, Any], topic: str, target: str, llm: Callable[[str, str], str], *, max_repairs: int = 1,
                  prompt_root: Path | None = None) -> dict[str, Any]:
    """The blind reader: one model call with the excerpt, the topic and the target (never code), a check by code, and one repair round with the problems
    listed when the reply was not usable JSON or most quotations were missing. Returns the record of the read: the facts, the problems, the raw replies."""
    from agent.core import prompts
    load = (lambda n: prompts.load(n, root=prompt_root)) if prompt_root else prompts.load
    system = load(PROMPTS["system"])
    user = _fill(load(PROMPTS["user"]), TOPIC=topic, TARGET=target, DOCUMENT=document["text"])
    replies: list[str] = []
    facts: list[dict[str, Any]] = []
    problems: list[str] = []
    t0 = time.time()
    repairs = 0
    reply = llm(system, user)
    replies.append(reply)
    while True:
        try:
            facts, problems = validate_facts(_json_of(reply), document)
            parse_error = None
        except (ValueError, TypeError) as e:
            facts, problems, parse_error = [], [f"the reply is not valid JSON ({type(e).__name__})"], True
        bad_quotes = sum(1 for f in facts if not f["quote_ok"])
        needs_repair = parse_error or (facts and bad_quotes * 4 > len(facts)) or (not facts and problems)
        if not needs_repair or repairs >= max_repairs:
            break
        repairs += 1
        reply = llm(system, user + "\n\n" + _fill(load(PROMPTS["repair"]), PROBLEMS="\n".join(f"- {p}" for p in problems[:40])))
        replies.append(reply)
    return {"facts": facts, "problems": problems, "repairs": repairs, "seconds": round(time.time() - t0, 1), "raw_replies": replies,
            "prompts": {k: v for k, v in PROMPTS.items()}, "prompt_hashes": {k: sha(load(v)) for k, v in PROMPTS.items()}}


# ------------------------------------------------------------------------------------------------------- comparison

def _doc_addresses(f: dict[str, Any]) -> list[int]:
    if f.get("values"):
        return list(f["values"])
    if f.get("value") is not None:
        return [f["value"]]
    return []


def _fmt(v: Any) -> str:
    if isinstance(v, int) and not isinstance(v, bool):
        return hex(v) if v > 9 else str(v)
    if isinstance(v, (list, tuple)):
        if len(v) > 12:
            return "[" + ", ".join(_fmt(x) for x in v[:6]) + f", ... ({len(v)} items) ..., " + ", ".join(_fmt(x) for x in v[-2:]) + "]"
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_fmt(k)}: {_fmt(x)}" for k, x in list(v.items())[:8]) + (", ..." if len(v) > 8 else "") + "}"
    return str(v)


def _cite(c: dict[str, Any]) -> str:
    return f"{Path(c['file']).name}:{c['line']} {c['name']} = {_fmt(c['value'])}"


def _judge(f: dict[str, Any], c: dict[str, Any]) -> tuple[str, str] | None:
    """One document fact against one code fact: ("agree" | "disagree", reason) or None when this code fact says nothing comparable."""
    k, v = f["kind"], c["value"]
    if k == "address":
        want = _doc_addresses(f)
        have = set(_ints(v))
        if not have:
            return None
        return ("agree", "") if set(want) <= have else ("disagree", "")
    if k == "word_count":
        if c["cls"] != "list":
            return None
        return ("agree", "") if len(v) == f["value"] else ("disagree", f"the code list has {len(v)} entries")
    if k == "width_bits":
        if c.get("aspect") == "WIDTH" and isinstance(v, int):
            return ("agree", "") if v == f["value"] else ("disagree", "")
        if c.get("declared_width") and c.get("aspect") is None and isinstance(v, int):
            return ("agree", "") if c["declared_width"] == f["value"] else ("disagree", f"declared as {c['declared_width']} bits")
        return None
    if k == "reset_value":
        if not isinstance(v, int):
            return None
        return ("agree", "") if v == f["value"] else ("disagree", "")
    if k == "bit_range":
        if not isinstance(v, int) or isinstance(v, bool):
            return None
        lo, hi = f["lo"], f["hi"] if f["hi"] is not None else f["lo"]
        mask = ((1 << (hi - lo + 1)) - 1) << lo
        if c.get("aspect") == "SHIFT":
            return ("agree", "") if v == lo else ("disagree", f"shift {v}, the document puts the field at bit {lo}")
        if c.get("aspect") == "WIDTH":
            return ("agree", "") if v == hi - lo + 1 else ("disagree", f"width {v}, the document's field is {hi - lo + 1} bits")
        return ("agree", "") if v in (mask, lo) or (v == 1 << lo and hi == lo) else ("disagree", f"document: bits [{hi}:{lo}] = mask {hex(mask)} (or shift {lo})")
    if k == "value":
        want = f["values"] if f.get("values") else ([f["value"]] if f.get("value") is not None else [])
        have_l = list(v) if isinstance(v, (list, tuple)) else ([v] if isinstance(v, int) else [])
        if not have_l:
            return None
        if f.get("values"):
            return ("agree", "") if have_l == want or set(want) <= set(have_l) else ("disagree", "")
        return ("agree", "") if want[0] in have_l else ("disagree", "")
    return None


def compare(doc_facts: list[dict[str, Any]], code: dict[str, Any]) -> dict[str, Any]:
    """Compare the reader's facts with the code facts. Returns {"rows": [...], "not_in_document": [...], "summary": {...}}."""
    cfacts = code["facts"]
    prefix = frozenset(code.get("common_prefix") or [])
    mentions = code.get("mentions", {})
    all_ints: dict[int, list[dict[str, Any]]] = {}
    for c in cfacts:
        for i in _ints(c["value"]):
            all_ints.setdefault(i, []).append(c)
    rows: list[dict[str, Any]] = []
    matched_code: set[int] = set()
    for f in doc_facts:
        row: dict[str, Any] = {"fact": f, "status": None, "tier": None, "code": [], "why": ""}
        rows.append(row)
        if not f["for_target"]:
            row.update(status="other_variant", why=f"applies to {f['applies_to']!r}, not the target; not compared")
            continue
        dtoks = tokens(f["subject"]) + (tokens(f["field"]) if f.get("field") else [])
        alts = [dtoks] + [tokens(a) for a in f["aliases"] if tokens(a)]
        if f["kind"] in TEXT_KINDS:
            names = {n.upper() for n in f["names"]} | {n.upper() for n in [f["subject"]] + f["aliases"] if re.fullmatch(r"[A-Za-z_]\w+", n)}
            where = {n: mentions[n] for n in sorted(names) if n in mentions}
            code_hits = sorted(n for n, w in where.items() if w == "code")
            if code_hits:
                row.update(status="mentioned", why="the code uses " + ", ".join(code_hits) + "; the sentence itself is not compared (read the evidence)")
            elif where:
                row.update(status="mentioned", why="named only in comments or strings: " + ", ".join(sorted(where)))
            else:
                row.update(status="not_in_code", why="none of " + (", ".join(sorted(names)) or "its names") + " appears in the code")
            continue
        asp = ASPECT_OK[f["kind"]]
        cands: list[tuple[float, dict[str, Any]]] = []
        for c in cfacts:
            if c["aspect"] not in asp or c["cls"] == "map":
                continue
            s = max(name_score(a, c["tokens"], prefix) for a in alts)
            if s > 0:
                cands.append((s, c))
        pool: list[dict[str, Any]] = []
        if cands:
            if f["kind"] == "word_count":
                lists = [x for x in cands if x[1]["cls"] == "list"]
                best = max((s for s, _ in lists), default=0)
                pool = [c for s, c in lists if s == best]
            else:
                scal = [x for x in cands if x[1]["cls"] == "scalar"]
                src = scal or cands
                best = max(s for s, _ in src)
                pool = [c for s, c in src if s == best]
                if f["kind"] == "address":              # a table of addresses named for the item (QUALIFIER_ADDRS) also counts
                    pool += [c for s, c in cands if c["cls"] == "list" and c["aspect"] == "OFFSET" and c not in pool]
            row["tier"] = "name"
        judged = [(c, _judge(f, c)) for c in pool]
        judged = [(c, j) for c, j in judged if j is not None]
        if f["kind"] == "address" and judged:
            # one fact per code name is not enough for a block: take the union of the addresses of the best-named facts
            union = {i for c, _ in judged for i in _ints(c["value"])}
            want = _doc_addresses(f)
            if set(want) <= union:
                judged = [(c, ("agree", "")) for c, _ in judged]
            elif len(want) > 1 and want[0] in union and all(c["cls"] == "scalar" for c, _ in judged):
                judged = [(c, ("agree", "the code holds the base address only; the other words are not listed in code")) for c, _ in judged]
            else:
                missing = [w for w in want if w not in union]
                judged = [(c, ("disagree", f"document address(es) {', '.join(hex(w) for w in missing[:8])}{' ...' if len(missing) > 8 else ''} not among the code's {', '.join(hex(u) for u in sorted(union)[:8])}")) for c, _ in judged]
        if judged:
            row["code"] = [c for c, _ in judged]
            matched_code.update(id(c) for c, _ in judged)
            bad = [(c, j) for c, j in judged if j[0] == "disagree"]
            if bad:
                row.update(status="disagree", why="; ".join(sorted({j[1] for _, j in bad if j[1]})) or "the numbers differ")
                row["code"] = [c for c, _ in bad]
            else:
                row.update(status="agree", why="; ".join(sorted({j[1] for _, j in judged if j[1]})))
            continue
        if f["kind"] == "address":
            want = _doc_addresses(f)
            if want and all(w in all_ints for w in want):
                row.update(status="agree", tier="value", why="found by value only: no code name matched the document's name (check that the right item uses it)",
                           code=[all_ints[want[0]][0]])
                continue
        if pool:
            row.update(status="not_in_code", why="a code name matches but holds nothing comparable with this fact")
        else:
            row.update(status="not_in_code", why="no code name matches (the code may use another name: pass an alias, or read the document fact)")
    not_in_doc = [c for c in cfacts if id(c) not in matched_code and c["cls"] != "map" and c["aspect"] != "ACCESS"]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"rows": rows, "not_in_document": not_in_doc, "summary": counts}


# ------------------------------------------------------------------------------------------------------------ report

def to_record(*, document: dict[str, Any], code: dict[str, Any], read: dict[str, Any] | None, cmp: dict[str, Any], topic: str, target: str,
              model_info: dict[str, Any] | None = None, usage: dict[str, Any] | None = None, source_of_facts: str = "reader") -> dict[str, Any]:
    """The record a check keeps: hashes, the facts, the rows. No prompt text and no raw reply (those go to the private repository)."""
    def row(r: dict[str, Any]) -> dict[str, Any]:
        f = r["fact"]
        return {"id": f["id"], "status": r["status"], "tier": r["tier"], "why": r["why"], "kind": f["kind"], "subject": f["subject"], "field": f["field"],
                "doc": {k: f.get(k) for k in ("value", "values", "lo", "hi", "unit", "applies_to", "for_target", "page", "ref", "quote", "quote_ok", "page_ok", "statement")},
                "code": [{"file": c["file"], "line": c["line"], "name": c["name"], "value": c["value"] if not isinstance(c["value"], list) or len(c["value"]) <= 40 else c["value"][:40] + ["..."],
                          "n": len(c["value"]) if isinstance(c["value"], (list, tuple)) else None} for c in r["code"]]}
    return {"schema": SCHEMA, "purpose": PURPOSE, "topic": topic, "target": target,
            "document": {k: document[k] for k in ("source", "pages", "sha256", "chars")}, "code": {"files": code["files"], "n_facts": len(code["facts"]),
                                                                                                    "not_parsed": code["not_parsed"], "limits": list(CODE_LIMITS)},
            "reader": ({k: read[k] for k in ("repairs", "seconds", "problems", "prompts", "prompt_hashes")} | {"n_facts": len(read["facts"]), "source": source_of_facts}) if read else {"source": source_of_facts},
            "model": model_info, "usage": usage, "summary": cmp["summary"], "rows": [row(r) for r in cmp["rows"]],
            "not_in_document": [{"file": c["file"], "line": c["line"], "name": c["name"], "value": c["value"] if not isinstance(c["value"], list) else f"list of {len(c['value'])}"} for c in cmp["not_in_document"]]}


def render(rec: dict[str, Any], *, width: int = 100, show_agree: bool = False) -> str:
    order = {"disagree": 0, "not_in_code": 1, "mentioned": 2, "agree": 3, "other_variant": 4}
    s = rec["summary"]
    out = [f"document cross-read: {rec['topic']!r} for {rec['target']!r}",
           f"document {Path(rec['document']['source']).name} pages {rec['document']['pages'][0] if rec['document']['pages'] else '-'}-{rec['document']['pages'][-1] if rec['document']['pages'] else '-'} (sha256 {rec['document']['sha256'][:12]}); "
           f"code {', '.join(Path(f['path']).name for f in rec['code']['files'])}",
           "facts: " + ", ".join(f"{n} {k}" for k, n in sorted(s.items(), key=lambda kv: order.get(kv[0], 9))), ""]
    unver = [r for r in rec["rows"] if not r["doc"]["quote_ok"]]
    if unver:
        out.append(f"WARNING: {len(unver)} fact(s) cite a quotation that is not in the excerpt (marked [unverified citation]); do not rely on them without reading the document.\n")
    for r in sorted(rec["rows"], key=lambda r: (order.get(r["status"], 9), r["id"])):
        if r["status"] in ("agree", "other_variant") and not show_agree:
            continue
        d = r["doc"]
        flag = "" if d["quote_ok"] else " [unverified citation]"
        val = d["values"] if d["values"] else d["value"]
        rng = f" bits [{d['hi']}:{d['lo']}]" if r["kind"] == "bit_range" else ""
        out.append(f"{r['status'].upper():<12} {r['id']:<5} {r['subject']}{('.' + r['field']) if r['field'] else ''} ({r['kind']}) {_fmt(val) if val is not None else ''}{rng}{flag}")
        out.append(f"    document: p.{d['page']} {d['ref'] or ''}: \"{d['quote']}\"")
        for c in r["code"][:4]:
            out.append(f"    code:     {Path(c['file']).name}:{c['line']} {c['name']} = {_fmt(c['value'])}")
        if r["why"]:
            out.append(f"    why:      {r['why']}")
    if rec["code"]["not_parsed"]:
        n = rec["code"]["not_parsed"]
        out += ["", f"code not parsed ({len(n)}): " + "; ".join(f"{Path(x['file']).name}:{x['line']} {x['name']} ({x['why']})" for x in n[:12]) + (" ..." if len(n) > 12 else "")]
    if rec["not_in_document"]:
        n = rec["not_in_document"]
        out += ["", f"in the code but not matched by any document fact ({len(n)}): " + ", ".join(sorted({x['name'] for x in n})[:30]) + (" ..." if len(n) > 30 else "")]
    out += ["", "limits: " + " | ".join(rec["code"]["limits"])]
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------------------- run

def crossread(document: dict[str, Any], code_paths: list[Path | str], topic: str, target: str, *, llm: Callable[[str, str], str] | None = None,
              facts: list[dict[str, Any]] | Path | None = None, model_info: dict[str, Any] | None = None, usage: dict[str, Any] | None = None,
              prompt_root: Path | None = None, aliases: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The whole check. Facts come from the reader (``llm``) or from a stored reply (``facts``: a list, or a path to the JSON). Returns (record, read)."""
    code = extract_code([Path(p) for p in code_paths])
    read = None
    src = "reader"
    if facts is not None:
        if isinstance(facts, (str, Path)):
            raw = json.loads(Path(facts).read_text())
            raw = raw if isinstance(raw, dict) and "facts" in raw else {"facts": raw}
        else:
            raw = {"facts": facts}
        dfacts, problems = validate_facts(raw, document)
        read = {"facts": dfacts, "problems": problems, "repairs": 0, "seconds": 0, "prompts": {}, "prompt_hashes": {}}
        src = "stored reply"
    elif llm is not None:
        read = read_document(document, topic, target, llm, prompt_root=prompt_root)
        dfacts = read["facts"]
    else:
        raise ValueError("give a model (llm) or stored facts")
    if aliases:                                    # --alias DOCNAME=CODENAME: an engineer's mapping, added to the document fact's aliases
        for f in dfacts:
            for dn, cn in aliases.items():
                if tokens(dn) and set(tokens(dn)) <= set(tokens(f["subject"])):
                    f["aliases"] = f["aliases"] + [cn]
    cmp = compare(dfacts, code)
    return to_record(document=document, code=code, read=read, cmp=cmp, topic=topic, target=target, model_info=model_info, usage=usage, source_of_facts=src), read


class UsageMeter:
    """Wraps a Resolver ``text_result`` call so the reader's tokens, plan-cost estimate and seconds are kept (the plain text callable drops them)."""

    def __init__(self, resolver: Any, purpose: str = PURPOSE):
        from agent.models.config import ConfigError
        self.resolver, self.purpose = resolver, purpose
        self.entry = resolver.entry(purpose)
        if self.entry.model is None:
            raise ConfigError(f"purpose {purpose!r} has no model configured")
        self.calls: list[dict[str, Any]] = []

    def __call__(self, system: str, user: str) -> str:
        e = self.entry
        t0 = time.time()
        if e.kind == "claude_code":
            res = self.resolver.text_result(e, system, user, timeout_s=e.options.get("timeout_s", 900), effort=e.options.get("effort"), prefix="fda_crossread_")
            u = res.get("usage") or {}
            self.calls.append({"seconds": round(time.time() - t0, 1), "input_tokens": u.get("input_tokens"), "cache_read_input_tokens": u.get("cache_read_input_tokens"),
                               "cache_creation_input_tokens": u.get("cache_creation_input_tokens"), "output_tokens": u.get("output_tokens"),
                               "plan_cost_estimate_usd": res.get("total_cost_usd"), "is_error": res.get("is_error"), "turns": res.get("num_turns")})
            self.resolver.log_text_call(e, time.time() - t0)
            if res.get("is_error"):
                raise RuntimeError("the model call failed: " + str(res.get("result", ""))[:120])
            return str(res.get("result", ""))
        client = self.resolver.chat(self.purpose)
        r = client([{"role": "system", "content": system}, {"role": "user", "content": user}])
        self.calls.append({"seconds": round(time.time() - t0, 1), "input_tokens": getattr(r, "prompt_tokens", None), "output_tokens": getattr(r, "completion_tokens", None),
                           "cost_usd": getattr(r, "cost", None)})
        return r.text

    def totals(self) -> dict[str, Any]:
        def s(k: str) -> float | None:
            v = [c[k] for c in self.calls if isinstance(c.get(k), (int, float))]
            return round(sum(v), 4) if v else None
        return {"calls": len(self.calls), "seconds": s("seconds"), "input_tokens": s("input_tokens"), "cache_read_input_tokens": s("cache_read_input_tokens"),
                "cache_creation_input_tokens": s("cache_creation_input_tokens"), "output_tokens": s("output_tokens"),
                "plan_cost_estimate_usd": s("plan_cost_estimate_usd"), "cost_usd": s("cost_usd")}

    def model_info(self) -> dict[str, Any]:
        e = self.entry
        return {"purpose": self.purpose, "endpoint": e.endpoint, "kind": e.kind, "model": e.model, "options": dict(e.options), "entry_hash": e.hash,
                "table_hash": self.resolver.table.hash}


def make_resolver(models_file: Path | None = None, model_config: str | None = None, model: str | None = None, run_dir: Path | None = None):
    from agent.models import resolver as R
    extra = json.loads(model_config) if model_config else None
    return R.resolver_for(PURPOSE, model=model, project_file=models_file, run_dir=run_dir, extra=extra)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m flow.doc_crossread", description=__doc__.split("\n\n")[0])
    p.add_argument("--doc", type=Path, help="a text excerpt of the document (form-feed separated pages, or one page)")
    p.add_argument("--pdf", type=Path, help="a local PDF (never committed); needs --pages")
    p.add_argument("--pages", help="PDF page numbers or ranges, e.g. 226-234,462-464 (with --doc: which form-feed pages to use)")
    p.add_argument("--page-offset", type=int, default=0, help="printed page = PDF page - offset (default 0)")
    p.add_argument("--code", type=Path, action="append", default=[], help="a code file (.py, .sv, .h); repeat for more")
    p.add_argument("--topic", default="", help="what the code is about, in your own words (no code, no values): this is all the reader is told besides the excerpt")
    p.add_argument("--target", default="the device or configuration the code is for", help="the device family or configuration, as the document names it")
    p.add_argument("--facts", type=Path, help="compare a stored reader reply (JSON) instead of calling a model")
    p.add_argument("--alias", action="append", default=[], metavar="DOC=CODE", help="a document name and the code name for it")
    p.add_argument("--code-only", action="store_true", help="print what the code side reads and stop (no document, no model)")
    p.add_argument("--json", action="store_true", help="print the record as JSON")
    p.add_argument("--show-agree", action="store_true", help="list the agreeing facts too")
    p.add_argument("--record", type=Path, help="write the record (and the raw replies, if any) to this directory")
    p.add_argument("--models-file", type=Path, help="the project's model table (purpose doc_crossread)")
    p.add_argument("--model-config", help="JSON command-line layer of the model table")
    p.add_argument("--model", help="the model for this run (an alias for the table's doc_crossread entry)")
    a = p.parse_args(argv)
    if not a.code:
        p.error("give at least one --code file")
    if a.code_only:
        code = extract_code(a.code)
        print(f"{len(code['facts'])} facts, {len(code['not_parsed'])} not parsed; common prefix tokens: {code['common_prefix']}")
        for c in code["facts"]:
            print(f"  {Path(c['file']).name}:{c['line']:<5} {c['name']:<40} {c['cls']:<6} {_fmt(c['value'])}" + (f"  [{c['aspect']}]" if c["aspect"] else ""))
        for u in code["not_parsed"]:
            print(f"  NOT PARSED {Path(u['file']).name}:{u['line']} {u['name']}: {u['why']}")
        return 0
    if not (a.doc or a.pdf):
        p.error("give --doc or --pdf")
    doc = load_document(doc=a.doc, pdf=a.pdf, pages=a.pages, page_offset=a.page_offset)
    aliases = dict(x.split("=", 1) for x in a.alias)
    meter = None
    if a.facts is None:
        from agent.access import require_or_exit
        require_or_exit("doc_crossread")
        meter = UsageMeter(make_resolver(a.models_file, a.model_config, a.model, a.record))
    rec, read = crossread(doc, a.code, a.topic, a.target, llm=meter, facts=a.facts, aliases=aliases,
                          model_info=meter.model_info() if meter else None, usage=meter.totals() if meter else None)
    if meter:
        rec["usage"] = meter.totals()
    if a.record:
        a.record.mkdir(parents=True, exist_ok=True)
        (a.record / "record.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
        if read and read.get("raw_replies"):
            (a.record / "raw_replies.json").write_text(json.dumps(read["raw_replies"], indent=1))
    print(json.dumps(rec, indent=1, default=str) if a.json else render(rec, show_agree=a.show_agree))
    return 2 if rec["summary"].get("disagree") else 0


if __name__ == "__main__":
    sys.exit(main())
