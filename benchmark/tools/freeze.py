#!/usr/bin/env python3
"""The benchmark freeze: SHA-256 of every file per task, the split, the tool versions; and its verification.

    freeze.py make   [--private DIR] [--out benchmark/MANIFEST.json] [--private-out DIR/MANIFEST_full.json]
    freeze.py verify [--private DIR] [--manifest benchmark/MANIFEST.json]

A unit is one directory: a task (public benchmark/tasks/<id> or private <DIR>/tasks/<id>), a pool spec
(benchmark/pool/<id>), a probe task (<DIR>/contamination/<id>), or the shared bench code (benchmark/lib, the
benchmark/tools that scoring runs). Its digest is the SHA-256 of the sorted lines "<sha256>  <relative path>" of its
files (__pycache__ skipped), so `sha256sum` reproduces every number. The public manifest lists, for a held-out or
probe unit, only its digest and file count; the private copy lists every file. `verify` recomputes every unit it can
reach (public units always; private ones when --private is given) and fails on any difference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmark"
DEFAULT_PRIVATE = ROOT.parent / "FPGA_Design_Agent_Knowledge" / "benchmark_private"
SHARED = ["lib", "tools/run_task.py", "tools/check_task.py", "tools/board_xdc.py"]


def files_of(d: Path) -> dict[str, str]:
    out = {}
    paths = [d] if d.is_file() else sorted(p for p in d.rglob("*") if p.is_file())
    for p in paths:
        if "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        rel = p.name if d.is_file() else str(p.relative_to(d))
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def digest(files: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{h}  {p}\n" for p, h in sorted(files.items())).encode()).hexdigest()


def ver(cmd: list[str], pat: str = r"(\d+\.\d+(?:\.\d+)?)") -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        m = re.search(pat, out.stdout + out.stderr)
        return m.group(1) if m else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def tool_versions() -> dict:
    import cocotb
    return {"python": platform.python_version(), "cocotb": cocotb.__version__,
            "icarus": ver(["iverilog", "-V"]),
            "verilator": ver([str(Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator/bin/verilator"),
                              "--version"]),
            "vivado": "2025.2", "pyyaml": yaml.__version__}


def units(private: Path | None) -> list[dict]:
    split = yaml.safe_load((BENCH / "split.yaml").read_text())
    held = {i for t in split["tiers"].values() for i in t["held_out"]}
    tier_of = {i: t for t, v in split["tiers"].items() for i in v["held_out"] + v["dev"]}
    us = []
    for d in sorted((BENCH / "tasks").iterdir()):
        if d.is_dir():
            us.append({"id": d.name, "kind": "task", "tier": tier_of.get(d.name), "split": "dev", "where": "public",
                       "path": d})
    for i in sorted(held):
        p = private / "tasks" / i if private else None
        us.append({"id": i, "kind": "task", "tier": tier_of[i], "split": "held_out", "where": "private", "path": p})
    if (BENCH / "pool").exists():
        for d in sorted((BENCH / "pool").iterdir()):
            if d.is_dir():
                us.append({"id": d.name, "kind": "pool", "where": "public", "path": d})
    if private and (private / "contamination").exists():
        for d in sorted((private / "contamination").iterdir()):
            if d.is_dir():
                us.append({"id": d.name, "kind": "probe", "where": "private", "path": d})
    for s in SHARED:
        us.append({"id": "shared:" + s, "kind": "shared", "where": "public", "path": BENCH / s})
    return us


def make(private: Path, out: Path, private_out: Path) -> None:
    split_file = BENCH / "split.yaml"
    full, pub = [], []
    for u in units(private):
        f = files_of(u["path"])
        rec = {k: v for k, v in u.items() if k != "path"}
        rec.update({"files": len(f), "digest": digest(f)})
        full.append({**rec, "file_hashes": f})
        pub.append(rec if u["where"] == "private" else {**rec, "file_hashes": f})
    head = {"benchmark": "FPGA_Design_Agent benchmark v1 (T1-T2)", "frozen": time.strftime("%Y-%m-%d"),
            "split_sha256": hashlib.sha256(split_file.read_bytes()).hexdigest(), "tools": tool_versions()}
    out.write_text(json.dumps({**head, "units": pub}, indent=1) + "\n")
    private_out.write_text(json.dumps({**head, "units": full}, indent=1) + "\n")
    print(f"{len(pub)} units; manifest {out}; private manifest {private_out}")


def verify(private: Path | None, manifest: Path) -> int:
    m = json.loads(manifest.read_text())
    bad, checked, skipped = [], 0, 0
    split_now = hashlib.sha256((BENCH / "split.yaml").read_bytes()).hexdigest()
    if split_now != m["split_sha256"]:
        bad.append("split.yaml")
    by_id = {(u["kind"], u["id"]): u for u in units(private)}
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
    ap.add_argument("--out", type=Path, default=BENCH / "MANIFEST.json")
    ap.add_argument("--private-out", type=Path, default=None)
    ap.add_argument("--manifest", type=Path, default=BENCH / "MANIFEST.json")
    a = ap.parse_args()
    if a.cmd == "make":
        priv = a.private or DEFAULT_PRIVATE
        make(priv, a.out, a.private_out or priv / "MANIFEST_full.json")
        return 0
    return verify(a.private, a.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
