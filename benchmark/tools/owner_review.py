#!/usr/bin/env python3
"""Write the owner's review checklists (the owner track): one row block per task.

    owner_review.py --public benchmark/OWNER_REVIEW.md --private <private>/OWNER_REVIEW_private.md

Public: every development task in full, held-out tasks and the probe by id only (their review is in the private
file). Each task gets four questions (spec clear? model right? tests fair? trap valid?) and a sign-off line. The
owner ticks the boxes and writes initials and date; scoring of the held-out set waits for its sign-off.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmark"


def twin(task: Path) -> str:
    m = yaml.safe_load((task / "hidden" / "mutants.yaml").read_text()) if (task / "hidden" / "mutants.yaml").exists() else {}
    return (m.get("trap") or {}).get("twin", "none")


def block(task: Path, tier: str, split: str, results: Path) -> str:
    spec = yaml.safe_load((task / "hidden" / "spec.yaml").read_text())
    r = results / f"{task.name}__icarus.json"
    tests = mut = trap = "?"
    if r.exists():
        j = json.loads(r.read_text())
        tests = len(j.get("ref", {}).get("tests", {}))
        mut = f"{j.get('mutants_killed', '?')}/{j.get('mutants_total', '?')}"
        trap = "fires" if j.get("trap", {}).get("trap_fires") else ("none" if "trap" not in j else "DOES NOT FIRE")
    tw = twin(task)
    lines = [f"### {task.name} ({tier}, {split}): {spec.get('title', '')}", "",
             f"Files: `{task.name}/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, "
             f"`hidden/NOTES.md`, `ref/rtl/`. Tests {tests}; mutants killed {mut}; book/demo twin: {tw}; trap {trap}.", "",
             "- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml",
             "- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)",
             "- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice",
             f"- [ ] **Trap valid?** {'the trap test fails on the textbook/demo behaviour and only on a real difference' if tw != 'none' else 'n/a (no twin)'}",
             "- Signed: ________ (initials, date)   Notes:", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public", type=Path, default=BENCH / "OWNER_REVIEW.md")
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--private-root", type=Path, required=True)
    a = ap.parse_args()
    split = yaml.safe_load((BENCH / "split.yaml").read_text())
    head = ["# Benchmark v1: the owner's review (owner track)", "",
            "One block per task. Tick each question after reading the files named, then sign. **Scoring of the "
            "held-out set waits until every held-out block is signed**; development tasks may be used for agent work "
            "once signed. Signed so far: none (2026-11-03).", ""]
    pub, priv = list(head), list(head)
    for tier, v in split["tiers"].items():
        pub += [f"## {tier}", ""]
        priv += [f"## {tier} (held out)", ""]
        for i in v["dev"]:
            pub.append(block(BENCH / "tasks" / i, tier, "dev", BENCH / "results" / "reference"))
        for i in v["held_out"]:
            pub += [f"### {i} ({tier}, held out)", "", "Reviewed in the private repository "
                    "(`benchmark_private/OWNER_REVIEW_private.md`).", "", "- Signed: ________", ""]
            priv.append(block(a.private_root / "tasks" / i, tier, "held out", a.private_root / "results" / "reference"))
    c = a.private_root / "contamination"
    if c.exists():
        priv += ["## Contamination probe", ""]
        for d in sorted(x for x in c.iterdir() if x.is_dir()):
            priv.append(block(d, "probe", d.name.split("_")[1], a.private_root / "results" / "contamination"))
        pub += ["## Contamination probe", "", "18 tasks, reviewed in the private repository.", ""]
    a.public.write_text("\n".join(pub) + "\n")
    a.private.write_text("\n".join(priv) + "\n")
    print(f"wrote {a.public} and {a.private}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
