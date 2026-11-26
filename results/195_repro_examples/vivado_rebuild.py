"""Rebuild stored reference RTL with Vivado (no cache, to post-route) and record what repeats: writes vivado_rebuilds.json. A heavy job: each rebuild takes a slot.

    python results/195_repro_examples/vivado_rebuild.py <example> <ref> same|other [<example> <ref> same|other ...]

`same` rebuilds at the relative path the design was built at (the build stamp is then the same); `other` at runs/_tools/ (another stamp): the difference is what the
path-dependent stamp does to a netlist.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.repro import tools as T  # noqa: E402

OUT = Path(__file__).resolve().parent / "vivado_rebuilds.json"
rows = json.loads(OUT.read_text()) if OUT.is_file() else []
a = sys.argv[1:]
for ex, n, how in zip(a[0::3], a[1::3], a[2::3]):
    for attempt in range(10):
        r = T.vivado_check(ex, int(n), slot=True, same_path=(how == "same"))
        if r.get("refused_or_failed") is None:
            break
        print(f"{ex} {n} {how}: {r['refused_or_failed']}; retry in 120 s", flush=True)
        time.sleep(120)
    rows.append({"example": ex, "ref": int(n), "path": r.get("path"), "same_path": r.get("same_path"), "date": time.strftime("%Y-%m-%d"), "ok": r.get("ok"), "now": r.get("now"), "record": r.get("record"),
                 "differences": r.get("differences"), "vivado_wall_s": r.get("vivado_wall_s"), "note": r.get("error") or r.get("refused_or_failed")})
    OUT.write_text(json.dumps(rows, indent=1) + "\n")
    print(rows[-1], flush=True)
