#!/usr/bin/env python3
"""The architecture artefact (brief 05d, additions 2 and 4): ``architecture.yaml`` beside ``ARCHITECTURE.md``.

``architecture.yaml`` is the machine-readable half of the architecture note: blocks, interfaces, clock domains,
clock-domain crossings and the **predicted resources** the post-synthesis sanity gate compares the synthesised
design with. Three things live here, all pure functions over files, so the flow, the core tools and the tests
share one definition:

1. :func:`check_architecture` - the shape the gates read (validated when the file is written, with the path of
   the bad key);
2. :func:`resource_check` - the resource sanity gate. The architect predicts a LUT/FF/BRAM/DSP range; a result
   outside it by more than ``factor`` (``flow/gates.yaml``, default 2x) fails (Taylor, FPGA Horizons issue 5:
   the AI's own estimate of what it is about to build is a cheap cross-check on what came out);
3. the **approval record**: the architecture must be approved before the RTL stage. The record stores the SHA-256
   of both files at approval time, so a later edit invalidates it (the gate then sends the run back to the
   architecture stage).

    python3 flow/architecture.py check designs/<name> [--json OUT]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "fpga-design-agent/architecture/v1"
RESOURCES = ("lut", "ff", "bram_tile", "dsp")
#: interface protocols a new block interface may use (design standard STD-AXI-01); others are internal wiring
PROTOCOLS = ("axi4-lite", "axi4-stream", "simple", "uart", "gpio", "other")
#: clock-domain-crossing primitives a crossing may name: the patterns of the bank's clock-domain-crossing and
#: reset-strategy skills, the test shell's two, and AMD's XPM CDC macros
CDC_PRIMITIVES = ("sync_2ff", "sync2", "pulse_cdc", "reset_sync", "gray_pointer", "handshake_cdc", "async_fifo",
                  "xpm_cdc_single", "xpm_cdc_array_single", "xpm_cdc_gray", "xpm_cdc_handshake", "xpm_cdc_pulse",
                  "xpm_cdc_async_rst", "xpm_fifo_async")
GATES_YAML = Path(__file__).with_name("gates.yaml")
APPROVAL = Path("build") / "approvals" / "architecture.json"
FILES = ("architecture.yaml", "ARCHITECTURE.md")


def gates_config(path: Path | None = None) -> dict[str, Any]:
    """``flow/gates.yaml``: thresholds the flow owns (the resource sanity factor). Missing file: the defaults."""
    cfg = {"resource_sanity": {"factor": 2.0, "resources": list(RESOURCES)}}
    p = path or GATES_YAML
    if p.is_file():
        data = yaml.safe_load(p.read_text()) or {}
        for k, v in (data.get("resource_sanity") or {}).items():
            cfg["resource_sanity"][k] = v
    return cfg


# ---- the file ---------------------------------------------------------------------------------------------
def _range(v: Any) -> tuple[float, float] | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
        return float(v), float(v)
    if (isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                              for x in v) and 0 <= v[0] <= v[1]):
        return float(v[0]), float(v[1])
    return None


def check_architecture(data: Any) -> list[str]:
    """What the gates read from ``architecture.yaml``, as problems (empty list: it can read it)."""
    if not isinstance(data, dict):
        return ["architecture.yaml must be a YAML mapping at the top level"]
    errs: list[str] = []
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks or not all(isinstance(b, dict) and b.get("name") for b in blocks):
        errs.append("'blocks' must be a non-empty list of mappings, each with a 'name' (and a 'function')")
    names = {b["name"] for b in blocks if isinstance(b, dict) and b.get("name")} if isinstance(blocks, list) else set()
    ifs = data.get("interfaces")
    if not isinstance(ifs, list):
        errs.append("'interfaces' must be a list (it may be empty: each entry {name, between: [a, b], protocol, "
                    f"prefix}}, protocol one of {', '.join(PROTOCOLS)})")
    else:
        for i, f in enumerate(ifs):
            if not isinstance(f, dict) or not f.get("name") or f.get("protocol") not in PROTOCOLS:
                errs.append(f"interfaces[{i}] must be a mapping with a 'name' and a 'protocol' in {', '.join(PROTOCOLS)}")
            elif f["protocol"].startswith("axi4") and not f.get("prefix"):
                errs.append(f"interfaces[{i}] ({f['name']}): an AXI interface needs a 'prefix' (for example s_axi) "
                            "and, optionally, 'module' (the module that has the ports)")
    doms = data.get("clock_domains")
    if not isinstance(doms, list) or not doms or not all(isinstance(d, dict) and d.get("name") and d.get("clock")
                                                         for d in doms):
        errs.append("'clock_domains' must be a non-empty list of mappings, each with a 'name' and a 'clock' (the "
                    "clock port or net name; freq_mhz recommended)")
    dnames = {d["name"] for d in doms if isinstance(d, dict) and d.get("name")} if isinstance(doms, list) else set()
    xs = data.get("crossings")
    if not isinstance(xs, list):
        errs.append("'crossings' must be a list (empty if there are none): each {from, to, signal, primitive}; "
                    "'from' may be 'async' for an asynchronous external input")
    else:
        for i, x in enumerate(xs):
            if not (isinstance(x, dict) and x.get("from") and x.get("to") and x.get("primitive")):
                errs.append(f"crossings[{i}] must be a mapping with 'from', 'to', 'primitive' (and 'signal')")
                continue
            for end in ("from", "to"):
                if x[end] != "async" and dnames and x[end] not in dnames:
                    errs.append(f"crossings[{i}].{end} = {x[end]!r} is not a declared clock domain ({', '.join(sorted(dnames))})")
            if x["primitive"] not in CDC_PRIMITIVES:
                errs.append(f"crossings[{i}].primitive = {x['primitive']!r} is not a bank CDC primitive "
                            f"({', '.join(CDC_PRIMITIVES)})")
    pr = data.get("predicted_resources")
    if not isinstance(pr, dict):
        errs.append("'predicted_resources' must be a mapping with a [low, high] range for each of "
                    f"{', '.join(RESOURCES)} (a single number means exactly that many)")
    else:
        for r in RESOURCES:
            if r not in pr:
                errs.append(f"predicted_resources has no {r!r}")
            elif _range(pr[r]) is None:
                errs.append(f"predicted_resources.{r} must be a number or [low, high] with 0 <= low <= high")
    try:                                                 # closure-loop hook: the optional design-time datapaths (timing plan)
        from flow.timing_plan import check_datapaths
    except ModuleNotFoundError:                          # run as a script from flow/ (standards_check.py)
        from timing_plan import check_datapaths
    errs += check_datapaths(data)
    return errs


def load(design: Path) -> dict[str, Any]:
    p = design / "architecture.yaml"
    return yaml.safe_load(p.read_text()) or {} if p.is_file() else {}


def predicted(data: dict[str, Any]) -> dict[str, tuple[float, float]]:
    return {r: _range((data.get("predicted_resources") or {}).get(r)) or (0.0, 0.0) for r in RESOURCES}


def declared_clocks(data: dict[str, Any]) -> set[str]:
    return {str(d["clock"]) for d in data.get("clock_domains") or [] if isinstance(d, dict) and d.get("clock")}


# ---- resource sanity (addition 4) -------------------------------------------------------------------------
def resource_check(util: dict[str, Any], arch: dict[str, Any], factor: float | None = None) -> dict[str, Any]:
    """Compare a utilisation (``flow/gates.parse_utilization``) with the predicted ranges. A resource passes when
    ``low / factor <= used <= high * factor`` (a predicted 0 therefore allows 0 only). ``direction`` says which
    side it fell off; the rows hold raw numbers only."""
    f = float(factor if factor is not None else gates_config()["resource_sanity"]["factor"])
    rows: dict[str, Any] = {}
    for r, (lo, hi) in predicted(arch).items():
        used = util.get(r)
        used = 0 if used is None else used
        lo_lim, hi_lim = lo / f, hi * f
        ok = lo_lim <= used <= hi_lim
        rows[r] = {"used": used, "predicted": [lo, hi], "allowed": [round(lo_lim, 2), round(hi_lim, 2)], "pass": ok,
                   "direction": None if ok else ("above" if used > hi_lim else "below")}
    return {"factor": f, "resources": rows, "pass": all(v["pass"] for v in rows.values())}


def resource_failures(rc: dict[str, Any]) -> list[str]:
    return [f"resources: {r} used {v['used']} outside the predicted {v['predicted']} by more than {rc['factor']:g}x "
            f"({v['direction']}; allowed {v['allowed']})" for r, v in rc["resources"].items() if not v["pass"]]


# ---- the approval record (addition 2) ---------------------------------------------------------------------
def digest(design: Path) -> str:
    h = hashlib.sha256()
    for n in FILES:
        p = design / n
        h.update(n.encode() + b"\0" + (p.read_bytes() if p.is_file() else b"") + b"\0")
    return h.hexdigest()


def write_approval(design: Path, by: str, source: str, note: str = "") -> dict[str, Any]:
    """Record an approval. ``by``: ``owner`` (a person approved it), ``auto`` (``--review off``). ``source``:
    ``agent`` (the agent wrote it) or ``owner`` (the owner supplied or edited it)."""
    rec = {"decision": "approve", "by": by, "source": source, "note": note, "sha256": digest(design),
           "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    p = design / APPROVAL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=1) + "\n")
    return rec


def read_approval(design: Path) -> dict[str, Any] | None:
    p = design / APPROVAL
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def approval_status(design: Path) -> tuple[bool, str]:
    """(approved, why not). Approved means a record exists AND the files are the ones it was made for."""
    rec = read_approval(design)
    if not rec or rec.get("decision") != "approve":
        return False, "the architecture has not been approved"
    if rec.get("sha256") != digest(design):
        return False, "architecture.yaml or ARCHITECTURE.md changed after it was approved"
    return True, ""


def check_design(design: Path) -> dict[str, Any]:
    p = design / "architecture.yaml"
    if not p.is_file():
        return {"ok": False, "errors": ["architecture.yaml does not exist"], "approved": False}
    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        return {"ok": False, "errors": [f"architecture.yaml is not valid YAML: {' '.join(str(e).split())}"],
                "approved": False}
    errs = check_architecture(data)
    if not (design / "ARCHITECTURE.md").is_file():
        errs.append("ARCHITECTURE.md does not exist")
    ok, why = approval_status(design)
    return {"ok": not errs, "errors": errs, "approved": ok, "approval_note": why, "approval": read_approval(design)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("design", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    res = check_design(a.design.resolve())
    for e in res["errors"]:
        print(f"architecture: {e}")
    print(f"architecture: {'valid' if res['ok'] else 'INVALID'}; approved: {res['approved']}"
          + ("" if res["approved"] else f" ({res['approval_note']})"))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=1) + "\n")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
