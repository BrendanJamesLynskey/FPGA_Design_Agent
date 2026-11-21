"""The latency-critical path of a design: stages from ``latency_stages.yaml``, clocks reconciled against the benches (brief 97).

Two different "critical paths" (say it every time, because a loop that mixes them shaves picoseconds off the wrong path):

* the **timing-critical path** has the worst slack and limits the clock period;
* the **latency-critical path** is the chain of registers and clock crossings from the first bit of the input on the wire
  to the first bit of the output on the wire. Latency = (registers on that chain) x (period), plus the GT and optics.
  Cutting a register usually beats shaving picoseconds; shaving picoseconds matters only when it lets the clock go faster or
  lets two stages merge into one.

Nothing here simulates or builds. ``run_trace`` runs the design's own whole-core bench (its pytest entry named in
``latency_stages.yaml``) and ``load_slack`` reads the JSON that ``netlist_slack.tcl`` wrote from a post-route checkpoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CRITICAL_SLACK_NS = 0.30            # a stage whose registers have less setup slack than this is called timing-critical


class LatencyError(Exception):
    pass


def load_stages(design: Path) -> dict[str, Any]:
    f = Path(design) / "latency_stages.yaml"
    if not f.is_file():
        raise LatencyError(f"{f} not found: the design has not declared its latency chain")
    d = yaml.safe_load(f.read_text())
    if d.get("schema") != "fda.latency_stages/1":
        raise LatencyError(f"{f}: unknown schema {d.get('schema')!r}")
    return d


def _dig(obj: Any, dotted: str) -> Any:
    for k in dotted.split("."):
        if not isinstance(obj, dict) or k not in obj:
            raise LatencyError(f"key {dotted!r} not found in the recorded results (at {k!r})")
        obj = obj[k]
    return obj


def run_trace(design: Path, st: dict[str, Any] | None = None, out: Path | None = None, timeout: int = 900,
              root: Path | None = None, extra: list[str] | None = None, entry: str | None = None) -> Path:
    """Run the design's whole-core bench; return the JSON it wrote. Only a pytest entry under ``designs/`` is run (no free command)."""
    st = st or load_stages(design)
    t = st["trace"]
    entry = entry or t["pytest"]
    if not entry.startswith("designs/") or ".." in entry or not entry.split("::")[0].endswith(".py"):
        raise LatencyError(f"trace entry {entry!r} must be a pytest file under designs/")
    root = Path(root) if root else ROOT          # the checkout that holds the design (a frozen copy under test, or this one)
    out = Path(out) if out else root / "build" / "latency" / f"{st['design']}_core_sim.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()                              # never report an older run's clocks as this run's
    env = {**os.environ, t["results_env"]: str(out), "PYTHONPATH": str(root)}
    p = subprocess.run([sys.executable, "-m", "pytest", entry, *(extra or []), "-x", "-q"], cwd=root, env=env, capture_output=True,
                       text=True, timeout=timeout)
    if p.returncode != 0 or not out.is_file():
        raise LatencyError("the whole-core bench failed, so no clocks were measured:\n" + (p.stdout + p.stderr)[-1500:])
    return out


def load_slack(path: Path | None) -> dict[str, Any] | None:
    if path and Path(path).is_file():
        return json.loads(Path(path).read_text())
    return None


