"""Run the closure loop on a benchmark task's RTL (brief 62A proof cases).

    python3 -m agent.graph.closure_task <task_dir> --rtl <rtl dir> --case <name> [--arch architecture.yaml]
           [--max-iter 6] [--max-usd 2.0] [--model openai/gpt-6-luna] [--replay calls.json] [--out results/62a_closure/<case>]

- The design is staged under ``build/closure/<case>/`` (gitignored) as ``benchmark/tools/ref_build.py`` stages a
  reference: the RTL given, an XDC from the task's ``hidden/spec.yaml``, a generated architecture.yaml (or ``--arch``,
  whose ``datapaths`` are planned by flow/timing_plan.py), build.yaml.
- **G1** is the task's hidden acceptance bench (``benchmark/tools/run_task.py``), never the writer's own test.
- **The build** is ``flow/run_vivado.sh <design> base`` (its own MemoryMax=6G scope), started only inside a heavy
  slot taken through ``_handoff/take_heavy_slot.sh --env`` with ``--slot-prefix`` (the lock is released only if its
  text starts with that prefix).
- **The RTL writer** is one OpenRouter call per attempt (luna by default; Fable and Opus are refused by llm.py).

Records ``history.jsonl``, ``summary.json``, ``llm_calls.jsonl`` and the final RTL in ``--out``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.graph import closure as cl  # noqa: E402
from flow import timing_plan  # noqa: E402
from flow.digest.build import digest_build  # noqa: E402

SLOT_SCRIPT = Path(os.environ.get("FDA_SLOT_SCRIPT", "/home/brendan/Claude_sandbox/_handoff/take_heavy_slot.sh"))


def stage(task: Path, rtl: Path, case: str, arch: Path | None = None) -> Path:
    from benchmark.tools.board_xdc import make_xdc
    from benchmark.tools.ref_build import architecture
    spec = yaml.safe_load((task / "hidden" / "spec.yaml").read_text())
    d = ROOT / "build" / "closure" / case
    shutil.rmtree(d, ignore_errors=True)
    (d / "rtl").mkdir(parents=True)
    for f in sorted(rtl.iterdir()):
        if f.suffix in (".sv", ".v", ".svh"):
            shutil.copy2(f, d / "rtl" / f.name)
    (d / "design.xdc").write_text(make_xdc(spec))
    a = architecture(spec, d / "rtl")
    if arch:
        extra = yaml.safe_load(arch.read_text()) or {}
        for k in ("datapaths",):
            if k in extra:
                a[k] = extra[k]
    (d / "architecture.yaml").write_text(yaml.safe_dump(a, sort_keys=False))
    rel = d.relative_to(ROOT)
    (d / "build.yaml").write_text(yaml.safe_dump({
        "top": spec["top"], "part": spec.get("part", "xc7a100tcsg324-1"), "board": "nexys_a7_100t",
        "sources": ["shell/rtl/*.sv", f"{rel}/rtl/*.sv"], "constraints": [f"{rel}/design.xdc"], "generics": {}},
        sort_keys=False))
    return d


def acceptance_g1(task: Path, case: str, sim: str = "icarus"):
    from benchmark.tools import run_task
    n = {"i": 0}

    def g1(rtl: Path) -> dict:
        n["i"] += 1
        r = run_task.run(task, rtl, sim, tag=f"closure_{case}_{n['i']}")
        detail = r.get("error") or ""
        if not r["pass"] and r.get("log"):
            try:
                log = Path(r["log"]).read_text(errors="replace")
                detail += "\n" + "\n".join(l for l in log.splitlines() if "FAIL" in l or "Error" in l or "assert" in l.lower())[-2000:]
            except OSError:
                pass
        return {"pass": r["pass"], "tests": r["tests"], "detail": detail.strip()}
    return g1


def slot_build(prefix: str, minutes: int = 20, peak_g: float = 4.0, log=print):
    def build(d: Path) -> dict:
        text = f"{prefix}: closure build {d.name} Vivado impl, peak {peak_g:g}G"
        while True:
            e = subprocess.run([str(SLOT_SCRIPT), "--env", f"{text}, {time.strftime('%H:%M')}, expected end "
                                f"{time.strftime('%H:%M', time.localtime(time.time() + minutes * 60))}"],
                               capture_output=True, text=True)
            if e.returncode == 0:
                break
            time.sleep(60)
        env = dict(os.environ)
        lock = None
        for part in e.stdout.replace(";", "\n").split("\n"):
            part = part.strip().removeprefix("export ").strip()
            if part.startswith("HEAVY_LOCK="):
                lock = Path(part.split("=", 1)[1])
            elif part.startswith("FDA_VIVADO_THREADS="):
                env["FDA_VIVADO_THREADS"] = part.split("=", 1)[1]
        env["FDA_VIVADO_MAX"] = "2"
        log(f"[slot] {lock}: {lock.read_text().strip() if lock else '?'}")
        try:
            r = subprocess.run([str(ROOT / "flow" / "run_vivado.sh"), str(d), "base"], cwd=ROOT, env=env,
                               capture_output=True, text=True)
            (d / "build" / "last_build.out").parent.mkdir(parents=True, exist_ok=True)
            (d / "build" / "last_build.out").write_text(r.stdout[-20000:] + "\n" + r.stderr[-5000:])
        finally:
            if lock and lock.is_file() and lock.read_text().startswith(prefix + ":"):
                lock.unlink()
        return digest_build(d / "build" / "base")
    return build


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", type=Path)
    ap.add_argument("--rtl", type=Path, required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--arch", type=Path, help="architecture.yaml whose datapaths are planned (design-time plan arm)")
    ap.add_argument("--max-iter", type=int, default=6)
    ap.add_argument("--max-usd", type=float, default=2.0)
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("--replay", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--slot-prefix", default="FPGA b62a")
    ap.add_argument("--build-only", action="store_true", help="stage, check G1 and build once; no edits")
    a = ap.parse_args(argv)
    task = a.task.resolve()
    out = (a.out or ROOT / "results" / "62a_closure" / a.case).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "history.jsonl").unlink(missing_ok=True)
    d = stage(task, a.rtl.resolve(), a.case, a.arch)
    spec = yaml.safe_load((task / "hidden" / "spec.yaml").read_text())
    pl = timing_plan.plan_design(d) if a.arch else {"plan": None}
    if pl.get("plan"):
        (out / "timing_plan.json").write_text(json.dumps(pl["plan"], indent=1) + "\n")
    from agent.graph.llm import OpenRouterClient, Recorder, Replay
    calls: list = []
    if a.replay:
        client = Replay(a.replay)
    else:
        client = Recorder(OpenRouterClient(a.model), out / "llm_replay.json")
    c = cl.Closure(ws=cl.Workspace(d), goals=cl.goals_from_spec(spec), g1=acceptance_g1(task, a.case),
                   build=slot_build(a.slot_prefix), editor=cl.llm_editor(client, calls), contract=cl.contract_from_spec(spec),
                   spec=spec, plan_text=timing_plan.plan_text(pl["plan"]) if pl.get("plan") else "",
                   plan_check=(lambda _dg: timing_plan.post_synth_failures(d, json.loads((d / "build" / "base" / "gates.json").read_text())))
                   if pl.get("plan") else None,
                   max_iter=0 if a.build_only else a.max_iter, max_usd=a.max_usd, record=out)
    rep = c.run()
    rep.update({"case": a.case, "task": task.name, "model": a.model, "rtl_in": str(a.rtl), "plan": bool(pl.get("plan"))})
    (out / "summary.json").write_text(json.dumps(rep, indent=1, default=str) + "\n")
    with (out / "llm_calls.jsonl").open("w") as f:
        for r in calls:
            f.write(json.dumps(r) + "\n")
    shutil.rmtree(out / "rtl_final", ignore_errors=True)
    shutil.copytree(d / "rtl", out / "rtl_final")
    if pl.get("plan"):
        timing_plan.record_calibration(d, out / "calibration.jsonl")
    print(json.dumps({k: rep[k] for k in ("stop", "start_line", "final_line", "iterations", "accepted", "reverted", "usd")}, indent=1))
    return 0 if rep["all_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
