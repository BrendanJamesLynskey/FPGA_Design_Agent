#!/usr/bin/env python3
"""The brief 59A board run: transaction programs on the Nexys A7 (SRAM only), with operating conditions as evidence.

    python3 axi_tx/host/run_board.py --plan axi_tx/programs/board_plan.yaml --json results/59a_axi_tx/board_run.json

The caller holds _handoff/board.lock. Steps:
  1. power_ok for the design's base build; discover the one board (by cable serial) and its UART
  2. operating conditions over JTAG (tools/board_conditions.tcl: die temperature, VCCINT, VCCAUX, VCCBRAM and the XADC's
     own min/max registers since configuration)
  3. program SRAM (flow/program.py: build stamp and power gate checked again; never flash)
  4. for each run of the plan: the program through the UART shell (axi_tx/host/host.py), then the fabric XADC readout
     (current, min and max codes, and the alarm latch, whose thresholds sit inside the recommended operating conditions)
     and, where the AMD AXI protocol checker is built in, its sticky pc_asserted
  5. operating conditions over JTAG again; a verdict: inside or outside the recommended operating conditions (ROC)
Every result is compared with the simulation of the same program where one exists (build/59a/sim/<tag>.json, or
results/59a_axi_tx/sim/<tag>.json): the transaction log against the model, and for the peripheral target, whose RTL is
the same on both, the digest (which includes every transaction's latency) must be identical.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from axi_tx.host import host, model, regs  # noqa: E402
from axi_tx.host.program import assemble  # noqa: E402
from flow import hw, hw_discover, program  # noqa: E402
from shell.host.fpga_shell import FpgaShell, design_id_text  # noqa: E402
from tools.vhdl_board_run import ROC, conditions  # noqa: E402

DESIGN = ROOT / "designs" / "b59a_axi_tx"
DESIGN_ID = 0x4158_5431          # "AXT1"


def xadc_temp(code: int) -> float:
    return round(code * 503.975 / 4096 - 273.15, 2)


def xadc_v(code: int) -> float:
    return round(code * 3.0 / 4096, 4)


def fabric_conditions(sh: FpgaShell, clear: bool = False) -> dict[str, Any]:
    """The fabric's own XADC readout (current, max and min since configuration) and the alarm latch."""
    c = [sh.read(regs.WINDOW + regs.XADC_BASE + i) & 0xFFF for i in range(12)]
    alarms = sh.read(regs.WINDOW + regs.XADC_ALARMS)
    if clear:
        sh.write(regs.WINDOW + regs.XADC_ALARMS, 0x1F)
    conv = [xadc_temp if n.endswith("temp") else xadc_v for n in regs.XADC_CODES]
    vals = {n: f(x) for n, f, x in zip(regs.XADC_CODES, conv, c)}
    return {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **vals,
            "alarms_latched": [n for b, n in regs.ALARM_BITS.items() if alarms >> b & 1]}


def fabric_verdict(samples: list[dict[str, Any]]) -> dict[str, Any]:
    bad = []
    keymap = {"temp": "TEMPERATURE", "vccint": "VCCINT", "vccaux": "VCCAUX", "vccbram": "VCCBRAM"}
    for s in samples:
        for pre in ("", "max_", "min_"):
            for k, rk in keymap.items():
                lo, hi = ROC[rk]
                v = s.get(pre + k)
                if v is not None and ((lo is not None and v < lo) or (hi is not None and v > hi)):
                    bad.append(f"{s['time']} {pre}{k}={v}")
        if s.get("alarms_latched"):
            bad.append(f"{s['time']} alarms {s['alarms_latched']}")
    return {"inside_roc": not bad, "outside": bad}


def sim_record(tag: str) -> dict[str, Any] | None:
    for d in (ROOT / "build" / "59a" / "sim", ROOT / "results" / "59a_axi_tx" / "sim"):
        f = d / f"{tag}.json"
        if f.is_file():
            return json.loads(f.read_text())
    return None


