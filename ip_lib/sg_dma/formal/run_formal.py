#!/usr/bin/env python3
"""run_formal.py (brief 241): the SymbiYosys jobs of sg_dma.sby (AXI rule proofs by k-induction at 32, 64 and 128 bits in both directions, bounded
proofs of the burst bookkeeping, two covers) and the seeded faults of faults.yaml that name formal tasks, each run on a throw-away copy of the RTL.

    python3 ip_lib/sg_dma/formal/run_formal.py --json results/241_dma/formal.json
    python3 ip_lib/sg_dma/formal/run_formal.py --only m32,no_4k_split      # one task, one fault

Needs sby, yosys, boolector and the slang plugin (the OSS CAD Suite the repo's CI pins), found through FDA_OSS_CAD, ~/.local/opt/oss-cad-suite
or PATH. The RTL itself is never edited."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ENTRY = HERE.parent
PROVE = ["m32", "s32", "m64", "s64", "m128", "s128"]      # k-induction, every depth
BOUNDED = ["g32m", "g32s"]                # bmc, depth 30 (the burst bookkeeping is not tied to the engine's counters)
COVER = ["m32c", "s32c"]
TASKS = PROVE + BOUNDED + COVER


def oss_bin() -> str:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return str(Path(c) / "bin")
    w = shutil.which("sby")
    return str(Path(w).parent) if w else ""


def run_sby(root: Path, task: str, out: Path) -> tuple[str, float]:
    env = dict(os.environ, PATH=oss_bin() + os.pathsep + os.environ["PATH"])
    t0 = time.time()
    subprocess.run(["sby", "-f", "-d", str(out), "sg_dma.sby", task], cwd=root / "formal", env=env, capture_output=True, text=True, timeout=3600)
    st = (out / "status").read_text().split()[0] if (out / "status").exists() else "ABSENT"
    return st, round(time.time() - t0, 1)


def faults() -> list[dict]:
    return [m for m in yaml.safe_load((ENTRY / "faults.yaml").read_text())["faults"] if m.get("formal")]


def main_for_test() -> int:
    sys.argv = [sys.argv[0], "--only", ",".join(m["name"] for m in faults())]
    return main()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    if not oss_bin():
        print("sby not found (set FDA_OSS_CAD)")
        return 2
    only = set(filter(None, a.only.split(",")))
    out: dict = {"proofs": [], "faults": []}
    bad = 0
    with tempfile.TemporaryDirectory(prefix="b241formal_") as tmp:
        tmp = Path(tmp)
        for t in TASKS:
            if only and t not in only:
                continue
            st, sec = run_sby(ENTRY, t, tmp / f"p_{t}")
            kind = "k-induction" if t in PROVE else ("bounded (bmc depth 30)" if t in BOUNDED else "cover")
            out["proofs"].append({"task": t, "kind": kind, "status": st, "seconds": sec})
            print(f"{t}: {st} ({kind}, {sec}s)")
            bad += st != "PASS"
        for m in faults():
            if only and m["name"] not in only:
                continue
            copy = tmp / f"rtl_{m['name']}"
            shutil.copytree(ENTRY / "rtl", copy)
            (copy / "formal").mkdir(exist_ok=True)
            f = copy / m["file"]
            text = f.read_text()
            if text.count(m["old"]) != 1:
                print(f"{m['name']}: invalid (old string occurs {text.count(m['old'])} times)")
                bad += 1
                continue
            f.write_text(text.replace(m["old"], m["new"]))
            root = tmp / f"root_{m['name']}"
            (root / "rtl").mkdir(parents=True)
            shutil.copy(f, root / "rtl" / m["file"])
            shutil.copytree(HERE, root / "formal", ignore=shutil.ignore_patterns("__pycache__", "*.json"))
            res = {}
            for t in m["formal"]:
                st, sec = run_sby(root, t, tmp / f"f_{m['name']}_{t}")
                res[t] = st
                print(f"fault {m['name']} {t}: {st} ({sec}s)")
            caught = all(s == "FAIL" for s in res.values())
            out["faults"].append({"name": m["name"], "tasks": res, "refuted": caught})
            bad += not caught
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
