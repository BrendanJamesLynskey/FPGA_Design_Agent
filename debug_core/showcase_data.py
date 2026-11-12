"""Page data for the showcase page "Debugging in plain English" (site/showcase/nl_debug.yaml), from committed results only.

    python -m debug_core.showcase_data [--results results/50a_nl_debug]

Writes two files into the results folder, both derived from files committed beside them (demo.json, builds.json and each
run's plan.json, capture.json, check.json, answer.txt):

- ``summary.json``: the values the page's ``{name}`` placeholders read (counts, ranges, costs, conditions);
- ``hero.json``: the hero in the site kit's ``wave`` form: the COUNT-write capture over the cycles the request asked for,
  with one caption per cycle that walks through the real run (request, plan, build, arming, trigger, answer).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from debug_core.capture import trim
from debug_core.rtl_index import ROOT

ORDER = ["t1_count_write", "t1_pwm_period", "t1_sync_byte", "t1_or_flags", "t1_reuse_rise"]
HERO_RUN = "t1_count_write"


def _load(d: Path) -> tuple[dict, dict, dict]:
    return (json.loads((d / "plan.json").read_text()), json.loads((d / "capture.json").read_text()),
            json.loads((d / "check.json").read_text()))


def summary(res: Path) -> dict[str, Any]:
    demo = json.loads((res / "demo.json").read_text())
    builds = json.loads((res / "builds.json").read_text())["builds"]
    runs = [n for n in ORDER if (res / n / "capture.json").is_file()]
    temps, vccint, vccaux, vccbram, alarms, verdicts = [], [], [], [], [], []
    for n in runs:
        cond = json.loads((res / n / "capture.json").read_text())["conditions"]
        verdicts.append(cond.get("verdict"))
        alarms += cond.get("alarms") or []
        for w in ("programmed", "armed", "done"):
            now = (cond.get(w) or {}).get("now") or {}
            temps.append(now["TEMPERATURE"]); vccint.append(now["VCCINT"]); vccaux.append(now["VCCAUX"]); vccbram.append(now["VCCBRAM"])
    costs = [demo[n]["parse"]["cost"] for n in runs]
    walls = [b["wall_s"] for b in builds.values()]
    wns = [b["wns_ns"] for b in builds.values()]
    cap_s = [demo[n]["seconds_program_capture"] for n in runs]
    plan0, cap0, _ = _load(res / HERO_RUN)
    b0 = builds[cap0["build"]["probeset"]]
    return {
        "runs": len(runs), "passed": sum(1 for n in runs if demo[n]["pass"]),
        "reused_runs": sum(1 for n in runs if demo[n].get("reused_build")),
        "builds": len(builds), "build_s_min": min(walls), "build_s_max": max(walls),
        "build_min_minutes": round(min(walls) / 60), "build_max_minutes": int(-(-max(walls) // 60)),
        "peak_mib_max": max(b["scope_anon_peak_mib"] for b in builds.values()),
        "wns_ns_min": min(wns), "wns_ns_max": max(wns),
        "power_w_max": max(b["power_total_w"] for b in builds.values()),
        "capture_s_min": min(cap_s), "capture_s_max": max(cap_s),
        # truncated, not rounded, to 5 decimals (0.000274675 is stated as 0.00027)
        "parse_cost_usd_min": math.floor(min(costs) * 1e5) / 1e5, "parse_cost_usd_max": math.floor(max(costs) * 1e5) / 1e5,
        "parse_model": demo[runs[0]]["parse"]["model"],
        "die_c_min": min(temps), "die_c_max": max(temps), "vccint_v": sorted(set(vccint)), "vccaux_v_min": min(vccaux),
        "vccaux_v_max": max(vccaux), "vccbram_v": sorted(set(vccbram)),
        "inside_roc_runs": sum(1 for v in verdicts if v == "inside ROC"), "alarms": len(alarms),
        "max_ports": plan0["fit"]["max_ports"],
        "hero": {"request": plan0["request"], "build_id": cap0["build"]["build_id"], "probeset": cap0["build"]["probeset"],
                 "build_s": b0["wall_s"], "wns_ns": b0["wns_ns"], "ports_used": len(plan0["ports"]),
                 "pre": plan0["window"]["requested"]["pre"], "post": plan0["window"]["requested"]["post"],
                 "depth": plan0["window"]["depth"]},
    }


def hero(res: Path) -> dict[str, Any]:
    plan, cap, chk = _load(res / HERO_RUN)
    req = plan["window"]["requested"]
    win = trim(cap, -int(req["pre"]), int(req["post"]))
    t0 = win["timebase"]["trigger_sample"]
    n = win["timebase"]["samples"]
    xs = [k - t0 for k in range(n)]
    sigs = []
    for c in win["channels"]:
        sg: dict[str, Any] = {"name": c["name"], "kind": "bit" if c["width"] == 1 else "bus", "v": c["samples"]}
        if c["width"] > 1:
            sg.update({"radix": "hex", "width": c["width"]})
        sigs.append(sg)
    builds = json.loads((res / "builds.json").read_text())["builds"]
    b = builds[cap["build"]["probeset"]]
    probes = ", ".join(f"{p['label']} ({p['path']})" for p in plan["probes"])
    trig = " AND ".join(c["text"] for c in plan["trigger"]["conditions"])
    answer = (res / HERO_RUN / "answer.txt").read_text().strip().splitlines()
    rb = cap["readback"]
    cond = cap["conditions"]
    steps = [
        f"Request, in plain English: \"{plan['request']}\"",
        f"Plan: probes {probes}; trigger {trig}; {req['pre']} cycles before and {req['post']} after; "
        f"{len(plan['ports'])} of the {plan['fit']['max_ports']} allowed probe ports.",
        f"Build: one logic analyser added to the design; Vivado 2026.1 build {cap['build']['build_id']}, "
        f"{b['wall_s']} s, every check passed; programmed into the board's SRAM.",
        "Over the UART shell: " + "; ".join(
            [f"before arming, {o['register']} written to 0x{o['value']:X}" for o in plan["setup"] if o["op"] == "write"]
            + [f"after arming, {o['register']} written to 0x{o['value']:X}" for o in plan["stimulus"] if o["op"] == "write"]) + ".",
    ]
    line = {name: next((l for l in answer if l.startswith(name + " ")), "") for name in (c["name"] for c in win["channels"])}
    data_lines = [line[c["name"]] for c in win["channels"]]
    caps = []
    for x in xs:
        if x < 0:
            caps.append(steps[min(len(steps) - 1, (x + int(req["pre"])) * len(steps) // int(req["pre"]))]
                        + f" (cycle {x}, before the trigger)")
        elif x == 0:
            caps.append(f"Cycle 0, the trigger: {trig}. " + answer[1])
        elif x < int(req["post"]):
            caps.append(f"Cycle {x}. Answer: " + data_lines[(x - 1) % len(data_lines)])
        else:
            caps.append(f"Cycle {x}, the end of the asked window. Read back over the shell: COUNT = 0x{rb['COUNT']:08X}; "
                        f"{'inside the recommended operating conditions' if cond.get('verdict') == 'inside ROC' else cond.get('verdict')}.")
    return {"unit": "cycle", "x": xs, "signals": sigs, "captions": caps,
            "source": {"run": f"results/50a_nl_debug/{HERO_RUN}", "check_pass": chk["pass"]}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--results", type=Path, default=ROOT / "results" / "50a_nl_debug")
    a = ap.parse_args(argv)
    (a.results / "summary.json").write_text(json.dumps(summary(a.results), indent=1) + "\n")
    (a.results / "hero.json").write_text(json.dumps(hero(a.results), indent=1) + "\n")
    print(a.results / "summary.json", a.results / "hero.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
