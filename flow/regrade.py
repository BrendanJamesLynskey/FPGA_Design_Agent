"""Brief 213 item 3: the fresh-stimulus regrade. After a design is accepted at V2, run the RTL against ``model.py`` on long sequences the design's own bench
never applied, and say what happened.

The reference is ``model.py`` through the model API contract (``Model.step`` once per clock); the stimulus is the harness's own (``flow/lockstep.py``,
``fresh`` mode): values drawn from the pool the bench used for each input (so the addresses and opcodes are ones the spec defines) plus random and
neighbour values, bursts and holds, ready-like inputs toggled for back-pressure, resets mid-stream, a seed drawn at the gate and recorded.

Statuses (``result["status"]``):

* ``not_applicable``: the bench did not drive the model through ``step(inputs)`` (it used ``read_reg``/``write_reg`` or stepped with no inputs), so there is no
  stimulus vocabulary to draw from; or nothing was recorded. Never blocks.
* ``not_calibrated``: the bench's own recorded stimulus, replayed through the same lock-step bench, already differs from the model (the model is not cycle
  aligned with the RTL at the ports: a latency the bench allows for, for example). A fresh divergence would be a false alarm. Never blocks.
* ``pass`` / ``fail``: the calibration replay agreed and the fresh run agreed / differed. ``fail`` carries the first-divergence digest.
* ``error``: the lock-step bench did not run. Never blocks.

Whether ``fail`` blocks acceptance at a verification level is ``BLOCKS`` below; the evidence for it is in reports/213_repair_feedback_report.md.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from flow import divergence

SCHEMA = "fda/regrade/v1"
MIN_INPUT_CYCLES = 20
#: where a calibrated fresh-stimulus divergence stops the run. Set from the measured false-alarm rate (see the report); a level not listed reports only.
BLOCKS: dict[str, bool] = {"V1": False, "V2": False, "V3": False}


def recording_stats(path: Path) -> dict[str, int]:
    st = {"segments": 0, "steps": 0, "steps_with_inputs": 0, "register_calls": 0, "truncated": 0}
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return st
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        op = r.get("op")
        if op == "new":
            st["segments"] += 1
        elif op == "step":
            st["steps"] += 1
            st["steps_with_inputs"] += 1 if r.get("in") else 0
        elif op in ("rd", "wr"):
            st["register_calls"] += 1
        elif op == "truncated":
            st["truncated"] = 1
    return st


def applicable(stats: dict[str, int]) -> tuple[bool, str]:
    if not stats["segments"]:
        return False, "no model calls were recorded (the bench never constructed model.Model, or recording was off)"
    if stats["steps_with_inputs"] < MIN_INPUT_CYCLES:
        why = f"the bench passed inputs to Model.step in only {stats['steps_with_inputs']} cycles (need {MIN_INPUT_CYCLES})"
        if stats["register_calls"]:
            why += f"; it drove the model through read_reg/write_reg ({stats['register_calls']} calls), whose bus protocol the harness does not know"
        return False, why
    return True, ""


def run_regrade(design: Path, run: divergence.Run, *, seed: int | None = None, sim: str = "icarus", fresh_cycles: int = 4000, segments: int = 3,
                replay_cycles: int = 20000, timeout: int = 900, py: str | None = None, rtl_files: list[Path] | None = None) -> dict[str, Any]:
    """The regrade of the design as it stands. Returns the record kept in the run state and the run record."""
    design = Path(design)
    rec = divergence.record_path(design)
    stats = recording_stats(rec)
    out: dict[str, Any] = {"schema": SCHEMA, "status": "not_applicable", "seed": None, "recording": stats, "sim": sim}
    ok, why = applicable(stats)
    if not ok:
        out["why"] = why
        return out
    cal = divergence.lockstep(design, run, mode="replay", cycles=replay_cycles, sim=sim, timeout=timeout, py=py)
    if cal.get("ok") is None:
        return {**out, "status": "error", "why": cal.get("error")}
    out["calibration"] = {"cycles": cal.get("cycles"), "segments": len(cal.get("segments") or []), "agreed": bool(cal.get("ok")),
                          "unmapped": cal.get("unmapped"), "notes": cal.get("notes")}
    if not cal.get("ok"):
        out.update(status="not_calibrated", why="the bench's own recorded stimulus, replayed in lock step, already differs from the model; "
                                                "the model is not cycle aligned with the RTL at the ports, so a fresh divergence would prove nothing",
                   digest=divergence.lockstep_digest(cal, rtl_files, label="calibration divergence"))
        return out
    seed = secrets.randbelow(2 ** 31) if seed is None else seed
    out["seed"] = seed
    fr = divergence.lockstep(design, run, mode="fresh", seed=seed, fresh_cycles=fresh_cycles, cycles=fresh_cycles * segments + 10, sim=sim,
                             timeout=timeout, py=py)
    if fr.get("ok") is None:
        return {**out, "status": "error", "why": fr.get("error")}
    out["fresh"] = {"cycles": fr.get("cycles"), "resets": fr.get("resets"), "segments": len(fr.get("segments") or []), "unmapped": fr.get("unmapped")}
    if fr.get("ok"):
        out["status"] = "pass"
    else:
        out["status"] = "fail"
        out["divergence"] = {k: fr["divergence"][k] for k in ("segment", "cycle", "signals")}
        out["digest"] = divergence.lockstep_digest(fr, rtl_files, label="fresh-stimulus regrade: first divergence")
    return out


def blocks(result: dict[str, Any] | None, level: str) -> bool:
    return bool(result) and result.get("status") == "fail" and BLOCKS.get(level, False)
