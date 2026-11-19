#!/usr/bin/env python3
"""The derived-constants gate (brief 106): a constant that code can derive from a structured source is derived by code,
and the RTL is checked against it. The model never decides it.

    python3 -m flow.derived_constants designs/<d> [--json OUT]

What is derived, and from what (nothing else is checked, so a finding is always a mismatch against a derivation):

1. **The shell design ID.** The spec names it as a quoted four-character string ("The design ID is "UEP1""). The test
   shell's protocol (shell/PROTOCOL.md, register 0x00) defines DESIGN_ID as four ASCII characters, most significant
   first, so the value is ``int.from_bytes(b"UEP1", "big")``. The RTL's binding is the ``DESIGN_ID`` parameter of the
   ``fpga_shell`` instance (a literal, a string, or a name that resolves to a parameter or localparam with a literal
   value in the build's sources). ``CONST-ID-01`` (blocking): the binding is a different value. This is the 82P3
   failure: four of six runs bound the register-0 "identification word" 0x55445031 where the string gives 0x55455031.
2. **Named spec literals.** A hex literal the spec attaches to an identity word ("identification word 0x55445031") is a
   constant the RTL must contain. ``CONST-LIT-01`` (advisory): no 32-bit literal in the sources has that value. Advisory,
   because a value can be built another way (a concatenation, a parameter set outside the sources).
3. **The board clock period.** ``create_clock -period`` on the board's own oscillator port must be 1000 / freq_mhz of
   the board file. ``CONST-CLK-01`` (blocking).

What the gate cannot do (recorded in ``reports/106_orchestrator_lessons_report.md``): it does not read the spec's
meaning. A constant the spec states in prose it has no pattern for is not checked, and a design with no quoted design ID
or no shell instance gets no ID finding at all (the result says so, it is never a silent pass). The table it derives is
written to ``build/derived_constants.json`` so the run record states every derived value and where it came from.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

_DESIGN_ID = re.compile(r"design\s+id\s*(?:is|=|:)\s*[\"“'‘]([\x20-\x7e]{4})[\"”'’]", re.I)
_HEX = re.compile(r"\b0x([0-9A-Fa-f][0-9A-Fa-f_]{3,15})\b")
#: words that make a hex literal an identity word (a constant that names the design, not a polynomial or a mask)
_IDENTITY = re.compile(r"\b(id|identification|identity|magic|signature)\b", re.I)
_NUM = re.compile(r"(\d+)?\s*'\s*([sS]?)([hHdDbBoO])\s*([0-9a-fA-F_xXzZ]+)")


def spec_table(spec_text: str) -> dict[str, Any]:
    """What code can read out of the spec text: the quoted design ID, and the hex literals tied to an identity word."""
    out: dict[str, Any] = {"design_id": None, "named_literals": []}
    m = _DESIGN_ID.search(spec_text)
    if m:
        s = m.group(1)
        out["design_id"] = {"string": s, "value": int.from_bytes(s.encode("ascii"), "big"),
                            "source": f'spec.md: "{m.group(0).strip()}"', "rule": "shell/PROTOCOL.md register 0x00: four ASCII characters, MSB first"}
    for m in _HEX.finditer(spec_text):
        before = " ".join(spec_text[max(0, m.start() - 60):m.start()].split()[-3:])
        if _IDENTITY.search(before):
            v = int(m.group(1).replace("_", ""), 16)
            out["named_literals"].append({"text": "0x" + m.group(1), "value": v, "context": before})
    return out


def _strip_comments(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def parse_literal(expr: str) -> int | None:
    """The integer value of a Verilog literal (sized or not, underscores allowed) or a short string, else None."""
    e = expr.strip()
    s = re.fullmatch(r'"([^"]{1,8})"', e)
    if s:
        return int.from_bytes(s.group(1).encode("ascii", "replace"), "big")
    m = _NUM.fullmatch(e)
    if m:
        digits = m.group(4).replace("_", "")
        if re.search(r"[xXzZ]", digits):
            return None
        return int(digits, {"h": 16, "d": 10, "b": 2, "o": 8}[m.group(3).lower()])
    if re.fullmatch(r"\d+", e):
        return int(e)
    return None


def _params(texts: dict[str, str]) -> dict[str, list[tuple[str, int | None]]]:
    """name -> [(file, value)] for every ``parameter``/``localparam`` assignment with a literal value."""
    out: dict[str, list[tuple[str, int | None]]] = {}
    for f, t in texts.items():
        for m in re.finditer(r"\b(?:parameter|localparam)\b[^;=,)]*?\b([A-Za-z_]\w*)\s*=\s*([^;,)]+)", t):
            out.setdefault(m.group(1), []).append((f, parse_literal(m.group(2))))
    return out


def design_id_bindings(texts: dict[str, str], cfg_generics: dict | None = None) -> list[dict[str, Any]]:
    """Each ``.DESIGN_ID(expr)`` binding on an ``fpga_shell`` instance: file, the expression, its value or None."""
    params = _params(texts)
    out = []
    for f, t in texts.items():
        for inst in re.finditer(r"\bfpga_shell\b\s*(?:#\s*\((.*?)\))?\s*\w+\s*\(", t, re.S):
            body = inst.group(1) or ""
            m = re.search(r"\.DESIGN_ID\s*\(\s*(.*?)\s*\)\s*(?:,|$)", body, re.S) or re.search(r"\.DESIGN_ID\s*\(\s*([^()]*?)\s*\)", body)
            if not m:
                continue
            expr = m.group(1).strip()
            val = parse_literal(expr)
            how = "literal"
            if val is None and re.fullmatch(r"[A-Za-z_]\w*", expr) and expr not in (cfg_generics or {}):
                cands = [v for (pf, v) in params.get(expr, []) if v is not None]
                same = [v for (pf, v) in params.get(expr, []) if v is not None and pf == f]
                pick = same or cands
                if pick:
                    val, how = pick[0], f"parameter {expr}"
            out.append({"file": f, "expr": expr, "value": val, "how": how})
    return out


def _sources(design: Path, root: Path) -> tuple[list[Path], dict[str, Any]]:
    try:
        cfg = yaml.safe_load((design / "build.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        cfg = {}
    files: list[Path] = []
    for g in cfg.get("sources") or []:
        files += [p for p in sorted(root.glob(g)) if p.suffix in (".sv", ".v", ".svh", ".vh") and p not in files]
    if not files:                                        # no build.yaml (a bare design directory): its own rtl/
        files = sorted(p for p in design.glob("rtl/**/*") if p.suffix in (".sv", ".v"))
    return files, cfg


def board_clock(cfg: dict[str, Any], root: Path) -> dict[str, Any] | None:
    try:
        from flow.stale_check import board_name
        b = board_name(cfg, root)
        d = yaml.safe_load((root / "boards" / str(b) / "board.yaml").read_text()) or {}
    except Exception:                                   # noqa: BLE001 (no board file: no clock check, said in the result)
        return None
    c = d.get("clock") or {}
    if not c.get("port") or not c.get("freq_mhz"):
        return None
    return {"board": b, "port": str(c["port"]), "freq_mhz": float(c["freq_mhz"]), "period_ns": 1000.0 / float(c["freq_mhz"])}


_CREATE = re.compile(r"create_clock\b([^\n;]*)")


def xdc_clock_periods(text: str, port: str) -> list[float]:
    """Periods (ns) of the ``create_clock`` lines that name ``port`` (comment lines skipped)."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for m in _CREATE.finditer(line):
            body = m.group(1)
            p = re.search(r"-period\s+([0-9.]+)", body)
            if p and re.search(r"get_ports\s*\{?\s*" + re.escape(port) + r"\b", body):
                out.append(float(p.group(1)))
    return out


