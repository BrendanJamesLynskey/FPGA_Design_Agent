"""Advisory source check (brief 190, item 17): a data-dependent shift or index of a wide vector in a fast-path module.

``x >> n`` with ``n`` a signal, or ``x[i +: W]`` / ``x[i]`` with ``i`` a signal, is a barrel shifter or a wide multiplexer: it reads like one line
and costs several LUT levels (about log2 of the range), so it eats the clock budget of a path that has to be fast. The question the finding asks:
can the data stay where it is while a small position register moves (a pointer, an offset, a one-hot select)? Idea from Edwards 2026, ch 3; the
detector and its thresholds are ours. Advisory: it never blocks, and a wide shift that is not on the fast path is none of its business.

**Which modules.** Only those declared fast-path: named in the design's ``architecture.yaml`` under ``fast_path: [module, ...]``, or carrying the
marker comment ``// fda:fast_path`` inside the module or on the lines just before its ``module`` keyword. A design that declares none gets no findings and a ``parts`` note saying so.

**What counts.** The left operand (or the indexed vector) must be a vector declared in the same file with a width that evaluates to at least
``MIN_WIDTH`` (32 bits) from literal numbers, ``parameter``/``localparam`` values and ``$clog2``; a vector whose width cannot be evaluated is
counted in ``parts`` and not flagged. The amount or index must contain a name that is not a parameter, a genvar or a ``for`` loop variable (those
are constants after unrolling). A shifted literal (``1 << n``, a decoder) and a part-select with constant bounds are not flagged. Memory arrays
(``logic [W-1:0] mem [N]``) are not flagged: reading a RAM by address is not a barrel shifter. This is a text scan, not an elaboration: a name
shadowed in an inner scope, or a width set by a macro, can be misjudged, which is why the rule is advice.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MIN_WIDTH = 32
MARKER = re.compile(r"//\s*fda:\s*fast_path\b")
_MODULE = re.compile(r"\bmodule\s+(\w+)\b(.*?)\bendmodule\b", re.S)
_PARAM = re.compile(r"\b(?:parameter|localparam)\b(?:\s+(?:int|integer|unsigned|signed|logic|bit|reg)\b|\s*\[[^\]]*\])*\s*(\w+)\s*=\s*")
_DECL = re.compile(r"\b(?:logic|reg|wire|bit|input|output|inout)\b(?:\s+(?:signed|unsigned|logic|reg|wire|var)\b)*\s*\[\s*([^:\]\[]+?)\s*:\s*([^:\]\[]+?)\s*\]\s*([^;=)]+?)\s*(?=[;=)]|,\s*(?:input|output|inout|\.))")
_LOOPVAR = re.compile(r"\bfor\s*\(\s*(?:int|integer|genvar|bit|logic)?\s*(\w+)\s*=|\bgenvar\s+([\w\s,]+);")
_IDENT = re.compile(r"[A-Za-z_]\w*")


def strip_comments(text: str) -> str:
    """Comments and string literals blanked (newlines kept, so line numbers hold)."""
    def blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"', blank, text, flags=re.S)


def _eval(expr: str, env: dict[str, int]) -> int | None:
    """An integer expression of numbers, known parameters, ``$clog2`` and + - * / ( ) << >>; None when it cannot be evaluated."""
    e = expr.strip()
    e = re.sub(r"\$clog2\s*\(", "_clog2(", e)
    e = re.sub(r"\b(\d+)'[sS]?[dD](\d+)", r"\2", e)
    e = re.sub(r"\b\d*'[sS]?[hH]([0-9a-fA-F_]+)", lambda m: str(int(m.group(1).replace("_", ""), 16)), e)
    e = re.sub(r"\b\d*'[sS]?[bB]([01_]+)", lambda m: str(int(m.group(1).replace("_", ""), 2)), e)
    e = e.replace("_", "") if re.fullmatch(r"[\d_]+", e) else e
    toks = _IDENT.findall(e)
    for t in toks:
        if t == "_clog2":
            continue
        if t not in env:
            return None
        e = re.sub(rf"\b{t}\b", str(env[t]), e)
    if not re.fullmatch(r"[\d\s+\-*/()<>_a-z]*", e) or "__" in e:
        return None
    e = e.replace("/", "//")
    try:
        return int(eval(e, {"__builtins__": {}}, {"_clog2": lambda x: max(1, (int(x) - 1).bit_length()) if x > 1 else 0}))   # noqa: S307 (charset-checked above)
    except Exception:                                   # noqa: BLE001
        return None


def _params(text: str) -> dict[str, int]:
    env: dict[str, int] = {}
    for _ in range(3):                                   # a few passes: a parameter may use one declared after it
        for m in _PARAM.finditer(text):
            v = _eval(text[m.end():_end_of_operand(text, m.end())], env)
            if v is not None:
                env.setdefault(m.group(1), v)
    return env


def _end_of_operand(t: str, i: int) -> int:
    """Index just past the shift amount that starts at i: up to a ; , ? : or an unmatched closer."""
    depth = 0
    while i < len(t):
        c = t[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and c in ";,?:":
            break
        i += 1
    return i


def _variable(expr: str, consts: set[str]) -> bool:
    names = [n for n in _IDENT.findall(re.sub(r"\d*'[sS]?[bBdDhH][0-9a-fA-F_xXzZ]+", " ", expr)) if n != "clog2"]
    return any(n not in consts for n in names)


def modules_in_scope(text: str, declared: set[str]) -> list[tuple[str, str, int]]:
    """(name, body, first line) of each module that is declared in architecture.yaml or carries the marker comment."""
    out = []
    clean = strip_comments(text)
    prev = 0
    for m in _MODULE.finditer(clean):
        raw = text[prev:m.end()]            # the marker may sit just before the module keyword (after the previous module) or inside the module
        prev = m.end()
        if m.group(1) in declared or MARKER.search(raw):
            out.append((m.group(1), clean[m.start():m.end()], text.count("\n", 0, m.start()) + 1))
    return out


def findings_in_module(name: str, body: str, first_line: int, where: str = "", min_width: int = MIN_WIDTH) -> tuple[list[dict[str, Any]], int]:
    """(findings, number of shifts or indexes left unjudged because the vector's width could not be evaluated)."""
    env = _params(body)
    consts = set(env)
    for m in _LOOPVAR.finditer(body):
        consts |= set(re.findall(r"\w+", m.group(1) or m.group(2)))
    widths: dict[str, int | None] = {}
    arrays: set[str] = set()
    for m in _DECL.finditer(body):
        hi, lo = _eval(m.group(1), env), _eval(m.group(2), env)
        for nm in re.split(r"\s*,\s*", m.group(3).strip()):
            mm = re.match(r"(\w+)\s*(\[.*)?$", nm.strip(), re.S)
            if not mm:
                continue
            if mm.group(2):                               # an unpacked array dimension after the name: a memory
                arrays.add(mm.group(1))
            widths[mm.group(1)] = None if hi is None or lo is None else abs(hi - lo) + 1
    out: list[dict[str, Any]] = []
    unjudged = 0

    def line_of(pos: int) -> int:
        return first_line + body.count("\n", 0, pos)

    def add(code: str, pos: int, vec: str, w: int, what: str) -> None:
        loc = f"{where}:{line_of(pos)}" if where else str(line_of(pos))
        out.append({"code": code, "where": loc, "module": name, "vector": vec, "width": w, "blocking": False,
                    "message": f"{what} on the {w}-bit vector '{vec}' in fast-path module {name} is a barrel shifter or wide multiplexer (about log2 of "
                               "the range in LUT levels); can the data stay in place while a small position register moves?"})

    def judge(vec: str) -> int | None:
        nonlocal unjudged
        if vec in arrays or vec not in widths:
            return None
        w = widths[vec]
        if w is None:
            unjudged += 1
            return None
        return w if w >= min_width else None

    for m in re.finditer(r"(?<![\w$.'])([A-Za-z_]\w*)\s*(<<<|>>>|<<|>>)(?!=)\s*", body):
        end = _end_of_operand(body, m.end())
        amount = body[m.end():end]
        if not amount.strip() or not _variable(amount, consts):
            continue
        w = judge(m.group(1))
        if w:
            add("FAST-SHIFT-01", m.start(), m.group(1), w, f"a shift by the signal expression '{amount.strip()}'")
    for m in re.finditer(r"(?<![\w$.'])([A-Za-z_]\w*)\s*\[([^\[\]]*?)(\+:|-:)([^\[\]]+)\]", body):
        if _variable(m.group(2), consts):
            w = judge(m.group(1))
            if w:
                add("FAST-INDEX-01", m.start(), m.group(1), w, f"an indexed part-select starting at '{m.group(2).strip()}'")
    for m in re.finditer(r"(?<![\w$.'])([A-Za-z_]\w*)\s*\[([^\[\]:+\-]*?)\]", body):
        if m.group(1) in widths and _variable(m.group(2), consts) and m.group(2).strip():
            w = judge(m.group(1))
            if w:
                add("FAST-INDEX-01", m.start(), m.group(1), w, f"a bit-select by the signal '{m.group(2).strip()}'")
    return out, unjudged


def findings(text: str, declared: set[str] | None = None, where: str = "", min_width: int = MIN_WIDTH, all_modules: bool = False) -> tuple[list[dict[str, Any]], int, int]:
    """(findings, modules examined, unjudged count) for one file's text. ``all_modules=True`` examines every module (measurement and tests)."""
    mods = modules_in_scope(text, declared or set())
    if all_modules:
        clean = strip_comments(text)
        mods = [(m.group(1), clean[m.start():m.end()], text.count("\n", 0, m.start()) + 1) for m in _MODULE.finditer(clean)]
    fs: list[dict[str, Any]] = []
    unj = 0
    for name, body, line in mods:
        f, u = findings_in_module(name, body, line, where, min_width)
        fs += f
        unj += u
    return fs, len(mods), unj


def run(sources: list[Path], declared: set[str], root: Path) -> dict[str, Any]:
    fs: list[dict[str, Any]] = []
    n_mod = unj = 0
    for f in sources:
        if f.suffix not in (".sv", ".v"):
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(root)) if f.is_relative_to(root) else str(f)
        a, n, u = findings(text, declared, rel)
        fs += a
        n_mod += n
        unj += u
    return {"findings": fs, "modules": n_mod, "unjudged": unj}
