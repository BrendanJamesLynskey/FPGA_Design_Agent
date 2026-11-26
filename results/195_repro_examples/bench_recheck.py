"""Re-score every stored reference RTL with the task's hidden bench and compare with the record (no model, no Vivado): writes bench_recheck.json.

    python results/195_repro_examples/bench_recheck.py            # from the repository root
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.repro import tools as T  # noqa: E402

D = Path(__file__).resolve().parent
out = []
for ex in sorted(p for p in D.iterdir() if p.is_dir()):
    for f in sorted(q for q in ex.glob("ref_*.json") if re.fullmatch(r"ref_\d+\.json", q.name)):
        n = int(f.stem.split("_")[1])
        r = T.bench_check(ex.name, n)
        out.append({"example": ex.name, "ref": n, "same_rtl": r.get("same_rtl"), "verdicts_match": not r.get("differences") and bool(r.get("tests_now")), "tests": len(r.get("tests_now") or {}), "differences": r.get("differences")})
        print(out[-1])
(D / "bench_recheck.json").write_text(json.dumps(out, indent=1) + "\n")
print(f"{sum(1 for x in out if x['same_rtl'] and x['verdicts_match'])}/{len(out)} references: same RTL hash and every bench verdict equal to the record")
