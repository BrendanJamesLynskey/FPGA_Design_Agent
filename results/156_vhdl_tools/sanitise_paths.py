#!/usr/bin/env python3
"""Rewrite machine paths in the records so a results file carries none: the repo root becomes '' (paths relative to the repo) and the home
directory becomes '~'. Run once after the measurement scripts (records are text: .json, .xml, .lcov, .txt, .md)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = str(Path.home())
for p in sorted(Path(__file__).resolve().parent.rglob("*")):
    if p.is_file() and p.suffix in (".json", ".xml", ".lcov", ".txt", ".md"):
        t = p.read_text()
        n = t.replace(str(ROOT) + "/", "").replace(HOME + "/", "~/")
        if n != t:
            p.write_text(n)
            print("rewrote", p.relative_to(Path(__file__).resolve().parent), file=sys.stderr)
