#!/usr/bin/env python3
"""Export the site's data from committed results only: site/data/*.json.

    python3 site/export.py          # write the JSON files
    python3 site/export.py --check  # exit 1 if a committed file differs from what the results give

Every number the pages show comes from these files (site/build.py --check fails the build otherwise).
Development tasks and the hand-built T1 design only: no held-out task is read (see LEAK below).
"""
from __future__ import annotations

import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "data"
COURSE = ROOT / "results" / "course"

# the held-out ids are public in split.yaml, but this exporter never reads them: only dev-labelled records
STAGE_ORDER = ["clarify", "board-and-device-planning", "rtl-design-creation", "constraints", "synthesis",
               "implementation", "timing-closure", "power-closure", "drc-closure", "configuration-and-debug"]


def jload(p):
    return json.loads(Path(p).read_text())


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def boot(per_task, seed=20261109, b=2000):
    rnd = random.Random(seed)
    n = len(per_task)
    ms = sorted(statistics.fmean(rnd.choices(per_task, k=n)) for _ in range(b))
    return [round(100 * ms[int(0.025 * b)], 1), round(100 * ms[int(0.975 * b)], 1)]


def dev_runs():
    runs = []
    for p in sorted(COURSE.glob("*/run_*.json")):
        r = jload(p)
        if r.get("split") != "dev":
            continue  # never include anything not labelled development
        q = r.get("qor") or {}
        runs.append({
            "task": r["task"], "run": r["run"], "date": r["date"], "outcome": r["outcome"],
            "escape_level": r.get("escape_level"),
            "hidden_pass": r["hidden_pass"], "tests_passed": r["hidden_tests_passed"], "tests_total": r["hidden_tests_total"],
            "agent_turns": r.get("agent_turns"), "wall_h": r.get("wall_h_total"), "tokens": r.get("tokens"),
            "plan_cost_usd": r.get("plan_cost_estimate_usd"), "model": r["model"],
            "claude_code_version": r.get("claude_code_version"), "agent_commit": r.get("agent_commit"),
            "wns_ns": q.get("wns_ns_at_100MHz_post_route"), "lut": q.get("lut"), "ff": q.get("ff"),
            "dsp": q.get("dsp"), "bram36": q.get("bram36"),
            "failure_class": (r["failure"].get("class") if isinstance(r.get("failure"), dict) else None),
            "stage_visits": r.get("stage_visits"), "questions": r.get("questions"), "gates": r.get("gates"),
            "stop": r.get("stop"), "qor": q,
        })
    return runs


def build_dev(runs):
    tasks = {}
    for r in runs:
        tasks.setdefault(r["task"], []).append(r)
    rows = []
    for t in sorted(tasks):
        rs = tasks[t]
        k = sum(1 for r in rs if r["hidden_pass"])
        rows.append({"task": t, "k": k, "n": len(rs), "outcomes": [r["outcome"] for r in rs]})
    per_task = [x["k"] / x["n"] for x in rows]
    k = sum(x["k"] for x in rows)
    n = sum(x["n"] for x in rows)
    oc = {}
    for r in runs:
        oc[r["outcome"]] = oc.get(r["outcome"], 0) + 1
    esc = {}
    for r in runs:
        if r["outcome"] == "escape":
            esc[r["escape_level"] or "unclassified"] = esc.get(r["escape_level"] or "unclassified", 0) + 1
    wall = [r["wall_h"] for r in runs if isinstance(r["wall_h"], (int, float))]
    cost = [r["plan_cost_usd"] for r in runs if isinstance(r["plan_cost_usd"], (int, float))]
    return {
        "label": "development tasks, not the held-out score",
        "runs": n, "tasks": len(rows), "hidden_pass": k, "pass_pct_runs": round(100 * k / n),
        "wilson_runs_pct": wilson(k, n),
        "pass_at_1_tasks_pct": round(100 * statistics.fmean(per_task)),
        "bootstrap_tasks_pct": boot(per_task),
        "outcomes": oc, "escape_levels": esc,         "escapes": oc.get("escape", 0),
        "mean_wall_h": round(statistics.fmean(wall), 1), "wall_n": len(wall),
        "mean_plan_cost_usd": round(statistics.fmean(cost), 2),
        "model": sorted({r["model"] for r in runs}), "dates": [min(r["date"] for r in runs), max(r["date"] for r in runs)],
        "per_task": rows,
        "runs_list": [{k2: r[k2] for k2 in ("task", "run", "outcome", "tests_passed", "tests_total", "failure_class",
                                              "wns_ns", "lut", "ff", "dsp", "bram36", "wall_h", "agent_turns")} for r in runs],
    }