def latency_path(design: Path, core_sim: dict[str, Any], slack: dict[str, Any] | None = None, path: str = "tick_to_trade",
                 st: dict[str, Any] | None = None, lat_sim: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every stage of ``path`` with its clocks (cumulative and added), ns, domain, the registers it is made of and their
    post-route slack, reconciled against the bench. ``reconciled`` is false when the stage clocks do not add up to what the
    bench measured: then the table is not to be trusted and says so."""
    st = st or load_stages(design)
    if path not in st["paths"]:
        raise LatencyError(f"unknown path {path!r}; the design declares {sorted(st['paths'])}")
    p = st["paths"][path]
    period = float(st["period_ns"])
    files = {"core_sim.json": core_sim, "latency_sim.json": lat_sim or {}}

    def measured(m: dict[str, Any]) -> int | None:
        if "value" in m:
            return int(m["value"])
        if m.get("residual"):
            return None
        return int(_dig(files[m["file"]], m["key"]))

    segs = {s["id"]: {"id": s["id"], "measured": measured(s["measured"]), "stages": [], "sum": 0} for s in p["segments"]}
    total_measured = int(_dig(files[p["measured"]["file"]], p["measured"]["key"]))
    rows = []
    cum = 0
    slack_by = (slack or {}).get("stages", {})
    for s in p["stages"]:
        c = int(s["clocks"])
        if c >= 0:
            cum += c
            segs[s["segment"]]["sum"] += c
        segs[s["segment"]]["stages"].append(s["id"])
        sl = slack_by.get(s["id"], {})
        rows.append({"id": s["id"], "name": s["name"], "domain": s["domain"], "kind": s["kind"],
                     "clocks": c if c >= 0 else None, "cumulative_clocks": cum if c >= 0 else None,
                     "ns": round(c * period, 3) if c >= 0 else None,
                     "registers": s.get("registers", []),
                     "netlist": {"cells": sl.get("cells"), "clock": sl.get("clock"), "setup_slack_ns": sl.get("setup_slack_ns")} if sl else None,
                     "timing_critical": (sl.get("setup_slack_ns") is not None and sl["setup_slack_ns"] < CRITICAL_SLACK_NS) if sl else None,
                     "segment": s["segment"], "why": s["why"], "remove_risk": s["remove_risk"],
                     "technique": s.get("technique", "none"), "removable": int(s.get("removable", 0)),
                     **({"coupled_with": [str(x) for x in s["coupled_with"]]} if s.get("coupled_with") else {})})      # brief 104B: optional, read by flow/options/split.py
    problems = []
    for sg in segs.values():
        if sg["measured"] is not None and sg["sum"] != sg["measured"]:
            problems.append(f"segment {sg['id']}: stages add to {sg['sum']} clocks, the bench measured {sg['measured']}")
    # a residual segment (the echo's receive side) takes whatever the total leaves
    resid = [sg for sg in segs.values() if sg["measured"] is None]
    if resid:
        known = sum(sg["sum"] for sg in segs.values() if sg["measured"] is not None)
        resid[0]["measured"] = total_measured - known
        for r in rows:
            if r["segment"] == resid[0]["id"] and r["clocks"] is None:
                r["clocks"], r["ns"] = resid[0]["measured"], round(resid[0]["measured"] * period, 3)
                r["residual"] = True
    else:
        if cum != total_measured:
            problems.append(f"the stages add to {cum} clocks, the bench measured {total_measured}")
    return {"design": st["design"], "path": path, "title": p["title"], "period_ns": period,
            "total_clocks": total_measured, "total_ns": round(total_measured * period, 3), "stages": rows,
            "segments": list(segs.values()), "reconciled": not problems, "problems": problems,
            "slack_source": (slack or {}).get("source"), "note": "timing-critical = worst setup slack (limits the clock period); "
            "latency-critical = this chain (registers x period); the two are different paths"}


def board_numbers(st: dict[str, Any], results: Path) -> dict[str, Any] | None:
    b = st.get("board")
    f = results / b["file"] if b else None
    if not f or not f.is_file():
        return None
    d = json.loads(f.read_text())
    E = float(_dig(d, b["echo_clocks_key"]))
    L = float(_dig(d, b["loop_clocks_key"]))
    fibre = float(_dig(d, b["fibre_one_way_ns_key"]))
    return {"file": str(b["file"]), "E_clocks": E, "L_clocks": L, "fibre_ns": fibre}


def latency_budget(design: Path, core_sim: dict[str, Any], slack: dict[str, Any] | None = None, results: Path | None = None,
                   st: dict[str, Any] | None = None, path: str = "tick_to_trade") -> dict[str, Any]:
    """The table the agent reasons from: the stages of the path ranked by what could come out, with the board's share beside them.
    The GT and optics row and the wire-to-wire total come only from the recorded board run; simulation figures and board
    figures are never added into one number without the residual shown."""
    st = st or load_stages(design)
    lp = latency_path(design, core_sim, slack, path, st)
    period = lp["period_ns"]
    digital = lp["total_clocks"]
    table = []
    for r in lp["stages"]:
        table.append({"stage": r["id"], "what": r["name"], "domain": r["domain"], "kind": r["kind"], "clocks": r["clocks"], "ns": r["ns"],
                      "setup_slack_ns": (r["netlist"] or {}).get("setup_slack_ns"), "timing_critical": r["timing_critical"],
                      "why_it_exists": r["why"], "risk_of_removing": r["remove_risk"], "technique": r["technique"],
                      "removable_clocks": r["removable"], "needs_board": False})
    out: dict[str, Any] = {"design": lp["design"], "path": path, "period_ns": period, "reconciled": lp["reconciled"],
                           "problems": lp["problems"], "digital_clocks": digital, "digital_ns": lp["total_ns"], "rows": table}
    bn = board_numbers(st, results) if results else None
    if bn and path == "tick_to_trade":
        g = st["board"]["gt_optics_stage"]
        gt_clocks = bn["E_clocks"] - st["board"]["digital_echo_clocks"]
        w2w = bn["L_clocks"] - bn["E_clocks"] - bn["fibre_ns"] / period
        table.append({"stage": g["id"], "what": g["name"], "domain": g["domain"], "kind": g["kind"], "clocks": round(gt_clocks, 1),
                      "ns": round(gt_clocks * period, 1), "setup_slack_ns": None, "timing_critical": None, "why_it_exists": g["why"],
                      "risk_of_removing": g["remove_risk"], "technique": g["technique"], "removable_clocks": g["removable_estimate_clocks"],
                      "needs_board": True, "source": g["source"]})
        residual = w2w - digital - gt_clocks
        out["board"] = {**bn, "wire_to_wire_clocks": round(w2w, 1), "wire_to_wire_ns": round(w2w * period, 1),
                        "gt_optics_clocks": round(gt_clocks, 1), "unattributed_clocks": round(residual, 1),
                        "note": "wire-to-wire = L - E - fibre (board, medians of 100 restarts); digital = the simulated GT-word-to-GT-word "
                                "chain; the unattributed clocks are the two accountings' difference (the RX stamp's synchroniser delay "
                                "understates D, the echo counts digital TX and RX clocks once): never hidden, never counted as saved"}
    ranked = sorted((r for r in table if r["removable_clocks"] not in (0, "unknown")), key=lambda r: -float(r["removable_clocks"]))
    out["ranking_by_removable_clocks"] = [r["stage"] for r in ranked]
    out["total_removable_digital_clocks_upper_bound"] = sum(int(r["removable_clocks"]) for r in table if isinstance(r["removable_clocks"], int))
    out["note"] = ("an upper bound, not a plan: each removable clock carries the risk in its row, and removals interact "
                   "(two merged stages cannot both be merged again)")
    return out
