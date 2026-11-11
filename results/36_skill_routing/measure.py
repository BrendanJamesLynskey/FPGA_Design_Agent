#!/usr/bin/env python3
"""Brief 36 retrieval and context measurement (PREREG.md sections 1 and 2), on the labelled development tasks.

    FDA_KNOWLEDGE=<bank> PYTHONPATH=<fastembed dir> python3 results/36_skill_routing/measure.py [--with-model]

Writes retrieval.json and retrieval.md next to this file. Deterministic except arm R2 (``--with-model``: one OpenRouter call
per task to the router's classifier; provider-reported cost recorded). Needs the private bank with its vectors and fastembed
for the vector arms (it says which mode each index ran in, and refuses to write a table whose hybrid arms fell back to BM25).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from agent.core import skill_index as SI  # noqa: E402
from agent.core import tools as T  # noqa: E402
from agent.core.bank import LocalBank  # noqa: E402
from agent.core.registry import dispatch  # noqa: E402
from agent.core.session import Session  # noqa: E402
from agent.graph import router  # noqa: E402

KS = (3, 6, 10)
MRR_DEPTH = 20


def metrics(ranked: list[str], needs: list[str]) -> dict:
    out = {f"recall@{k}": round(len(set(ranked[:k]) & set(needs)) / len(needs), 4) for k in KS}
    first = next((i + 1 for i, n in enumerate(ranked[:MRR_DEPTH]) if n in needs), None)
    out["rr"] = round(1.0 / first, 4) if first else 0.0
    out["first_hit"] = first
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-model", action="store_true", help="arm R2: one classifier call per task (OpenRouter)")
    ap.add_argument("--router-model", default="openai/gpt-6-luna")
    a = ap.parse_args()
    lab = yaml.safe_load((HERE / "labels.yaml").read_text())
    bank = LocalBank()
    vocab = router.section_vocab(bank.root)
    idx = SI.open_index(bank, lab["board"], None, part=lab["part"])
    if idx.mode != "hybrid":
        raise SystemExit(f"index mode is {idx.mode}: install fastembed and build the bank's vectors first")
    names = set(idx.by_name)
    missing = {t: [n for n in v["needs"] if n not in names] for t, v in lab["tasks"].items()}
    if any(missing.values()):
        raise SystemExit(f"labels name skills not in the catalogue: {missing}")
    client = None
    if a.with_model:
        from agent.graph.llm import OpenRouterClient
        client = OpenRouterClient(a.router_model)
    rows, cost = {}, 0.0
    for task, v in lab["tasks"].items():
        spec = (ROOT / v["spec"]).read_text()
        needs = v["needs"]
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / task
            d.mkdir()
            (d / "spec.md").write_text(spec)
            s = Session(design=d, root=Path(td), bank=bank, board=lab["board"], part=lab["part"])
            s.stage = "rtl-design-creation"
            secs = router.rule_sections(spec, None)[:4] or ["rtl-coding"]
            r0 = dispatch(s, "load_skill", {"sections": secs})
            t0 = [Path(p).parent.name for p in r0["skills"]]
            s.skill_routing = "router"
            r1 = dispatch(s, "load_skill", {"sections": secs})
            t1_cut = [Path(p).parent.name for p in r1["skills"]]
            every = T._bank_skills(s, secs, False)
            t1_all = [x["name"] for x in T._rank_rows(s, every, secs)]
            t1 = t1_cut + [n for n in t1_all if n not in t1_cut]
        def sl(version, extra=None, k=10):
            return [x["name"] for x in router.shortlist(idx, spec, 2, "rtl-design-creation", vocab, k=k,
                                                        extra_sections=extra, version=version)["skills"]]
        arms = {"T0": t0, "T1": t1, "R1": sl(1)}
        extra = None
        if client is not None:
            extra, reply = router.classify(client, spec, 2, "rtl-design-creation", vocab)
            cost += reply.cost or 0.0
            arms["R2"] = sl(1, extra)
            arms["_R2_sections"] = extra
        for mode, key in (("bm25", "I-bm25"), ("vector", "I-vec"), ("hybrid", "I-hybrid")):
            arms[key] = [x["name"] for x in idx.search(spec, k=MRR_DEPTH, mode=mode)]
        # post hoc (after the pre-registered arms were read; same 12 tasks, so biased in their favour)
        arms["R3*"] = sl(2, k=MRR_DEPTH)
        if extra is not None:
            arms["R4*"] = sl(2, extra, k=MRR_DEPTH)
        arms["I-hybrid-clean*"] = [x["name"] for x in idx.search(router.clean_spec(spec), k=MRR_DEPTH)]
        # context (characters): T0's six bodies against the router block plus the labelled shortlisted bodies
        t0_chars = len(r0["output"])
        t0_unclipped = sum(len(idx.by_name[n].text) + len(T.DATA_NOTE) + 1 for n in t0 if n in idx.by_name)
        block = router.shortlist_text(router.shortlist(idx, spec, 2, "rtl-design-creation", vocab, k=8))
        hit = [n for n in arms["R3*"][:8] if n in needs]
        new_chars = len(block) + sum(len(idx.by_name[n].text) + len(T.DATA_NOTE) + 1 for n in hit)
        rows[task] = {"needs": needs, "t0_sections": secs, "lists": arms,
                      "metrics": {k: metrics(v_, needs) for k, v_ in arms.items() if not k.startswith("_")},
                      "context_chars": {"T0_bodies": t0_chars, "T0_bodies_unclipped": t0_unclipped, "router_block": len(block),
                                        "router_block_plus_needed_bodies": new_chars, "needed_in_shortlist": hit}}
    arms_all = [k for k in next(iter(rows.values()))["metrics"]]
    summary = {k: {m: round(sum(r["metrics"][k][m] for r in rows.values()) / len(rows), 4)
                   for m in [f"recall@{x}" for x in KS] + ["rr"]} for k in arms_all}
    for k in summary:
        summary[k]["MRR"] = summary[k].pop("rr")
    out = {"bank_mode": idx.mode, "embed_model": SI.EMBED_MODEL, "stale_vectors": idx.stale, "catalogue": len(idx.entries),
           "router_model": a.router_model if client else None, "router_cost_usd": round(cost, 6) if client else None,
           "summary": summary, "tasks": rows}
    (HERE / "retrieval.json").write_text(json.dumps(out, indent=1) + "\n")
    md = ["# Brief 36 retrieval (written by measure.py)", "",
          f"12 labelled development tasks; catalogue {len(idx.entries)} skills (Nexys A7-100T, xc7a100tcsg324-1); index "
          f"{idx.mode} ({SI.EMBED_MODEL}); stale vectors: {len(idx.stale)}."
          + (f" R2 classifier {a.router_model}, provider-reported cost ${cost:.4f}." if client else ""), "",
          "Arms marked * were added after the pre-registered arms were read (post hoc, on the same 12 tasks).", "",
          "| Arm | recall@3 | recall@6 | recall@10 | MRR |", "|---|---|---|---|---|"]
    for k, v_ in summary.items():
        md.append(f"| {k} | {v_['recall@3']:.3f} | {v_['recall@6']:.3f} | {v_['recall@10']:.3f} | {v_['MRR']:.3f} |")
    md += ["", "Per task, recall@6 (and first labelled rank):", "",
           "| Task | " + " | ".join(arms_all) + " |", "|---|" + "---|" * len(arms_all)]
    for t, r in rows.items():
        md.append(f"| {t} | " + " | ".join(f"{r['metrics'][k]['recall@6']:.2f} ({r['metrics'][k]['first_hit'] or '-'})"
                                          for k in arms_all) + " |")
    md += ["", "Context per stage-2 role from the knowledge tools (characters):", "",
           "T0 is what one `load_skill(sections)` call returns after the registry's 20,000-character clip (MAX_OUTPUT);"
           " unclipped is the six bodies' full length. The router block is the v2 shortlist (k = 8); the last column adds"
           " the bodies of the labelled skills in it (what a role that loads only those would read).", "",
           "| Task | T0: one load_skill (clipped) | T0 unclipped | router block | block + labelled shortlisted bodies |",
           "|---|---|---|---|---|"]
    for t, r in rows.items():
        c = r["context_chars"]
        md.append(f"| {t} | {c['T0_bodies']} | {c['T0_bodies_unclipped']} | {c['router_block']} | "
                  f"{c['router_block_plus_needed_bodies']} |")
    keys = ("T0_bodies", "T0_bodies_unclipped", "router_block", "router_block_plus_needed_bodies")
    tot = {k: sum(r["context_chars"][k] for r in rows.values()) // len(rows) for k in keys}
    md.append("| **mean** | " + " | ".join(str(tot[k]) for k in keys) + " |")
    (HERE / "retrieval.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:12 + len(summary)]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
