#!/usr/bin/env python3
"""Brief 216: run closure-recipe candidates in Vivado, one at a time, from a post-synthesis checkpoint.

The Tcl comes only from ``agent.graph.closure_recipes.render_impl_tcl`` (fixed templates). The caller holds ONE heavy slot (take_heavy_slot.sh
with ``Vivado impl`` and the declared peak) for the whole sequence; each run is a ``systemd-run --user --scope -p MemoryMax=<N+1>G nice -n 15``
Vivado batch with one thread, so runs are sequential and the load stays low. Outcomes are parsed with ``flow.tournament.parse`` (the same
parser the 178 results used), so numbers are comparable with ``results/178_tournament``.

    python3 -m flow.closure_recipe_run <plan.json> <post_synth.dcp> <out_dir> [--peak-g 4]      # one candidate (debugging)

A plan that needs a synthesis run (``plan.synth`` non-empty) is mapped to a recorded synthesis checkpoint through ``synth_dcps``
(key = :func:`synth_key`); a plan with a synthesis option that has no checkpoint is reported ``status: no synth checkpoint`` (not run, not scored).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.graph import closure_recipes as R          # noqa: E402
from flow import tournament as T                      # noqa: E402


def family_of(part: str) -> str:
    return "7series" if part.startswith("xc7") else "ultrascale+"


def synth_key(plan: R.ImplPlan) -> str:
    """The key of a plan's synthesis settings: ``default`` for none, else the sorted options (``retiming``, ``keep_equivalent_registers``, ...)."""
    return "default" if not plan.synth else "+".join(f"{k}" if v is None else f"{k}={v}" for k, v in plan.synth)


def run_one(plan: R.ImplPlan, start_dcp: Path, wd: Path, peak_g: float, clock_ns: float, timeout_s: int = 3 * 3600) -> dict[str, Any]:
    """One candidate: write run.tcl, run Vivado under a memory-capped scope, parse the reports. Never raises on a Vivado failure: the status says."""
    wd.mkdir(parents=True, exist_ok=True)
    tcl = wd / "run.tcl"
    tcl.write_text(R.render_impl_tcl(plan, str(start_dcp), str(wd)))
    log = wd / "vivado.log"
    t0 = time.time()
    p = subprocess.run(T._child_cmd(tcl, log, peak_g + 1), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_s)
    out = T.parse(wd)
    if p.returncode != 0 and out.get("status") == "ok":
        out["status"] = f"vivado exit {p.returncode}"
    out.update({"clock_ns": clock_ns, "wall_s": round(time.time() - t0, 1), "plan": plan.to_dict()})
    return out


def make_runner(synth_dcps: dict[str, Path], wd_root: Path, peak_g: float, clock_ns: float, log: list[dict[str, Any]] | None = None
                ) -> Callable[[R.ImplPlan, str], dict[str, Any]]:
    """A search runner: (plan, node id) -> outcome. ``synth_dcps`` maps :func:`synth_key` to a post-synthesis checkpoint (``default`` is required)."""
    def runner(plan: R.ImplPlan, nid: str) -> dict[str, Any]:
        k = synth_key(plan)
        if k not in synth_dcps:
            out = {"status": "no synth checkpoint", "synth_key": k, "clock_ns": clock_ns}
        else:
            out = run_one(plan, synth_dcps[k], wd_root / nid, peak_g, clock_ns)
        out["node"] = nid
        if log is not None:
            log.append(out)
        return out
    return runner


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 3:
        raise SystemExit(__doc__)
    d = json.loads(Path(a[0]).read_text())
    plan = R.ImplPlan(directives=tuple(d.get("directives", {}).items()))
    peak = float(a[a.index("--peak-g") + 1]) if "--peak-g" in a else 4.0
    print(json.dumps(run_one(plan, Path(a[1]), Path(a[2]), peak, float(d.get("clock_ns", 0))), indent=1))
