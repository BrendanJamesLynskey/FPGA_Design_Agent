#!/usr/bin/env python3
"""Leak guard for the site: fail if any 80-byte window of private held-out material is in site/.

    python3 site/leak_guard.py [PATH ...] --private <FPGA_Design_Agent_Knowledge>/benchmark_private [--private-v2 DIR]
                               [--public DIR ...] [--public-ids SPLIT.yaml|TASKDIR ...]

Secrets: every text file under <private>/tasks and <private>/course/tasks (specs, hidden tests, models, reference RTL),
plus the names of the held-out tasks. A target file leaks if it holds an 80-byte window of a secret (raw or with white
space collapsed), unless that window also occurs in --public text (idioms, shared library code that is public anyway).
Also fails if a held-out task name appears. Prints counts and file names, never the matched text. Default PATH: site/.
Exit 1 on any hit.

Matching is comment- and string-insensitive for code and `#`-comment files (benchmark/tools/leak_norm.py): windows are
taken from raw text and from text with comments and string literals removed, so a unique comment on every line clears
nothing. Renamed identifiers are caught by benchmark/tools/task_leak.py (winnowing); cosmetic changes are never a way to
clear a hit.

Two exemptions, both counted in the summary (brief 09b S2):
- a window hit is cleared when the same text, compared on letters and digits only, is in the --public text (public spec
  text re-quoted in JSON differs from the YAML only in punctuation);
- --public-ids: held-out ids listed in these public split files, and the task ids of any public task folder given
  here (a v2 task drawn to development is public: its folder is in benchmark/v2/tasks), may appear (the problem index lists them by id and
  tier). Names from --private-v2 (benchmark v2 held-out tasks) are never exempt.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmark" / "tools"))
import leak_norm  # noqa: E402  (comment/string stripping, brief 83)

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


def stripped(f, b):
    """The file with comments and string literals removed (code and `#`-comment files), whitespace collapsed; b'' for
    other files. A window match on this text is not beaten by a trailing comment on every line (brief 83)."""
    if leak_norm.eff_suffix(f.name) not in leak_norm.CODE | leak_norm.HASH:
        return b""
    try:
        return (leak_norm.strip_text(b.decode("utf-8", errors="replace"), leak_norm.eff_suffix(f.name))
                + " " + leak_norm.hidden_text(b.decode("utf-8", errors="replace"), leak_norm.eff_suffix(f.name))).lower().encode()
    except Exception:
        return b""


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
    dir_ids = set()
    for f in a.public_ids:
        if Path(f).is_dir():  # a public task folder (e.g. benchmark/v2/tasks): its task ids are public by being there
            dir_ids |= {d.name for d in Path(f).iterdir() if d.is_dir() and not d.name.startswith("__")}
            continue
        for blk in re.findall(r"held_out:\n((?:\s+- \S+\n)+)", Path(f).read_text()):
            pub_ids |= set(re.findall(r"- (\S+)", blk))
    pub_ids = (pub_ids - v2names) | dir_ids
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
            secret |= windows(norm(b)) | windows(stripped(f, b))
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
            public |= windows(norm(b)) | windows(stripped(f, b))
            pub_text.append(alnum(b))
    secret -= public
    pub_text = b"\x00".join(pub_text)
    paths = a.paths or [str(Path(__file__).resolve().parent)]
    hits, scanned, cleared, listed = 0, 0, 0, 0
    for p in paths:
        for f in files(p):
            if f.suffix in (".jpg", ".png", ".pyc") or f.name == "leak_guard.py":
                continue
            raw = f.read_bytes()
            b = norm(raw)
            scanned += 1
            bad = [i for i in range(0, max(0, len(b) - W + 1)) if hash(b[i:i + W]) in secret]
            sb = stripped(f, raw)           # comment-insensitive pass: the same windows, on stripped text
            bad += [i for i in range(0, max(0, len(sb) - W + 1)) if hash(sb[i:i + W]) in secret]
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
