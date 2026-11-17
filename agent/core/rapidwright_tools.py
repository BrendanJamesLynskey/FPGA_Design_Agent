"""Agent tools that use RapidWright (brief 100): move a pre-implemented block, place the latency chain, route chosen nets, and ask Vivado to
judge the result. RapidWright reads and writes Vivado checkpoints between two Vivado steps; **Vivado's timing analysis is the referee**: no
tool here reports a RapidWright estimate as a result, and the only tool that returns timing is ``rw_referee``, which runs Vivado.

Rules the tools follow (as for the other flow tools, :mod:`agent.core.tools`):
- inputs are checkpoints the flow wrote under build/<variant>/ (a file name, not a path); outputs go under build/<variant>/rw/;
- the agent never supplies a script, a command or a path outside the design; argv is fixed here from validated arguments;
- every call needs RapidWright installed (``tools/rapidwright_env/setup.sh``); without it the tool says so and nothing else happens;
- the tools return raw JSON/text from the scripts, no fix hints.
The schemas are offered to the stage roles only when ``FDA_RAPIDWRIGHT=1`` (agent.core.rapidwright_tools.enabled), so the golden requests of
earlier briefs are unchanged.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agent.core.registry import tool
from agent.core.security import SecurityError
from agent.core.session import Session
from flow import rapidwright_pin as pin

_DCP = re.compile(r"^[A-Za-z0-9_\-]{1,60}\.dcp$")
_SITE = re.compile(r"^SLICE_X\d{1,3}Y\d{1,3}$")
_CELL_PAT = re.compile(r"^[A-Za-z0-9_\-\[\]\*\./]{1,80}$")
_NET = re.compile(r"^[A-Za-z0-9_\-\[\]\./]{1,120}$")
_ANCHOR = re.compile(r"^(GTHE4_CHANNEL|GTYE4_CHANNEL|SLICE)_X\d{1,3}Y\d{1,3}$")
HEAVY = ("RapidWright starts a JVM (about 3 GB the first time for a checkpoint, 1 GB after) and, on a first read, a Vivado; "
         "run it only where the heavy-job rules allow.")


def enabled() -> bool:
    """The tools are offered to a role only with FDA_RAPIDWRIGHT=1 and RapidWright installed."""
    return os.environ.get("FDA_RAPIDWRIGHT") == "1" and pin.available()[0]


def _vdir(s: Session, variant: str) -> Path:
    return s.jail.resolve(f"build/{variant}")


def _in_dcp(s: Session, variant: str, name: str) -> Path:
    if not _DCP.match(name):
        raise SecurityError("arguments", f"checkpoint {name!r} must be a plain file name ending .dcp inside build/{variant}/")
    p = _vdir(s, variant) / name
    if not p.is_file():
        raise SecurityError("arguments", f"no checkpoint build/{variant}/{name} (the flow writes post_synth.dcp and post_route.dcp)")
    return p


def _out_dcp(s: Session, variant: str, name: str) -> Path:
    if not _DCP.match(name):
        raise SecurityError("arguments", f"output {name!r} must be a plain file name ending .dcp")
    d = _vdir(s, variant) / "rw"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _rw(s: Session, kind: str, script: str, *args: str, timeout: float = 1800) -> dict[str, Any]:
    ok, why = pin.available()
    if not ok:
        return {"ok": False, "output": why}
    r = s.runner.run(kind, pin.argv(s.root / "flow" / "rw" / script, *args), s.root, pin.env(), timeout=timeout)
    js = next((json.loads(l) for l in reversed(r.stdout.splitlines()) if l.startswith("{")), None)
    return {"ok": r.returncode == 0 and js is not None, "result": js, "returncode": r.returncode,
            "output": (json.dumps(js) if js else (r.stdout + r.stderr)[-3000:]), "seconds": r.seconds}


_V = {"type": "string", "enum": ["base", "ila"]}
_CK = {"type": "string", "pattern": _DCP.pattern, "description": "A checkpoint file name in build/<variant>/ (post_route.dcp)."}
_OUT = {"type": "string", "pattern": _DCP.pattern, "description": "Output checkpoint name; written to build/<variant>/rw/."}


@tool("rw_status", "Is RapidWright usable on this machine, and which versions the tools were measured with (RapidWright, Vivado, Java). "
      "Nothing is run.", {})
def rw_status(s: Session) -> dict:
    ok, why = pin.available()
    return {"ok": ok, "output": why or f"RapidWright {pin.RAPIDWRIGHT_VERSION} with Vivado {pin.VIVADO_VERSION}'s JRE is installed",
            "rapidwright": pin.RAPIDWRIGHT_VERSION, "vivado": pin.VIVADO_VERSION, "available": ok}


@tool("rw_relocate_block", "Move a pre-implemented routed block (the whole checkpoint is the block, for example an out-of-context "
      "checkpoint) so that its anchor slice lands on target_site, keeping its placement and routing shape. RapidWright refuses a target "
      "whose column pattern does not match (ok false). Returns the tile offset and bounding boxes. Judge the stamped block with rw_referee. "
      + HEAVY, {"variant": _V, "checkpoint": _CK, "output": _OUT, "target_site": {"type": "string", "pattern": _SITE.pattern}},
      ["checkpoint", "output", "target_site"])
def rw_relocate_block(s: Session, checkpoint: str, output: str, target_site: str, variant: str = "base") -> dict:
    if not _SITE.match(target_site):
        raise SecurityError("arguments", "target_site must look like SLICE_X41Y70")
    return _rw(s, "rw_relocate", "relocate.py", "moveto", str(_in_dcp(s, variant, checkpoint)), str(_out_dcp(s, variant, output)), target_site)


@tool("rw_place_chain", "Re-place a chain of cells with RapidWright: whole slices (LUT/FF packing kept) that hold a chain cell move to free sites "
      "near an anchor (a GT channel or a slice) by simulated annealing on wire length; nets of moved slices are un-routed, the rest keep "
      "their routing. Returns slices moved and RapidWright's own estimate (for the log: it is not a timing result). Then run rw_referee, "
      "which routes and times it in Vivado. cells: name patterns (fnmatch, for example u_pcs/*). " + HEAVY,
      {"variant": _V, "checkpoint": _CK, "output": _OUT, "cells": {"type": "array", "items": {"type": "string", "pattern": _CELL_PAT.pattern}, "minItems": 1, "maxItems": 16},
       "anchor": {"type": "string", "pattern": _ANCHOR.pattern}, "window_cols": {"type": "integer", "minimum": 4, "maximum": 120},
       "window_rows": {"type": "integer", "minimum": 4, "maximum": 120}, "seed": {"type": "integer", "minimum": 0, "maximum": 100000},
       "iterations": {"type": "integer", "minimum": 1000, "maximum": 400000}},
      ["checkpoint", "output", "cells", "anchor"])
def rw_place_chain(s: Session, checkpoint: str, output: str, cells: list, anchor: str, variant: str = "base", window_cols: int = 60,
                   window_rows: int = 40, seed: int = 1, iterations: int = 200000) -> dict:
    for c in cells:
        if not _CELL_PAT.match(c):
            raise SecurityError("arguments", f"cell pattern {c!r} has characters outside the allowed set")
    out = _out_dcp(s, variant, output)
    cfg = out.with_suffix(".chain.json")
    cfg.write_text(json.dumps({"cells": cells, "anchor": anchor, "window": {"cols": window_cols, "rows": window_rows}}))
    return _rw(s, "rw_place", "place_chain.py", str(_in_dcp(s, variant, checkpoint)), str(out), str(cfg), "--seed", str(seed), "--iters", str(iterations))


@tool("rw_route", "Route with RapidWright's RWRoute instead of Vivado's router. mode full: every net of the (placed or partly routed) checkpoint, "
      "timing-driven. mode nets: only the named nets (full net names), then lock them (fixed routes); Vivado's route_design (rw_referee "
      "route=true) routes the rest and keeps the locked nets. Returns the RWRoute wall time. Judge with rw_referee. " + HEAVY,
      {"variant": _V, "checkpoint": _CK, "output": _OUT, "mode": {"type": "string", "enum": ["full", "nets"]},
       "nets": {"type": "array", "items": {"type": "string", "pattern": _NET.pattern}, "maxItems": 200}}, ["checkpoint", "output", "mode"])
def rw_route(s: Session, checkpoint: str, output: str, mode: str, variant: str = "base", nets: list | None = None) -> dict:
    src, out = _in_dcp(s, variant, checkpoint), _out_dcp(s, variant, output)
    if mode == "full":
        return _rw(s, "rw_route", "route.py", "full", str(src), str(out), "timing")
    if not nets:
        raise SecurityError("arguments", "mode nets needs the net names")
    nf = out.with_suffix(".nets.txt")
    nf.write_text("\n".join(nets) + "\n")
    return _rw(s, "rw_route", "route.py", "nets", str(src), str(out), str(nf))


@tool("rw_referee", "Vivado's verdict on a checkpoint RapidWright wrote: optionally route_design first (needed after rw_place_chain, or after "
      "rw_route mode nets), then worst setup and hold slack, route status, DRC and utilisation. This is the only timing the rw_* tools "
      "report. Reports are written to build/<variant>/rw/<name>_*.rpt. Heavy: a Vivado run.",
      {"variant": _V, "checkpoint": {"type": "string", "pattern": _DCP.pattern, "description": "A checkpoint in build/<variant>/rw/ (an rw_* output) or in build/<variant>/."},
       "route": {"type": "boolean"}}, ["checkpoint"])
def rw_referee(s: Session, checkpoint: str, variant: str = "base", route: bool = False) -> dict:
    d = _vdir(s, variant)
    src = d / "rw" / checkpoint if (d / "rw" / checkpoint).is_file() else _in_dcp(s, variant, checkpoint)
    (d / "rw").mkdir(parents=True, exist_ok=True)
    stem = d / "rw" / src.with_suffix("").name       # reports always go to build/<variant>/rw/, never over the flow's own files
    env = {**pin.env(), "B100_IN_DCP": str(src), "B100_OUT": str(stem), "B100_ROUTE": "1" if route else "0", "B100_THREADS": "1"}
    from flow import version_pin
    r = s.runner.run("rw_referee", [version_pin.vivado_path(), "-mode", "batch", "-nojournal", "-nolog", "-source",
                                    str(s.root / "flow" / "rw" / "referee.tcl")], d, env, timeout=3600)
    rj = Path(f"{stem}_run.json")
    res = json.loads(rj.read_text()) if rj.is_file() else None
    extra = {}
    cj = Path(f"{stem}_chain.json")
    if cj.is_file():
        extra["chain"] = json.loads(cj.read_text())
    return {"ok": r.returncode == 0 and res is not None, "result": res, **extra, "returncode": r.returncode,
            "output": json.dumps({"result": res, **extra}) if res else (r.stdout + r.stderr)[-3000:], "seconds": r.seconds}
