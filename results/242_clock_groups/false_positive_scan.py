"""Brief 242: the clock-group plan on every committed design that has a build.yaml. Two readings:
(1) as committed: a design with no clock_relations and no clock_muxes gets no group, so nothing that closes today changes;
(2) as a stress: every pair of clock domains with a declared crossing in architecture.yaml is treated as `async`, to see where the refusal
    would fire (an unsynchronised or undeclared crossing). Usage: python false_positive_scan.py <out.json>"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import known_constraints as KC  # noqa: E402

_ARCH = KC._arch
rows = []
for b in sorted((ROOT / "designs").glob("**/build.yaml")):
    d = b.parent
    if "/build/" in str(d) or "/lat_" in str(d):
        continue
    try:
        ctx = KC.Ctx(d, ROOT)
        if not ctx.ports:
            continue
        xdc = KC.constraint_text(d, ctx.cfg, ROOT)
        committed = KC.clock_group_plan(ctx, xdc)
        arch = _ARCH(ctx)
        pairs = sorted({tuple(sorted((str(x["from"]), str(x["to"])))) for x in arch.get("crossings") or []
                        if isinstance(x, dict) and x.get("from") != "async" and x.get("to") != "async" and x.get("from") != x.get("to")})
        KC._arch = lambda c, a={**arch, "clock_relations": [{"between": list(p), "kind": "async"} for p in pairs]}: a   # stress reading
        stress = KC.clock_group_plan(ctx, xdc)
        KC._arch = _ARCH
        rows.append({"design": str(d.relative_to(ROOT)), "committed": {k: len(v) for k, v in committed.items()},
                     "stress_pairs": len(pairs), "stress_written": len(stress["written"]),
                     "stress_refused": [{"between": r["between"], "why": r["why"][:240]} for r in stress["refused"]]})
    except Exception as e:                    # noqa: BLE001
        rows.append({"design": str(d.relative_to(ROOT)), "error": f"{type(e).__name__}: {e}"[:200]})
Path(sys.argv[1]).write_text(json.dumps(rows, indent=1) + "\n")
ch = [r for r in rows if "committed" in r and (r["committed"]["written"] or r["committed"]["refused"])]
print(len(rows), "designs read;", len(ch), "change as committed;", sum(1 for r in rows if "error" in r), "errors")
for r in rows:
    if r.get("stress_pairs") or "error" in r:
        print(r["design"], r.get("stress_pairs"), r.get("stress_written"), r.get("stress_refused") or r.get("error"))
