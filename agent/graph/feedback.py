"""Brief 213: better repair feedback. Three harness arms of the stage-2 repair loop (``--harness-arm H1,R1,R2,R3``; none is on by default):

* ``R1`` first failing check: when the simulate gate fails on an assertion (a mismatch between the RTL and the model), the harness re-runs the bench once
  with a snapshot hook (flow/divergence.py) and the Designer's feedback carries the first failing check, the signals it names with the RTL's values
  over the last cycles and the model's value, the transaction in flight and the driver cone of the first wrong signal, in place of the raw log tail.
* ``R2`` failure ledger: each stage-2 visit records the gate, the finding and the first failing check, and what the repair before it changed
  (the files whose contents differ since the previous gate evaluation); the next repair visit is shown the earlier visits.
* ``R3`` fresh-stimulus regrade: after stage 2 would pass, flow/regrade.py runs the RTL against model.py on sequences the bench never applied.

Pure functions over dicts and files, so CI tests them on recorded evidence; the one process started is the simulator, through the session's runner.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from flow import divergence

LEDGER_SHOW = 5                  # earlier visits shown to a repair visit
ENTRY_CHARS = 330
FINGERPRINT_DIRS = ("rtl", "tests", "verif")
FINGERPRINT_FILES = ("model.py", "spec.yaml", "architecture.yaml", "ARCHITECTURE.md", "design.xdc", "build.yaml")


def session_run(session: Any, timeout_cap: int = 900) -> divergence.Run:
    """Adapt the session's runner to ``divergence.Run`` (the same runner and container as the simulate tool)."""
    def run(argv: list[str], env: dict[str, str], timeout: int) -> tuple[int, str]:
        r = session.runner.run("simulate", argv, session.root, env, timeout=min(timeout, timeout_cap))
        return r.returncode, (r.stdout + ("\n" + r.stderr if r.stderr.strip() else "")).strip()
    return run


def sim_name(used: str | None) -> str:
    """The simulator a gate result names (``verilator+icarus``, ``icarus (cross-check)``, ...) -> the one to re-run on (the one that failed)."""
    u = str(used or "icarus")
    return "icarus" if "icarus" in u else "verilator"


def first_failing_check(session: Any, design: Path, sim_result: dict[str, Any], rtl_files: list[Path]) -> dict[str, Any]:
    """The R1 diagnostic re-run for a failed simulate gate. Returns ``{"text": digest or "", "snapshot": bool, "seconds": n}`` (text empty when
    nothing was captured: the failure did not reproduce, or the bench died before a cocotb test failed)."""
    import time
    t0 = time.time()
    snap = divergence.diagnose(design, session_run(session), sim=sim_name(sim_result.get("sim")))
    text = divergence.snapshot_digest(snap, rtl_files) if snap else ""
    return {"text": text, "snapshot": bool(snap), "seconds": round(time.time() - t0, 1),
            "test": (snap or {}).get("test"), "site": (snap or {}).get("site"), "message": ((snap or {}).get("message") or "")[:200]}


# --- the failure ledger -------------------------------------------------------------------------------------------------------------------------

def fingerprint(design: Path) -> dict[str, str]:
    """SHA-1 of every file the repair roles write (rtl, tests, verif, model.py, the spec and architecture files), keyed by relative path."""
    out: dict[str, str] = {}
    design = Path(design)
    paths = [design / f for f in FINGERPRINT_FILES]
    for d in FINGERPRINT_DIRS:
        paths += sorted(p for p in (design / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for p in paths:
        if p.is_file():
            try:
                out[str(p.relative_to(design))] = hashlib.sha1(p.read_bytes()).hexdigest()[:12]
            except OSError:
                pass
    return out


def changed_files(old: dict[str, str] | None, new: dict[str, str]) -> list[str]:
    if old is None:
        return []
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))


def finding_of(ev: dict[str, Any], sig: str, fails: list[str]) -> str:
    """One line on why the visit failed, from the evidence only: the failing assertion, else the first gate lines."""
    sim = ev.get("simulate") or {}
    ff = sim.get("first_failure") or {}
    if sim.get("ok") is False and ff:
        msgs = [m for m in ff.get("message", []) if "cocotb run failed" not in m] or ff.get("message", [])
        return f"simulate: {ff.get('test')}: " + " | ".join(msgs[:2])
    return "; ".join(str(f) for f in fails[:2]) or sig


def ledger_entry(visit: int, sig: str, owners: dict[str, Any], ev: dict[str, Any], fails: list[str], changed: list[str],
                 check: dict[str, Any] | None = None) -> dict[str, Any]:
    from agent.graph.repair import _GATE_OF_TAG
    gates: list[str] = []
    for part in sig.split("|"):
        tag = part.partition(":")[2]
        key = tag.split(":")[0].split(" ")[0]
        g = "verification " + (tag.partition(":")[2] or "V2") if key.startswith("verif") else (_GATE_OF_TAG.get(key) or key)
        if g and g not in gates:
            gates.append(g)
    e: dict[str, Any] = {"visit": visit, "gates": gates, "roles": sorted(owners), "finding": finding_of(ev, sig, fails)[:240], "sig": sig,
                         "changed_before": changed[:12]}
    if check and (check.get("site") or check.get("message")):
        s = check.get("site") or {}
        e["first_failing_check"] = (f"{s.get('file')}:{s.get('line')} " if s else "") + str(check.get("message") or "")[:160]
    return e


def ledger_text(ledger: list[dict[str, Any]] | None, limit: int = LEDGER_SHOW) -> str:
    """The earlier visits of this stage for a repair visit: all entries but the newest (that failure is already the visit's own reason). "" before a second visit."""
    prev = (ledger or [])[:-1][-limit:]
    if not prev:
        return ""
    cur = (ledger or [])[-1]
    lines = ["[earlier visits of this stage, what was tried and why each failed; do not repeat an attempt that failed the same way]"]
    for e in prev:
        same = " (the same failure as now)" if e.get("sig") == cur.get("sig") else ""
        ch = ("repair before it changed " + ", ".join(e["changed_before"][:5])) if e.get("changed_before") else (
            "first attempt" if e.get("visit", 1) <= 1 else "repair before it changed no file")
        t = f"- visit {e.get('visit')} ({ch}): failed {', '.join(e.get('gates') or ['a gate'])} [{'/'.join(e.get('roles') or [])}]: {e.get('finding')}"
        if e.get("first_failing_check"):
            t += f"; first failing check {e['first_failing_check']}"
        lines.append((t + same)[:ENTRY_CHARS])
    run = 1 + sum(1 for e in reversed(prev) if e.get("sig") == cur.get("sig")) if prev and prev[-1].get("sig") == cur.get("sig") else 1
    if run >= 3:          # the classification of 215's disagreements: a failure repeated 3+ visits is often a bench or standard in conflict with the request
        lines.append(f"[this failure has now repeated on {run} consecutive visits] Before editing again, check whether the failing check itself contradicts the request text "
                     "or a design-standard (for example a reset style the request does not ask for, or the reverse): say which side the evidence supports.")
    return "\n".join(lines)


def with_ledger(owners: dict[str, list[str]], ledger: list[dict[str, Any]] | None) -> dict[str, list[str]]:
    """Owners' failure texts with the ledger text added to every role that is repairing (R2)."""
    txt = ledger_text(ledger)
    return {r: ([*v, txt] if txt else list(v)) for r, v in owners.items()}
