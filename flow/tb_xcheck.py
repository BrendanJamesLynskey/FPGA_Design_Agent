#!/usr/bin/env python3
"""Advisory source check: a testbench compare that cannot fail on X or Z (brief 189 item 11; idea from Edwards 2026, ch 4). ``enforced: false``.

Rule. In a self-checking SystemVerilog testbench the test fails when the actual value is X or Z. The logical operators ``==`` and ``!=`` return
X when an operand has an X bit, and ``if (X)`` takes the false branch, so ``if (got != want) $error(...)`` is silent for a DUT output
that is X: the broken design passes. Use the case operators (``!==``, ``===``), or test ``$isunknown(got)`` first. ``assert (got == want)``
is fine (an X condition is not true, so the assertion fails).

Finding TB-X-01: an ``if`` whose condition contains a ``!=`` (or a negated ``==``, ``!(a == b)``) and no ``!==``, ``===`` or ``$isunknown``, and
whose statement raises an error ($error, $fatal, a fail/error/mismatch call, an error counter, a $display of FAIL/ERROR/MISMATCH).
Silence a deliberate one with ``// x-ok: <reason>`` on the line. cocotb benches are not scanned: ``int(sig.value)`` raises on an unresolved
value, and the CDC and conservation fixtures assert ``is_resolvable`` explicitly (a gap, stated in docs/verification_measurement_rules.md).

    python3 -m flow.tb_xcheck [PATH ...] [--json OUT]       # with no path: SystemVerilog testbenches under designs/ and flow/tests/fixtures"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEG_EQ = re.compile(r"(?<![!=<>])!=(?!=)")
NEG_PAREN_EQ = re.compile(r"!\s*\([^()]*(?<![!=<>])==(?!=)")
SAFE = re.compile(r"!==|===|\$isunknown|\$countbits")
ACTION = re.compile(r"^\s*(?:begin\b\s*)?(?::\s*\w+\s*)?(?:\$(?:error|fatal)\b|\w*(?:fail|error|mismatch|err)\w*\s*(?:\(|\+\+|\+=|<=|=)|"
                    r"\$display\s*\([^;]*(?:FAIL|ERROR|MISMATCH))", re.I)


def _mask(text: str) -> str:
    """Comments replaced by spaces (strings kept: an action may be a $display of a message), offsets preserved."""
    return re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def scan_text(text: str, path: str = "-") -> list[dict[str, Any]]:
    clean = _mask(text)
    raw_lines = text.splitlines()
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"\bif\s*\(", clean):
        i, depth = m.end(), 1
        while i < len(clean) and depth:
            depth += {"(": 1, ")": -1}.get(clean[i], 0)
            i += 1
        cond = clean[m.end():i - 1]
        cond_nostr = re.sub(r'"[^"]*"', '""', cond)
        cond_nostr = re.sub(r"\.\s*(?:size|num|len)\s*\(\s*\)\s*!=\s*\w+", "", cond_nostr)   # a queue or array size is two-state
        if not (NEG_EQ.search(cond_nostr) or NEG_PAREN_EQ.search(cond_nostr)) or SAFE.search(cond_nostr):
            continue
        if not ACTION.match(clean[i:i + 240]):
            continue
        line = clean.count("\n", 0, m.start()) + 1
        if "x-ok:" in raw_lines[line - 1] or (line > 1 and "x-ok:" in raw_lines[line - 2]):
            continue
        out.append({"code": "TB-X-01", "where": f"{path}:{line}", "condition": " ".join(cond.split())[:120],
                    "message": "an error raised under a != (or negated ==) compare: an X or Z operand makes the condition X and the error is skipped; "
                               "use !== or test $isunknown first"})
    return out


def scan_file(p: Path, root: Path = ROOT) -> list[dict[str, Any]]:
    try:
        rel = str(p.relative_to(root))
    except ValueError:
        rel = str(p)
    try:
        return scan_text(p.read_text(errors="replace"), rel)
    except OSError:
        return []


def default_paths(root: Path = ROOT) -> list[Path]:
    out: list[Path] = []
    for g in ("designs/*/verif/**/*.sv", "designs/*/tests/**/*.sv", "designs/*/tb/**/*.sv", "flow/tests/fixtures/**/*.sv", "arith/**/tb/*.sv", "axi_tx/**/*.sv"):
        out += [p for p in sorted(root.glob(g)) if "/rtl/" not in p.as_posix() and "/xcompare/" not in p.as_posix()]   # xcompare holds the seeded defect
    return sorted(set(out))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json", dest="out")
    a = ap.parse_args(argv)
    paths = [Path(p) for p in a.paths] or default_paths()
    findings = [f for p in paths for f in scan_file(p)]
    rec = {"enforced": False, "files_scanned": len(paths), "findings": findings}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    for f in findings:
        print(f"{f['code']} {f['where']}: if ({f['condition']})")
    print(f"{len(findings)} advisory finding(s) in {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
