#!/usr/bin/env python3
"""Brief 221's example: re-plan the 209 pilot's p1_clkmeter bring-up with a lab file that holds a (mock) frequency counter, and show the requirement row
for the C3 frequency gaining an independent instrument check beside the on-chip count. No instrument, no board, no model.

    python3 results/221_lab_instruments/make_example.py

Writes next to this file: before_row.md, after_row.md, plan.json, lab_steps.yaml, BRINGUP_lab_block.md, dry_run_results.json, plan_owner_bench.json."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
os.environ["FDA_LAB_FILE"] = "none"                     # the owner's own profile is never read here

from flow import requirements_report as rr  # noqa: E402
from flow import traceability as tr  # noqa: E402
from hil import lab as L  # noqa: E402
from hil import lab_bringup as B  # noqa: E402

P1 = ROOT / "pilots" / "209" / "p1_clkmeter"
RUN = P1 / "run3" / "design"
REQ = "REQ-13"


def row_of(md: str, req: str) -> str:
    return next(l for l in md.splitlines() if l.startswith(f"| {req} "))


def report(design: Path, spec: dict) -> str:
    t = tr.build(RUN, None, defer=("analysis", "hardware", "coverage"))
    return rr.to_markdown(rr.build_report(design, t, spec, ""))


def main() -> int:
    spec = yaml.safe_load((RUN / "spec.yaml").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "p1_clkmeter"
        shutil.copytree(RUN, d, ignore=shutil.ignore_patterns("build", "__pycache__"))
        shutil.copy(P1 / "run1" / "design" / "BRINGUP.md", d / "BRINGUP.md")        # run 3 wrote none; run 1's text is the base the block is added to
        (d / "lab.yaml").write_text((HERE / "design_lab.yaml").read_text())
        (HERE / "before_row.md").write_text(row_of(report(d, spec), REQ) + "\n")      # no plan yet: the report is as before brief 221
        lab = L.load(d, HERE / "lab_profile_mock.yaml", strict=True)
        plan = B.apply_to_design(d, spec, lab)
        res = B.run_for_design(d, dry_run=True, lab=lab)
        after = report(d, spec)
        (HERE / "after_row.md").write_text(row_of(after, REQ) + "\n")
        (HERE / "plan.json").write_text(json.dumps(plan, indent=1, default=str) + "\n")
        shutil.copy(d / "lab_steps.yaml", HERE / "lab_steps.yaml")
        text = (d / "BRINGUP.md").read_text()
        (HERE / "BRINGUP_lab_block.md").write_text(text[text.index(B.BEGIN):])
        (HERE / "dry_run_results.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    owner = L.plan(L.load(None, ROOT / "hil" / "lab.example.yaml", strict=True), L.needs_from_spec(spec))        # the owner's seeded bench: nothing onboarded can measure it
    (HERE / "plan_owner_bench.json").write_text(json.dumps(owner, indent=1, default=str) + "\n")
    print(row_of(after, REQ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
