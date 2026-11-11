#!/usr/bin/env python3
"""Brief 36 small end-to-end run (PREREG.md section 3): 3 dev tasks x 3 seeds x skill routing off / router.

    python3 results/36_skill_routing/e2e.py run        # one run at a time, paired and interleaved; appends to e2e_runs.jsonl
    python3 results/36_skill_routing/e2e.py table      # e2e.md from e2e_runs.jsonl

Each run: ``python -m agent run <spec> --stop-after 2 --verif-level V1 --max-usd 0.60 --skill-routing <arm>`` (deepagents,
luna on OpenRouter). Score: the task's hidden bench on the run's rtl/ (benchmark/tools/run_task.py), never an LLM. Cost and
tokens: the run's summary.json (provider-reported). Stops when the brief's USD 5.00 cap would be passed. A slot already in
e2e_runs.jsonl is skipped, so the driver can be restarted.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOG = HERE / "e2e_runs.jsonl"
TASKS = {"t1_debounce_bank": "benchmark/tasks/t1_debounce_bank",
         "t2_spi_master_modes": "benchmark/tasks/t2_spi_master_modes",
         "c11_nco_mixer": "benchmark/course/tasks/c11_nco_mixer"}
SEEDS = (1,)                    # PREREG amendment 2: seed 1 only (seeds 2-3 move to brief 42 arm A1)
ARMS = ("off", "router")
CAP_USD = 5.00
STAGES = ("clarify", "board-and-device-planning", "rtl-design-creation")
RUN_USD = 0.60


def done() -> list[dict]:
    return [json.loads(x) for x in LOG.read_text().splitlines() if x.strip()] if LOG.exists() else []


def score(task_dir: Path, rtl: Path, out: Path) -> dict:
    if not rtl.is_dir() or not any(rtl.glob("*.sv")):
        return {"pass": False, "reason": "no rtl"}
    r = subprocess.run([sys.executable, str(ROOT / "benchmark/tools/run_task.py"), str(task_dir), "--rtl", str(rtl),
                        "--json", str(out)], cwd=ROOT, capture_output=True, text=True, timeout=3600)
    try:
        j = json.loads(out.read_text())
    except Exception:
        return {"pass": False, "reason": f"scorer rc {r.returncode}: {r.stderr[-300:]}"}
    tests = j.get("tests") or {}                     # {test name: passed} (run_task.py)
    passed = sum(1 for v in tests.values() if v is True)
    return {"pass": bool(j.get("pass")), "tests_passed": passed, "tests": len(tests)}


def run_all() -> int:
    have = {(r["task"], r["seed"], r["arm"]) for r in done()}
    spent = sum(r.get("cost_usd") or 0 for r in done())
    for seed in SEEDS:
        for task, tdir in TASKS.items():
            for arm in ARMS:
                if (task, seed, arm) in have:
                    continue
                if spent + RUN_USD > CAP_USD:
                    print(f"cap: spent {spent:.4f}, next run could pass {CAP_USD}")
                    return 3
                before = set(p.name for p in (ROOT / "runs").iterdir()) if (ROOT / "runs").is_dir() else set()
                t0 = time.time()
                cmd = [sys.executable, "-m", "agent", "run", str(ROOT / tdir / "spec.md"), "--name", task,
                       "--stop-after", "2", "--verif-level", "V1", "--max-usd", str(RUN_USD), "--skill-routing", arm]
                p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=4 * 3600)
                new = sorted(set(p.name for p in (ROOT / "runs").iterdir()) - before)
                rid = new[-1] if new else None
                rec = record(task, tdir, seed, arm, rid, p.returncode, round(time.time() - t0, 1), p.stderr or p.stdout)
                spent += rec.get("cost_usd") or 0
                with LOG.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                print(json.dumps({k: rec.get(k) for k in ("task", "seed", "arm", "run_id", "cost_usd", "stop", "score")}),
                      flush=True)
    return 0


def record(task, tdir, seed, arm, rid, rc, wall, out="") -> dict:
    rec = {"task": task, "seed": seed, "arm": arm, "run_id": rid, "rc": rc, "wall_s": wall}
    summ = ROOT / "runs" / str(rid) / "summary.json"
    if rid and summ.is_file():
        s = json.loads(summ.read_text())
        rec.update(cost_usd=s.get("cost_usd"), tokens=s.get("tokens"), stop=s.get("stop"),
                   gates_last=s.get("gates_last"), unreported_cost_calls=s.get("unreported_cost_calls"),
                   per_stage={k: {"tokens": v["tokens"], "cost_usd": v["cost_usd"], "calls": v["calls"]}
                              for k, v in (s.get("per_stage") or {}).items()},
                   knowledge_use=s.get("knowledge_use"))
        rec["stage2_gates_passed"] = bool((s.get("gates_last") or {}).get("rtl-design-creation"))
    else:
        rec["error"] = out[-800:]
    if rid:
        (HERE / "scores").mkdir(exist_ok=True)
        rec["score"] = score(ROOT / tdir, ROOT / "runs" / rid / task / "rtl", HERE / "scores" / f"{rid}.json")
    return rec


def adopt(task: str, seed: int, arm: str, rid: str) -> int:
    """Record (or re-score) a run that finished but whose record was not written (the first two runs: scorer bugs)."""
    rows = [r for r in done() if (r["task"], r["seed"], r["arm"]) != (task, seed, arm)]
    rec = record(task, TASKS[task], seed, arm, rid, None, None)
    rec["note"] = "recorded after the run by e2e.py adopt (scorer bug fixed after the run)"
    LOG.write_text("".join(json.dumps(r) + "\n" for r in rows + [rec]))
    print(json.dumps({k: rec.get(k) for k in ("task", "arm", "run_id", "cost_usd", "stop", "score")}))
    return 0


def table() -> int:
    rows = done()
    md = ["# Brief 36 end to end (written by e2e.py table)", "",
          "Development tasks, deepagents, every role on openai/gpt-6-luna (OpenRouter, data_collection deny), interview and "
          "review off, `--stop-after 2 --verif-level V1`, cap USD 0.60 a run. Pass = every hidden-bench test passes on the "
          "run's rtl/ (benchmark/tools/run_task.py). Tokens and cost are provider-reported (summary.json). Each row is one run.",
          "", "| Task | Seed | Arm | Run | Stage-2 gates | Hidden bench | Tokens | Cost USD | Stop |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        sc = r.get("score") or {}
        hb = ("pass" if sc.get("pass") else "fail") + (f" {sc.get('tests_passed')}/{sc.get('tests')}" if "tests" in sc else
                                                       f" ({sc.get('reason', 'n/a')})")
        md.append(f"| {r['task']} | {r['seed']} | {r['arm']} | {r.get('run_id')} | {'pass' if r.get('stage2_gates_passed') else 'fail'} "
                  f"| {hb} | {r.get('tokens')} | {r.get('cost_usd')} | {r.get('stop')} |")
    md += ["", "| Arm | Runs | Hidden-bench passes | Stage-2 gate passes | Mean tokens | Total cost USD |", "|---|---|---|---|---|---|"]
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        md.append(f"| {arm} | {len(rs)} | {sum(1 for r in rs if (r.get('score') or {}).get('pass'))} | "
                  f"{sum(1 for r in rs if r.get('stage2_gates_passed'))} | "
                  f"{round(sum(r.get('tokens') or 0 for r in rs) / len(rs))} | {round(sum(r.get('cost_usd') or 0 for r in rs), 4)} |")
    md += ["", "Tokens per stage (mean over the arm's runs that reached the stage):", "",
           "| Arm | " + " | ".join(STAGES) + " |", "|---|---|---|---|"]
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        cells = []
        for n in STAGES:
            v = [r["per_stage"][n]["tokens"] for r in rs if n in (r.get("per_stage") or {})]
            cells.append(f"{round(sum(v) / len(v))} (n={len(v)})" if v else "-")
        if rs:
            md.append(f"| {arm} | " + " | ".join(cells) + " |")
    (HERE / "e2e.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    if sys.argv[1:2] == ["adopt"]:
        raise SystemExit(adopt(sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]))
    raise SystemExit(run_all() if sys.argv[1:] == ["run"] else table())
