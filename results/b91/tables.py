#!/usr/bin/env python3
"""Print the markdown tables of docs/what_we_found.md from summary.json and accuracy*.json (nothing typed by hand).

    python3 results/b91/tables.py
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent
s = json.loads((R / "summary.json").read_text())
sm = json.loads((R / "accuracy_seedmean.json").read_text())
acc = json.loads((R / "accuracy.json").read_text())
fz = {n["id"]: n for n in json.loads((R / "frozen.json").read_text())["networks"]}


def f(k, key):
    return "not built" if not k else str(k[key])


print("### Accuracy (test split, 95% t-interval over 10 sessions)\n")
print("| Network | Val mean (3 seeds) | Test, built seed | Test, mean of 3 seeds | vs trivial rule | vs 87 trees | vs `lg_small` | vs `lg_add` |")
print("|---|---|---|---|---|---|---|---|")
for nid, a in acc["networks"].items():
    t = next(r for r in a["runs"] if r["seed"] == a["built_seed"])["test"]
    p = a["paired_vs"]

    def d(k):
        return f"{p[k]['difference_mean']:+.4f} [{p[k]['ci95'][0]:+.4f}, {p[k]['ci95'][1]:+.4f}]"
    print(f"| `{nid}` | {fz[nid]['val_mean']:.4f} | {t['mean']:.4f} [{t['ci95'][0]:.4f}, {t['ci95'][1]:.4f}] | {a['test_mean_over_seeds']:.4f} | "
          f"{d('trivial_rule_87')} | {d('trees_87')} | {d('lg_small')} | {d('lg_add')} |")
print("\n### Accuracy, post hoc: mean of the 3 training seeds per session (`accuracy_seedmean.json`)\n")
print("| Network | Seed-mean test | vs trivial rule | vs 87 trees | vs `lg_small` |")
print("|---|---|---|---|---|")
for nid, a in sm["networks"].items():
    p = a["paired_vs"]

    def d(k):
        return f"{p[k]['difference_mean']:+.4f} [{p[k]['ci95'][0]:+.4f}, {p[k]['ci95'][1]:+.4f}]"
    print(f"| `{nid}` | {a['seed_mean_test']['mean']:.4f} | {d('trivial_rule_87')} | {d('trees_87')} | {d('lg_small')} |")
print("\n### Hardware (out of context, post-route, Vivado 2026.1; latency = clocks x max(closed period, 2.0 ns))\n")
print("| Module | Test acc. | K26 clocks | K26 closed ns | K26 latency ns | K26 LUT / FF | A7 closed ns | A7 latency ns | A7 LUT / FF | DSP / BRAM |")
print("|---|---|---|---|---|---|---|---|---|---|")
for r in s["rows"]:
    k, a = r["k26"], r["a7"]
    dsp = ",".join(sorted({f"{x['dsp']}/{x['bram_tiles']}" for x in (k, a) if x}))
    print(f"| `{r['module'][3:]}` | {r['test_accuracy']:.4f} | {f(k, 'clocks')} | {f(k, 'closed_at_ns')} | {f(k, 'latency_ns')} | "
          f"{(str(k['lut']) + ' / ' + str(k['ff'])) if k else 'not built'} | {f(a, 'closed_at_ns')} | {f(a, 'latency_ns')} | "
          f"{(str(a['lut']) + ' / ' + str(a['ff'])) if a else 'not built'} | {dsp} |")
print("\n### References on the K26 (committed brief 87 and 89 results)\n")
print("| Reference | Test acc. | K26 latency ns | K26 LUT / FF |")
print("|---|---|---|---|")
for r in s["references"]:
    print(f"| {r['id']} | {r['test_accuracy']:.4f} | {r['k26']['latency_ns']} | {r['k26']['lut']} / {r['k26']['ff']} |")
print("\nOn the K26 front (accuracy against LUTs):", ", ".join(s["fronts_k26"]["accuracy_vs_luts"]))
print("On the K26 front (accuracy against latency):", ", ".join(s["fronts_k26"]["accuracy_vs_latency"]))
