#!/usr/bin/env python3
"""Tail-percentile claim gate (brief 189 item 5; idea from Edwards 2026, ch 17). Advisory: ``enforced: false``.

Rule. A tail percentile is quoted only when at least 100 observations lie beyond it. Observations beyond the p-th percentile of N
samples number about N * (1 - p/100), so the p99 needs 10,000 samples, the p99.9 100,000 and the p99.99 one million. A figure that
states no sample count at all is flagged separately (the reader cannot tell). The maximum is not a percentile and is not checked.

What is scanned: Markdown and plain text (a mention of a percentile, with the sample count taken from the same table row under a
column named Reads, Samples, n and the like, else from the same line or the same paragraph), and JSON records (a dict holding both a
count ``n`` and keys such as ``p99``, ``p999``, ``p9999``). Board plans are text, so the same scan covers them; ``run_length`` turns
the rule into a run length for a plan (``required_samples`` at a message rate).

    python3 -m flow.claims_tail [PATH ...] [--json OUT] [--need PERCENTILE [--rate PER_SECOND]]

With no path the repository's README, docs, results and design docs are scanned. Exit status is 0 always: nothing here blocks."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MIN_BEYOND = 100
WAIVER = "tail-ok:"            # a line (or the one above it) holding "tail-ok: <reason>" is not flagged: the quantile is not a latency claim
MIN_PERCENTILE = 90.0          # below this the sample size needed is small enough that the rule is not worth a flag

COUNT_WORDS = r"(?:reads|read|samples|sample|observations|events|event|frames|frame|messages|message|packets|requests|measurements|orders|ticks|iterations|transactions|words)"
_NUM = r"(?<![\w.])(\d[\d,_]*(?:\.\d+)?)\s*(k|K|M|million|thousand)?"
RE_PCT_P = re.compile(r"(?<![A-Za-z0-9_.])p(\d{2})(\d{0,3})(?:\.(\d+))?(?![A-Za-z0-9_])")
RE_PCT_TH = re.compile(r"(?<![\d.])(\d{2}(?:\.\d+)?)\s*(?:st|nd|rd|th)?[\s-]*(?:percentile|%ile|pctl)", re.I)
RE_N_EQ = re.compile(r"(?<![A-Za-z])[nN]\s*=\s*" + _NUM)
RE_COUNT = re.compile(_NUM + r"\s*" + COUNT_WORDS + r"\b", re.I)
COUNT_HEADERS = {"n", "reads", "samples", "observations", "events", "frames", "messages", "count", "requests", "orders"}


def required_samples(pct: float) -> int:
    """Samples needed so that MIN_BEYOND observations lie beyond the pct-th percentile."""
    tail = round(1.0 - pct / 100.0, 9)
    return math.ceil(round(MIN_BEYOND / tail, 6))


def beyond(n: int, pct: float) -> float:
    return n * (1.0 - pct / 100.0)


def run_length(pct: float, rate_per_s: float) -> dict[str, float]:
    """Seconds a board run must last, at ``rate_per_s`` observations a second, to quote the pct-th percentile; add margin for spread."""
    n = required_samples(pct)
    return {"percentile": pct, "samples": n, "seconds": n / rate_per_s}


def _scale(num: str, unit: str | None) -> int:
    v = float(num.replace(",", "").replace("_", ""))
    return int(v * {"k": 1e3, "K": 1e3, "M": 1e6, "million": 1e6, "thousand": 1e3}.get(unit or "", 1))


def percentiles_in(text: str) -> list[float]:
    """Every percentile of at least MIN_PERCENTILE named in ``text`` (p99, p999, p99.9, 99.9th percentile)."""
    out: list[float] = []
    for m in RE_PCT_P.finditer(text):
        v = float(m.group(1) + ("." + (m.group(2) + (m.group(3) or "")) if (m.group(2) or m.group(3)) else ""))
        out.append(v)
    for m in RE_PCT_TH.finditer(text):
        out.append(float(m.group(1)))
    return sorted({v for v in out if MIN_PERCENTILE <= v < 100})


def counts_in(text: str) -> list[int]:
    out = []
    for m in RE_N_EQ.finditer(text):
        out.append(_scale(m.group(1), m.group(2)))
    for m in RE_COUNT.finditer(text):
        out.append(_scale(m.group(1), m.group(2)))
    return out


def _finding(path: str, line: int, pct: float, n: int | None, text: str) -> dict[str, Any]:
    need = required_samples(pct)
    if n is None:
        return {"code": "TAIL-N-02", "where": f"{path}:{line}", "percentile": pct, "samples": None, "required": need,
                "message": f"p{pct:g} quoted with no sample count; it needs at least {need:,} observations", "text": text.strip()[:160]}
    return {"code": "TAIL-N-01", "where": f"{path}:{line}", "percentile": pct, "samples": n, "required": need,
            "beyond": round(beyond(n, pct), 2),
            "message": f"p{pct:g} quoted from {n:,} observations: {beyond(n, pct):.1f} lie beyond it (need {MIN_BEYOND}, i.e. {need:,} observations)",
            "text": text.strip()[:160]}


def scan_text(text: str, path: str = "-") -> list[dict[str, Any]]:
    """Findings for one text. A table row takes its count from a count column (header row above it), else the line, else the paragraph."""
    lines = text.splitlines()
    findings: list[dict[str, Any]] = []
    header: list[str] | None = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if nxt.startswith("|") and set(nxt.replace("|", "")) <= set("-: "):
                header = [c.lower() for c in cells]                # this row is a header
                pcts = percentiles_in(line)
                if pcts and not any(h in COUNT_HEADERS for h in header):
                    pass
                continue
        else:
            header = None
        pcts = percentiles_in(line)
        hdr_pcts: list[float] = []
        if line.lstrip().startswith("|") and header:                # percentiles named in the header apply to the row's values
            hdr_pcts = percentiles_in(" ".join(header))
        pcts = sorted(set(pcts) | set(hdr_pcts))
        if not pcts:
            continue
        ns: list[int] = counts_in(line)
        if line.lstrip().startswith("|") and header:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            for h, c in zip(header, cells):
                if h in COUNT_HEADERS:
                    m = re.fullmatch(_NUM, c.replace(",", ""))
                    if m:
                        ns.append(_scale(m.group(1), m.group(2)))
        if not ns:                                                   # the paragraph around the line
            j0 = i
            while j0 > 0 and lines[j0 - 1].strip():
                j0 -= 1
            j1 = i
            while j1 + 1 < len(lines) and lines[j1 + 1].strip():
                j1 += 1
            ns = counts_in(" ".join(lines[j0:j1 + 1]))
        if WAIVER in line or WAIVER in " ".join(lines[max(0, i - 1):i + 1]):
            continue
        n = max(ns) if ns else None                                  # the largest stated count is the most generous reading
        for p in pcts:
            if n is None or beyond(n, p) < MIN_BEYOND:
                findings.append(_finding(path, i + 1, p, n, line))
    return findings


_KEY = re.compile(r"^p(\d{2})(\d{0,3})$")


def scan_json(obj: Any, path: str = "-", trail: str = "", inherited: int | None = None) -> list[dict[str, Any]]:
    """Findings in a JSON value: a dict with percentile keys (p99, p999, p9999) and a count ``n`` in the same dict, else the count of a
    sibling dict (a record that keeps clocks and nanoseconds side by side counts once), else the enclosing dict's."""
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        n = obj.get("n") if isinstance(obj.get("n"), int) else inherited
        for k, v in obj.items():
            m = _KEY.match(k) if isinstance(k, str) else None
            if m and isinstance(v, (int, float)):
                p = float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
                if p >= MIN_PERCENTILE and (n is None or beyond(n, p) < MIN_BEYOND):
                    out.append({**_finding(f"{path}", 0, p, n, f"{trail}.{k}"), "where": f"{path}:{trail}.{k}"})
        sib = next((v["n"] for v in obj.values() if isinstance(v, dict) and isinstance(v.get("n"), int)), n)
        for k, v in obj.items():
            out += scan_json(v, path, f"{trail}.{k}" if trail else str(k), sib)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += scan_json(v, path, f"{trail}[{i}]")
    return out