def jtag_conditions(out: Path, tag: str, wait_s: int = 1800) -> dict[str, Any]:
    """tools/board_conditions.tcl, waiting (up to wait_s) for a moment with no other Vivado on the PC (flow/hw.py preflight)."""
    import subprocess
    t0 = time.monotonic()
    while True:
        busy = subprocess.run(["pgrep", "-x", "vivado"], capture_output=True).returncode == 0
        if not busy:
            try:
                return conditions(out, tag)
            except hw.HwError as e:
                if "another Vivado" not in str(e) or time.monotonic() - t0 > wait_s:
                    raise
        elif time.monotonic() - t0 > wait_s:
            return {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "unavailable": "another Vivado ran for the whole wait"}
        time.sleep(15)


def summarise(r: dict[str, Any]) -> dict[str, Any]:
    """The fields a board run and its simulation are compared on."""
    keys = ("n_txn", "digest", "sb_checked", "sb_mism", "sb_unchecked", "exp_mism", "resp_mism", "cycles")
    s = {k: r[k] for k in keys}
    s["lite_rules"] = r["lite_rules"]["counts"]
    s["stream_rules"] = r["stream_rules"]["counts"]
    s["sink"] = {k: v for k, v in r["sink"].items() if k != "first_mism"}
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", type=Path, default=ROOT / "axi_tx" / "programs" / "board_plan.yaml")
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--board", default="nexys_a7_100t")
    a = ap.parse_args(argv)
    plan = yaml.safe_load(a.plan.read_text())
    out = ROOT / "build" / "59a" / "board"
    out.mkdir(parents=True, exist_ok=True)
    res: dict[str, Any] = {"design": str(DESIGN.relative_to(ROOT)), "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "plan": a.plan.name, "runs": []}
    commit, dirty = hw.git_commit()
    res["git_commit"], res["git_dirty"] = commit, dirty
    pw = hw.power_ok(DESIGN / "build" / "base", a.board)
    res["power_ok"] = {k: pw.get(k) for k in ("pass", "total_w", "junction_c", "source", "why")}
    if not pw["pass"]:
        raise SystemExit(f"power_ok failed: {pw.get('why')}")
    disc = hw_discover.discover(a.board, out / "discover")
    board = hw.load_board(a.board)
    res["vivado_version"] = disc.get("vivado_version")
    res["conditions_jtag"] = [conditions(out, "before")]
    pr = program.program(DESIGN, "base", board["name"], out / "program")
    res["build_stamp"], res["build_id"] = pr["build_stamp"], pr.get("build_id")
    fab: list[dict[str, Any]] = []
    ok = True
    with FpgaShell.open(board["uart"]) as sh:
        ident = sh.identify()
        res["identify"] = {"design_id": design_id_text(ident["design_id"]), "build_stamp": f"{ident['build_stamp']:08x}"}
        if ident["design_id"] != DESIGN_ID or f"{ident['build_stamp']:08x}" != res["build_stamp"]:
            raise SystemExit("wrong design or stale bitstream on the board")
        info = sh.read(regs.WINDOW + regs.SYS_INFO)
        has_pc = True                     # designs/b59a_axi_tx always builds the AMD checker in (0x50)
        res["sys_info"] = info
        fab.append(fabric_conditions(sh, clear=True) | {"at": "start"})
        sync = host.SyncHost(sh)
        for item in plan["runs"]:
            for rep in range(item.get("repeat", 1)):
                item.setdefault("program", Path(item.get("path", "program")).stem)
                src = Path(item["path"]) if "path" in item else ROOT / "axi_tx" / "programs" / f"{item['program']}.yaml"
                prog = assemble(src)
                prog.lite_bug = item.get("lite_bug", "none")
                prog.stream_bug = item.get("stream_bug", "none")
                tag = item.get("tag", item["program"])
                t0 = time.monotonic()
                if has_pc:
                    sh.write(regs.WINDOW + regs.AMD_PC_STATUS, 1)          # clear the cross-check's sticky flag
                r = sync.run(host.run_program(prog))
                secs = round(time.monotonic() - t0, 2)
                pred = model.run(prog)
                run: dict[str, Any] = {"tag": tag, "repeat": rep, "program": item["program"], "lite_bug": prog.lite_bug,
                                       "stream_bug": prog.stream_bug, "seconds": secs, "status": r["status"],
                                       "summary": summarise(r), "lite_rules": r["lite_rules"],
                                       "stream_rules": r["stream_rules"], "sink": r["sink"],
                                       "lite_mon": r["lite_mon"], "stream_mon": r["stream_mon"],
                                       "model_compare": model.compare(pred, r["log"]), "model_counts": pred.counts,
                                       "digest_check": r.get("digest_check"),
                                       "first_mismatch": {k: r[k] for k in ("first_mismatch_txn", "first_mismatch_addr",
                                                                            "first_mismatch_expected", "first_mismatch_got")},
                                       "capture": r["capture"], "log": r["log"][:64]}
                if has_pc:
                    run["amd_pc_asserted"] = bool(sh.read(regs.WINDOW + regs.AMD_PC_STATUS) & 1)
                sim = sim_record(tag)
                if sim is not None:
                    keys = ("n_txn", "digest", "sb_checked", "sb_mism", "sb_unchecked", "exp_mism", "resp_mism", "cycles")
                    run["sim_compare"] = {k: {"board": r[k], "sim": sim.get(k), "equal": r[k] == sim.get(k)} for k in keys}
                    run["sim_compare"]["lite_rules_equal"] = r["lite_rules"]["counts"] == sim["lite_rules"]["counts"]
                    run["sim_compare"]["stream_rules_equal"] = r["stream_rules"]["counts"] == sim["stream_rules"]["counts"]
                    # transaction by transaction (the logged first 256): kind, address, response and latency in cycles;
                    # data too, except where the model cannot know it (the peripheral's free-running COUNT, memory words
                    # this run did not write)
                    unknown = {i for i, t in enumerate(pred.txns) if t["data"] is None}
                    diffs = []
                    for i, (b, s_) in enumerate(zip(r["log"], sim.get("log", []))):
                        f = [k for k in ("kind", "addr", "resp", "latency") if b[k] != s_[k]]
                        if i not in unknown and b["data"] != s_["data"]:
                            f.append("data")
                        if f:
                            diffs.append({"txn": i, "fields": f})
                    run["sim_compare"]["log"] = {"compared": min(len(r["log"]), len(sim.get("log", []))),
                                                 "data_not_compared": len([i for i in unknown if i < 256]),
                                                 "differences": len(diffs), "first": diffs[:3]}
                exp = item.get("expect", {})
                fired = sorted(k for k, v in r["lite_rules"]["counts"].items() if v)
                sfired = sorted(k for k, v in r["stream_rules"]["counts"].items() if v)
                checks = {"done": "done" in r["status"]["flags"] and "hang" not in r["status"]["flags"],
                          "lite_rules": fired == sorted(exp.get("lite_rules", [])),
                          "stream_rules": sfired == sorted(exp.get("stream_rules", [])),
                          "model_match": run["model_compare"]["match"] or bool(exp.get("model_differs"))}
                if "sb_mism" in exp:
                    checks["sb_mism"] = (r["sb_mism"] > 0) == bool(exp["sb_mism"])
                if "sink_last_mism" in exp:
                    checks["sink_last_mism"] = (r["sink"]["last_mism"] > 0) == bool(exp["sink_last_mism"])
                run["checks"] = checks
                run["pass"] = all(checks.values())
                ok &= run["pass"]
                fab.append(fabric_conditions(sh, clear=False) | {"at": f"after {tag} #{rep}"})
                res["runs"].append(run)
                print(f"run_board: {tag} #{rep}: {'PASS' if run['pass'] else 'FAIL'} {checks} rules={fired}{sfired} "
                      f"{secs}s digest=0x{r['digest']:08x}", flush=True)
        fab.append(fabric_conditions(sh, clear=False) | {"at": "end"})
    res["conditions_fabric"] = fab
    res["conditions_jtag"].append(jtag_conditions(out, "after"))
    from tools.vhdl_board_run import verdict
    res["verdict_jtag"] = verdict(res["conditions_jtag"])
    res["verdict_fabric"] = fabric_verdict(fab)
    res["inside_roc"] = res["verdict_jtag"]["inside_roc"] and res["verdict_fabric"]["inside_roc"]
    res["roc_limits"] = {k: list(v) for k, v in ROC.items()}
    res["note"] = "XADC: about 1 MSPS across channels; no nanosecond droop; alarms latched in fabric between reads"
    res["pass"] = ok
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"pass": ok, "inside_roc": res["inside_roc"], "runs": len(res["runs"])}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
