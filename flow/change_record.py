"""Configuration and change record for the traceability matrix (brief 53).

Two jobs:

1. **What the evidence was made from.** Brief 54 writes a build manifest (``manifest.json``: input hashes, tool versions,
   knowledge-bank pin, flow commit). :func:`read_manifest` reads it when it exists and otherwise computes a minimal record
   of the same four things itself, marked ``"source": "computed"``, so the matrix never depends on brief 54 having landed.
   The interface it needs from the manifest is only::

       {"inputs": {"<repo-relative path>": "<sha256>", ...},
        "tools": {"<tool>": "<version>", ...},
        "kb_pin": "<knowledge-bank commit>",
        "flow": {"commit": "<git commit>", "dirty": true|false}}

   Any other key of the manifest is kept under ``"extra"`` untouched.
2. **What changed since the last baseline.** Each requirement gets a fingerprint of its own text and proof methods
   (``req_hash``) and of its evidence (``evidence_hash``: the source of every test, property or formal job that cites it,
   plus their results). Against a baseline ``trace.json`` this lists the requirements whose evidence changed, and the
   requirements whose *text* changed while their evidence did not: their old evidence was written for the old text, so it
   no longer counts until a person re-confirms it (``reconfirmed:`` in ``verif/justifications.yaml``, with owner, reason
   and date) or the evidence itself changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
#: where brief 54's manifest may be, relative to the design directory (first found wins)
MANIFEST_PLACES = ("build/base/manifest.json", "build/manifest.json", "manifest.json")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(t: str) -> str:
    return sha256_bytes(t.encode())


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def _version(cmd: list[str], pattern: str = r"(\d+\.\d+(?:\.\d+)?)") -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(pattern, (out.stdout or "") + (out.stderr or ""))
    return m.group(1) if m else None


def tool_versions() -> dict[str, str | None]:
    """The versions of the tools whose results the matrix reads (None: not on PATH here)."""
    vers: dict[str, str | None] = {"python": sys.version.split()[0]}
    for name in ("cocotb", "cocotb_coverage", "pyyaml"):
        try:
            from importlib import metadata
            vers[name] = metadata.version(name.replace("_", "-") if name != "pyyaml" else "PyYAML")
        except Exception:                                   # noqa: BLE001 (absent package: recorded as None)
            vers[name] = None
    vers["icarus"] = _version(["iverilog", "-V"], r"version (\d+\.\d+)")
    vers["verilator"] = _version(["verilator", "--version"], r"Verilator (\d+\.\d+)")
    vers["yosys"] = _version(["yosys", "-V"], r"Yosys (\d+\.\d+)")
    vers["sby"] = "present" if shutil.which("sby") else None
    try:
        from flow import version_pin
    except ImportError:                                     # run as a script
        import version_pin                                  # type: ignore[no-redef]
    vers["vivado_expected"] = version_pin.DEFAULT_VIVADO_VERSION
    return vers


def kb_pin() -> str | None:
    """The knowledge-bank commit named in knowledge/PACKS.md ("Private repo commit: `abc1234`")."""
    try:
        m = re.search(r"Private repo commit:\s*`([0-9a-f]{7,40})`", (ROOT / "knowledge" / "PACKS.md").read_text())
    except OSError:
        return None
    return m.group(1) if m else None


def flow_commit() -> dict[str, Any]:
    def git(*a: str) -> str | None:
        try:
            r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None
    head = git("rev-parse", "--short=12", "HEAD")
    st = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": head, "dirty": None if st is None else bool(st)}


def design_inputs(design: Path, extra: list[Path] | None = None) -> dict[str, str]:
    """sha256 of every file the evidence depends on: spec, testplan, justifications, bench, checkers, formal jobs, RTL,
    constraints and the build sources listed in build.yaml."""
    files: set[Path] = set()
    for pat in ("spec.yaml", "model.py", "design.xdc", "build.yaml", "verif/*.yaml", "tests/*.py", "verif/checkers/*",
                "verif/formal/*", "rtl/*", "lint/*.yaml"):
        files.update(p for p in design.glob(pat) if p.is_file())
    try:
        import yaml
        b = yaml.safe_load((design / "build.yaml").read_text()) or {}
        for g in b.get("sources") or []:
            files.update(p for p in ROOT.glob(str(g)) if p.is_file())
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    files.update(p for p in (extra or []) if p.is_file())
    return {_rel(p): sha256_bytes(p.read_bytes()) for p in sorted(files)}


def read_manifest(design: Path, build_dir: Path | None = None) -> dict[str, Any]:
    """Brief 54's manifest if present (``source: manifest``), else a computed record of the same shape
    (``source: computed``). Never raises: a malformed manifest is reported and the computed record is used."""
    places = ([build_dir / "manifest.json"] if build_dir else []) + [design / p for p in MANIFEST_PLACES]
    note = None
    for p in places:
        if p.is_file():
            try:
                m = json.loads(p.read_text())
            except (OSError, ValueError) as e:
                note = f"{_rel(p)} is not readable JSON ({e}); computed record used instead"
                break
            if not isinstance(m, dict):
                note = f"{_rel(p)} is not a JSON object; computed record used instead"
                break
            known = ("inputs", "tools", "kb_pin", "flow")
            return {"source": "manifest", "path": _rel(p),
                    "inputs": m.get("inputs") or {}, "tools": m.get("tools") or {},
                    "kb_pin": m.get("kb_pin"), "flow": m.get("flow") or {},
                    "missing_keys": [k for k in known if k not in m],
                    "extra": {k: v for k, v in m.items() if k not in known}}
    return {"source": "computed",
            "note": note or "no build manifest (brief 54) found; inputs, tools, knowledge-bank pin and flow commit computed here",
            "inputs": design_inputs(design), "tools": tool_versions(), "kb_pin": kb_pin(), "flow": flow_commit()}


# ---- fingerprints and the baseline diff -------------------------------------------------------------------------
def req_hash(r: dict) -> str:
    """The requirement as written: id, text and proof methods (whitespace-normalised)."""
    return sha256_text(json.dumps({"id": r.get("id"), "text": " ".join(str(r.get("text", "")).split()),
                                   "proof": sorted(map(str, r.get("proof") or []))}, sort_keys=True))


def evidence_hash(items: list[dict]) -> str:
    """The evidence of one requirement: each citing artefact's source hash and result, order-free."""
    rows = sorted((str(i.get("kind")), str(i.get("name")), str(i.get("source_sha256")), str(i.get("result")))
                  for i in items)
    return sha256_text(json.dumps(rows))


