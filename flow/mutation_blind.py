#!/usr/bin/env python3
"""Blind mutant generator (brief 143b): mutants made from the RTL text alone, never from the tests.

    python3 -m flow.mutation_blind FILE.sv [FILE.sv ...] --seed 1 --count 40 [--json OUT]

Why "blind". A mutant list written by the person (or agent) who wrote the bench tends to contain the bugs that bench already catches
(brief 123: the pyuvm bench was written with the UVM mutant list in hand). This generator takes only RTL source text and an integer seed:
it has no argument through which a test, a model or a bench could reach it, so the mutants cannot lean on them. ``generate`` is a pure
function of (the file contents, the seed, the operator set): the same inputs give the same mutants, and the seed is recorded in the result.

Operators (a mutant is one substitution on one code line; comment, declaration, assertion and parameter lines are skipped):
  comparison   ``==`` <-> ``!=``; ``<`` <-> ``<=``; ``>`` <-> ``>=``; ``>=`` -> ``<`` and ``>`` -> ``<=`` (the inverted forms)
  logic        ``&&`` <-> ``||``; ``&`` <-> ``|``; ``^`` -> ``|``; a logical ``!`` removed; a bitwise ``~`` removed
  arithmetic   `` + `` <-> `` - ``; ``<<`` <-> ``>>``; 
  constant     a one-bit constant flipped; a sized constant ``N'dV`` (or ``N'hV``) changed by +1 and by -1
  select       the two arms of ``c ? a : b`` swapped (one-line ternaries)

Optional, still blind to the tests: ``llm_prompt`` builds the prompt for a model asked to propose realistic bugs from the RTL text alone, and
``load_llm_proposals`` validates what comes back (each ``old`` text must occur exactly once in its file; anything else is dropped and
listed). No test, model or bench text is ever put into the prompt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

#: (name, regex, replacement, words). Each regex match on a code line is one candidate mutant.
OPERATORS: list[tuple[str, str, str, str]] = [
    ("eq_to_ne", r"(?<![=!<>])==(?!=)", "!=", "'==' replaced by '!='"),
    ("ne_to_eq", r"!=(?!=)", "==", "'!=' replaced by '=='"),
    ("lt_to_le", r"(?<![<])<(?![<=])", "<=", "'<' replaced by '<='"),
    ("gt_to_ge", r"(?<![>-])>(?![>=])", ">=", "'>' replaced by '>='"),
    ("ge_to_gt", r">=", ">", "'>=' replaced by '>'"),
    ("ge_to_lt", r" >= ", " < ", "'>=' replaced by '<'"),
    ("gt_to_le", r" > ", " <= ", "'>' replaced by '<='"),
    ("and_to_or", r"&&", "||", "'&&' replaced by '||'"),
    ("or_to_and", r"\|\|", "&&", "'||' replaced by '&&'"),
    ("band_to_bor", r"(?<![&])&(?![&])", "|", "bitwise '&' replaced by '|'"),
    ("bor_to_band", r"(?<![|])\|(?![|])", "&", "bitwise '|' replaced by '&'"),
    ("xor_to_or", r"\^", "|", "'^' replaced by '|'"),
    ("not_removed", r"(?<![!=<>&|])!(?![=])", "", "a logical negation '!' removed"),
    ("tilde_removed", r"~(?![&|^])", "", "a bitwise negation '~' removed"),
    ("plus_to_minus", r" \+ ", " - ", "'+' replaced by '-'"),
    ("minus_to_plus", r" - ", " + ", "'-' replaced by '+'"),
    ("shl_to_shr", r"<<(?!<)", ">>", "'<<' replaced by '>>'"),
    ("shr_to_shl", r"(?<![>])>>(?![>])", "<<", "'>>' replaced by '<<'"),
    ("bit0_to_1", r"\b1'b0\b", "1'b1", "constant 1'b0 replaced by 1'b1"),
    ("bit1_to_0", r"\b1'b1\b", "1'b0", "constant 1'b1 replaced by 1'b0"),
]
_SIZED = re.compile(r"\b(\d+)'([dh])([0-9a-fA-F_]+)\b")
_SKIP_LINE = re.compile(r"^\s*(//|/\*|\*|`|import\b|parameter\b|localparam\b|module\b|endmodule\b|input\b|output\b|inout\b|typedef\b|function\b|endfunction\b)"
                        r"|\bassert\b|\bassume\b|\bcover\b|\$(display|error|fatal|info|finish|warning)|\bproperty\b")


def _code(raw: str) -> str:
    return raw.split("//", 1)[0]


def _ternaries(code: str) -> list[tuple[int, int, str]]:
    """One-line ``c ? a : b`` with bracket-aware arms: [(start of a, end of b, "b : a")]. Skips a nested ternary and any line it cannot parse cleanly."""
    out = []
    for q in [i for i, ch in enumerate(code) if ch == "?"]:
        if code.count("?") > 1 or "'" in code[q - 1:q]:
            continue
        depth, colon, end = 0, None, None
        for i in range(q + 1, len(code)):
            ch = code[i]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    end = i
                    break
                depth -= 1
            elif ch == ":" and depth == 0 and colon is None:
                colon = i
            elif ch in ";," and depth == 0 and colon is not None:
                end = i
                break
        if colon is None:
            continue
        end = len(code.rstrip()) if end is None else end
        a, b = code[q + 1:colon].strip(), code[colon + 1:end].strip()
        if a and b and a != b:
            out.append((q + 1 + (len(code[q + 1:colon]) - len(code[q + 1:colon].lstrip())), colon + 1 + (len(code[colon + 1:end]) - len(code[colon + 1:end].lstrip())) + len(b), f"{b} : {a}"))
    return out


def _const_changes(code: str) -> list[tuple[int, int, str, str, str]]:
    """Sized-constant mutants: (start, end, replacement, operator name, words)."""
    out = []
    for m in _SIZED.finditer(code):
        width, base, digits = int(m.group(1)), m.group(2), m.group(3).replace("_", "")
        if width < 2:
            continue
        v = int(digits, 10 if base == "d" else 16)
        for delta, nm in ((1, "const_plus1"), (-1, "const_minus1")):
            nv = v + delta
            if nv < 0 or nv >= (1 << width):
                continue
            txt = f"{width}'{base}{nv if base == 'd' else format(nv, 'x')}"
            out.append((m.start(), m.end(), txt, nm, f"constant {m.group(0)} changed to {txt}"))
    return out


def candidates(files: list[Path], operators: list[str] | None = None) -> list[dict]:
    """Every operator mutation of the RTL code lines, in a fixed order (file name, line, operator, column)."""
    out: list[dict] = []
    for f in sorted(files, key=lambda p: p.name):
        for n, raw in enumerate(f.read_text(errors="replace").splitlines(), 1):
            code = _code(raw)
            if not code.strip() or _SKIP_LINE.search(code):
                continue
            found: list[tuple[int, int, str, str, str]] = []
            for name, rx, rep, words in OPERATORS:
                for m in re.finditer(rx, code):
                    found.append((m.start(), m.end(), rep, name, words))
            found += _const_changes(code)
            for st_, en_, rep_ in _ternaries(code):
                found.append((st_, en_, rep_, "ternary_swap", "the two arms of a ?: swapped"))
            for start, end, rep, name, words in found:
                if operators and name not in operators:
                    continue
                new = code[:start] + rep + code[end:]
                if new == code:
                    continue
                out.append({"name": f"{f.stem}_L{n}_{name}_{start}", "file": f.name, "line": n, "col": start, "span": end - start, "rep": rep,
                            "class": name, "why": words, "old_line": code.strip(), "new_line": new.strip()})
    # one candidate per (file, line, column, replacement): overlapping regex hits can repeat a change
    seen, uniq = set(), []
    for c in out:
        k = (c["file"], c["line"], c["col"], c["span"], c["rep"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


def apply(m: dict, src: str) -> str | None:
    """The mutated source, or None when the text at the recorded position is not what the generator saw."""
    if "old_text" in m:
        return src.replace(m["old_text"], m["new_text"]) if src.count(m["old_text"]) == 1 else None
    lines = src.splitlines(keepends=True)
    if not 1 <= m["line"] <= len(lines):
        return None
    raw = lines[m["line"] - 1]
    code = _code(raw.rstrip("\n"))
    if code[m["col"]:m["col"] + m["span"]] == "" or code.strip() != m["old_line"]:
        return None
    tail = raw.rstrip("\n")[len(code):]
    lines[m["line"] - 1] = code[:m["col"]] + m["rep"] + code[m["col"] + m["span"]:] + tail + ("\n" if raw.endswith("\n") else "")
    return "".join(lines)


def generate(files: list[Path], seed: int, count: int | None = 40, operators: list[str] | None = None) -> dict:
    """A seeded sample of the candidates. ``count`` None takes every candidate. Pure in (the file contents, seed, count, operators)."""
    pool = candidates(files, operators)
    rng = random.Random(seed)
    chosen = pool if count is None or count >= len(pool) else sorted(rng.sample(pool, count), key=pool.index)
    digest = hashlib.sha256("".join(f"{f.name}\n{f.read_text(errors='replace')}" for f in sorted(files, key=lambda p: p.name)).encode()).hexdigest()
    return {"seed": seed, "requested": count, "candidates": len(pool), "sampled": len(chosen),
            "operators": sorted({o[0] for o in OPERATORS} | {"const_plus1", "const_minus1", "ternary_swap"}) if not operators else sorted(operators),
            "rtl_sha256": digest, "mutants": chosen, "source": "operator-based, blind to the tests"}


def llm_prompt(files: list[Path]) -> str:
    """The prompt for a model asked to propose realistic bugs from the RTL alone. It contains the RTL text and nothing from any test or bench."""
    body = "\n\n".join(f"// ---- {f.name}\n{f.read_text(errors='replace')}" for f in sorted(files, key=lambda p: p.name))
    return ("You are given the SystemVerilog source of a hardware block. Propose up to 20 realistic single-line bugs a careless engineer could introduce "
            "(off-by-one, wrong reset value, a dropped condition, a swapped operand, a wrong width, a missing hold). Reply with JSON only: a list of "
            '{"file": "<file name>", "old": "<exact text, occurring once in that file>", "new": "<replacement>", "why": "<one line>"}. '
            "You have not been shown any test; do not guess at what is tested.\n\n" + body)


def load_llm_proposals(raw: str, files: list[Path]) -> tuple[list[dict], list[dict]]:
    """(valid mutants, dropped proposals with the reason). Each ``old`` must occur exactly once in its file and differ from ``new``."""
    by_name = {f.name: f for f in files}
    ok, bad = [], []
    try:
        props = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], [{"proposal": None, "reason": f"not JSON: {e}"}]
    for i, p in enumerate(props if isinstance(props, list) else []):
        try:
            f, old, new = by_name[p["file"]], p["old"], p["new"]
        except (KeyError, TypeError):
            bad.append({"proposal": p, "reason": "missing or unknown file/old/new"})
            continue
        n = f.read_text(errors="replace").count(old)
        if n != 1 or old == new:
            bad.append({"proposal": p, "reason": f"old text occurs {n} times" if n != 1 else "old equals new"})
            continue
        line = f.read_text(errors="replace")[:f.read_text(errors="replace").find(old)].count("\n") + 1
        ok.append({"name": f"{f.stem}_llm{i}", "file": f.name, "line": line, "class": "llm_proposed", "why": p.get("why", ""),
                   "old_text": old, "new_text": new, "old_line": old.strip().splitlines()[0], "new_line": new.strip().splitlines()[0]})
    return ok, bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    res = generate([Path(f) for f in a.files], a.seed, a.count)
    print(f"{res['candidates']} candidates, {res['sampled']} sampled (seed {a.seed})")
    for m in res["mutants"]:
        print(f"  {m['name']}: {m['file']}:{m['line']} {m['why']}")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
