#!/usr/bin/env python3
"""The scripted review-on run on T1 (brief 05d smoke): scripted model, fake runner, scripted owner replies, no spend.

    python3 tools/scripted_review_run.py OUT.json RUN_DIR

Approve the architecture, make one hand edit while stage 2 is paused, approve again; then print and write what the
ledger, the approval record and the snapshot repository say. The review pages stay in RUN_DIR for screenshots."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.graph import ownership  # noqa: E402
from agent.graph import run as gr  # noqa: E402
from agent.tests import test_05d as t  # noqa: E402
from flow import architecture as am  # noqa: E402


class MP:
    def setattr(self, obj, name, val):
        setattr(obj, name, val)


def main() -> int:
    out, keep = Path(sys.argv[1]), Path(sys.argv[2])
    tmp = Path(tempfile.mkdtemp())

    def edit(rt, p, pauses):
        if p["stage"] == 2 and pauses.count(2) == 1:
            f = rt.design / "rtl" / "debounce.sv"
            f.write_text(f.read_text() + "\n// owner: note added by hand while paused\n")

    with mock.patch("flow.hw.load_board", lambda b: {"cable_serial": "TEST0000"}):
        rt, st, pauses, runs = t._drive(tmp, MP(), "on", {}, stop_after=3, before_reply=edit)
    authors = subprocess.run(["git", f"--git-dir={rt.run_dir / 'snap.git'}", "log", "--format=%an|%s"],
                             capture_output=True, text=True).stdout.splitlines()
    res = {"pauses_at_stage": pauses, "architecture_approval": am.read_approval(rt.design),
           "ledger": ownership.load(rt.design), "snapshot_commits": authors,
           "review_pages": sorted(p.name for p in (rt.design / "build" / "review").glob("*.html")),
           "hand_edit_kept": (rt.design / "rtl" / "debounce.sv").read_text().rstrip().endswith("while paused"),
           "who_did_what_in_build_note": "Who did what" in (rt.design / "BUILD_NOTE.md").read_text()}
    out.write_text(json.dumps(res, indent=1) + "\n")
    shutil.rmtree(keep, ignore_errors=True)
    shutil.copytree(rt.design, keep / rt.design.name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.rmtree(runs, ignore_errors=True)
    print(json.dumps({k: res[k] for k in ("pauses_at_stage", "review_pages", "hand_edit_kept")}))
    for r in res["ledger"]:
        print(f"  {r['who']:6} {r['stage']:28} {r['what']}: {r['detail'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
