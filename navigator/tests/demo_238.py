"""Screenshot and recording fixture for the stage map (brief 238): the navigator on a scratch run directory that holds the three recorded 213 runs of fixtures_238/
(finished, role_usage mode) and one synthetic run in the trace mode (written "now", so it counts as working; a Vivado build step is open). A FAKE spawner and board
transport are used as in demo_stage2 (nothing starts). ``--append`` writes one more stage event to the synthetic run every few seconds so a live stage change can be watched.

    python3 -m navigator.tests.demo_238 --port 8794 --workdir /tmp/x [--append]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from pathlib import Path

from navigator.tests import demo_stage2

FIX = Path(__file__).parent / "fixtures_238"
LIVE = "20261126-120000-live"


def ev(name, t, stage, **f):
    return json.dumps({"v": 1, "kind": "event", "event": name, "stage": stage, "t": t, **f}) + "\n"


def make_live(runs: Path) -> Path:
    rd = runs / LIVE
    (rd / "demo_live" / "build").mkdir(parents=True)
    (rd / "config.json").write_text(json.dumps({"name": "demo_live", "run_limits": {"usd": 3.0, "visits_per_stage": 4}, "harness": "claude_code"}))
    t = time.time()
    names = ["clarify", "board-and-device-planning", "rtl-design-creation"]
    rows = ""
    for i, n in enumerate(names[:2]):
        rows += ev("stage_start", t - 400 + i * 100, n, n=i, visit=1) + ev("stage_end", t - 330 + i * 100, n, n=i, visit=1, passed=True)
    rows += ev("stage_start", t - 190, names[2], n=2, visit=1)
    (rd / "trace.jsonl").write_text(rows)
    (rd / "role_usage.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [{"stage": "clarify", "visit": 1, "role": "clarify"}, {"stage": "board-and-device-planning", "visit": 1, "role": "rtl"},
                                                                                {"stage": "rtl-design-creation", "visit": 1, "role": "model"}, {"stage": "rtl-design-creation", "visit": 1, "role": "tests"}, {"stage": "rtl-design-creation", "visit": 1, "role": "rtl"}]))
    (rd / "demo_live" / "build" / "audit.jsonl").write_text(json.dumps({"t": t - 120, "tool": "gates", "stage": "rtl-design-creation", "ok": False,
                                                                       "result_summary": "gates: demo (base): FAIL wns=0\n  rtl: FAIL\n    FAIL lint"}) + "\n")
    with (rd / "trace.jsonl").open("a") as f:
        f.write(ev("build_step", t - 30, "rtl-design-creation", state="start", until="synth", variant="base"))
    return rd


def appender(rd: Path, every: float) -> None:
    seq = [("stage_end", "rtl-design-creation", dict(n=2, visit=1, passed=False)), ("stage_start", "board-and-device-planning", dict(n=1, visit=2)),
           ("stage_end", "board-and-device-planning", dict(n=1, visit=2, passed=True)), ("stage_start", "rtl-design-creation", dict(n=2, visit=2))]
    for name, stage, f in seq:
        time.sleep(every)
        with (rd / "trace.jsonl").open("a") as fh:
            fh.write(ev(name, time.time(), stage, **f))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8794)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--append-every", type=float, default=8.0)
    a = ap.parse_args()
    runs = a.workdir / "stage_map_runs"
    if runs.exists():
        shutil.rmtree(runs)
    runs.mkdir(parents=True)
    for r in FIX.iterdir():
        shutil.copytree(r, runs / r.name)
    rd = make_live(runs)
    if a.append:
        threading.Thread(target=appender, args=(rd, a.append_every), daemon=True).start()
    sys.argv = [sys.argv[0], "--port", str(a.port), "--workdir", str(a.workdir), "--runs", str(runs)]
    return demo_stage2.main()


if __name__ == "__main__":
    sys.exit(main())
