#!/usr/bin/env python3
"""The course-tier freeze: SHA-256 of every file per task, the split, the tool versions; and its verification (as benchmark/tools/freeze.py).

    freeze.py make   [--private DIR] [--out benchmark/course/MANIFEST.json] [--private-out DIR/course/MANIFEST_full.json]
    freeze.py verify [--private DIR] [--manifest benchmark/course/MANIFEST.json] [--grader-shell DIR]
    freeze.py refreeze UNIT...                                    # dated amendment: re-record named public units only
    freeze.py refreeze UNIT... --private-manifest DIR/course/MANIFEST_full.json [--dry-run]    # the same, in the owner's private manifest

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
from benchmark.tools.freeze import digest, files_of, refreeze_private, tool_versions  # noqa: E402

COURSE = ROOT / "benchmark" / "course"
DEFAULT_PRIVATE = ROOT.parent / "FPGA_Design_Agent_Knowledge" / "benchmark_private"
SHARED = ["benchmark/lib", "benchmark/tools/run_task.py", "benchmark/tools/check_task.py", "benchmark/tools/board_xdc.py",
          "benchmark/course/tools/no_shell.py", "benchmark/course/tools/run_task.py", "benchmark/course/tools/check_task.py"]


SPLITS = ["split.yaml", "split_c9_c12.yaml"]      # Parts 13-16 (course v1), Parts 9-12 (course v1.2)


def load_split() -> dict:
    """The tiers of every split file, merged (the files hold disjoint tiers)."""
    out: dict = {"tiers": {}}
    for f in SPLITS:
        p = COURSE / f
        if p.exists():
            out["tiers"].update(yaml.safe_load(p.read_text())["tiers"])
    return out


def units(private: Path | None) -> tuple[list[dict], list[str]]:
    split = load_split()
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
    head = {"benchmark": "FPGA_Design_Agent benchmark, course tier (Parts 9-16)", "frozen": time.strftime("%Y-%m-%d"),
            "split_sha256": hashlib.sha256((COURSE / "split.yaml").read_bytes()).hexdigest(),
            "split_c9_c12_sha256": hashlib.sha256((COURSE / "split_c9_c12.yaml").read_bytes()).hexdigest(), "pending": pending,
            "tools": tool_versions()}
    out.write_text(json.dumps({**head, "units": pub}, indent=1) + "\n")
    private_out.parent.mkdir(parents=True, exist_ok=True)
    private_out.write_text(json.dumps({**head, "units": full}, indent=1) + "\n")
    print(f"{len(pub)} units, {len(pending)} pending; manifest {out}; private manifest {private_out}")


def refreeze(ids: list[str], manifest: Path) -> int:
    """Re-record the named public units in an existing manifest (a dated amendment, benchmark/AMENDMENTS.md); nothing else changes."""
    m = json.loads(manifest.read_text())
    by_id = {u["id"]: u for u in units(None)[0] if u["where"] == "public"}
    for i in ids:
        rec = next((r for r in m["units"] if r["id"] == i), None)
        if rec is None or rec["where"] != "public" or i not in by_id:
            raise SystemExit(f"{i}: not a public unit of {manifest.name}")
        f = files_of(by_id[i]["path"])
        old = rec["digest"]
        rec.update({"files": len(f), "digest": digest(f), "file_hashes": f})
        print(f"{i}: {old[:16]} -> {rec['digest'][:16]} ({len(f)} files)")
    manifest.write_text(json.dumps(m, indent=1) + "\n")
    return 0


def verify(private: Path | None, manifest: Path, grader_shell: Path | None = None) -> int:
    m = json.loads(manifest.read_text())
    bad, checked, skipped = [], 0, 0
    from benchmark.tools import shell_freeze
    deps = manifest.parent / "GRADER_DEPS.json"
    bad += (shell_freeze.verify_record(json.loads(deps.read_text()), grader_shell, label="shell") if deps.exists()
            else [f"{deps.name} (missing: the shell fingerprint is not recorded)"])
    if hashlib.sha256((COURSE / "split.yaml").read_bytes()).hexdigest() != m["split_sha256"]:
        bad.append("split.yaml")
    if "split_c9_c12_sha256" in m and hashlib.sha256((COURSE / "split_c9_c12.yaml").read_bytes()).hexdigest() != m["split_c9_c12_sha256"]:
        bad.append("split_c9_c12.yaml")
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
    ap.add_argument("cmd", choices=["make", "verify", "refreeze"])
    ap.add_argument("units", nargs="*")
    ap.add_argument("--grader-shell", type=Path, default=None)
    ap.add_argument("--private", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=COURSE / "MANIFEST.json")
    ap.add_argument("--private-out", type=Path, default=None)
    ap.add_argument("--manifest", type=Path, default=COURSE / "MANIFEST.json")
    ap.add_argument("--private-manifest", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.dry_run and not a.private_manifest:
        ap.error("--dry-run needs --private-manifest")
    if a.cmd == "make":
        priv = a.private or DEFAULT_PRIVATE
        make(priv, a.out, a.private_out or priv / "course" / "MANIFEST_full.json")
        return 0
    if a.cmd == "refreeze" and a.private_manifest:
        return refreeze_private(a.units, {u["id"]: u for u in units(None)[0] if u["where"] == "public"}, a.private_manifest, a.dry_run)
    if a.cmd == "refreeze":
        return refreeze(a.units, a.manifest)
    return verify(a.private, a.manifest, a.grader_shell)


if __name__ == "__main__":
    raise SystemExit(main())
