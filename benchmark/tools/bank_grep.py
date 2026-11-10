#!/usr/bin/env python3
"""The knowledge bank must not contain any benchmark spec's distinctive phrases (brief 06a, independence).

    bank_grep.py [--bank DIR] [--json OUT] TASK_ROOT...

Every task under the given roots lists 3-5 verbatim phrases of its spec.md in hidden/bench.yaml (`phrases`). Each
phrase is searched, case-insensitive and whitespace-normalised, in every text file of the bank (default: the private
FPGA_Design_Agent_Knowledge checkout next to this repo), skipping .git and benchmark_private/ (where the held-out
material itself lives, outside every pack unit and the search library). Exit 1 on any hit.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK = ROOT.parent / "FPGA_Design_Agent_Knowledge"
SKIP = {".git", "benchmark_private", "__pycache__"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def bank_text(bank: Path) -> list[tuple[str, str]]:
    out = []
    for p in sorted(bank.rglob("*")):
        if not p.is_file() or SKIP & set(p.relative_to(bank).parts):
            continue
        if p.suffix.lower() in (".pdf", ".png", ".jpg", ".gz", ".zip", ".sqlite", ".pkl", ".npy", ".bin"):
            continue
        try:
            out.append((str(p.relative_to(bank)), norm(p.read_text(errors="strict"))))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="+", type=Path)
    ap.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    files = bank_text(a.bank)
    if not files:                           # a wrong --bank path would otherwise report "0 hits: PASS"
        raise SystemExit(f"bank grep: no text files under {a.bank}")
    tasks, hits = 0, []
    for root in a.roots:
        for b in sorted(root.glob("*/hidden/bench.yaml")):
            tasks += 1
            phrases = yaml.safe_load(b.read_text()).get("phrases") or []
            if len(phrases) < 3:            # the contract in the docstring is 3-5 phrases per task
                hits.append({"task": b.parent.parent.name, "phrase": f"(only {len(phrases)} phrases listed)", "file": str(b)})
            for ph in phrases:
                n = norm(ph)
                for f, text in files:
                    if n in text:
                        hits.append({"task": b.parent.parent.name, "phrase": ph, "file": f})
    r = {"bank": str(a.bank), "files_searched": len(files), "tasks": tasks, "hits": hits, "pass": not hits}
    if a.json:
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    print(f"bank grep: {tasks} tasks, {len(files)} bank files, {len(hits)} hits: {'PASS' if not hits else 'FAIL'}")
    for h in hits:
        print(f"  {h['task']}: {h['phrase']!r} in {h['file']}")
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