def diff_baseline(current: list[dict], baseline: dict | None, reconfirmed: list[dict]) -> dict[str, Any]:
    """``current``: [{id, req_hash, evidence_hash}]. Returns the change record against ``baseline`` (a trace.json):
    added, removed, requirement text changed, evidence changed, and ``stale``: text changed but evidence not, and no
    re-confirmation recorded for the new text (its old evidence no longer counts)."""
    if not baseline:
        return {"baseline": None, "added": [], "removed": [], "text_changed": [], "evidence_changed": [], "stale": []}
    old = {r["id"]: r for r in (baseline.get("requirements") or []) if isinstance(r, dict) and r.get("id")}
    cur = {r["id"]: r for r in current}
    text_changed = sorted(i for i in cur if i in old and cur[i]["req_hash"] != old[i].get("req_hash"))
    ev_changed = sorted(i for i in cur if i in old and cur[i]["evidence_hash"] != old[i].get("evidence_hash"))
    ok = {(c.get("requirement"), c.get("req_hash")) for c in reconfirmed if isinstance(c, dict)}
    stale = sorted(i for i in text_changed if i not in ev_changed and (i, cur[i]["req_hash"]) not in ok
                   and (i, cur[i]["req_hash"][:12]) not in ok)
    return {"baseline": {"generated": baseline.get("generated"), "flow": (baseline.get("inputs") or {}).get("flow")},
            "added": sorted(set(cur) - set(old)), "removed": sorted(set(old) - set(cur)),
            "text_changed": text_changed, "evidence_changed": ev_changed, "stale": stale}
