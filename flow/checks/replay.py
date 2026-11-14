"""Replay recorded runs' builds through the check suite (brief 71): do the registry's checks give the gate outcomes the
run recorded?

    python3 -m flow.checks.replay <run-dir>/<design> [...] --json results/71_check_suite/replay.json

For each design's ``build/base``: (1) ``flow/gates.py`` re-evaluates the recorded reports twice, with the code before
this brief (``--base-gates``, a copy of origin/main's flow/gates.py) and with today's, and every gate value and the first
failed stage are compared (the brief-71 change must not move any gate of a build without the reset scan); (2) the
registry's checks run on the same reports (no Vivado) and each check's verdict is compared with the base gate(s) it
shares a decision with:

    methodology  <-> rtl_methodology_no_critical / post_synth_methodology_no_critical / methodology_no_critical
    drc          <-> post_synth_drc_clean / drc_clean
    cdc          <-> post_synth_cdc_no_critical and post_synth_cdc_structure_clean / cdc_no_critical
    exceptions   <-> post_synth_exceptions_clean / exceptions_clean
    io           <-> post_synth_io_constraints_clean / io_timing_clean

The run directories are copied first; nothing in them is changed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from flow import checks as C
from flow import gates as G

PAIRS = {
    "synth": {"methodology": ["post_synth_methodology_no_critical"], "drc": ["post_synth_drc_clean"],
              "cdc": ["post_synth_cdc_no_critical", "post_synth_cdc_structure_clean"],
              "exceptions": ["post_synth_exceptions_clean"], "io": ["post_synth_io_constraints_clean"]},
    "route": {"methodology": ["methodology_no_critical"], "drc": ["drc_clean"], "cdc": ["cdc_no_critical"],
              "exceptions": ["exceptions_clean"], "io": ["io_timing_clean"]},
}


def _load_gates(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("base_gates", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replay(design: Path, base_gates) -> dict:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / design.name
        shutil.copytree(design, d, ignore=shutil.ignore_patterns("*.dcp", ".Xil", "checks"))
        b = d / "build" / "base"
        rec = json.loads((b / "gates.json").read_text())
        base = base_gates.evaluate(b)
        now = G.evaluate(b)
        gate_diff = {k: [base["gates"].get(k), now["gates"].get(k)] for k in sorted(set(base["gates"]) | set(now["gates"]))
                     if base["gates"].get(k) != now["gates"].get(k)}
        rec_diff = sorted(k for k in set(rec["gates"]) | set(base["gates"]) if rec["gates"].get(k) != base["gates"].get(k))
        out = {"design": design.name, "run": design.parent.name, "recorded_first_failed": rec.get("first_failed_stage"),
               "base_first_failed": base.get("first_failed_stage"), "now_first_failed": now.get("first_failed_stage"),
               "gate_diff": gate_diff, "recorded_vs_base_code": rec_diff, "checks": {}}
        rec = base
        for scope in ("synth", "route"):
            if not (now["stages"].get("post_synth" if scope == "synth" else "post_route") or {}).get("ran"):
                continue
            rep = C.run(d, list(PAIRS[scope]), scope, "summary", vivado=None)
            for c in rep["checks"]:
                keys = [k for k in PAIRS[scope][c["check"]] if k in rec["gates"]]
                if not keys:
                    out["checks"][f"{scope}:{c['check']}"] = {"check": c["status"], "gates": "none recorded"}
                    continue
                gate_ok = all(rec["gates"][k] for k in keys)
                same = (c["status"] == "pass") == gate_ok if c["status"] != "not_run" else None
                out["checks"][f"{scope}:{c['check']}"] = {"check": c["status"], "gates": {k: rec["gates"][k] for k in keys},
                                                         "same": same}
        out["agree"] = all(v.get("same") is not False for v in out["checks"].values())
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--base-gates", required=True, help="origin/main's flow/gates.py (git show origin/main:flow/gates.py)")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    bg = _load_gates(Path(a.base_gates))
    rows = [replay(Path(p).resolve(), bg) for p in a.designs]
    for r in rows:
        nr = sum(1 for v in r["checks"].values() if v.get("same") is None and v.get("gates") != "none recorded")
        print(f"{r['run']}/{r['design']}: gates before/after brief 71 differ in {len(r['gate_diff'])}, first failed "
              f"{r['base_first_failed']} -> {r['now_first_failed']}, checks agree {r['agree']}"
              f" ({len(r['checks'])} compared, {nr} not run)" + (f" {r['gate_diff']}" if r["gate_diff"] else ""))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"rows": rows}, indent=1, default=str) + "\n")
    return 0 if all(r["agree"] and not r["gate_diff"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