def scan_file(p: Path, root: Path = ROOT) -> list[dict[str, Any]]:
    try:
        rel = str(p.relative_to(root))
    except ValueError:
        rel = str(p)
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return []
    if p.suffix == ".json":
        try:
            return scan_json(json.loads(text), rel)
        except ValueError:
            return []
    return scan_text(text, rel)


def default_paths(root: Path = ROOT) -> list[Path]:
    pats = ["README.md", "docs/*.md", "results/**/*.md", "results/**/*.json", "designs/*/README.md", "designs/*/docs/*.md"]
    out: list[Path] = []
    for g in pats:
        out += sorted(root.glob(g))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json", dest="out")
    ap.add_argument("--need", type=float, help="print the samples needed to quote this percentile")
    ap.add_argument("--rate", type=float, help="observations per second, with --need: the run length")
    a = ap.parse_args(argv)
    if a.need is not None:
        print(json.dumps(run_length(a.need, a.rate) if a.rate else {"percentile": a.need, "samples": required_samples(a.need)}))
        return 0
    paths = [Path(p) for p in a.paths] or default_paths()
    findings: list[dict[str, Any]] = []
    for p in paths:
        findings += scan_file(p)
    rec = {"enforced": False, "rule": f"a tail percentile (>= p{MIN_PERCENTILE:g}) needs at least {MIN_BEYOND} observations beyond it",
           "files_scanned": len(paths), "findings": findings}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    for f in findings:
        print(f"{f['code']} {f['where']}: {f['message']}")
    print(f"{len(findings)} advisory finding(s) in {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
