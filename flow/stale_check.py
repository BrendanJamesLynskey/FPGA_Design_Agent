#!/usr/bin/env python3
"""The stale-data check (brief 106): a build, a simulation result or a report is stale when any input it was made from has
changed since. The comparison is by hash and mechanical; no model judges it.

    python3 -m flow.stale_check stamp   designs/<d> <kind>          record the inputs a piece of evidence was made from
    python3 -m flow.stale_check check   designs/<d> [kind ...]      fresh or stale, and which inputs changed (exit 1: stale)
    python3 -m flow.stale_check claims  designs/<d> <file> ...      every build ID a document cites is a fresh build

**Evidence kinds** (``build/lineage.json`` holds one stamp per kind: the time and the SHA-256 of each input):

- ``build:<variant>``: the Vivado build (``base`` or ``ila``). Inputs: everything the build manifest hashes (RTL, XDC, data,
  IP, build.yaml, the flow's Tcl and Python), read from ``build/<variant>/manifest.json`` (flow/manifest.py), PLUS what the
  manifest does not hash and a result still depends on: the spec files, ``project.yaml``, ``architecture.yaml``, and the board
  file and master XDC of the design's board.
- ``sim``: the simulation and the verification evidence. Inputs: the build's sources, the design's tests and reference model
  (``tests/``, ``model/``), and the spec files.

**Where a stamp is taken.** A build's manifest is written by the flow before Vivado runs (that is the record of the inputs of
the build); this module adds the extras at the same moment, from the core's ``build`` tool. ``simulate`` stamps ``sim``. A
result read with no stamp is ``no_record``, never ``fresh``.

**The input set is closed on purpose and the holes are listed** (``HOLES``): what a stamp does not cover is stated in the
result, not left for the reader to guess.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LINEAGE = ("build", "lineage.json")
SPEC_FILES = ("spec.md", "spec.yaml", "architecture.yaml", "project.yaml")

#: what the stamp does not cover (read by the check, shown in its result and in docs)
HOLES = (
    "the Vivado installation is covered by its version only (the manifest's tools.vivado), not by a hash of the binaries",
    "the knowledge bank is covered by its commit pin only (knowledge/PACKS.md), not by the files a role read",
    "environment switches other than the manifest's result switches (FDA_INCREMENTAL, FDA_ILA_INSERT) are not hashed",
    "a file outside the repo (a user's tools.yaml, the host's Python packages) is not hashed",
    "a model's prompt is not an input of a build; only the files the model wrote are",
)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rel(p: Path, root: Path) -> str:
    return str(p.relative_to(root)) if p.is_relative_to(root) else str(p)


def _build_cfg(design: Path) -> dict[str, Any]:
    try:
        return yaml.safe_load((design / "build.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _expand(globs: list[str], root: Path) -> list[Path]:
    out: list[Path] = []
    for g in globs:
        out += [p for p in sorted(root.glob(g)) if p.is_file() and p not in out]
    return out


def source_files(design: Path, root: Path = ROOT) -> list[Path]:
    """The build's own source and constraint files, by the globs in build.yaml (a bare design: its rtl/ and *.xdc)."""
    cfg = _build_cfg(design)
    files = _expand([*(cfg.get("sources") or []), *(cfg.get("constraints") or [])], root)
    if not files:
        files = sorted(p for p in design.glob("rtl/**/*") if p.is_file()) + sorted(design.glob("*.xdc"))
    return files


def extras(design: Path, root: Path = ROOT) -> dict[str, str]:
    """The inputs a build result depends on that the build manifest does not hash: spec files and the board's files."""
    out = {_rel(design / n, root): sha(design / n) for n in SPEC_FILES if (design / n).is_file()}
    try:
        from flow.prepare import board_for
        b = board_for(_build_cfg(design))
    except Exception:                                  # noqa: BLE001 (no board known: no board file hashed, and HOLES says nothing about it)
        b = None
    if b and (root / "boards" / str(b)).is_dir():
        for p in sorted((root / "boards" / str(b)).glob("*")):
            if p.is_file() and p.suffix in (".yaml", ".xdc", ".yml"):
                out[_rel(p, root)] = sha(p)
    return out


