"""Drive the core directly (no LLM) through T1's stages to a bitstream, then program and bring up the board.

    python -m agent.core.smoke --record agent/tests/fixtures/t1_episode.json     # builds with Vivado (about 5 minutes)
    python -m agent.core.smoke --hardware                                          # also: ILA build, program, bring-up

Phase 1 (always): the scripted episode clarify -> ... -> bitstream through ``dispatch`` on real tools. Every step
runs through the security layer. With ``--record`` the model-side steps and the tool-side runs are written as
the CI replay fixture. Phase 2 (``--hardware``): ``build`` the ILA variant, ``program`` and ``bringup`` on the
attached board, with the policy checks active (stage, power_ok, budget); then a flash request, which must be
refused. Results: ``results/f2/core_smoke.json``. Gates are compared with ``results/ultrafast/``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from agent.core import Session, dispatch
from agent.core.replay import DETERMINISTIC, digest
from agent.core.runner import LocalRunner, RecordingRunner
from agent.core.session import ROOT
from agent.core.trace import Trace

DESIGN = "t1_dimmer_counter"
EPISODE: list[dict[str, Any]] = [
    {"tool": "stage_note", "arguments": {"stage": "clarify", "text": "T1: LED dimmer and push-button counter; spec.yaml is signed off."}},
    {"tool": "read_file", "arguments": {"path": "spec.yaml", "max_bytes": 4000}},
    {"tool": "list_files", "arguments": {"path": "rtl"}},
    {"tool": "stage_note", "arguments": {"stage": "board-and-device-planning", "text": "Pins and standards from the master XDC; one 100 MHz clock."}},
    {"tool": "search_docs", "arguments": {"query": "clock capable input global buffer", "k": 3, "sections": ["clocking"]}, "bank": True},
    {"tool": "load_skill", "arguments": {"sections": ["clocking"]}, "bank": True},
    {"tool": "stage_note", "arguments": {"stage": "rtl-design-creation", "text": "RTL exists; lint, simulate, formal."}},
    {"tool": "lint", "arguments": {}},
    {"tool": "simulate", "arguments": {"sim": "icarus"}},
    {"tool": "formal", "arguments": {}},
    {"tool": "stage_note", "arguments": {"stage": "constraints", "text": "Check design.xdc against the board."}},
    {"tool": "check_constraints", "arguments": {}},
    {"tool": "stage_note", "arguments": {"stage": "synthesis", "text": "Build to post_synth."}},
    {"tool": "build", "arguments": {"until": "synth"}},
    {"tool": "gates", "arguments": {"kind": "stages"}, "allow_fail": True},
    {"tool": "report", "arguments": {"name": "utilization_synth.rpt", "max_bytes": 3000}},
    {"tool": "stage_note", "arguments": {"stage": "implementation", "text": "Build to the bitstream."}},
    {"tool": "build", "arguments": {"until": "bitstream"}},
    {"tool": "gates", "arguments": {"kind": "stages"}},
    {"tool": "stage_note", "arguments": {"stage": "power-closure", "text": "Read report_power."}},
    {"tool": "report", "arguments": {"name": "power.rpt", "max_bytes": 3000}},
]
CAPTURE = {"build": [f"designs/{DESIGN}/build/{v}/{f}" for v in ("base", "ila")
                     for f in ("run.json", "utilization_synth.rpt", "power.rpt")],
           "gates": [f"designs/{DESIGN}/build/base/gates.json"]}


def short(res: dict) -> dict:
    return {"tool": res["tool"], "stage": res["stage"], "ok": res["ok"], "refused": res["refused"],
            "seconds": res["seconds"], "returncode": res.get("returncode"), "summary": res["output"][:200].replace("\n", " | ")}


def same_gates(new: dict, old: dict) -> dict:
    a = {k: v for k, v in new.items() if k != "build_dir"}
    b = {k: v for k, v in old.items() if k != "build_dir"}
    return {"identical": a == b, "differences": sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--record", type=Path, help="write the CI replay episode here")
    ap.add_argument("--hardware", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "f2" / "core_smoke.json")
    ap.add_argument("--skip-formal", action="store_true")
    a = ap.parse_args(argv)
    design = ROOT / "designs" / DESIGN
    bank = None
    try:
        from agent.core.bank import LocalBank
        bank = LocalBank()
    except Exception as e:
        print(f"smoke: no knowledge bank ({type(e).__name__}); the bank steps will be recorded as failed", file=sys.stderr)
    rec = RecordingRunner(LocalRunner(), CAPTURE)
    audit_path = design / "build" / "audit.jsonl"
    audit_path.unlink(missing_ok=True)
    trace_path = ROOT / "build" / "f2" / "smoke_trace.jsonl"
    trace_path.unlink(missing_ok=True)
    s = Session(design=design, runner=rec, bank=bank, trace=Trace(trace_path, "smoke"))
    steps, report, t0 = [], [], time.monotonic()
    for st in EPISODE:
        if a.skip_formal and st["tool"] == "formal":
            continue
        res = dispatch(s, st["tool"], st["arguments"])
        report.append(short(res))
        print(f"[{res['stage']}] {st['tool']} -> ok={res['ok']} ({res['seconds']} s)", flush=True)
        if not res["ok"] and not st.get("allow_fail"):
            print(res["output"][:1500])
            return 1
        exp: dict[str, Any] = {"ok": res["ok"], "refused": res["refused"]}
        if st["tool"] in DETERMINISTIC:
            exp["digest"] = digest(res)
        steps.append({**{k: v for k, v in st.items() if k in ("tool", "arguments", "bank")}, "expect": exp})
    g = json.loads((design / "build" / "base" / "gates.json").read_text())
    ref = json.loads((ROOT / "results" / "ultrafast" / "t1_dimmer_counter_base.json").read_text())["gates"]
    phase1 = {"wall_s": round(time.monotonic() - t0, 1), "steps": report, "gates_pass": g["pass"],
              "first_failed_stage": g["first_failed_stage"], "gates_vs_results_ultrafast": same_gates(g, ref)}
    out: dict[str, Any] = {"design": f"designs/{DESIGN}", "build_stamp": g["build_stamp"], "phase1_bitstream": phase1}
    if a.record:
        a.record.parent.mkdir(parents=True, exist_ok=True)
        a.record.write_text(json.dumps({"design": DESIGN, "recorded": time.strftime("%Y-%m-%d"), "steps": steps,
                                        "runs": rec.records}, indent=1) + "\n")
        print("recorded", a.record)
    if a.hardware:
        n0 = len(rec.records)
        hw_steps = [
            ("stage_note", {"stage": "configuration-and-debug", "text": "ILA build, program (SRAM), bring-up."}),
            ("build", {"until": "bitstream", "variant": "ila"}),
            ("gates", {"kind": "stages", "variant": "ila"}),
            ("program", {"variant": "base"}),
            ("bringup", {}),
        ]
        hwrep = []
        for tool, args in hw_steps:
            res = dispatch(s, tool, args)
            hwrep.append({**short(res), **({"program": res.get("program")} if tool == "program" else {}),
                          **({"bringup_pass": (res.get("bringup") or {}).get("pass")} if tool == "bringup" else {}),
                          **({"power_ok": res.get("power_ok")} if "power_ok" in res else {})})
            print(f"[{res['stage']}] {tool} -> ok={res['ok']} ({res['seconds']} s)", flush=True)
            if not res["ok"]:
                print(res["output"][:1500])
                break
        flash = dispatch(s, "program", {"target": "flash"})
        out["phase2_hardware"] = {"steps": hwrep, "hw_budget_used": s.hw.used, "hw_budget": s.hw.budget,
                                  "flash_request": {"refused": flash["refused"], "rule": flash.get("rule")}}
    out["audit_records"] = len(s.audit.records)
    out["refusals_logged"] = len(s.audit.refusals())
    out["trace_records"] = len(s.trace.records)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print("wrote", a.out)
    ok = phase1["gates_pass"] and (not a.hardware or all(x["ok"] for x in out["phase2_hardware"]["steps"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
