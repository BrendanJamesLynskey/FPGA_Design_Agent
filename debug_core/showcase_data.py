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
    latched = [((json.loads((res / n / "capture.json").read_text())["conditions"].get(w) or {}).get("max") or {}).get("TEMPERATURE")
               for n in runs for w in ("programmed", "armed", "done")]
    refused_builds = [k for k, b in builds.items() if k not in {json.loads((res / n / "capture.json").read_text())["build"]["probeset"] for n in runs}]
    return {
        "runs_table": run_table(res, runs, demo, builds),
        "trust": trust(res),
        "die_c_latched_max": max(x for x in latched if x is not None),
        "power_w_min": min(b["power_total_w"] for b in builds.values()),
        "builds_used": len(builds) - len(refused_builds), "builds_refused": len(refused_builds),
        "cost_usd_lo_rounded": math.floor(min(costs) * 1e4) / 1e4, "cost_usd_hi_rounded": math.ceil(max(costs) * 1e4) / 1e4,
        "readback_runs": sum(1 for n in runs if json.loads((res / n / "capture.json").read_text()).get("readback")),
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


WHAT = {"t1_count_write": "a register write over the serial link", "t1_pwm_period": "one dimmer (PWM) period",
        "t1_sync_byte": "the serial sync byte, on a rising edge", "t1_or_flags": "either of two edges (OR)",
        "t1_reuse_rise": "a write, on a build made for another request"}


def run_table(res: Path, runs: list[str], demo: dict, builds: dict) -> list[dict[str, Any]]:
    out = []
    for n in runs:
        plan, cap, chk = _load(res / n)
        b = builds[cap["build"]["probeset"]]
        out.append({"run": n, "capture": f"results/50a_nl_debug/{n}/capture.json", "what": WHAT.get(n, n),
                    "trigger": " AND ".join(c["text"] for c in plan["trigger"]["conditions"]) if plan["trigger"]["combine"] == "AND"
                    else " OR ".join(c["text"] for c in plan["trigger"]["conditions"]),
                    "build": "reused" if demo[n].get("reused_build")
                    else f"new{' (rebuilt)' if _rebuilt(cap['build']['probeset'], runs, res, builds) else ''}, {b['wall_s']} s",
                    "capture_s": demo[n]["seconds_program_capture"],
                    "readback": ", ".join(f"{k} 0x{v:X}" for k, v in (cap.get("readback") or {}).items()) or "none",
                    "result": "matched" if chk["pass"] else "did not match"})
    return out


def _rebuilt(probeset: str, runs: list[str], res: Path, builds: dict) -> bool:
    """A build is a rebuild when another build of the same probes (same pins) exists that no run used (a refused layout)."""
    used = {json.loads((res / n / "capture.json").read_text())["build"]["probeset"] for n in runs}
    pins = {p["pins"] for p in builds[probeset]["probes"]}
    return any(k not in used and {p["pins"] for p in b["probes"]} == pins for k, b in builds.items())


def trust(res: Path) -> dict[str, Any]:
    """Examples computed now by the repository's own code from committed files (the T1 RTL and a committed capture)."""
    from debug_core.answer import unquoted_numbers
    from debug_core.rtl_index import RtlIndex
    idx = RtlIndex.from_design(ROOT / "designs" / "t1_dimmer_counter")
    amb = idx.resolve("cnt")
    plan, cap, _ = _load(res / HERO_RUN)
    req = plan["window"]["requested"]
    asked = trim(cap, -int(req["pre"]), int(req["post"]))
    # the good sentence is the answer's own line for count; the bad one changes its last value
    good = next(l for l in (res / HERO_RUN / "answer.txt").read_text().splitlines() if l.startswith("count "))
    last = [c for c in cap["channels"] if c["name"] == "count"][0]["samples"][-1]
    wrong = last ^ 0x5115 if last ^ 0x5115 not in set([c for c in cap["channels"] if c["name"] == "count"][0]["samples"]) else last + 1
    bad = good.replace(f"0x{last:04X}", f"0x{wrong:04X}")
    if unquoted_numbers(good, cap, asked) or not unquoted_numbers(bad, cap, asked) or good == bad:
        raise ValueError("the answer-check example no longer behaves as the page says (the good line must pass, the bad fail)")
    addr = next(p for p in plan["probes"] if p["label"] == "addr")
    k0 = cap["timebase"]["trigger_sample"]
    ch = {c["name"]: c["samples"] for c in cap["channels"]}
    return {"ambiguous_query": "cnt", "ambiguous_kind": amb.kind, "ambiguous_candidates": ", ".join(amb.candidates),
            "ambiguous_n": len(amb.candidates),
            "phrase": "the shell's ADDR byte", "phrase_parsed_as": addr["requested_as"], "phrase_resolved_to": addr["path"],
            "phrase_pins": addr["pins"],
            "check_good": good, "check_good_refused": ", ".join(unquoted_numbers(good, cap, asked)) or "none",
            "check_bad": bad, "check_bad_refused": ", ".join(unquoted_numbers(bad, cap, asked)),
            "trigger_win_wr": ch["win_wr"][k0], "trigger_addr": f"0x{ch['addr'][k0]:02X}",
            "count_before": f"0x{ch['count'][k0]:04X}", "count_after": f"0x{ch['count'][k0 + 1]:04X}"}


def hero(res: Path) -> dict[str, Any]:
    """The kit's staged wave: five stages with their real numbers, the samples of the asked window revealed during the
    capture stage, marks on the trigger sample and on the counter's change, captions for the narrative as stages."""
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
    ch = {c["name"]: c["samples"] for c in win["channels"]}
    builds = json.loads((res / "builds.json").read_text())["builds"]
    b = builds[cap["build"]["probeset"]]
    trig = " AND ".join(c["text"] for c in plan["trigger"]["conditions"])
    answer = (res / HERO_RUN / "answer.txt").read_text().strip().splitlines()
    line = {nm: next((l for l in answer if l.startswith(nm + " ")), "") for nm in ch}
    rb = cap["readback"]
    demo = json.loads((res / "demo.json").read_text())[HERO_RUN]
    writes = lambda ops: ", ".join(f"{o['register']} = 0x{o['value']:X}" for o in ops if o["op"] == "write")
    ci = next(k for k in range(t0, n - 1) if ch["count"][k + 1] != ch["count"][k]) + 1   # sample index of the change
    stages = [
        {"name": "Request", "fact": "in words", "phase": "before",
         "captions": [f"Request, in plain English: \"{plan['request']}\""]},
        {"name": "Plan", "fact": f"{len(plan['probes'])} signals, {len(plan['ports'])} of {plan['fit']['max_ports']} ports", "phase": "before",
         "captions": ["Plan: " + "; ".join(f"{p['requested_as']} is {p['path']}" for p in plan["probes"]) + f". Trigger: {trig}. "
                      f"A {plan['window']['depth']}-sample window, the smallest that holds the {req['pre']} cycles before and "
                      f"{req['post']} after that were asked for."]},
        {"name": "Build", "fact": f"{b['wall_s']} s, ID {cap['build']['build_id']}", "phase": "before",
         "captions": [f"Build: the logic analyser added to the design, Vivado 2026.1, {b['wall_s']} s, every check passed "
                      f"(worst setup slack {b['wns_ns']} ns). Programmed into the board's memory; build ID "
                      f"{cap['build']['build_id']} read back over JTAG before arming."]},
        {"name": "Arm and capture", "fact": trig, "phase": "during",
         "captions": [f"Armed. Over the serial link: before arming {writes(plan['setup'])}; after arming {writes(plan['stimulus'])}, "
                      "the write that fires the trigger."]},
        {"name": "Answer", "fact": f"matched; read back 0x{rb['COUNT']:X}" if rb.get("COUNT") is not None else "matched", "phase": "after",
         "captions": [f"Answer: {line['count']}", f"Read back over the serial link: COUNT = 0x{rb['COUNT']:08X}, the value the "
                      f"capture shows. Programming and capture took {demo['seconds_program_capture']} s, inside the recommended "
                      "operating conditions."]},
    ]
    caps: list[str | None] = [None] * n
    caps[0] = f"Capture: the {req['pre']} cycles before the trigger come from the analyser's buffer, recorded before the trigger fired."
    caps[t0] = f"Cycle 0, the trigger sample: {trig} (win_wr = {ch['win_wr'][t0]}, addr = 0x{ch['addr'][t0]:02X})."
    caps[ci] = (f"Cycle {xs[ci]}: count changes from 0x{ch['count'][ci - 1]:04X} to "
                         f"0x{ch['count'][ci]:04X}, one clock after the write strobe: the register loads on the clock "
                         "edge that ends it.")
    alt = (f"Waveform of win_wr, addr and count from cycle {xs[0]} to {xs[-1]} around the trigger: win_wr is 1 only at cycle 0, "
           f"addr holds 0x{ch['addr'][t0]:02X}, count is 0x{ch['count'][0]:04X} up to cycle 0 and 0x{ch['count'][-1]:04X} from "
           f"cycle {xs[ci]}.")
    return {"unit": "cycle", "x": xs, "signals": sigs, "captions": caps, "stages": stages, "tick": 8, "alt": alt,
            "marks": [{"x": 0, "label": "trigger, cycle 0"},
                      {"x": xs[ci], "signal": "count",
                       "label": f"0x{ch['count'][ci - 1]:04X} to 0x{ch['count'][ci]:04X}"}],
            "source": {"run": f"results/50a_nl_debug/{HERO_RUN}", "check_pass": chk["pass"]}}


def render(res: Path) -> dict[str, str]:
    """The two files' exact text (a test compares it with the committed files, byte for byte)."""
    return {"summary.json": json.dumps(summary(res), indent=1) + "\n", "hero.json": json.dumps(hero(res), indent=1) + "\n"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--results", type=Path, default=ROOT / "results" / "50a_nl_debug")
    a = ap.parse_args(argv)
    for name, text in render(a.results).items():
        (a.results / name).write_text(text)
    print(a.results / "summary.json", a.results / "hero.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
