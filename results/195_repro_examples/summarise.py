"""Print the tables of results/195_repro_examples/README.md from the committed reference records (no tool, no model).

    python results/195_repro_examples/summarise.py
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

D = Path(__file__).resolve().parent


def refs(ex: Path):
    return [json.loads(f.read_text()) for f in sorted((q for q in ex.glob("ref_*.json") if re.fullmatch(r"ref_\d+\.json", q.name)), key=lambda q: int(q.stem.split("_")[1]))]


def rng(vals, nd=0):
    xs = [v for v in vals if isinstance(v, (int, float))]
    if not xs:
        return "n/a"
    return f"{min(xs):.{nd}f} / {statistics.median(xs):.{nd}f} / {max(xs):.{nd}f}"


def main() -> None:
    print("| example | runs | hidden tests passed | agent's own gates passed | distinct RTL | LUT min/med/max | worst setup slack ns | repair loops | wall min | cost USD |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for ex in sorted(p for p in D.iterdir() if p.is_dir()):
        r = refs(ex)
        if not r:
            continue
        t = lambda k: [x["tool_results"].get(k) for x in r]                       # noqa: E731
        v = lambda k: [x["varies"].get(k) for x in r]                             # noqa: E731
        print(f"| {ex.name} | {len(r)} | {sum(1 for x in r if x['outcome']['hidden_pass'])}/{len(r)} | {sum(1 for x in r if x['outcome']['internal_pass'])}/{len(r)} | {len({x['tool_results']['rtl_sha256'] for x in r})} | "
              f"{rng(t('lut'))} | {rng(t('wns_ns'), 3)} | {rng(v('repair_visits'))} | {rng([w / 60 if w else None for w in v('wall_s')])} | {rng(v('cost_usd'), 2)} |")
    print()
    print("| example | run | hidden tests | own gates | stop | RTL hash | LUT | FF | setup slack ns | build stamp | loops | turns | tokens | cost USD | wall s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for ex in sorted(p for p in D.iterdir() if p.is_dir()):
        for x in refs(ex):
            o, t, v = x["outcome"], x["tool_results"], x["varies"]
            print(f"| {ex.name} | ref_{x['reference']} ({x['run_id']}) | {o['tests_passed']}/{o['tests_total']} | {'yes' if o['internal_pass'] else 'no'} | {o['stop']} | {t['rtl_sha256'][:8]} | {t['lut']} | {t['ff']} | {t['wns_ns']} | {t['build_stamp']} | {v['repair_visits']} | {v['agent_turns']} | {v['tokens']} | {v['cost_usd']} | {v['wall_s']} |")


if __name__ == "__main__":
    main()
