#!/usr/bin/env python3
"""Leak guard for the site: fail if any 80-byte window of private held-out material is in site/.

    python3 site/leak_guard.py --private <FPGA_Design_Agent_Knowledge>/benchmark_private [--public DIR ...] [PATH ...]

Secrets: every text file under <private>/tasks and <private>/course/tasks (specs, hidden tests, models, reference RTL),
plus the names of the held-out tasks. A target file leaks if it holds an 80-byte window of a secret (raw or with white
space collapsed), unless that window also occurs in --public text (idioms, shared library code that is public anyway).
Also fails if a held-out task name appears. Prints counts and file names, never the matched text. Default PATH: site/.
Exit 1 on any hit.
"""
import argparse
import re
import sys
from pathlib import Path

W = 80
WS = re.compile(rb"\s+")


def norm(b):
    return WS.sub(b" ", b)


def files(p):
    p = Path(p)
    if p.is_file():
        yield p
    else:
        for f in sorted(p.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and ".git" not in f.parts:
                yield f


def windows(b):
    return {hash(b[i:i + W]) for i in range(0, max(0, len(b) - W + 1))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--public", nargs="*", default=[])
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    priv = Path(a.private)
    roots = [priv / "tasks", priv / "course" / "tasks"]
    names = sorted({d.name for r in roots if r.exists() for d in r.iterdir() if d.is_dir()})
    secret, nfiles = set(), 0
    for r in roots:
        if not r.exists():
            continue
        for f in files(r):
            try:
                b = f.read_bytes()
            except OSError:
                continue
            if b"\0" in b[:2000]:
                continue
            secret |= windows(norm(b))
            nfiles += 1
    public = set()
    for p in a.public:
        for f in files(p):
            try:
                b = f.read_bytes()
            except OSError:
                continue
            if b"\0" in b[:2000]:
                continue
            public |= windows(norm(b))
    secret -= public
    paths = a.paths or [str(Path(__file__).resolve().parent)]
    hits, scanned = 0, 0
    for p in paths:
        for f in files(p):
            if f.suffix in (".jpg", ".png", ".pyc") or f.name == "leak_guard.py":
                continue
            b = norm(f.read_bytes())
            scanned += 1
            bad = [i for i in range(0, max(0, len(b) - W + 1)) if hash(b[i:i + W]) in secret]
            if bad:
                hits += 1
                print(f"LEAK window in {f} (offset {bad[0]}, {len(bad)} windows)")
            low = b.lower()
            for n in names:
                if n.encode() in low:
                    hits += 1
                    print(f"LEAK held-out task name in {f}: name #{names.index(n)}")
    print(f"secret files {nfiles}, held-out task names {len(names)}, target files scanned {scanned}, hits {hits}")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
