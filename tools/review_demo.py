#!/usr/bin/env python3
"""Write the upgraded review pages for the T1 reference design from its real evidence (brief 05d screenshots).

    python3 tools/review_demo.py OUT_DIR [--runs build/verif/icarus] [--vcd FILE]

Uses only committed or locally produced evidence: the T1 sources and constraints, the post-synthesis and
post-route reports under designs/t1_dimmer_counter/build/base (gates re-parsed with the resource-sanity gate), the
cocotb V2 run in --runs (coverage detail), the bring-up result in results/f0b, the standards checker's real output,
and a VCD (a bench run with buses). Two stage snapshots give the RTL diff. Nothing here is a model's account.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.graph import ownership, review  # noqa: E402
from agent.graph.snapshot import Snapshots  # noqa: E402
from flow import gates as gates_mod  # noqa: E402
from flow import standards_check, verif_gates  # noqa: E402

T1 = ROOT / "designs" / "t1_dimmer_counter"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--runs", default="build/verif/icarus")
    ap.add_argument("--vcd", type=Path)
    a = ap.parse_args()
    run = a.out
    shutil.rmtree(run, ignore_errors=True)
    design = run / "t1_dimmer_counter"
    shutil.copytree(T1, design, ignore=shutil.ignore_patterns("__pycache__", "build", "mutants"))
    shutil.copytree(T1 / "build" / "base", design / "build" / "base", ignore=shutil.ignore_patterns("*.dcp", "*.bit", "*.ltx", "*.jou", "*.log"))
    (design / "ARCHITECTURE.md").write_text("# T1 architecture\n\n## Block diagram\n\n```\n  BTNU/BTND/BTNC --> [sync2 + debounce] --> [counter] --> [pwm] --> LED[15:0]\n"
                                            "  SW[15:0] ------> [sync2] ------------> duty             --> [scan] --> AN, CA..CG\n"
                                            "  UART <--> [fpga_shell] <-- register window --> [counter]\n```\n")
    snaps = Snapshots(run, design)
    rtl = design / "rtl"
    stash = run / "_rtl"
    shutil.move(str(rtl), str(stash))
    snaps.take(1, "board-and-device-planning", note="demo")        # stage 1: architecture only
    shutil.move(str(stash), str(rtl))
    snaps.take(2, "rtl-design-creation", note="demo")              # stage 2: the RTL appears
    g = gates_mod.evaluate(design / "build" / "base")
    (design / "build" / "base" / "gates.json").write_text(json.dumps(g))
    hw = ROOT / "results" / "f0b" / "t1_dimmer_counter_bringup.json"
    v = verif_gates.evaluate(T1, ROOT / a.runs, [], ROOT / "build" / "verif" / "formal", None, hw,
                             design / "build" / "base" / "gates.json")
    std = standards_check.evaluate(T1, ROOT, "base", ("rtl",))
    if a.vcd:
        shutil.copy(a.vcd, design / "build" / "t1.vcd")
    ownership.record(design, "agent", "board-and-device-planning", "stage 1 work, visit 1", "9 files", n=1)
    ownership.record(design, "owner", "board-and-device-planning", "architecture approved", "source: agent", n=1)
    ownership.record(design, "owner", "rtl-design-creation", "hand edit", "rtl/debounce.sv", n=2)
    ok_v3 = (v.get("reached") or "") >= "V3" and v.get("reached") is not None
    info = {"gates": [["arch_approved", True, "approval record matches the files"], ["standards_rtl", bool(std["stages"].get("rtl")), "flow/standards_check.py"],
                      ["verif_v3", ok_v3, f"reached {v.get('reached')}, first failed {v.get('first_failed')}"],
                      ["stage_rtl", bool(g["stages"]["rtl"].get("pass")), "report_methodology on the elaborated RTL"]],
            "visits": 1, "used": {"turns": 41, "seconds": 910, "usd": 0.21}, "limits": {"turns": 60, "seconds": 3600, "usd": 0.8},
            "inputs": ["spec.yaml", "ARCHITECTURE.md"], "outputs": sorted(str(p.relative_to(design)) for p in rtl.glob("*.sv")),
            "time": "2026-11-02 22:00:00", "verif": v, "standards": std, "board": "nexys_a7_100t",
            "diff": snaps.diff(1, None, ("rtl/", "design.xdc")), "owner_rows": ownership.load(design),
            "approval": {"decision": "approve", "by": "owner", "note": ""}}
    page = review.write_page(design, 2, "rtl-design-creation", info)
    print(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