def current_inputs(design: Path, kind: str, root: Path = ROOT) -> dict[str, str]:
    """The inputs of ``kind`` as they are on disk now: the source and constraint files of build.yaml, the files a build
    manifest lists, the extras, and for ``sim`` the design's tests and model."""
    design = Path(design).resolve()
    ins = {_rel(p, root): sha(p) for p in source_files(design, root)}
    if kind.startswith("build:"):
        mf = design / "build" / kind.split(":", 1)[1] / "manifest.json"
        if mf.is_file():
            for rel in json.loads(mf.read_text()).get("inputs", {}):
                p = root / rel
                ins[rel] = sha(p) if p.is_file() else "missing"
    elif kind == "sim":
        for sub in ("tests", "model"):
            ins.update({_rel(p, root): sha(p) for p in sorted((design / sub).glob("**/*.py")) if "__pycache__" not in p.parts})
    else:
        raise ValueError(f"unknown evidence kind {kind!r}: build:<variant> or sim")
    return {**ins, **extras(design, root)}


def _load(design: Path) -> dict[str, Any]:
    try:
        return json.loads(design.joinpath(*LINEAGE).read_text())
    except (OSError, ValueError):
        return {}


def stamp(design: Path, kind: str, root: Path = ROOT, inputs: dict[str, str] | None = None) -> dict[str, Any]:
    """Record the inputs ``kind`` is made from (``inputs``: hashes taken before the run, else now)."""
    design = Path(design).resolve()
    d = _load(design)
    rec = {"taken": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "inputs": inputs if inputs is not None else current_inputs(design, kind, root)}
    if kind.startswith("build:"):
        mf = design / "build" / kind.split(":", 1)[1] / "manifest.json"
        if mf.is_file():
            rec["build_id"] = json.loads(mf.read_text()).get("build_id")
    d.setdefault("schema", "fda-lineage/1")
    d.setdefault("stamps", {})[kind] = rec
    p = design.joinpath(*LINEAGE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    return rec


def check(design: Path, kind: str, root: Path = ROOT) -> dict[str, Any]:
    """``status``: ``fresh``, ``stale`` (with ``changed``, ``added``, ``removed``), or ``no_record`` (nothing to compare with).

    For a build the manifest's own hashes decide first (they exist even when no stamp was taken): a build whose manifest
    inputs differ from the files now is stale, stamp or not. The stamp adds what the manifest does not hash (the extras)
    and, for ``sim``, everything. A new source file the build.yaml globs now match, which the build did not have, is
    ``added``."""
    design = Path(design).resolve()
    now = current_inputs(design, kind, root)
    ref: dict[str, str] = {}
    src: list[str] = []
    if kind.startswith("build:"):
        mf = design / "build" / kind.split(":", 1)[1] / "manifest.json"
        if mf.is_file():
            ref.update(json.loads(mf.read_text()).get("inputs", {}))
            src.append("manifest")
    rec = _load(design).get("stamps", {}).get(kind)
    if rec:
        for f, h in rec["inputs"].items():
            ref.setdefault(f, h)
        src.append("stamp")
    if not ref:
        return {"kind": kind, "status": "no_record", "why": "no manifest and no stamp: nothing to compare with", "changed": [],
                "added": [], "removed": [], "holes": list(HOLES)}
    changed = sorted(f for f, h in ref.items() if f in now and now[f] != h)
    removed = sorted(f for f in ref if f not in now or now[f] == "missing")
    changed = [f for f in changed if f not in removed]
    # "added": a file now in the build's source list (or, with a stamp, any tracked input) that the record does not have
    tracked = {_rel(p, root) for p in source_files(design, root)}
    added = sorted(f for f in now if f not in ref and (f in tracked or rec is not None))
    stale = bool(changed or added or removed)
    return {"kind": kind, "status": "stale" if stale else "fresh", "source": "+".join(src), "changed": changed, "added": added,
            "removed": removed, "build_id": (rec or {}).get("build_id"), "holes": list(HOLES)}


def check_manifest(manifest: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """The same comparison for a manifest record kept anywhere (results/*/manifest.json): which of its input hashes differ
    from the files in ``root`` now. For the back-test over recorded builds."""
    ins = manifest.get("inputs", {})
    changed, removed = [], []
    for rel, h in ins.items():
        p = root / rel
        if not p.is_file():
            removed.append(rel)
        elif sha(p) != h:
            changed.append(rel)
    return {"build_id": manifest.get("build_id"), "design": manifest.get("design"), "inputs": len(ins),
            "status": "stale" if changed or removed else "fresh", "changed": sorted(changed), "removed": sorted(removed)}


def findings(design: Path, root: Path = ROOT) -> list[dict[str, Any]]:
    """The check-suite rows: one STALE-EVID-01 per stale kind (blocking), for every kind that has a record."""
    design = Path(design).resolve()
    kinds = [f"build:{v}" for v in ("base", "ila") if (design / "build" / v / "manifest.json").is_file()]
    kinds += [k for k in _load(design).get("stamps", {}) if k not in kinds]
    out = []
    for k in kinds:
        r = check(design, k, root)
        if r["status"] == "stale":
            what = [*(f"changed {x}" for x in r["changed"][:5]), *(f"new {x}" for x in r["added"][:3]), *(f"gone {x}" for x in r["removed"][:3])]
            out.append({"code": "STALE-EVID-01", "severity": "error", "blocking": True, "where": f"build/{k}",
                        "message": f"{k} evidence is stale: " + "; ".join(what) + " since it was made; rebuild or re-run it before reading its result"})
    return out + claim_findings(design, root)


_CITE = re.compile(r"\bbuild[\s_-]*(?:id)?\W{0,4}`?([0-9a-f]{8})\b", re.I)


def cited_ids(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1).lower() for m in _CITE.finditer(text)))


