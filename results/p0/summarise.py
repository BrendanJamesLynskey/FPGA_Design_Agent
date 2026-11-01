"""Summarise the P0 runs from their committed CSVs (collect.py rows). Descriptive only: every run here is void
(guard-truncated, PREREG deviations 1 and 2), so nothing is scored. Usage: python3 results/p0/summarise.py"""
import csv, glob, collections, os

here = os.path.dirname(os.path.abspath(__file__))
print("| Run | Model | Pass | Stop reasons | Provider-reported $ | $/problem | Providers served |")
print("|---|---|---|---|---|---|---|")
for path in sorted(glob.glob(os.path.join(here, "runs", "*.csv"))):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    name = os.path.basename(path)[:-4]
    model = rows[0]["requested_model"]
    passed = sum(1 for r in rows if r["pass"] == "1")
    stops = collections.Counter(r["stop_reason"] for r in rows)
    cost = sum(float(r["cost_usd"] or 0) for r in rows)
    provs = collections.Counter(seg.split(":")[0].strip() for r in rows for seg in (r["providers"] or "").split("+") if seg.strip())
    stop_s = ", ".join(f"{k} {v}" for k, v in stops.most_common())
    prov_s = ", ".join(f"{k} {v}" for k, v in provs.most_common())
    print(f"| {name} | {model} | {passed}/{len(rows)} | {stop_s} | {cost:.4f} | {cost/len(rows):.4f} | {prov_s} |")
