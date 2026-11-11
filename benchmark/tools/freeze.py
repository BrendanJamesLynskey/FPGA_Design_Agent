#!/usr/bin/env python3
"""The benchmark freeze: SHA-256 of every file per task, the split, the tool versions; and its verification.

    freeze.py make   [--private DIR] [--out benchmark/MANIFEST.json] [--private-out DIR/MANIFEST_full.json]
    freeze.py verify [--private DIR] [--manifest benchmark/MANIFEST.json] [--grader-shell DIR]
    freeze.py refreeze UNIT... [--manifest benchmark/MANIFEST.json]    # dated amendment: re-record named public units only
    freeze.py refreeze UNIT... --private-manifest DIR/MANIFEST_full.json [--dry-run]    # the same, in the owner's private manifest

A unit is one directory: a task (public benchmark/tasks/<id> or private <DIR>/tasks/<id>), a pool spec
(benchmark/pool/<id>), a probe task (<DIR>/contamination/<id>), or the shared bench code (benchmark/lib, the
benchmark/tools that scoring runs). Its digest is the SHA-256 of the sorted lines "<sha256>  <relative path>" of its
files (__pycache__ skipped), so `sha256sum` reproduces every number. The public manifest lists, for a held-out or
probe unit, only its digest and file count; the private copy lists every file. `verify` recomputes every unit it can
reach (public units always; private ones when --private is given) and fails on any difference. It also checks the shell
fingerprint recorded next to the manifest (``GRADER_DEPS.json``, benchmark/tools/shell_freeze.py): the shell a grader imports
must be the frozen one, or ``--grader-shell DIR`` must point at a checked-out frozen copy that is.

``refreeze`` rewrites the record of the named public units (``shared:<path>`` for the shared code) and nothing else; every
use is a dated entry in benchmark/AMENDMENTS.md. Held-out and private units are never touched by it.

``refreeze --private-manifest PATH`` does the same in a private manifest (``make`` would regenerate every entry, held-out ones included, and
so accept a held-out change unseen). It takes each digest from the public files only, rewrites only the named public or ``shared:`` entries,
leaves every other entry byte for byte as it was, refuses any id that is not a public or shared unit of that manifest, and prints old and
new digests. ``--dry-run`` prints them and writes nothing.
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


def shell_problems(manifest: Path, grader_shell: Path | None) -> list[str]:
    """The shell fingerprint recorded beside the manifest (GRADER_DEPS.json) against the current or the given shell."""
    sys.path.insert(0, str(ROOT))
    from benchmark.tools import shell_freeze
    deps = manifest.parent / "GRADER_DEPS.json"
    if not deps.exists():
        return [f"{deps.name} (missing: the shell fingerprint is not recorded)"]
    return shell_freeze.verify_record(json.loads(deps.read_text()), grader_shell, label="shell")


def refreeze(ids: list[str], manifest: Path) -> int:
    """Re-record the named public units in an existing manifest; the digest rule and all other units stay as they are."""
    m = json.loads(manifest.read_text())
    by_id = {u["id"]: u for u in units(None) if u["where"] == "public"}
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


def refreeze_private(ids: list[str], public_units: dict[str, dict], manifest: Path, dry_run: bool = False) -> int:
    """Re-record the named public/shared units in a private manifest; every other entry stays byte for byte.

    ``public_units`` maps id -> unit for the public units only (so a held-out or probe id can never be named). The file is read
    for the manifest's JSON, and the digests come from the public files; no private directory is opened. The manifest must be in the
    canonical form ``make`` writes, so the rewrite can change nothing but the named entries.
    """
    text = manifest.read_text()
    m = json.loads(text)
    if json.dumps(m, indent=1) + "\n" != text:
        raise SystemExit(f"{manifest.name}: not in the form freeze.py make writes; refusing to rewrite it")
    if not ids:
        raise SystemExit("no unit named")
    if len(set(ids)) != len(ids):
        raise SystemExit("a unit is named twice")
    recs = {}
    for i in ids:
        rec = next((r for r in m["units"] if r["id"] == i), None)
        if i not in public_units or rec is None or rec["where"] != "public" or rec["kind"] == "probe":
            raise SystemExit(f"{i}: not a public or shared unit of {manifest.name}; nothing written")
        recs[i] = rec
    for i in ids:
        rec = recs[i]
        f = files_of(public_units[i]["path"])
        old = rec["digest"]
        rec.update({"files": len(f), "digest": digest(f), "file_hashes": f})
        print(f"{i}: {old} -> {rec['digest']} ({len(f)} files)" + ("  [unchanged]" if old == rec["digest"] else ""))
    if dry_run:
        print("dry run: nothing written")
    else:
        manifest.write_text(json.dumps(m, indent=1) + "\n")
        print(f"{len(ids)} entries re-recorded in {manifest.name}")
    return 0


def verify(private: Path | None, manifest: Path, grader_shell: Path | None = None) -> int:
    m = json.loads(manifest.read_text())
    bad, checked, skipped = [], 0, 0
    bad += shell_problems(manifest, grader_shell)
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
    ap.add_argument("cmd", choices=["make", "verify", "refreeze"])
    ap.add_argument("units", nargs="*")
    ap.add_argument("--grader-shell", type=Path, default=None)
    ap.add_argument("--private", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=BENCH / "MANIFEST.json")
    ap.add_argument("--private-out", type=Path, default=None)
    ap.add_argument("--manifest", type=Path, default=BENCH / "MANIFEST.json")
    ap.add_argument("--private-manifest", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.dry_run and not a.private_manifest:
        ap.error("--dry-run needs --private-manifest")
    if a.cmd == "make":
        priv = a.private or DEFAULT_PRIVATE
        make(priv, a.out, a.private_out or priv / "MANIFEST_full.json")
        return 0
    if a.cmd == "refreeze" and a.private_manifest:
        return refreeze_private(a.units, {u["id"]: u for u in units(None) if u["where"] == "public"}, a.private_manifest, a.dry_run)
    if a.cmd == "refreeze":
        return refreeze(a.units, a.manifest)
    return verify(a.private, a.manifest, a.grader_shell)


if __name__ == "__main__":
    raise SystemExit(main())