def claim_findings(design: Path, root: Path = ROOT, files: list[Path] | None = None) -> list[dict[str, Any]]:
    """A document that cites a build ID must cite a fresh build of this design. Only decided when the design's build
    manifests are on disk (an ID with no local manifest is not judged: the build directory is regenerable)."""
    design = Path(design).resolve()
    mans = {}
    for v in ("base", "ila"):
        mf = design / "build" / v / "manifest.json"
        if mf.is_file():
            mans[json.loads(mf.read_text()).get("build_id")] = v
    if not mans:
        return []
    files = files if files is not None else [design / n for n in ("README.md", "handover.yaml") if (design / n).is_file()]
    out = []
    for f in files:
        for bid in cited_ids(Path(f).read_text(errors="replace")):
            if bid not in mans:
                out.append({"code": "STALE-CLAIM-01", "severity": "error", "blocking": True, "where": _rel(Path(f), root),
                            "message": f"{Path(f).name} cites build {bid}, which is not the current build of this design "
                                       f"(current: {', '.join(sorted(map(str, mans)))}); a claim must cite a fresh build"})
            else:
                r = check(design, f"build:{mans[bid]}", root)
                if r["status"] == "stale":
                    out.append({"code": "STALE-CLAIM-01", "severity": "error", "blocking": True, "where": _rel(Path(f), root),
                                "message": f"{Path(f).name} cites build {bid}, but its inputs have changed since (changed: "
                                           f"{', '.join(r['changed'][:3]) or 'n/a'}); a claim must cite a fresh build"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("stamp", "check", "claims"):
        p = sub.add_parser(n)
        p.add_argument("design")
        p.add_argument("rest", nargs="*")
    a = ap.parse_args(argv)
    d = Path(a.design).resolve()
    if a.cmd == "stamp":
        print(json.dumps(stamp(d, a.rest[0] if a.rest else "build:base"), indent=1))
        return 0
    if a.cmd == "claims":
        fs = claim_findings(d, files=[Path(x) for x in a.rest] or None)
        for f in fs:
            print(f"{f['code']} {f['where']}: {f['message']}")
        return 1 if fs else 0
    kinds = a.rest or [k for k in ("build:base", "build:ila", "sim") if (d / "build" / k.split(":")[-1] / "manifest.json").is_file()
                       or k in _load(d).get("stamps", {})]
    bad = 0
    for k in kinds:
        r = check(d, k)
        print(f"{k}: {r['status']}" + (f" (changed {r['changed']}, new {r['added']}, gone {r['removed']})" if r["status"] == "stale" else ""))
        bad += r["status"] == "stale"
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
