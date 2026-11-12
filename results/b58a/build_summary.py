"""summary.json of the recorded KR260 build, generated from the build's own records in results/b58a/build/ (gates.json,
run.json, manifest.json, utilization.rpt, io_paths_route.txt): nothing in it is written by hand, so the failed gates
listed are exactly the ones gates.json fails. Re-run after recording a build:

    python3 results/b58a/build_summary.py           # write results/b58a/build/summary.json
    python3 results/b58a/build_summary.py --check   # exit 1 if the committed summary differs
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "build"


def failed_gates(g: dict) -> list[str]:
    """Every gate gates.json fails, in its own order (stage gates included)."""
    out = [k for k, v in g["gates"].items() if v is False]
    for st in g.get("stages", {}).values():
        out += [k for k, v in (st.get("gates") or {}).items() if v is False and k not in out]
    return out


def util(text: str) -> dict:
    rows = {}
    for name in ("CLB LUTs", "CLB Registers", "Block RAM Tile", "BUFGCE", "MMCM"):
        m = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*([\d.]+)\s*\|.*?\|\s*([\d.]+)\s*\|\s*([\d.<]+)\s*\|$", text, re.M)
        if m:
            rows[name] = {"used": float(m.group(1)), "available": float(m.group(2)),
                          "pct": float(m.group(3).lstrip("<"))}
    return rows


def rgmii(text: str) -> dict:
    worst: dict[str, float] = {}
    for line in text.splitlines():
        f = line.split("|")
        if f[0] != "IO" or not re.match(r"[ab]_(rxd|rx_ctl|txd|tx_ctl)", f[1]) or not f[4]:
            continue
        k = f"{f[1][0]}_{'rx' if '_rx' in f[1] else 'tx'}_{'setup' if f[3] == 'max' else 'hold'}"
        worst[k] = min(worst.get(k, float(f[4])), float(f[4]))
    return dict(sorted(worst.items()))


def summary() -> dict:
    g = json.loads((HERE / "gates.json").read_text())
    run = json.loads((HERE / "run.json").read_text())
    man = json.loads((HERE / "manifest.json").read_text())
    t = g["timing"]
    failed = failed_gates(g)
    io = rgmii((HERE / "io_paths_route.txt").read_text())
    tx_fail = [k for k, v in io.items() if "_tx_" in k and v < 0]
    note = [f"{len(failed)} gate(s) fail: {', '.join(failed)}." if failed else "Every gate passes."]
    if tx_fail:
        note.append("Setup or hold fails on the RGMII transmit pins; reported, not waived.")
    if any("cdc" in k for k in failed):
        note.append("A CDC gate fails: see cdc.rpt.")
    return {
        "design": "designs/b58a_trigger", "top": g["top"], "part": "xck26-sfvc784-2LV-c",
        "vivado": f"{g['vivado_version']} (Basic tier)", "build_id": man["build_id"], "wall_s": run.get("wall_s"),
        "run": run,
        "timing_post_route": {"source": "gates.json timing (timing_summary.rpt)", "wns_ns": t["wns_ns"],
                              "tns_ns": t["tns_ns"], "tns_failing_endpoints": t.get("tns_failing_endpoints"),
                              "whs_ns": t["whs_ns"], "ths_ns": t["ths_ns"],
                              "ths_failing_endpoints": t.get("ths_failing_endpoints"),
                              "all_constraints_met": bool(t.get("timing_met"))},
        "rgmii_io_slack_ns": {"source": "io_paths_route.txt, worst per port, direction and check", **io},
        "rgmii_constraints": {
            "rx": "centre-aligned, PHY RX delay on (register 20.7 = 1; the 88E1111 datasheet's 1.2/1.2 ns); -max 2.8, "
                  "-min 1.2 on both edges; IDELAYE3 1000 ps on each data input",
            "tx": "edge-aligned forwarded TXC, PHY TX delay on (register 20.1 = 1); the 88E1111 datasheet window (a change "
                  "up to 0.9 ns after its edge, no earlier than 1.3 ns before the next) less an assumed 0.1 ns board "
                  "skew: -max 3.2, -min +1.2 on both edges"},
        "utilisation": util((HERE / "utilization.rpt").read_text()),
        "power": {"total_on_chip_w": g["power"]["total_w"], "junction_c": g["power_environment"]["junction_c"],
                  "environment": "still air, no heat sink, 40 C ambient: the pessimistic bound (boards/kr260/board.yaml)"},
        "first_failed_stage": g.get("first_failed_stage"),
        "gates_failed": failed,
        "note": " ".join(note),
    }


def main() -> int:
    text = json.dumps(summary(), indent=1) + "\n"
    out = HERE / "summary.json"
    if "--check" in sys.argv:
        if out.read_text() != text:
            print("results/b58a/build/summary.json is stale: run python3 results/b58a/build_summary.py")
            return 1
        return 0
    out.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