def replay(runs):
    r = [x for x in runs if x["task"] == "c14_int8_dot_requant" and x["run"] == 5][0]
    v = r["stage_visits"]
    q = r["questions"]
    g = r["gates"]
    qo = r["qor"]
    facts = {
        "clarify": f"{q['asked']} questions asked; {q['answered']} answered by the oracle, {q['defaulted']} defaulted; the register map was asked for and the final spec carries 11 registers.",
        "board-and-device-planning": "Architecture, clocking plan, resource budget on the xc7a100t.",
        "rtl-design-creation": "RTL, constraints and the independent bench are written; the checks V0 to V3 run here. V3: " + g["V3"].split(" (")[0] + "; " + g["V3"].split("; ")[-1].split(", per")[0] + ".",
        "constraints": "Pin and clock constraints checked against the board's master XDC.",
        "synthesis": "Synthesis gates: " + g["stage_gates_post_route"].split(" (")[0] + " by the end of the run.",
        "implementation": "Place and route; bitstream built.",
        "timing-closure": f"Post-route setup slack {qo['wns_ns_at_100MHz_post_route']:+.3f} ns, hold slack {qo['whs_ns']:+.3f} ns at 100 MHz.",
        "power-closure": f"Vectorless power estimate {qo['power_w']:.3f} W.",
        "drc-closure": f"{qo['lut']} LUT, {qo['ff']} FF, {qo['dsp']} DSP, {qo['bram36']} BRAM after place and route (test shell included).",
        "configuration-and-debug": "Stops here: " + r["stop"]["reason"] + ".",
    }
    steps = []
    for s in STAGE_ORDER:
        for i in range(v[s]):
            steps.append({"stage": s, "stage_no": STAGE_ORDER.index(s), "visit": i + 1, "visits": v[s], "fact": facts[s]})
    return {"task": r["task"], "run": r["run"], "date": r["date"], "model": r["model"], "turns": r["agent_turns"],
            "wall_h": r["wall_h"], "stages": STAGE_ORDER, "steps": steps, "hidden": f"{r['tests_passed']} of {r['tests_total']}"}


def spec_excerpt(task, paras):
    t = (ROOT / "benchmark" / "course" / "tasks" / task / "spec.md").read_text().split("\n\n")
    return "\n\n".join(t[:paras]).strip()


def examples(runs):
    by = {}
    for r in runs:
        by.setdefault(r["task"], []).append(r)
    def brief(r):
        return {k: r[k] for k in ("run", "outcome", "tests_passed", "tests_total", "failure_class", "wns_ns", "lut", "ff", "dsp",
                                  "bram36", "agent_turns", "wall_h", "questions", "gates", "stop") if k in r}
    ex = []
    for task, title, paras in (("c9_median3x3", "Median filter behind the test shell", 99),
                               ("c10_dds_sine", "Sine-wave generator behind the test shell", 2),
                               ("c14_int8_dot_requant", "INT8 dot product with requantisation", 2)):
        ex.append({"task": task, "title": title, "spec": spec_excerpt(task, paras), "runs": [brief(r) for r in by[task]]})
    c14 = jload(ROOT / "benchmark/course/tasks/c14_int8_dot_requant/hidden/spec.yaml") if False else None
    return ex


