"""Page data for the brief 50A showcase page, from committed results only.

    python -m debug_core.showcase_data [--results results/50a_nl_debug] [--out site/data/showcase_nl_debug.json]

Every number in the output is copied from ``results/50a_nl_debug`` (demo.json, builds.json and each run's plan.json,
capture.json, check.json); nothing is computed that is not also in those files except the trimmed sample windows for the
hero replay (the cycles each request asked for, sliced from the capture) and simple sums stated as such.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from debug_core.capture import trim
from debug_core.plan import render
from debug_core.rtl_index import ROOT

ORDER = ["t1_count_write", "t1_pwm_period", "t1_sync_byte", "t1_or_flags", "t1_reuse_rise"]


def run_entry(d: Path, demo: dict[str, Any], builds: dict[str, Any]) -> dict[str, Any]:
    plan = json.loads((d / "plan.json").read_text())
    cap = json.loads((d / "capture.json").read_text())
    chk = json.loads((d / "check.json").read_text())
    req = plan["window"].get("requested") or {}
    full0 = -cap["timebase"]["trigger_sample"]
    lo = -int(req["pre"]) if req.get("pre") is not None else full0
    hi = int(req["post"]) if req.get("post") is not None else full0 + cap["timebase"]["samples"] - 1
    win = trim(cap, lo, hi)
    b = builds.get(cap["build"].get("probeset") or "", {})
    rel = d.relative_to(ROOT)
    return {
        "name": d.name, "request": plan["request"], "pass": demo.get("pass"),
        "parse": demo.get("parse"),
        "intent": plan.get("intent"),
        "plan_text": render(plan),
        "plan": {"probes": [{k: p[k] for k in ("label", "path", "width", "pins", "requested_as", "role")} for p in plan["probes"]],
                 "trigger": plan["trigger"], "window": plan["window"], "ports": plan["ports"], "fit": plan["fit"],
                 "setup": plan["setup"], "stimulus": plan["stimulus"], "readback": plan["readback"],
                 "probeset": plan["probeset"]},
        "build": {"probeset": cap["build"].get("probeset"), "build_id": cap["build"].get("build_id"),
                  "reused_other_probe_set": cap["build"].get("reused"), "vivado": cap["build"].get("vivado"),
                  "wall_s": b.get("wall_s"), "wns_ns": b.get("wns_ns"), "utilization": b.get("utilization"),
                  "gates_pass": b.get("gates_pass"), "program_seconds": cap["build"].get("program_seconds"),
                  "power_ok": cap["build"].get("power_ok")},
        "replay": {"first_cycle": lo if lo > full0 else full0, "trigger_sample": win["timebase"]["trigger_sample"],
                   "mhz": cap["timebase"]["mhz"], "channels": [{k: c[k] for k in ("name", "path", "width", "samples")}
                                                               for c in win["channels"]],
                   "full_samples": cap["timebase"]["samples"]},
        "answer": (d / "answer.txt").read_text().strip(),
        "check": chk, "readback": cap.get("readback"),
        "conditions": {k: cap["conditions"].get(k) for k in ("programmed", "armed", "done", "verdict", "alarms", "outside",
                                                              "limits")},
        "seconds": {"total": demo.get("seconds_total"), "program_and_capture": demo.get("seconds_program_capture")},
        "files": {k: str(rel / f) for k, f in (("plan", "plan.json"), ("capture", "capture.json"), ("vcd", "capture.vcd"),
                                              ("answer", "answer.txt"), ("view", "view.html"), ("ila_csv", "ila/cap.csv"))
                  if (d / f).is_file()},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--results", type=Path, default=ROOT / "results" / "50a_nl_debug")
    ap.add_argument("--out", type=Path, default=ROOT / "site" / "data" / "showcase_nl_debug.json")
    a = ap.parse_args(argv)
    demo = json.loads((a.results / "demo.json").read_text())
    builds = json.loads((a.results / "builds.json").read_text())
    runs = [run_entry(a.results / n, demo[n], builds["builds"]) for n in ORDER if (a.results / n / "capture.json").is_file()]
    passed = sum(1 for r in runs if r["pass"])
    costs = [r["parse"].get("cost") for r in runs if r.get("parse") and r["parse"].get("cost") is not None]
    rebuilds = [r for r in runs if r["build"]["reused_other_probe_set"]]
    walls = [b["wall_s"] for b in builds["builds"].values()]
    data = {
        "id": "nl_debug", "brief": "50A", "title": "Debug on the board from a plain-English request",
        "board": "Nexys A7-100T", "part": "xc7a100tcsg324-1", "vivado": "2026.1", "licence_tier": "Basic",
        "headline": {"known_answer_runs": len(runs), "passed": passed,
                     "parse_cost_usd_max": max(costs) if costs else None, "parse_model": runs[0]["parse"].get("model") if runs else None,
                     "builds": len(builds["builds"]),
                     "build_wall_s": sorted(b["wall_s"] for b in builds["builds"].values()),
                     "runs_without_a_new_build": len(rebuilds),
                     "conditions": sorted({r["conditions"]["verdict"] for r in runs})},
        "runs": runs, "builds": builds["builds"],
        "limits": [
            "Vivado 2026.1 Basic licence tier: one ILA instance per design, so one clock domain per build, and at most 5 "
            "probe ports, and each port has one comparator (measured).",
            "Trigger compares are per bit (0, 1, X and rising/falling/either edge); != and magnitude compares on buses are "
            "refused unless they reduce to a per-bit pattern; OR only across 1-bit terms.",
            f"A new probe set is a new build ({min(walls):g} to {max(walls):g} s for these {len(walls)} T1 builds, one each); "
            "trigger, window and stimulus are run-time settings.",
            "One design (T1) and five requests; the parser was not measured on a held-out set of requests.",
            "Clocks made inside the design (MMCM outputs) and signals inside generate blocks are not resolved yet.",
            "XADC samples are read through JTAG at arm and after upload, not on the capture timeline.",
            "No agent role is offered the debug tools yet: offering them needs its own pre-registered evaluation first."],
        "agent_vs_owner": {"owner": "asked for the capability, the order (front end first) and the safety rules "
                                    "(SRAM only, power and temperature limits, DRCs never skipped)",
                           "agent": "wrote the front end, the tests and the docs, ran the builds and board runs; a language "
                                    "model (the project's cheap default) only turned each request into the intent JSON"},
        "try_it": ["python -m debug_core plan designs/t1_dimmer_counter \"<request>\"",
                   "python -m debug_core view results/50a_nl_debug/t1_count_write/capture.json -o view.html"],
        "sources": {"results": "results/50a_nl_debug", "docs": "docs/debug.md", "code": "debug_core/"},
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, indent=1) + "\n")
    print(a.out, len(runs), "runs", passed, "passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
