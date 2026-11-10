#!/usr/bin/env python3
"""Leak guard for the site: fail if any 80-byte window of private held-out material is in site/.

    python3 site/leak_guard.py [PATH ...] --private <FPGA_Design_Agent_Knowledge>/benchmark_private [--private-v2 DIR]
                               [--public DIR ...] [--public-ids SPLIT.yaml ...]

Secrets: every text file under <private>/tasks and <private>/course/tasks (specs, hidden tests, models, reference RTL),
plus the names of the held-out tasks. A target file leaks if it holds an 80-byte window of a secret (raw or with white
space collapsed), unless that window also occurs in --public text (idioms, shared library code that is public anyway).
Also fails if a held-out task name appears. Prints counts and file names, never the matched text. Default PATH: site/.
Exit 1 on any hit.

Two exemptions, both counted in the summary (brief 09b S2):
- a window hit is cleared when the same text, compared on letters and digits only, is in the --public text (public spec
  text re-quoted in JSON differs from the YAML only in punctuation);
- --public-ids: held-out ids listed in these public split files may appear (the problem index lists them by id and
  tier). Names from --private-v2 (benchmark v2 held-out tasks) are never exempt.
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


ALNUM = re.compile(rb"[^0-9A-Za-z]+")


def alnum(b):
    return ALNUM.sub(b"", b).lower()


def windows(b):
    return {hash(b[i:i + W]) for i in range(0, max(0, len(b) - W + 1))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--private-v2", default=None)
    ap.add_argument("--public", nargs="*", default=[])
    ap.add_argument("--public-ids", nargs="*", default=[])
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    priv = Path(a.private)
    roots = [priv / "tasks", priv / "course" / "tasks"]
    if a.private_v2:
        roots.append(Path(a.private_v2))
    names = sorted({d.name for r in roots if r.exists() for d in r.iterdir() if d.is_dir()})
    v2names = {d.name for d in Path(a.private_v2).iterdir() if d.is_dir()} if a.private_v2 and Path(a.private_v2).exists() else set()
    pub_ids = set()
    for f in a.public_ids:
        for blk in re.findall(r"held_out:\n((?:\s+- \S+\n)+)", Path(f).read_text()):
            pub_ids |= set(re.findall(r"- (\S+)", blk))
    pub_ids -= v2names
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
    public, pub_text = set(), []
    for p in a.public:
        for f in files(p):
            try:
                b = f.read_bytes()
            except OSError:
                continue
            if b"\0" in b[:2000]:
                continue
            public |= windows(norm(b))
            pub_text.append(alnum(b))
    secret -= public
    pub_text = b"\x00".join(pub_text)
    paths = a.paths or [str(Path(__file__).resolve().parent)]
    hits, scanned, cleared, listed = 0, 0, 0, 0
    for p in paths:
        for f in files(p):
            if f.suffix in (".jpg", ".png", ".pyc") or f.name == "leak_guard.py":
                continue
            b = norm(f.read_bytes())
            scanned += 1
            bad = [i for i in range(0, max(0, len(b) - W + 1)) if hash(b[i:i + W]) in secret]
            keep = [i for i in bad if alnum(b[i:i + W]) not in pub_text]
            cleared += len(bad) - len(keep)
            bad = keep
            if bad:
                hits += 1
                print(f"LEAK window in {f} (offset {bad[0]}, {len(bad)} windows)")
            low = b.lower()
            for n in names:
                if n.encode() in low and n in pub_ids:
                    listed += 1
                elif n.encode() in low:
                    hits += 1
                    print(f"LEAK held-out task name in {f}: name #{names.index(n)}")
    print(f"secret files {nfiles}, held-out task names {len(names)} ({len(v2names)} v2), target files scanned {scanned}, "
          f"public-listed id occurrences {listed}, windows cleared as public text {cleared}, hits {hits}")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
