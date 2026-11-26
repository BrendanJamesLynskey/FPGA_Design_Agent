#!/usr/bin/env python3
"""Brief 231 item 8: does a Yosys logic-depth estimate rank designs like Vivado's synthesis-stage logic levels?

Reads the brief 142 benchmark set (results/b142/scripts/manifest.py) and Vivado's recorded synthesis-stage worst path
(results/b142/vivado/k26/viv_default/<case>/timing_worst_synth.rpt, line "Logic Levels:"), runs ``synth_xilinx -family xcup
-flatten`` on each case through flow/yosys_depth.py, and writes depth.csv and summary.json. Needs Yosys with the slang plugin.

    python3 results/231_yosys_depth/compare.py
"""
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results" / "b142" / "scripts"))
from manifest import BENCH  # noqa: E402
from flow.yosys_depth import run_yosys  # noqa: E402

VIV = ROOT / "results" / "b142" / "vivado" / "k26" / "viv_default"


def vivado_levels(name: str):
    p = VIV / name / "timing_worst_synth.rpt"
    if not p.is_file():
        return None
    m = re.search(r"Logic Levels:\s+(\d+)", p.read_text(errors="replace"))
    return int(m.group(1)) if m else None


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def one(name):
    b = BENCH[name]
    try:
        r = run_yosys(b["sources"], b["top"], "xcup", {k: str(v) for k, v in b["generics"].items()})
        return name, b["group"], r
    except Exception as e:                                   # noqa: BLE001
        return name, b["group"], {"error": str(e)[-200:]}


def main():
    names = [n for n in sorted(BENCH) if vivado_levels(n) is not None]
    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(one, names))
    rows = []
    for n, g, r in res:
        rows.append({"case": n, "group": g, "vivado_levels": vivado_levels(n), "yosys_depth": r.get("depth"),
                     "yosys_levels": r.get("levels"), "yosys_path": " ".join(r.get("path", [])[-12:]), "error": r.get("error", "")})
    with open(HERE / "depth.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["yosys_depth"] is not None]
    v = [r["vivado_levels"] for r in ok]
    y = [r["yosys_depth"] for r in ok]
    diff = [abs(a - b) for a, b in zip(v, y)]
    # top quartile of Vivado levels: how many are also in Yosys's top quartile
    k = max(1, len(ok) // 4)
    top_v = {r["case"] for r in sorted(ok, key=lambda r: -r["vivado_levels"])[:k]}
    top_y = {r["case"] for r in sorted(ok, key=lambda r: -r["yosys_depth"])[:k]}
    out = {"n_cases": len(rows), "n_ok": len(ok), "spearman": round(spearman(v, y), 3),
           "median_abs_diff": sorted(diff)[len(diff) // 2], "max_abs_diff": max(diff),
           "within_2_levels": sum(1 for d in diff if d <= 2), "top_quartile_k": k, "top_quartile_overlap": len(top_v & top_y),
           "errors": [r["case"] for r in rows if r["error"]]}
    (HERE / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
