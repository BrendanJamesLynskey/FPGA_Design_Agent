"""Lab-instrument steps of a bring-up (brief 221): plan them, write them into the design, dry-run them, run them.

Stage 9 of an agent run calls :func:`apply_to_design` after the model has written ``BRINGUP.md``: for each requirement whose proof includes hardware
and whose text an instrument can check (``hil.lab.needs_from_spec``), the best available method is chosen (``hil.lab.plan_need``). The result is

* ``build/lab/plan.json``: the choice per requirement and what was left out and why (the requirements report reads it);
* ``lab_steps.yaml`` in the design: the steps a runner executes (the host checks);
* a ``Lab instruments`` section of ``BRINGUP.md`` between two marker lines, regenerated on every visit so a rewrite of the file by the model never
  loses it.

:func:`run_steps` executes the steps. A scripted step opens its adapter (``hil/lab_drivers.py``), a manual step asks the owner for a reading with its
unit, and a step that drives a signal into the board is marked, goes through ``hil.lab.check_drive`` and needs the owner's typed confirmation at run
time. A **dry run** (the agent's own) uses mock instruments, asks nobody and writes results marked ``dry_run``: they show the plumbing works and are
never evidence. The owner runs every instrument script; the agent writes and dry-runs them.

    python -m hil.lab_bringup plan <design>        # the plan as text (no instrument touched)
    python -m hil.lab_bringup dry-run <design>     # every step against mock instruments
    python -m hil.lab_bringup run <design>         # the owner's run: real instruments, prompts, confirmations
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from hil import lab as L
from hil import lab_drivers as D

STEPS_FILE = "lab_steps.yaml"
PLAN_REL = ("build", "lab", "plan.json")
RESULTS_REL = ("build", "lab", "results.json")
BEGIN, END = "<!-- lab:begin (written by the harness; regenerated each run) -->", "<!-- lab:end -->"
DRIVE_ACTION = "drive_instrument_output"      # brief 222's permission action for a step that drives an output into the board


# ---- plan -> steps --------------------------------------------------------------------------------------------------------------------
def steps_from_plan(plan: dict[str, Any], lab: L.Lab) -> list[dict[str, Any]]:
    """One wiring confirmation per connection used, then one measure step per requirement whose chosen method is an instrument."""
    steps: list[dict[str, Any]] = []
    wired: set[tuple[str, str]] = set()
    for r in plan["requirements"]:
        m = r["chosen"]
        if m["method"] == "on_chip":
            continue
        key = (m["instrument"], m["channel"])
        if key not in wired:
            wired.add(key)
            steps.append({"id": f"wire_{m['instrument']}_{m['channel']}".lower(), "kind": "confirm", "method": "manual", "instrument": m["instrument"],
                          "channel": m["channel"], "requirement": r["requirement"],
                          "prompt": f"Confirm {m['instrument']} channel {m['channel']} is connected to {m['probes']} (board powered off while wiring; "
                                    f"logic levels match the board's VCCO). Type yes to go on."})
        step = {"id": f"{r['requirement']}_{m['instrument']}".lower().replace("-", "_"), "kind": "measure", "method": m["method"],
                "instrument": m["instrument"], "channel": m["channel"], "probes": m["probes"], "requirement": r["requirement"],
                "quantity": r["quantity"], "target": r["target"], "expected": r["expected"], "tolerance_ppm": r["tolerance_ppm"],
                "accuracy_ppm": m.get("accuracy_ppm"), "mock": m.get("mock", False)}
        if m.get("accuracy_ppm") is None:
            step["caveat"] = "the instrument's accuracy is not recorded in the lab file: a pass here is a coarse independent check"
        if m["method"] == "manual":
            unit = {"frequency": "Hz, kHz, MHz or GHz", "voltage": "mV or V"}.get(r["quantity"], "its unit")
            step["prompt"] = (f"Read the {r['quantity']} of {r['target']} on {m['instrument']} {m['channel']} (probe on {m['probes']}) and type it with its unit "
                              f"({unit}). Expected about {_fmt(r['expected'], r['quantity'])}.")
        steps.append(step)
    return steps


def _fmt(v: float | None, quantity: str) -> str:
    if v is None:
        return "the value in the requirement"
    if quantity == "frequency":
        return f"{v / 1e6:g} MHz" if v >= 1e6 else (f"{v / 1e3:g} kHz" if v >= 1e3 else f"{v:g} Hz")
    return f"{v:g} V"


def render_block(plan: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    """The BRINGUP.md section: what was chosen per requirement, the steps in order, what was left out."""
    out = [BEGIN, "", "## Lab instruments", "",
           "The lab file (`hil/lab.example.yaml` is the template) lists the instruments; this section is generated from it. You run every instrument step "
           "yourself, one at a time: `python -m hil.lab_bringup run <design>`. The agent has only dry-run it against mock instruments. "
           "A step marked DRIVES puts a signal into the board and asks you to type `yes` first.", ""]
    if not plan["requirements"]:
        out += ["No requirement of this design states a frequency or a level that an instrument could check, so there are no instrument steps.", ""]
    else:
        out += ["| Requirement | Quantity | Method | Instrument and probe | Not used, and why |", "|---|---|---|---|---|"]
        for r in plan["requirements"]:
            m = r["chosen"]
            who = f"{m['instrument']} {m['channel']} on {m['probes']}" if m["instrument"] else "the design's own measurement (on-chip)"
            skip = "; ".join(f"{x['instrument']}: {x['reason']}" for x in r["left_out"]) or "none"
            out.append(f"| {r['requirement']} | {r['quantity']} of {r['target']} | {m['method']} | {who} | {skip} |")
        out.append("")
    n = 0
    for s in steps:
        n += 1
        if s["kind"] == "confirm":
            out.append(f"{n}. **Wiring.** {s['prompt']}")
        elif s["kind"] == "drive":
            out.append(f"{n}. **DRIVES** ({s['requirement']}): {s['instrument']} output {s['output']} at {s.get('volts')} V into the board. You type `yes` before it is enabled; "
                       f"it is switched off at the end of the run. Never above the lab file's limit.")
        elif s["method"] == "manual":
            out.append(f"{n}. **Reading** ({s['requirement']}): {s['prompt']} Pass: within {s['tolerance_ppm']:g} ppm of the expected value." if s.get("tolerance_ppm")
                       else f"{n}. **Reading** ({s['requirement']}): {s['prompt']}")
        else:
            out.append(f"{n}. **Measure** ({s['requirement']}): {s['instrument']} {s['channel']} reads the {s['quantity']} of {s['target']}"
                       + (f"; pass within {s['tolerance_ppm']:g} ppm of {_fmt(s['expected'], s['quantity'])}." if s.get("tolerance_ppm") else ".")
                       + (f" Note: {s['caveat']}." if s.get("caveat") else ""))
    if steps:
        out += ["", "A wrong probe pin shows up as a reading nowhere near the expected value, or as 'not enough edges': check the pin before the cable. "
                "A manual reading typed without its unit, or in the wrong one (kHz for MHz), is refused or flagged.", ""]
    out.append(END)
    return "\n".join(out) + "\n"


def splice_block(text: str, block: str) -> str:
    """BRINGUP.md with the lab block replaced (or appended): idempotent, so a rewrite of the file by the model is repaired on the next visit."""
    rx = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
    if rx.search(text):
        return rx.sub(lambda _m: block, text)
    return text.rstrip("\n") + "\n\n" + block


def apply_to_design(design: Path, spec: dict[str, Any], lab: L.Lab | None = None) -> dict[str, Any]:
    """Stage 9: plan, write ``build/lab/plan.json``, ``lab_steps.yaml`` and the BRINGUP.md block. Returns the plan. With no lab at all (no profile, no
    design file) nothing is written: a design without a lab behaves exactly as before."""
    design = Path(design)
    lab = lab if lab is not None else L.load(design)
    if not lab.present and not lab.problems:
        return {"requirements": [], "summary": {"needs": 0, "independent_check": 0, "on_chip_only": 0}, "lab": lab.provenance(), "skipped": "no lab file"}
    needs = L.needs_from_spec(spec)
    plan = L.plan(lab, needs)
    steps = steps_from_plan(plan, lab)
    p = design.joinpath(*PLAN_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan, indent=1, default=str) + "\n")
    (design / STEPS_FILE).write_text(yaml.safe_dump({"schema": "fpga-force/lab-steps/v1", "steps": steps}, sort_keys=False))
    bring = design / "BRINGUP.md"
    if bring.is_file():
        bring.write_text(splice_block(bring.read_text(), render_block(plan, steps)))
    return plan


# ---- running --------------------------------------------------------------------------------------------------------------------------
def _err_ppm(value: float, expected: float) -> float:
    return (value - expected) / expected * 1e6 if expected else float("inf")


def judge(step: dict[str, Any], value: float) -> tuple[bool, float | None, list[str]]:
    """(pass, error in ppm, warnings) of a reading against a step's expected value."""
    exp, warn = step.get("expected"), []
    if exp is None:
        return True, None, ["the requirement gives no expected value: the reading is recorded, not judged"]
    ppm = _err_ppm(value, exp)
    if step["quantity"] == "frequency":
        ok = abs(ppm) <= float(step.get("tolerance_ppm") or 1000.0)
        for k in (1e3, 1e6, 1e-3, 1e-6):                      # a reading off by exactly a power of a thousand is a unit slip, not a fault
            if exp and abs(value / exp / k - 1) < 0.05:
                warn.append(f"the reading is about {k:g}x the expected value: was the unit typed wrongly?")
                break
        return ok, ppm, warn
    return abs(value - exp) <= float(step.get("tolerance_v", 0.1)), ppm, warn