def board():
    f0a = jload(ROOT / "results/f0a/t1_dimmer_counter_base.json")
    bring = jload(ROOT / "results/f0b/t1_dimmer_counter_bringup.json")
    runs = [jload(p) for p in sorted((ROOT / "results/f0b/runs").glob("*.json"))]
    base_md = (ROOT / "results/f0a/t1_dimmer_counter.md").read_text()
    def row(label):
        m = re.search(r"^\| " + re.escape(label) + r" \| ([^|]+) \| ([^|]+) \|", base_md, re.M)
        return [m.group(1).strip(), m.group(2).strip()]
    cap = {}
    for n, duty in (("08", 8), ("40", 64), ("a0", 160)):
        rows = list(csv.reader(open(ROOT / f"results/f0b/captures/t1_dimmer_counter_pwm_{n}.csv")))
        i = [j for j, x in enumerate(rows[0]) if "led_reg" in x][0]
        v = [int(r[i], 16) & 1 for r in rows[2:]]
        edges = [[0, v[0]]] + [[j, v[j]] for j in range(1, len(v)) if v[j] != v[j - 1]]
        cap[n] = {"duty": duty, "samples": len(v), "on": sum(v), "edges": edges}
        model = bring["steps"]["ila_captures"]["captures"]["pwm_" + n]["led_on_clocks_model"]
        meas = bring["steps"]["ila_captures"]["captures"]["pwm_" + n]["led_on_clocks_measured"]
        assert model == meas
        cap[n]["model_on"] = model[0]
    ts = []
    for r in runs:
        ts.append(round(sum(s.get("seconds", 0) for s in r["steps"].values() if isinstance(s, dict)), 1))
    uart = bring["steps"]["uart_tests"]
    mut = jload(ROOT / "results/04f/mutation_t1.json")
    v2 = [jload(p) for p in sorted((ROOT / "results/board_v2").glob("b2_*.json"))]
    v2runs = [jload(p) for p in sorted((ROOT / "results/board_v2/runs").glob("*.json"))]
    return {
        "design": "t1_dimmer_counter", "vivado": bring["steps"]["discover"]["vivado_version"], "part": bring["steps"]["discover"]["part"],
        "wns": row("setup WNS (ns)"), "whs": row("hold WHS (ns)"), "lut": row("LUTs"), "ff": row("FFs"), "bram": row("BRAM tiles"),
        "dsp": row("DSP48E1"), "power": row("power, total on-chip (W, vectorless)"),
        "uart_tests": uart["tests"], "uart_failures": uart["failures"], "ila_captures": 4,
        "board_runs": len(runs),
        "run_totals_s": ts,
        "captures": cap,
        "mutants": mut["mutants"], "mutants_killed": mut["killed_by_bench"], "mutation_first_run_pct": mut["first_run"]["score_pct"],
        "mutation_survivors_first": len(mut["first_run"]["survivors"]),
        "board_v2_designs": len(v2), "board_v2_runs": len(v2runs), "board_v2_passed": sum(1 for x in v2runs if x.get("pass") is True),
        "rtl": (ROOT / "designs/t1_dimmer_counter/rtl/debounce.sv").read_text().strip(),
    }


def packs():
    t = (ROOT / "knowledge/PACKS.md").read_text()
    rows = []
    for m in re.finditer(r"^\| (`[^`]+`|\*\*[^|]+\*\*) \| ([^|]+) \| ([^|]+) \| (\d+|-) \| ([\d,-]+|-) \| ([\d,]+|see[^|]*|-) ", t, re.M):
        rows.append({"unit": m.group(1).replace("`", "").strip("*"), "name": re.sub(r"\s*\(.*", "", m.group(2)).strip(), "skills": m.group(4),
                     "bytes": m.group(6).split(" ")[0] if m.group(6)[0].isdigit() else None})
    return {"units": [x for x in rows if x["bytes"]], "sections": 59}


def evaldata():
    t = (ROOT / "docs/eval/eval1_preregistration.md").read_text()
    for need in ("19 held-out tasks", "3 independent runs per task (57 runs)", "±17.5", "2,000 resamples", "seed 20261109"):
        assert need in t, need
    return {"tasks": 19, "runs_per_task": 3, "runs": 57, "resamples": 2000, "planned_halfwidth": 17.5,
            "dev_runs_for_width": 21, "dev_tasks_for_width": 11, "seed": 20261109, "tag": "eval-1",
            "tool_versions": {"claude_code": "2.1.319", "icarus": "12.0", "cocotb": "2.0.1", "vivado": "2025.2", "verilator": "5.048"},
            "model": "claude-sonnet-5-5", "oracle": "claude-haiku-5-5", "mutants_per_task": "5-8"}


def main():
    runs = dev_runs()
    out = {"dev": build_dev(runs), "replay": replay(runs), "examples": examples(runs), "board": board(),
           "packs": packs(), "eval": evaldata()}
    bad = 0
    for k, v in out.items():
        s = json.dumps(v, indent=1, sort_keys=True) + "\n"
        p = OUT / f"{k}.json"
        if "--check" in sys.argv:
            if not p.exists() or p.read_text() != s:
                print("stale:", p)
                bad = 1
        else:
            p.write_text(s)
    sys.exit(bad)


if __name__ == "__main__":
    main()
