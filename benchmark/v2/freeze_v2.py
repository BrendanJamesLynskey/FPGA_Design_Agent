#!/usr/bin/env python3
"""Per-task freeze manifest for benchmark v2 (brief 10 B1). benchmark/tools/freeze.py handles only the v1 paths, so
this writes the same unit record for one v2 task directory, in the same format and with the same digest rule
(SHA-256 of the sorted "<sha256>  <relative path>" lines; __pycache__ skipped).

    freeze_v2.py make   TASK_DIR OUT.json
    freeze_v2.py verify TASK_DIR MANIFEST.json

The manifest of a task goes to the private repository; split.py submit stores only the SHA-256 of that file.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmark.tools.freeze import digest, files_of, tool_versions  # noqa: E402


def unit(task: Path) -> dict:
    f = files_of(task)
    return {"id": task.name, "kind": "task", "tier": "drill", "split": "pending", "where": "private",
            "files": len(f), "digest": digest(f), "file_hashes": f}


def make(task: Path, out: Path) -> None:
    head = {"benchmark": "FPGA_Design_Agent benchmark v2 (batch 1)", "frozen": time.strftime("%Y-%m-%d"),
            "tools": tool_versions()}
    out.write_text(json.dumps({**head, "units": [unit(task)]}, indent=1) + "\n")


def verify(task: Path, manifest: Path) -> int:
    rec = json.loads(manifest.read_text())["units"][0]
    now = unit(task)
    ok = rec["digest"] == now["digest"] and rec["file_hashes"] == now["file_hashes"]
    print(f"{task.name}: {'OK' if ok else 'MISMATCH'} ({now['files']} files, digest {now['digest'][:16]})")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("make", "verify"):
        raise SystemExit(__doc__)
    t, o = Path(sys.argv[2]), Path(sys.argv[3])
    if sys.argv[1] == "make":
        make(t, o)
    else:
        raise SystemExit(verify(t, o))