def run_steps(steps: list[dict[str, Any]], lab: L.Lab, *, dry_run: bool = True, truth: dict[Any, Any] | None = None,
              ask: Callable[[str], str] | None = None, confirm: Callable[[str], bool] | None = None,
              open_fn: Callable[..., D.LabInstrument] = D.open_instrument, board_vcco_v: float | None = None) -> dict[str, Any]:
    """Execute the steps in order; the first failed or refused step does not stop the later ones (every requirement gets its row), but a refused or
    unconfirmed ``confirm`` step skips the measure steps on that channel. Outputs are stopped at the end whatever happened.

    ``dry_run``: mock instruments for every step (the truth defaults to each step's expected value, so the dry run shows the plumbing; pass
    ``truth`` to inject a fault), nobody is asked, nothing is confirmed: rows are marked ``dry_run`` and are never evidence."""
    rows: list[dict[str, Any]] = []
    opened: dict[str, D.LabInstrument] = {}
    skipped: set[tuple[str, str]] = set()
    mode_all = "dry_run" if dry_run else None
    try:
        for s in steps:
            iid, ch = s["instrument"], s.get("channel")
            row: dict[str, Any] = {"step": s["id"], "requirement": s.get("requirement"), "instrument": iid, "channel": ch, "kind": s["kind"],
                                   "method": mode_all or s["method"], "planned_method": s["method"], "action": DRIVE_ACTION if s["kind"] == "drive" else None,
                                   "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            rows.append(row)
            try:
                inst = lab.get(iid)
                if s["kind"] == "confirm":
                    if dry_run:
                        row.update(result="dry_run", detail="would ask: " + s["prompt"])
                    else:
                        ok = bool(confirm and confirm(s["prompt"]))
                        row.update(result="confirmed" if ok else "not_confirmed")
                        if not ok:
                            skipped.add((iid, ch))
                    continue
                if (iid, ch) in skipped:
                    row.update(result="skipped", detail="the wiring was not confirmed")
                    continue
                if s["kind"] == "drive":
                    plan = {"drive": {"output": s["output"], "volts": s.get("volts"), "hz": s.get("hz"), "amps": s.get("amps"), "dbm": s.get("dbm"),
                                      "attenuator_db": s.get("attenuator_db"), "board_vcco_v": s.get("board_vcco_v", board_vcco_v), "shape": s.get("shape", "SINE")}}
                    L.check_drive(lab, iid, s["output"], volts=s.get("volts"), amps=s.get("amps"), dbm=s.get("dbm"), hz=s.get("hz"),
                                  attenuator_db=s.get("attenuator_db"), board_vcco_v=s.get("board_vcco_v", board_vcco_v))   # refused before the owner is even asked
                    if not dry_run and not (confirm and confirm(f"DRIVES: enable {iid} {s['output']} at {s.get('volts')} V into the board? Type yes to enable it.")):
                        row.update(result="not_confirmed", detail="the owner did not confirm driving the output")
                        continue
                else:
                    plan = {"measure": s["quantity"], "channel": ch, "prompt": s.get("prompt")}
                if iid not in opened:
                    tr = dict(truth or {})
                    if dry_run and s.get("expected") is not None:
                        tr.setdefault((s["quantity"], ch), s["expected"])
                    inst_obj = open_fn({**inst, "id": iid}, lab, mock=dry_run, truth=tr, ask=ask)
                    opened[iid] = inst_obj
                else:
                    inst_obj = opened[iid]
                    if isinstance(inst_obj, D.MockInstrument) and s.get("expected") is not None:
                        inst_obj.truth.setdefault((s["quantity"], ch), s["expected"])
                inst_obj.configure(plan)
                inst_obj.arm()
                cap = inst_obj.capture()
                if s["kind"] == "drive":
                    row.update(result="driven", detail=f"{iid} {s['output']} enabled" + (" (mock)" if inst_obj.mock else ""))
                    continue
                ok, ppm, warn = judge(s, cap["value"])
                row.update(value=cap["value"], unit=cap["unit"], expected=s.get("expected"), error_ppm=ppm, tolerance_ppm=s.get("tolerance_ppm"),
                           result="pass" if ok else "fail", warnings=warn, uncertainty=cap.get("uncertainty"), mock=bool(cap.get("mock")),
                           typed=getattr(inst_obj, "typed", None), caveat=s.get("caveat"))
                if dry_run:
                    row["result_if_real"], row["result"] = row["result"], "dry_run"
            except (L.LabError, D.ReadingError, RuntimeError, KeyError) as e:      # a refusal or a bad reading is that step's result, never a crash
                row.update(result="refused" if isinstance(e, L.SafetyRefused) else "error", detail=f"{type(e).__name__}: {e}")
    finally:
        for o in opened.values():
            try:
                o.close()                                                           # every output off, whatever happened
            except Exception:                                                        # noqa: BLE001
                pass
    bad = [r for r in rows if r["result"] in ("fail", "refused", "error", "not_confirmed")]
    return {"schema": "fpga-force/lab-results/v1", "mode": "dry_run" if dry_run else "run", "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "evidence": not dry_run and not any(r.get("mock") for r in rows), "pass": not bad, "rows": rows}


def load_steps(design: Path) -> list[dict[str, Any]]:
    f = Path(design) / STEPS_FILE
    if not f.is_file():
        return []
    return list((yaml.safe_load(f.read_text()) or {}).get("steps") or [])


def run_for_design(design: Path, *, dry_run: bool, lab: L.Lab | None = None, **kw: Any) -> dict[str, Any] | None:
    """Run ``lab_steps.yaml`` of a design and write ``build/lab/results.json``. None when the design has no lab steps."""
    steps = load_steps(design)
    if not steps:
        return None
    res = run_steps(steps, lab if lab is not None else L.load(design), dry_run=dry_run, **kw)
    p = Path(design).joinpath(*RESULTS_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1, default=str) + "\n")
    return res


def _tty_ask(prompt: str) -> str:
    return input(prompt + "\n> ")


def _tty_confirm(prompt: str) -> bool:
    return input(prompt + "\n(type yes) > ").strip().lower() == "yes"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("plan", "dry-run", "run"))
    ap.add_argument("design", type=Path)
    a = ap.parse_args(argv)
    lab = L.load(a.design)
    if a.cmd == "plan":
        spec = yaml.safe_load((a.design / "spec.yaml").read_text()) if (a.design / "spec.yaml").is_file() else {}
        plan = L.plan(lab, L.needs_from_spec(spec))
        for r in plan["requirements"]:
            m = r["chosen"]
            print(f"{r['requirement']:8} {r['quantity']:10} {m['method']:9} {m.get('instrument') or 'on-chip':14} left out: "
                  + ("; ".join(f"{x['instrument']} ({x['reason']})" for x in r["left_out"]) or "none"))
        return 0
    if lab.problems:
        print("lab file problems:", *lab.problems, sep="\n  ")
        return 2
    res = run_for_design(a.design, dry_run=a.cmd == "dry-run", lab=lab, ask=_tty_ask, confirm=_tty_confirm)
    if res is None:
        print(f"no {STEPS_FILE} in {a.design}: nothing to run")
        return 0
    for r in res["rows"]:
        print(f"{r['step']:28} {r['result']:14} {r.get('value', '')} {r.get('unit') or ''} {r.get('detail', '')}")
    print("PASS" if res["pass"] else "FAIL", f"({res['mode']})")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