def derive(design: Path, root: Path = ROOT) -> dict[str, Any]:
    """The derived table and the findings, as plain data."""
    design = Path(design).resolve()
    files, cfg = _sources(design, root)
    texts = {str(p.relative_to(root)) if p.is_relative_to(root) else str(p): _strip_comments(p.read_text(errors="replace")) for p in files}
    spec_f = design / "spec.md"
    spec = spec_table(spec_f.read_text(errors="replace")) if spec_f.is_file() else {"design_id": None, "named_literals": []}
    findings: list[dict[str, Any]] = []
    notes: list[str] = []
    table: dict[str, Any] = {"schema": "fda-derived-constants/1", "design": design.name, "spec": spec, "design_id_bindings": [],
                             "clock": None, "notes": notes}

    did = spec["design_id"]
    binds = design_id_bindings(texts, cfg.get("generics"))
    table["design_id_bindings"] = binds
    if not spec_f.is_file():
        notes.append("no spec.md: no spec constant derived")
    elif did is None:
        notes.append("the spec has no quoted design ID: no design-ID check")
    elif not binds:
        notes.append("a design ID is quoted in the spec but no fpga_shell instance binds DESIGN_ID: not checked")
    else:
        for b in binds:
            if b["value"] is None:
                findings.append({"code": "CONST-ID-02", "severity": "warning", "blocking": False, "where": b["file"],
                                 "message": f"DESIGN_ID is bound to `{b['expr']}`, which does not resolve to a literal in the build's "
                                            f"sources; the spec's design ID {did['string']!r} is 0x{did['value']:08X}"})
            elif b["value"] != did["value"]:
                alt = next((l for l in spec["named_literals"] if l["value"] == b["value"]), None)
                why = (f"; 0x{b['value']:08X} is the spec's own {alt['context']!r} word, a different constant" if alt else "")
                findings.append({"code": "CONST-ID-01", "severity": "error", "blocking": True, "where": b["file"],
                                 "message": f"DESIGN_ID is 0x{b['value']:08X} ({b['how']}) but the spec's design ID "
                                            f"{did['string']!r} is 0x{did['value']:08X} ({did['rule']}){why}"})

    all_lits = {parse_literal(m.group(0)) for t in texts.values() for m in re.finditer(r"\d*'[sS]?[hH][0-9a-fA-F_]+", t)}
    for lit in spec["named_literals"]:
        if lit["value"] not in all_lits:
            findings.append({"code": "CONST-LIT-01", "severity": "warning", "blocking": False, "where": "spec.md",
                             "message": f"the spec gives {lit['text']} ({lit['context']!r}) but no 32-bit literal with that value is in the sources"})

    clk = board_clock(cfg, root)
    if clk is None:
        notes.append("no board clock in the board file: no clock-period check")
    else:
        table["clock"] = clk
        for pat in cfg.get("constraints") or []:
            for x in sorted(root.glob(pat)):
                if x.suffix != ".xdc":
                    continue
                for per in xdc_clock_periods(x.read_text(errors="replace"), clk["port"]):
                    if abs(per - clk["period_ns"]) > max(0.01, 1e-4 * clk["period_ns"]):
                        findings.append({"code": "CONST-CLK-01", "severity": "error", "blocking": True,
                                         "where": str(x.relative_to(root)),
                                         "message": f"create_clock -period {per} ns on {clk['port']} but the board file "
                                                    f"({clk['board']}) says {clk['freq_mhz']:g} MHz = {clk['period_ns']:.3f} ns"})
    table["findings"] = findings
    return table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("design")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    t = derive(Path(a.design))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(t, indent=1) + "\n")
    for f in t["findings"]:
        print(f"{f['code']} {'BLOCK' if f['blocking'] else 'advice'} {f['where']}: {f['message']}")
    for n in t["notes"]:
        print(f"note: {n}")
    return 1 if any(f["blocking"] for f in t["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
