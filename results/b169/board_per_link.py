#!/usr/bin/env python3
"""Brief 169: per-link E, L and D (the register d_last) from two board records, to check board_inputs.json. usage: board_per_link.py <stage3.json> ..."""
import collections, json, statistics as st, sys
for p in sys.argv[1:]:
    sn = json.load(open(p))["restarts"]["snapshots"]
    rows = [(x["tx"]["e_min"], x["tx"]["l_min"], x["tx"]["d_last"]) for x in sn if x]
    byE = collections.defaultdict(list)
    for r in rows:
        byE[r[0]].append(r[2])
    print(p, "n", len(rows), "E mean", round(st.mean(r[0] for r in rows), 2), "L mean", round(st.mean(r[1] for r in rows), 2), "D mean", round(st.mean(r[2] for r in rows), 2),
          "D hist", sorted(collections.Counter(r[2] for r in rows).items()), "L-2E mean", round(st.mean(r[1] - 2 * r[0] for r in rows), 2), "D by E", {e: (len(v), round(st.mean(v), 2)) for e, v in sorted(byE.items())})
