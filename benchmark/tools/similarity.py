#!/usr/bin/env python3
"""Two similarity measures, no language model anywhere.

    similarity.py specs [--threshold 0.45] [--json OUT] DIR_A... -- DIR_B...
        TF-IDF cosine (word unigrams + bigrams, lower-cased, numbers kept) between every spec.md under the A dirs
        and every spec.md under the B dirs. Fails (exit 1) if any pair reaches the threshold. Used for the training
        pool against the benchmark and the contamination probe.

    similarity.py code <rtl_dir> [--ref DIR] [--k 25] [--w 8] [--json OUT]
        MOSS-style winnowing (Schleimer et al., SIGMOD 2003): the RTL is tokenised (comments dropped, identifiers
        and numbers normalised to I and N, keywords kept), hashed in k-token grams, and a fingerprint is chosen per
        window of w grams. Score = share of the RTL's fingerprints found in the reference corpus (default: the local
        clone of the textbook repositories, kept outside every repo at _amd_docs/books/repo/). Only scores are
        recorded; no reference code is copied anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_REF = Path(__file__).resolve().parents[3] / "_amd_docs" / "books" / "repo"
SV_KEYWORDS = set("""module endmodule input output inout logic wire reg always always_ff always_comb always_latch
assign begin end if else case casez casex endcase default for while posedge negedge or and not parameter localparam
int integer genvar generate endgenerate function endfunction task endtask return typedef enum struct packed
signed unsigned initial forever repeat unique priority import package endpackage bit byte""".split())


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def tfidf(docs: dict[str, str]) -> dict[str, dict[str, float]]:
    grams = {}
    for k, t in docs.items():
        w = words(t)
        grams[k] = Counter(w + [a + " " + b for a, b in zip(w, w[1:])])
    df = Counter(g for c in grams.values() for g in c)
    n = len(docs)
    vec = {}
    for k, c in grams.items():
        v = {g: (1 + math.log(f)) * math.log((1 + n) / (1 + df[g])) for g, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vec[k] = {g: x / norm for g, x in v.items()}
    return vec


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


def spec_files(dirs: list[Path]) -> dict[str, str]:
    out = {}
    for d in dirs:
        for p in sorted(d.rglob("spec.md")):
            out[str(p.parent.name)] = p.read_text()
    return out


def cmd_specs(a_dirs: list[Path], b_dirs: list[Path], threshold: float) -> dict:
    A, B = spec_files(a_dirs), spec_files(b_dirs)
    vec = tfidf({**{"A:" + k: v for k, v in A.items()}, **{"B:" + k: v for k, v in B.items()}})
    pairs = []
    for a in A:
        best = max(((cosine(vec["A:" + a], vec["B:" + b]), b) for b in B), default=(0.0, None))
        pairs.append({"a": a, "nearest": best[1], "cosine": round(best[0], 4)})
    pairs.sort(key=lambda r: -r["cosine"])
    return {"threshold": threshold, "n_a": len(A), "n_b": len(B), "max": pairs[0]["cosine"] if pairs else 0.0,
            "pass": all(r["cosine"] < threshold for r in pairs), "pairs": pairs}


def tokens(text: str) -> list[str]:
    text = re.sub(r"//[^\n]*|/\*.*?\*/|--[^\n]*", " ", text, flags=re.S)
    out = []
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_$]*|\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\d+|\S", text):
        if t in SV_KEYWORDS:
            out.append(t)
        elif re.match(r"[A-Za-z_]", t):
            out.append("I")
        elif re.match(r"\d", t):
            out.append("N")
        else:
            out.append(t)
    return out


def fingerprints(toks: list[str], k: int, w: int) -> set[int]:
    hs = [int.from_bytes(hashlib.blake2b(" ".join(toks[i:i + k]).encode(), digest_size=8).digest(), "big")
          for i in range(max(0, len(toks) - k + 1))]
    fp = set()
    for i in range(max(0, len(hs) - w + 1)):
        fp.add(min(hs[i:i + w]))
    if hs and len(hs) < w:
        fp.add(min(hs))
    return fp


def corpus(ref: Path, k: int, w: int) -> set[int]:
    fp: set[int] = set()
    for p in ref.rglob("*"):
        if p.suffix in (".sv", ".v", ".svh", ".vh") and p.is_file():
            fp |= fingerprints(tokens(p.read_text(errors="replace")), k, w)
    return fp


def cmd_code(rtl: Path, ref: Path, k: int, w: int, ref_fp: set[int] | None = None) -> dict:
    ref_fp = ref_fp if ref_fp is not None else corpus(ref, k, w)
    files = [p for p in sorted(rtl.rglob("*")) if p.suffix in (".sv", ".v")]
    fp = set().union(*[fingerprints(tokens(p.read_text(errors="replace")), k, w) for p in files]) if files else set()
    shared = fp & ref_fp
    return {"rtl": str(rtl), "k": k, "w": w, "fingerprints": len(fp), "shared": len(shared),
            "score": round(len(shared) / len(fp), 4) if fp else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("specs")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--threshold", type=float, default=0.45)
    s.add_argument("--json", type=Path)
    c = sub.add_parser("code")
    c.add_argument("rtl", type=Path, nargs="+")
    c.add_argument("--ref", type=Path, default=DEFAULT_REF)
    c.add_argument("--k", type=int, default=25)
    c.add_argument("--w", type=int, default=8)
    c.add_argument("--json", type=Path)
    a = ap.parse_args()
    if a.cmd == "specs":
        if "--" not in sys.argv:
            raise SystemExit("usage: similarity.py specs A_DIR... -- B_DIR...")
        raw = sys.argv[sys.argv.index("specs") + 1:]
        raw = [x for x in raw if not x.startswith("--threshold") and not x.startswith("--json")]
        cut = raw.index("--")
        A = [Path(x) for x in raw[:cut] if Path(x).exists()]
        B = [Path(x) for x in raw[cut + 1:] if Path(x).exists()]
        r = cmd_specs(A, B, a.threshold)
        print(f"specs: {r['n_a']} against {r['n_b']}: max cosine {r['max']} (threshold {r['threshold']}): "
              f"{'PASS' if r['pass'] else 'FAIL'}")
        for p in r["pairs"][:5]:
            print(f"  {p['cosine']:.3f}  {p['a']} ~ {p['nearest']}")
    else:
        ref_fp = corpus(a.ref, a.k, a.w)
        if not ref_fp:                      # a missing or empty corpus would score every design 0.0000 and exit 0
            raise SystemExit(f"similarity: no reference fingerprints under {a.ref} (is the textbook clone there?)")
        r = {"ref": str(a.ref), "ref_fingerprints": len(ref_fp),
             "results": [cmd_code(d, a.ref, a.k, a.w, ref_fp) for d in a.rtl]}
        for x in r["results"]:
            print(f"  {x['score']:.4f}  ({x['shared']}/{x['fingerprints']})  {x['rtl']}")
        r["pass"] = True
    if a.json:
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
