#!/usr/bin/env python3
"""Brief 107 level 2 proof: a recorded run and its replay are identical.

Runs the scripted T1 episode of ``agent/tests/test_episode.py`` through the whole stage graph twice: once recording every model
call to a tape (the scripted client is the "live" model), once replaying the tape with **no model client at all**. It then compares
(a) every tool call the core dispatched (``build/audit.jsonl``: tool, arguments, role, stage, refusal), (b) every file the model wrote
into the design (SHA-256 of each file's text), and (c) the run summary's stage path; and reports the tape counts (served, unused,
live calls, misses). Paths that carry the run's own name are neutralised on both sides. No network, no model call.

    python tools/determinism_replay_check.py OUT.json
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WRITTEN = ("rtl", "tests", "verif", "model.py", "spec.yaml", "build.yaml", "architecture.yaml", "ARCHITECTURE.md", "design.xdc", "probes.yaml", "BRINGUP.md",
           "hw_checks.py")


def _fingerprint(rt, runs: Path, tmp: Path) -> dict:
    def clean(text: str) -> str:
        rel = str(runs.relative_to(ROOT))
        return text.replace(str(runs), "<runs>").replace(rel, "<runs>").replace(runs.name, "<run>").replace(str(tmp), "<tmp>")
    audit = [json.loads(l) for l in (rt.design / "build" / "audit.jsonl").read_text().splitlines()]
    keep = [{k: a.get(k) for k in ("tool", "args", "arguments", "role", "stage", "refused", "rule", "ok")} for a in audit if "tool" in a]
    files = {}
    for name in WRITTEN:
        p = rt.design / name
        for f in ([p] if p.is_file() else sorted(p.rglob("*")) if p.is_dir() else []):
            if f.is_file() and "__pycache__" not in f.parts:
                files[str(f.relative_to(rt.design))] = hashlib.sha256(clean(f.read_text(errors="replace")).encode()).hexdigest()
    return {"core_tool_calls": len(keep), "core_tool_calls_sha256": hashlib.sha256(clean(json.dumps(keep, sort_keys=True)).encode()).hexdigest(),
            "files_written": len(files), "files_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def proof() -> dict:
    from agent import access
    import agent.core.tools  # noqa: F401   registers every tool up front: the tool list a model sees must not depend on which run came first
    from agent.graph import run as gr
    from agent.tests import test_episode as E
    from flow import hw
    access._TEST_BYPASS, access.CURRENT = True, None
    real = (gr.RUNS, hw.load_board, hw.power_ok)
    hw.load_board = lambda b: {"cable_serial": "TEST0000"}
    hw.power_ok = lambda d, b: {"pass": True, "total_w": 0.15, "junction_c": 42.7, "source": "wall"}
    tmp = Path(tempfile.mkdtemp(prefix="detproof_"))
    import os
    os.environ["FDA_HEAVY_LOCK"] = str(tmp / "heavy_slot.lock")       # the suite's own lock: never wait on or write the shared heavy slot
    runs_a, runs_b = ROOT / "runs" / f"_detproof_{uuid.uuid4().hex[:8]}", ROOT / "runs" / f"_detproof_{uuid.uuid4().hex[:8]}"
    out: dict = {}
    try:
        tape = tmp / "tape"
        gr.RUNS = runs_a
        rt_a = E._episode(tmp, runs_a, tape_spec={"dir": tape, "mode": "record", "level": 0, "note": "proof: record"})
        out["record"] = {**_fingerprint(rt_a, runs_a, tmp), "tape": rt_a.resolver.tape.state()}
        gr.RUNS = runs_b
        rt_b = E._episode(tmp, runs_b, tape_spec={"dir": tape, "mode": "replay", "level": 2, "note": "proof: replay"}, live=False)
        out["replay"] = {**_fingerprint(rt_b, runs_b, tmp), "tape": rt_b.resolver.tape.state()}
        det = json.loads((rt_b.run_dir / "config.json").read_text())["determinism"]
        out["replay_run_record_determinism"] = {k: det[k] for k in ("requested", "level", "mode", "level_meaning")}
        from flow import plan_repeat
        runs = [{"run_id": r.run_id, "stages_visited": r.summary_["stages_visited"]} for r in (rt_a, rt_b)]
        out["plan_repeatability"] = plan_repeat.score({"t1_episode:record_vs_replay": runs})       # brief 106's measuring stick
        a, b = out["record"], out["replay"]
        out["identical"] = {k: a[k] == b[k] for k in ("core_tool_calls", "core_tool_calls_sha256", "files_written", "files_sha256")}
        t = b["tape"]
        out["exact"] = all(out["identical"].values()) and t["served_from_tape"] == a["tape"]["calls_recorded"] and t["unused_recordings"] == 0 \
            and t["live_calls"] == 0 and t["replay_misses"] == 0
        return out
    finally:
        gr.RUNS, hw.load_board, hw.power_ok = real
        for d in (runs_a, runs_b, tmp):
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    r = proof()
    Path(sys.argv[1]).write_text(json.dumps(r, indent=1, sort_keys=True))
    print(json.dumps({"exact": r["exact"], "identical": r["identical"], "tape": r["replay"]["tape"]}, indent=1))
    sys.exit(0 if r["exact"] else 1)
