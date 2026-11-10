"""The input hash of each (module, stage): the key a stage's evidence is valid for (docs/design_environment.md, section 6).

Each stage hashes its own inputs (the table below) **and the key of the stage before it**, so a change to an input of
stage *k* changes the key of *k* and of every later stage. A piece of evidence is current only when the key it records
equals the key computed from today's files; the earliest stage whose key moved is where the flow re-enters.

| Stage | Own inputs (module directory unless marked) |
|---|---|
| 0 clarify | ``spec.md``; ``contract.yaml``; the system requirements that list the module (``system/requirements.yaml``) |
| 1 board-and-device-planning (architecture) | ``spec.yaml``; the module's binding in ``design.yaml`` (clocks, resets, parameters, register crossings); the far end of every connected interface, as declared in the other module's contract |
| 2 rtl-design-creation | ``architecture.yaml``, ``ARCHITECTURE.md``, ``rtl/``, ``model.py``, ``tests/``, ``verif/`` |
| 3 constraints | ``ooc.xdc``; the design's clock and reset plan |
| 4 synthesis | ``build.yaml`` |
| 5-8 implementation and closure | (chained only: they read the synthesis output) |
| 9 configuration-and-debug | ``hw_checks.py``, ``probes.yaml`` |

P0 puts no tool versions in the key (no tool runs yet). P2 adds the tool fingerprint the design names (Vivado and
simulator versions, knowledge-pack hashes, the commit of the ``flow/`` scripts a stage runs).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent.core.session import STAGES

KEY_SCHEMA = "fpga-design-agent/stage-key/v1"
OWN_INPUTS: dict[int, tuple[str, ...]] = {
    0: ("spec.md", "contract.yaml"),
    1: ("spec.yaml",),
    2: ("architecture.yaml", "ARCHITECTURE.md", "rtl", "model.py", "tests", "verif"),
    3: ("ooc.xdc",),
    4: ("build.yaml",),
    5: (), 6: (), 7: (), 8: (),
    9: ("hw_checks.py", "probes.yaml"),
}
SKIP_DIRS = {"__pycache__", "build", "sim_build", ".pytest_cache"}


def _files(mod_dir: Path, rel: str) -> list[tuple[str, str]]:
    """(relative path, sha256) of a file, or of every file under a directory; ``-`` marks an absent input."""
    p = mod_dir / rel
    if p.is_file():
        return [(rel, hashlib.sha256(p.read_bytes()).hexdigest())]
    if p.is_dir():
        out = []
        for f in sorted(p.rglob("*")):
            if f.is_file() and not (set(f.relative_to(mod_dir).parts) & SKIP_DIRS) and f.suffix != ".pyc":
                out.append((f.relative_to(mod_dir).as_posix(), hashlib.sha256(f.read_bytes()).hexdigest()))
        return out or [(rel + "/", "-")]
    return [(rel, "-")]


def _extras(project: Any, module: str, stage: int) -> dict[str, Any]:
    """The inputs of a stage that are not whole files in the module directory, as canonical data."""
    d = project.design
    if stage == 0:
        reqs = (project.requirements or {}).get("requirements") or []
        return {"requirements": [r for r in reqs if isinstance(r, dict) and module in (r.get("modules") or [])]}
    if stage == 1:
        m = project.module(module)
        far = []
        for x in d.get("connections") or []:
            if not isinstance(x, dict):
                continue
            for near, other in (("from", "to"), ("to", "from")):
                if str(x.get(near, "")).split(".")[0] == module:
                    far.append({"link": x, "far": project.iface(str(x.get(other, "")))})
        return {"binding": {k: m.get(k) for k in ("kind", "clocks", "resets", "params", "window_base",
                                                     "register_crossings")}, "connections": far}
    if stage == 3:
        return {"clocks": d.get("clocks"), "resets": d.get("resets")}
    return {}


def stage_inputs(project: Any, module: str, stage: int) -> dict[str, Any]:
    mod_dir = project.root / "modules" / module
    files = [x for rel in OWN_INPUTS[stage] for x in _files(mod_dir, rel)]
    return {"stage": STAGES[stage], "files": files, "extras": _extras(project, module, stage)}


def stage_keys(project: Any, module: str) -> list[dict[str, Any]]:
    """For each stage 0-9: {stage, n, key, own} where ``own`` is the hash of the stage's own inputs and ``key`` chains it
    with the previous stage's key."""
    out: list[dict[str, Any]] = []
    prev = ""
    for n, name in enumerate(STAGES):
        inp = stage_inputs(project, module, n)
        own = hashlib.sha256(json.dumps(inp, sort_keys=True, default=str).encode()).hexdigest()
        key = hashlib.sha256(f"{KEY_SCHEMA}\0{module}\0{name}\0{prev}\0{own}".encode()).hexdigest()
        out.append({"n": n, "stage": name, "own": own, "key": key, "files": inp["files"]})
        prev = key
    return out


def stage_index(name_or_n: Any) -> int | None:
    if isinstance(name_or_n, int) and not isinstance(name_or_n, bool) and 0 <= name_or_n < len(STAGES):
        return name_or_n
    return STAGES.index(name_or_n) if name_or_n in STAGES else None
