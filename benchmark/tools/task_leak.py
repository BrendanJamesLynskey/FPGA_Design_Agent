#!/usr/bin/env python3
"""Pre-freeze and pre-publication leak guard between tasks (brief 83), comment- and rename-insensitive.

    task_leak.py --secret ROOT_OR_TASK... --target ROOT_OR_TASK... [--public DIR...] [--k 12 --w 4] [--frac F] [--windows N]
    task_leak.py --pairwise ROOT_OR_TASK...      every task in turn is the secret, every other one a target
    task_leak.py --baseline ROOT_OR_TASK...      print the score distribution of the pairs (to justify the threshold)

A ROOT holds task folders (a folder with spec.md is a task). Every text file of a task is compared, visible or hidden.
Two checks per (secret task, target task) pair, each on text with comments and string literals removed
(`leak_norm.py`):

  1. windows: 80-byte windows of the stripped, whitespace-collapsed text of a secret file found in the target's
     stripped text; windows that also occur in --public text (shared idioms and library code) do not count.
  2. winnowing: identifiers and numbers normalised, k-token grams, one fingerprint per window of w grams.
     Code and prose (specs, YAML values) are scored apart. Fingerprints found in --public text do not count.
     score = shared / fingerprints of the secret (how much of the secret is in the target); the other direction
     (how much of the target is the secret's) is scored too; the larger of the two is compared with --frac.

A pair fails when the window count is above --windows or a winnowing score reaches --frac (defaults justified in
benchmark/README.md, "Leak guard"). Prints counts and file names only, never matched text. Exit 1 on any hit.
Cosmetic changes (comments, renames, indentation, number radix) are not a way to clear a hit: rework the structure.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leak_norm as N  # noqa: E402

W = 80
K, WIN = 12, 4
FRAC, WINDOWS = 0.30, 100
IDIOM_DF = 3                     # in this many tasks of the corpus: stock scaffolding, not task-identifying
MIN_FP = 5                       # fewer fingerprints than this in the smaller side: the score is not meaningful


def files(p: Path):
    for f in sorted(p.rglob("*")):
        if f.is_file() and not ({"__pycache__", ".git", "build", "runs"} & set(f.parts)) and f.suffix.lower() in N.SCANNED:
            yield f


def tasks(paths: list[Path]) -> dict[str, Path]:
    out = {}
    for p in paths:
        if (p / "spec.md").exists():
            out[p.name] = p
        else:
            out.update({d.name: d for d in sorted(p.iterdir()) if d.is_dir() and (d / "spec.md").exists()})
    return out


class Prof:
    """What one task (or the public text) reduces to."""

    def __init__(self, root: Path | None, k: int, w: int, many: list[Path] | None = None):
        self.windows: dict[int, str] = {}
        self.fp = {"code": set(), "prose": set()}
        self.byfile: dict[str, dict[str, set[int]]] = {}
        srcs = [(root, f) for f in files(root)] if root else [(m, f) for m in many for f in (files(m) if m.is_dir() else [m])]
        for base, f in srcs:
            try:
                text = f.read_text(errors="strict")
            except (UnicodeDecodeError, OSError):
                continue
            s = N.strip_text(text, f.suffix).encode()
            rel = str(f.relative_to(base)) if base and base.is_dir() else f.name
            for i in range(0, max(0, len(s) - W + 1)):
                self.windows.setdefault(hash(s[i:i + W]), rel)
            mode, toks = N.tokens_for(text, f.suffix)
            fp = N.fingerprints(toks, k, w)
            self.fp[mode] |= fp
            self.byfile[rel] = {mode: fp}


def compare(sec: Prof, tgt: Prof, pub: Prof, secret_name: str, target_name: str, idiom_w=frozenset(), idiom_f=frozenset()) -> dict:
    wins = [h for h in sec.windows if h in tgt.windows and h not in pub.windows and h not in idiom_w]
    files_hit = sorted({sec.windows[h] for h in wins})
    r = {"secret": secret_name, "target": target_name, "windows": len(wins), "files": files_hit[:5], "scores": {}}
    for mode in ("code", "prose"):
        a, b = sec.fp[mode] - pub.fp[mode] - idiom_f, tgt.fp[mode] - pub.fp[mode] - idiom_f
        sh = a & b
        if min(len(a), len(b)) < MIN_FP:
            r["scores"][mode] = {"secret_in_target": 0.0, "target_in_secret": 0.0, "shared": len(sh), "small": True}
            continue
        r["scores"][mode] = {"secret_in_target": round(len(sh) / len(a), 3), "target_in_secret": round(len(sh) / len(b), 3),
                             "shared": len(sh), "small": False}
    # per file: a copied file or snippet is diluted by the rest of its task in the task-level score
    best = (0.0, "")
    for side, other, tag in ((sec, tgt, "secret"), (tgt, sec, "target")):
        for rel, d in side.byfile.items():
            for mode, fp in d.items():
                fp = fp - pub.fp[mode] - idiom_f
                if len(fp) < MIN_FP:
                    continue
                c = len(fp & other.fp[mode]) / len(fp)
                if c > best[0]:
                    best = (round(c, 3), f"{tag}:{rel}")
    r["file_max"], r["file_max_where"] = best
    return r


def score(r: dict) -> float:
    return max([r.get("file_max", 0.0)] + [max(s["secret_in_target"], s["target_in_secret"]) for s in r["scores"].values()])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secret", nargs="*", type=Path, default=[])
    ap.add_argument("--target", nargs="*", type=Path, default=[])
    ap.add_argument("--pairwise", nargs="*", type=Path, default=[])
    ap.add_argument("--baseline", nargs="*", type=Path, default=[])
    ap.add_argument("--public", nargs="*", type=Path, default=[])
    ap.add_argument("--corpus", nargs="*", type=Path, default=[], help="more task roots, only to count how common a fingerprint is")
    ap.add_argument("--idiom-df", type=int, default=IDIOM_DF, help="a window or fingerprint in this many tasks is a stock idiom")
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--w", type=int, default=WIN)
    ap.add_argument("--frac", type=float, default=FRAC)
    ap.add_argument("--windows", type=int, default=WINDOWS)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    pub = Prof(None, a.k, a.w, many=a.public) if a.public else Prof(None, a.k, a.w, many=[])
    if a.pairwise or a.baseline:
        ts = tasks(a.pairwise or a.baseline)
        if len(ts) < 2:
            raise SystemExit("task_leak: fewer than two tasks found")
        prof = {n: Prof(p, a.k, a.w) for n, p in ts.items()}
        pairs = [(s, t) for s in ts for t in ts if s != t]
    else:
        S, T = tasks(a.secret), tasks(a.target)
        if not S or not T:
            raise SystemExit("task_leak: no secret or no target tasks found (a task folder holds spec.md)")
        prof = {("S:" + n): Prof(p, a.k, a.w) for n, p in S.items()} | {("T:" + n): Prof(p, a.k, a.w) for n, p in T.items()}
        pairs = [("S:" + s, "T:" + t) for s in S for t in T if s != t]
    here = {n.split(":")[-1] for n in prof}          # a corpus copy of a task under test would count it twice
    corpus = [Prof(p, a.k, a.w) for n, p in tasks(a.corpus).items() if n not in here] if a.corpus else []
    allp = list(prof.values()) + corpus
    dfw, dff = Counter(), Counter()
    for pr in allp:
        dfw.update(pr.windows.keys())
        dff.update(pr.fp["code"] | pr.fp["prose"])
    idiom_w = frozenset(h for h, n in dfw.items() if n >= a.idiom_df)
    idiom_f = frozenset(h for h, n in dff.items() if n >= a.idiom_df)
    res = [compare(prof[s], prof[t], pub, s, t, idiom_w, idiom_f) for s, t in pairs]
    if a.baseline:
        sc = sorted(score(r) for r in res)
        wn = sorted(r["windows"] for r in res)
        q = lambda v, p: v[min(len(v) - 1, int(p * len(v)))]  # noqa: E731
        print(f"baseline: {len(ts)} tasks, {len(res)} ordered pairs; winnowing score median {q(sc, .5)}, p95 {q(sc, .95)}, "
              f"p99 {q(sc, .99)}, max {sc[-1]}; windows median {q(wn, .5)}, max {wn[-1]}")
        for r in sorted(res, key=lambda r: -score(r))[:8]:
            print(f"  {score(r):.3f} windows {r['windows']}  {r['secret']} ~ {r['target']}")
    bad = [r for r in res if r["windows"] > a.windows or score(r) >= a.frac]
    if a.json:
        a.json.write_text(json.dumps({"k": a.k, "w": a.w, "frac": a.frac, "windows": a.windows, "pairs": res}, indent=1) + "\n")
    print(f"task leak: {len(res)} pairs, {len(bad)} hits (frac {a.frac}, windows {a.windows}, k {a.k}, w {a.w}): "
          f"{'PASS' if not bad else 'FAIL'}")
    for r in bad:
        print(f"  {r['secret']} -> {r['target']}: score {score(r):.3f} (worst file {r['file_max_where']}), windows {r['windows']} {r['files']}, "
              + ", ".join(f"{m} {s['shared']} shared" for m, s in r["scores"].items()))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
