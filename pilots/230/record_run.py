#!/usr/bin/env python3
"""Brief 230 (from brief 209's pilots/230/record_run.py, without the host-check part): a run's record (run_record.json) from its run directory: outcome, real dollars, tokens, truncated calls, timing, utilisation, gates,
requirement results, the generated hw_checks.py against its own mock, and the pilot host check against that mock (where it can run).

    python3 pilots/230/record_run.py <run dir> <design id> <k> <log file> <agent sha>
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def num(rx: str, text: str, grp: int = 1):
    m = re.search(rx, text)
    return m.group(grp) if m else None


def main() -> int:
    run, did, k, log, sha = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4]), sys.argv[5]
    rec: dict = {"design": did, "run": int(k), "run_id": run.name, "agent_sha": sha}
    calls = [json.loads(l) for l in (run / "model_calls.jsonl").read_text().splitlines() if l.strip()]
    rec["model"] = sorted({c.get("model") for c in calls})
    rec["endpoint"] = sorted({c.get("endpoint") for c in calls})
    rec["api_calls"] = len(calls)
    rec["real_usd"] = round(sum(c.get("cost_usd") or 0 for c in calls), 4)
    for key in ("prompt_tokens", "completion_tokens", "input_tokens", "cache_read_tokens", "cache_write_tokens"):
        rec[key] = sum(c.get(key) or 0 for c in calls)
    rec["tokens_total"] = rec["prompt_tokens"] + rec["completion_tokens"]
    rec["truncated_calls"] = sum(1 for c in calls if c.get("stop_reason") == "max_tokens")
    rec["cost_basis"] = sorted({str(c.get("cost_basis")) for c in calls})
    txt = log.read_text() if log.exists() else ""
    t0, t1 = num(r"start (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", txt), num(r"exit \d+ (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", txt)
    slot = num(r"taken (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", txt)
    if slot and t1:
        f = "%Y-%m-%d %H:%M:%S"
        rec["wall_s_after_slot"] = int(time.mktime(time.strptime(t1, f)) - time.mktime(time.strptime(slot, f)))
    summ = run / "summary.json"
    d = json.loads(summ.read_text()) if summ.exists() else {}
    stages = []
    for l in (run / "role_usage.jsonl").read_text().splitlines():
        r = json.loads(l)
        stages.append((r["stage"], r["visit"], r["role"], r["ended"], r["turns"], round(r.get("cost_usd") or 0, 3)))
    rec["stage_visits"] = stages
    paused = re.search(r'"paused": \{[^}]*"stage": (\d+)', txt, re.S)
    if paused:
        rec["outcome"] = f"reached stage {paused.group(1)}: paused awaiting approval to program the board (never approved; the pilot does not touch the board)"
        rec["reached_stage"] = int(paused.group(1))
    elif d:
        rec["outcome"] = "stopped: " + str(d.get("stop")); rec["reached_stage"] = max(d.get("stages_visited") or [0])
    else:
        rec["outcome"] = "no summary and no pause: see the log"
    if d:
        rec["summary_stop"], rec["interview"], rec["cost_usd_agent"] = d.get("stop"), d.get("interview"), d.get("cost_usd")
    rec["interview_note"] = "--interview off: the agent's defaults were taken, nothing asked or answered by hand"
    dd = run / did
    b = dd / "build"
    tsr = b / "base/timing_summary.rpt"
    if tsr.exists():
        t = tsr.read_text()
        m = re.search(r"WNS\(ns\).*?\n.*?\n\s*(-?[\d.]+)\s+(-?[\d.]+)\s+\d+\s+\d+\s+(-?[\d.]+)", t, re.S)
        if m:
            rec["timing_after_route"] = {"WNS_ns": float(m.group(1)), "TNS_ns": float(m.group(2)), "WHS_ns": float(m.group(3))}
    ut = b / "base/utilization.rpt"
    if ut.exists():
        u = ut.read_text()
        rec["utilisation"] = {"LUT": num(r"\| CLB LUTs\s+\|\s+(\d+)", u), "FF": num(r"\| CLB Registers\s+\|\s+(\d+)", u),
                              "BRAM_tiles": num(r"\| Block RAM Tile\s+\|\s+([\d.]+)", u), "DSP": num(r"\| DSPs\s+\|\s+(\d+)", u)}
    rj = b / "base/run.json"
    if rj.exists():
        x = json.loads(rj.read_text())
        rec["bitstream"] = {"build_stamp": x.get("build_stamp"), "exit_code": x.get("exit_code"), "vivado": x.get("vivado_version")}
    mf = b / "base/manifest.json"
    if mf.exists():
        rec["build_id_usr_access"] = json.loads(mf.read_text()).get("build_id")
    rec["bitstream_built"] = bool(list(b.glob("base/*.bit")))
    vg = b / "verif/verif_gates.json"
    if vg.exists():
        rec["verif_stages"] = {s: v.get("pass") for s, v in json.loads(vg.read_text()).get("stages", {}).items()}
    br = b / "bringup_ready.json"
    if br.exists():
        rec["bringup_ready"] = json.loads(br.read_text())
    tj = b / "trace/trace.json"
    if tj.exists():
        t = json.loads(tj.read_text())
        reqs = t.get("requirements")
        rec["trace_pass"] = t.get("pass")
        n, per = {}, []
        for r in (reqs or []):
            ms = {m["method"]: m["status"] for m in r.get("methods", [])}
            per.append({"id": r.get("id"), "text": r.get("text"), "methods": ms})
            for st in ms.values():
                n[st] = n.get(st, 0) + 1
        rec["requirement_table"] = per
        rec["requirement_method_results"] = n
        rec["requirements"] = len(reqs or [])
    rec["hw_checks_present"] = (dd / "hw_checks.py").exists()
    out = run / "run_record.json"
    out.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps({k: rec.get(k) for k in ("outcome", "real_usd", "truncated_calls", "timing_after_route", "utilisation", "requirements")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
