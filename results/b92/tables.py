#!/usr/bin/env python3
"""Print the markdown tables of designs/b92_history_attention/docs/what_we_found.md from the committed records."""
import json
from pathlib import Path

R = Path(__file__).resolve().parent
j = lambda p: json.loads((R / p).read_text())  # noqa: E731
LABEL = {"ref_current": "head, no history", "a1_decay": "1 decaying sums", "a4_lut": "4 LUT net on the sums", "a2_win8": "2 window N=8",
         "a2_win16": "2 window N=16", "a3_top1": "3 attention, top-1", "a3_relu": "3 attention, ReLU-linear", "ref_lut": "89 LUT net, no history",
         "ref_mlp": "87 MLP, no history"}
f = lambda x: f"{x:+.4f}"  # noqa: E731


def ci(d):
    return f"{d['mean']:.4f} [{d['ci95'][0]:.4f}, {d['ci95'][1]:.4f}]"


def stage1():
    s = j("stage1_test.json")
    print("| Generator | Arm | Test accuracy (trees) | Paired difference to current-only trees | Histogram boosting difference |")
    print("|---|---|---|---|---|")
    for g, v in s["generators"].items():
        gc = v["gate_candidate"]
        print(f"| {g} | current only | {ci(v['arms']['current']['gbt'])} | | |")
        for nm in ("lagfeat4", "lagfeat8", "lagfeat16", "lagprim4", "lagprim8", "lagprim16"):
            d = v["paired_vs_current_gbt_all_candidates"][nm]
            sens = v["sensitivity_hist_boosting_difference"] if nm == gc else None
            print(f"| {g} | {nm}{' (gate candidate)' if nm == gc else ''} | {ci(v['arms'][nm]['gbt'])} | {f(d['mean'])} [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}] | "
                  f"{(f(sens['mean']) + ' [' + format(sens['ci95'][0], '+.4f') + ', ' + format(sens['ci95'][1], '+.4f') + ']') if sens else ''} |")


def stage2():
    s = j("stage2_accuracy.json")
    print("| Arm | Built seed | Test accuracy [95%] | 3-seed mean | vs head with no history | vs 1 decaying sums |")
    print("|---|---|---|---|---|---|")
    for a, v in s["arms"].items():
        t = next(r for r in v["runs"] if r["seed"] == v["built_seed"])["test"]
        p0, p1 = v["paired_vs"]["ref_current"], v["paired_vs"]["a1_decay"]
        print(f"| {LABEL[a]} | {v['built_seed']} | {ci(t)} | {v['test_mean_over_seeds']:.4f} | "
              f"{f(p0['difference_mean'])} [{p0['ci95'][0]:+.4f}, {p0['ci95'][1]:+.4f}] | "
              f"{f(p1['difference_mean'])} [{p1['ci95'][0]:+.4f}, {p1['ci95'][1]:+.4f}] |")
    for k, r in s["references"].items():
        print(f"| reference: {k} | | {ci(r)} | | | |")


def hardware():
    sm = j("summary.json")
    print("| Arm | Clocks | K26 closed ns | K26 latency ns | K26 LUT | K26 FF | A7 closed ns | A7 latency ns | A7 LUT | A7 FF | DSP / BRAM |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for a, v in sm["arms"].items():
        h = v["hardware"]
        if not h:
            continue
        k, s7 = h.get("k26"), h.get("a7")
        if not k:
            continue
        sx = (lambda key: s7[key]) if s7 else (lambda key: "n/a")
        print(f"| {LABEL[a]} | {k['clocks']} | {k['closed_at_ns']} | {k['latency_ns']} | {k['lut']} | {k['ff']} | {sx('closed_at_ns')} | {sx('latency_ns')} | "
              f"{sx('lut')} | {sx('ff')} | {k['dsp']} / {k['bram_tiles']} |")


if __name__ == "__main__":
    for fn in (stage1, stage2, hardware):
        print(f"\n## {fn.__name__}\n")
        fn()
