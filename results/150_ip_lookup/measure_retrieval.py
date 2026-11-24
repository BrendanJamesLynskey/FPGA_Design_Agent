#!/usr/bin/env python3
"""Brief 150 retrieval probe: recall@3 on the positives, decoy precision on the decoys, for flow.ipvariants.search (the
existing command), a stop-word-stripped version of it, and flow.iplookup (the new ranker). Plain Python, no model.

    python3 results/150_ip_lookup/measure_retrieval.py [--split dev|test|all] [--json out.json]
"""
import argparse, json, re, sys
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from flow import ipvariants as iv, iplookup as il


def old_search(q):          # exactly as shipped: every word must be a whole word of the entry's text
    return [r["block"] for r in iv.search(q)]


def old_search_trimmed(q):  # the same, with stop words removed first (the fairest use a person would make of it)
    words = [w for w in re.findall(r"\w+", q.lower()) if w not in il.STOP]
    return [r["block"] for r in iv.search(" ".join(words))]


def new(q):
    r = il.lookup(q, k=3)
    return [h["block"] for h in r["hits"]]


def run(split):
    d = yaml.safe_load((HERE / "labelled_queries.yaml").read_text())
    pos = [p for p in d["positives"] if split in ("all", p["split"])]
    dec = [p for p in d["decoys"] if split in ("all", p["split"])]
    out = {"split": split, "n_positive": len(pos), "n_decoy": len(dec), "systems": {}}
    def new_noalias(q):
        il.USE_ALIASES = False
        try:
            return new(q)
        finally:
            il.USE_ALIASES = True
    for name, fn in (("ipvariants_search", old_search), ("ipvariants_search_stopwords_removed", old_search_trimmed),
                     ("iplookup", new), ("iplookup_aliases_off", new_noalias)):
        hit = [(p["id"], p["query"], fn(p["query"])[:3], p["accept"]) for p in pos]
        ok = [h for h in hit if set(h[2]) & set(h[3])]
        top1 = [h for h in hit if h[2] and h[2][0] in h[3]]
        dh = [(p["id"], p["query"], fn(p["query"])[:3]) for p in dec]
        clean = [x for x in dh if not x[2]]
        out["systems"][name] = {"recall_at_3": f"{len(ok)}/{len(pos)}", "recall_at_3_value": round(len(ok) / len(pos), 3),
                                "top1": f"{len(top1)}/{len(pos)}", "decoy_precision": f"{len(clean)}/{len(dec)}",
                                "decoy_precision_value": round(len(clean) / len(dec), 3),
                                "misses": [{"id": h[0], "query": h[1], "got": h[2], "accept": h[3]} for h in hit if h not in ok],
                                "false_positives": [{"id": x[0], "query": x[1], "got": x[2]} for x in dh if x[2]]}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["dev", "test", "all"])
    ap.add_argument("--json")
    a = ap.parse_args()
    r = run(a.split)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1) + "\n")
    for n, s in r["systems"].items():
        print(f"{r['split']:5} {n:38} recall@3 {s['recall_at_3']:>6}  top1 {s['top1']:>6}  decoys clean {s['decoy_precision']}")
        for m in s["misses"] if n.startswith("iplookup") else []:
            print("   [%s] miss" % n[-3:], m["id"], m["got"], "want", m["accept"])
        for m in s["false_positives"] if n.startswith("iplookup") else []:
            print("   [%s] false positive" % n[-3:], m["id"], m["got"])
