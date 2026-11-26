"""Brief 218 inside the agent: the two steps of the stage-2 gate that sit behind ``--coverage-loop`` and ``--req-sva`` (both off by default).

* :func:`coverage_gate`: when V2 has passed and V3 fails only on checks the tests can change, run the coverage loop of
  ``flow/coverage_loop.py`` (rounds of: the tests role is shown only the holes, the V3 evidence is rerun) and return the new evidence.
* :func:`sva_step`: write an SVA property for each checkable requirement, read it back with a second model, compare in code, and prove it
  (``flow/sva_req.py``); the evidence file feeds the requirements report.

The roles and prompts are the ones stage 2 already uses (the tests role in repair mode, with the holes as its failures), so no private prompt
changes and no request golden changes: with both flags off nothing here runs. Imports of ``agent.graph.run`` are inside the functions
(that module imports this one).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flow import coverage_loop as CL


def _fmt(rt: Any, n: int = 2) -> dict[str, Any]:
    from agent.graph import run as R
    st = R.MACHINE[n]
    return {"board": rt.cfg.board, "name": rt.cfg.name, "stage": n, "stage_name": st.name, "allowed": ", ".join(st.tools), "fails": "none",
            "note": "none", "design_rel": str(rt.design.relative_to(R.ROOT)), "no_shell": rt.cfg.no_shell, "hdl": rt.cfg.hdl}


def _verif(rt: Any) -> dict[str, Any]:
    from agent.graph.run import dispatch
    return dispatch(rt.session, "gates", {"kind": "verif"}).get("gates") or {}


def _mutation(rt: Any) -> dict[str, Any] | None:
    try:
        return json.loads((rt.design / "build" / "verif" / "mutation.json").read_text())
    except (OSError, ValueError):
        return None


def observe(rt: Any, ev: dict[str, Any]) -> None:
    """Passive, whatever the flags: one line per stage-2 gate evaluation that has V3 evidence, in ``build/verif/coverage_visits.jsonl`` (the holes
    open then, and the run's cumulative tokens). It is how an arm without the loop is measured the same way as one with it: holes closed per
    million tokens between two evaluations. Never raises, never changes a result."""
    try:
        v = ev.get("verif") or {}
        if not ((v.get("stages") or {}).get("V3")):
            return
        hs = CL.holes_of(v, _mutation(rt))
        p = rt.design / "build" / "verif" / "coverage_visits.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps({"visit": getattr(rt, "visit", None), "tokens": int(rt.meter.run.get("tokens", 0)), "usd": round(float(rt.meter.run.get("usd", 0.0)), 4),
                                "reached": v.get("reached"), "holes": [h["key"] for h in hs], "counts": CL.counts(hs),
                                "mutation_score_pct": (_mutation(rt) or {}).get("score_pct"), "loop": bool(ev.get("coverage_loop"))}, sort_keys=True) + "\n")
    except Exception:                                      # a record, not a gate
        return


def coverage_gate(rt: Any, ev: dict[str, Any], d: Any, detail: list[str]) -> dict[str, Any] | None:
    """Run the loop for this gate evaluation. Returns None when it does not apply (flag off, not V3, V2 not reached, or V3 fails on something
    the tests cannot change). Otherwise updates ``ev`` (``verif``, ``v3_evidence``, ``simulate``) and returns the loop's summary, which is also
    in ``ev['coverage_loop']`` and the run's routing events."""
    from agent.graph import run as R
    if getattr(rt.cfg, "coverage_loop", "off") != "on" or rt.cfg.verif_level != "V3":
        return None
    if not (ev.get("lint", {}).get("ok") and ev.get("simulate", {}).get("ok")) or not CL.stimulus_only(ev.get("verif")):
        return None
    fmt = _fmt(rt)
    jtag = R.transport_of(rt) == "jtag_bus"
    conv_tests = R.tests_conventions_text(fmt) + (R.JTAG_NOTE.replace("{design_rel}", fmt["design_rel"]) if jtag else "")
    state: dict[str, Any] = {"wrote": False, "halt": None}

    def read_holes() -> list[dict[str, str]]:
        v = _verif(rt)
        ev["verif"] = v
        if (v.get("reached") or "") >= "V3":              # V3 passes: holes that remain are not failures, so the loop is done
            return []
        return CL.holes_of(v, _mutation(rt))

    def ask_tests(brief: str, n: int) -> dict[str, Any]:
        before = len(rt.budget_notes)
        try:
            written = R.run_role(rt, "tests", R.PROMPTS["tests"].format(**fmt) + R.repair_note("tests", [brief]) + R.tests_checklist(rt, 2, True) + conv_tests,
                                 R.role_allowed("tests", 2), True)
        except R.BudgetExceeded as e:
            if str(e).startswith("run "):                  # the real run limit stops the run, as everywhere else
                raise
            return {"ok": False, "error": f"budget: {e}"}
        if len(rt.budget_notes) > before:
            return {"ok": False, "error": "budget: " + rt.budget_notes[-1]}
        state["wrote"] = state["wrote"] or bool(written)
        return {"ok": True, "files": sorted(written)}

    def rerun() -> None:
        ev["v3_evidence"] = R.v3_evidence(rt, True)
        sim = ev["v3_evidence"]["coverage"]
        if "text" in sim and not sim["ok"]:                # the new stimulus fails the design or does not build
            ev["simulate"] = {"ok": False, "first_failure": sim.get("first_failure"), "text": sim["text"]}
            detail.append("[simulate, verilator coverage run, after a coverage round] " + sim["text"][-800:])
            state["halt"] = "the new stimulus fails the coverage run: the ordinary repair visit owns that"

    def halt() -> str | None:
        if state["halt"]:
            return state["halt"]
        v = _verif(rt)
        if (v.get("reached") or "") < "V2":
            ev["verif"] = v
            return "the new stimulus broke V2: the ordinary repair visit owns that"
        return None

    summary = CL.run_loop(rt.design, read_holes=read_holes, ask_tests=ask_tests, rerun=rerun, halt=halt,
                          spent=lambda: float(rt.meter.run.get("tokens", 0)))
    if state["wrote"] and not state["halt"]:               # the tests changed: the Icarus cross-check of stage 2 must pass them too
        ev["simulate"] = R.simulate_gate(rt.session, d)
    ev["verif"] = _verif(rt)
    ev["coverage_loop"] = summary
    R.log_routing_event(rt, "coverage_loop", **{k: v for k, v in summary.items() if k != "schema"})
    detail.append("[coverage loop] " + CL.summary_line(summary))
    return summary


def sva_step(rt: Any) -> dict[str, Any] | None:
    """Brief 218 part 2 for this design as it stands (after V2). Returns the evidence summary, or None when off. Never raises: a failed step is
    recorded as a reason in the result and the requirement keeps the evidence it had."""
    if getattr(rt.cfg, "req_sva", "off") != "on":
        return None
    from flow import sva_req
    log = rt.run_dir / "claude_code_calls.jsonl"
    try:
        gen = rt.resolver.text("assertgen", label="assertgen", claude_log=log)
        back = rt.resolver.text("assertback", label="assertback", claude_log=log)
    except Exception as e:                                  # no model configured for the step, or the arm is blocked
        return {"skipped": f"no model for the step: {e}"}
    formal_ok = sva_req.formal_env() is not None
    prefix = ["nice", "-n", "15"]
    try:
        rec = sva_req.process(rt.design, gen, back, formal=formal_ok, prefix=prefix)
        out = {"summary": sva_req.summary_line(rec), "counts": rec["counts"], "formal": formal_ok}
        from agent.graph.run import log_routing_event
        log_routing_event(rt, "req_sva", **{"counts": rec["counts"], "skipped": len(rec["skipped"]), "formal": formal_ok})
        return out
    except Exception as e:                                  # a model timeout, a bad spec.yaml: the step is a record, never a stage failure
        return {"skipped": f"the step failed: {type(e).__name__}: {str(e)[:200]}"}
