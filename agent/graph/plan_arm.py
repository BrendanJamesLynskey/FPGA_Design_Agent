"""First-build comparison with and without the design-time plan (brief 62A, "Pre-empt at design time").

    python3 -m agent.graph.plan_arm <task_dir> --module-file hough.sv --spec-yaml <run's spec.yaml> --out <dir>
           [--plan <timing_plan.json>] [--model openai/gpt-6-luna]

One RTL-writer call writes the task's core module from the clarified spec.yaml and the module's port list (taken from the
reference file's header; the body is never shown), with or without TIMING_PLAN.md. The other reference files (register
block, board top) are kept, so the two arms differ only in the core. G1 is the task's hidden acceptance bench; a failure
gets one repair call with the bench's failure text. The result is an RTL directory for ``agent.graph.closure_task``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.graph import closure as cl  # noqa: E402
from agent.graph.closure_task import acceptance_g1  # noqa: E402
from flow import timing_plan  # noqa: E402

SYSTEM = ("You are the RTL writer of an FPGA design agent (SystemVerilog, Vivado 2026.1, Artix-7 -1, 100 MHz unless the spec "
          "says otherwise). Write the one module asked for, synthesisable, with exactly the given header (module name, "
          "parameters, ports). Reply with the whole file as\n=== FILE: rtl/<name> ===\n```systemverilog\n<file>\n```\n"
          "then one line starting NOTE: with the latency in clocks and the resources you expect.")


def header(text: str, module: str) -> str:
    m = re.search(rf"^module\s+{module}\b.*?\);", text, re.S | re.M)
    if not m:
        raise ValueError(f"no header for module {module}")
    return m.group(0)


def write_core(client, spec_yaml: str, name: str, module: str, hdr: str, others: list[str], plan: str = "",
               failure: str = "") -> tuple[str | None, dict]:
    prompt = (f"Write rtl/{name}: module {module}. It is instantiated by the design's register block (not shown; files "
              f"{', '.join(others)}), which drives its ports exactly as the header below names them.\n\nHEADER (keep exactly):\n"
              f"{hdr}\n\nSPEC (spec.yaml, the design's clarified specification):\n{spec_yaml}\n")
    if plan:
        prompt += "\n" + plan + "\n"
    if failure:
        prompt += "\nYOUR LAST VERSION FAILED THE INDEPENDENT BENCH; fix it:\n" + failure[:2500] + "\n"
    rep = client([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}])
    files, note = cl.parse_reply(rep.text, {f"rtl/{name}"})
    return files.get(f"rtl/{name}"), {"cost": rep.cost, "prompt_tokens": rep.prompt_tokens,
                                      "completion_tokens": rep.completion_tokens, "note": note}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", type=Path)
    ap.add_argument("--rtl", type=Path, help="the RTL directory whose other files are kept (default: the task's ref/rtl)")
    ap.add_argument("--module-file", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--spec-yaml", type=Path, required=True)
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("--retries", type=int, default=1)
    a = ap.parse_args(argv)
    from agent.graph.llm import OpenRouterClient, Recorder
    task = a.task.resolve()
    src = (a.rtl or task / "ref" / "rtl").resolve()
    out = a.out.resolve()
    rtl = out / "rtl"
    shutil.rmtree(rtl, ignore_errors=True)
    shutil.copytree(src, rtl)
    hdr = header((src / a.module_file).read_text(), a.module)
    others = sorted(p.name for p in src.glob("*.sv") if p.name != a.module_file)
    plan = timing_plan.plan_text(json.loads(a.plan.read_text())) if a.plan else ""
    client = Recorder(OpenRouterClient(a.model), out / "llm_replay.json")
    g1 = acceptance_g1(task, out.name)
    calls, failure, res = [], "", None
    for attempt in range(a.retries + 1):
        text, info = write_core(client, a.spec_yaml.read_text(), a.module_file, a.module, hdr, others, plan, failure)
        calls.append(info)
        if not text:
            failure = "no file block in the reply"
            continue
        (rtl / a.module_file).write_text(text)
        res = g1(rtl)
        if res["pass"]:
            break
        failure = str(res.get("detail") or res.get("tests"))
    summary = {"task": task.name, "plan": bool(plan), "model": a.model, "attempts": len(calls), "g1": res,
               "usd": round(sum((c["cost"] if c["cost"] is not None else 0.05) for c in calls), 6),
               "tokens": sum(c["prompt_tokens"] + c["completion_tokens"] for c in calls), "calls": calls}
    (out / "write_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: summary[k] for k in ("plan", "attempts", "usd")} | {"g1": (res or {}).get("pass")}))
    return 0 if res and res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
