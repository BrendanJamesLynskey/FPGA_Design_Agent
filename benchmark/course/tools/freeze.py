#!/usr/bin/env python3
"""The course-tier freeze: SHA-256 of every file per task, the split, the tool versions; and its verification (as benchmark/tools/freeze.py).

    freeze.py make   [--private DIR] [--out benchmark/course/MANIFEST.json] [--private-out DIR/course/MANIFEST_full.json]
    freeze.py verify [--private DIR] [--manifest benchmark/course/MANIFEST.json]

Units: a task (public benchmark/course/tasks/<id>, or private <DIR>/course/tasks/<id> for the held-out ones) and the shared code (the v1 bench
library and scoring tools, which the course tier reuses unchanged, and benchmark/course/tools). A held-out unit appears in the public manifest by
digest and file count only; the private copy lists every file. Split ids with no task yet are listed under ``pending``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmark.tools.freeze import digest, files_of, tool_versions  # noqa: E402

COURSE = ROOT / "benchmark" / "course"
DEFAULT_PRIVATE = ROOT.parent / "FPGA_Design_Agent_Knowledge" / "benchmark_private"
SHARED = ["benchmark/lib", "benchmark/tools/run_task.py", "benchmark/tools/check_task.py", "benchmark/tools/board_xdc.py",
          "benchmark/course/tools/no_shell.py", "benchmark/course/tools/run_task.py", "benchmark/course/tools/check_task.py"]


def units(private: Path | None) -> tuple[list[dict], list[str]]:
    split = yaml.safe_load((COURSE / "split.yaml").read_text())
    held = {i for t in split["tiers"].values() for i in t["held_out"]}
    tier_of = {i: t for t, v in split["tiers"].items() for i in v["held_out"] + v["dev"]}
    us, have = [], set()
    for d in sorted((COURSE / "tasks").iterdir()):
        if d.is_dir():
            us.append({"id": d.name, "kind": "task", "tier": tier_of.get(d.name), "split": "dev", "where": "public", "path": d})
            have.add(d.name)
    for i in sorted(held):
        p = private / "course" / "tasks" / i if private else None
        if p is None or p.exists():
            us.append({"id": i, "kind": "task", "tier": tier_of[i], "split": "held_out", "where": "private", "path": p})
            have.add(i)
    for s in SHARED:
        us.append({"id": "shared:" + s, "kind": "shared", "where": "public", "path": ROOT / s})
    return us, sorted(set(tier_of) - have)


def make(private: Path, out: Path, private_out: Path) -> None:
    full, pub = [], []
    us, pending = units(private)
    for u in us:
        f = files_of(u["path"])
        rec = {k: v for k, v in u.items() if k != "path"}
        rec.update({"files": len(f), "digest": digest(f)})
        full.append({**rec, "file_hashes": f})
        pub.append(rec if u["where"] == "private" else {**rec, "file_hashes": f})
    head = {"benchmark": "FPGA_Design_Agent benchmark, course tier (Parts 13-16)", "frozen": time.strftime("%Y-%m-%d"),
            "split_sha256": hashlib.sha256((COURSE / "split.yaml").read_bytes()).hexdigest(), "pending": pending,
            "tools": tool_versions()}
    out.write_text(json.dumps({**head, "units": pub}, indent=1) + "\n")
    private_out.parent.mkdir(parents=True, exist_ok=True)
    private_out.write_text(json.dumps({**head, "units": full}, indent=1) + "\n")
    print(f"{len(pub)} units, {len(pending)} pending; manifest {out}; private manifest {private_out}")


def verify(private: Path | None, manifest: Path) -> int:
    m = json.loads(manifest.read_text())
    bad, checked, skipped = [], 0, 0
    if hashlib.sha256((COURSE / "split.yaml").read_bytes()).hexdigest() != m["split_sha256"]:
        bad.append("split.yaml")
    us, _ = units(private)
    by_id = {(u["kind"], u["id"]): u for u in us}
    for rec in m["units"]:
        u = by_id.get((rec["kind"], rec["id"]))
        if u is None or u["path"] is None or not Path(u["path"]).exists():
            skipped += 1
            if rec["where"] == "public":
                bad.append(f"{rec['id']} (missing)")
            continue
        checked += 1
        if digest(files_of(u["path"])) != rec["digest"]:
            bad.append(rec["id"])
    print(f"verify: {checked} units checked, {skipped} private units not reachable, {len(bad)} mismatches"
          + (": " + ", ".join(bad) if bad else ""))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "verify"])
    ap.add_argument("--private", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=COURSE / "MANIFEST.json")
    ap.add_argument("--private-out", type=Path, default=None)
    ap.add_argument("--manifest", type=Path, default=COURSE / "MANIFEST.json")
    a = ap.parse_args()
    if a.cmd == "make":
        priv = a.private or DEFAULT_PRIVATE
        make(priv, a.out, a.private_out or priv / "course" / "MANIFEST_full.json")
        return 0
    return verify(a.private, a.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
