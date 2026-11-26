#!/usr/bin/env python3
"""Brief 227: copy the stage-0 gate records of the pilot runs (tags ``b227_s0_<design>`` with the oracle, ``b227_s0c_<design>`` on the arm C document with nobody to answer) into
``results/227_requirements_readiness/gate_pilots/`` and write ``table.md``: rounds, questions asked and answered, reader agreement per round, repairs, calls and how it ended."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

RUNS, OUT = Path("runs"), Path("results/227_requirements_readiness/gate_pilots")


def main() -> int:
    best: dict[str, Path] = {}
    for r in sorted(RUNS.iterdir()):
        for c in r.iterdir() if r.is_dir() else []:
            if re.match(r"^b227_s0c?_p\d_", c.name) and (c / "build" / "requirements" / "readiness.json").is_file():
                best[c.name] = c
    OUT.mkdir(parents=True, exist_ok=True)
    rows = ["| Run | Input and answerer | Rounds | Questions asked | Answered | Reader agreement by round | Repairs (rows revised) | Model calls | Ended |", "|---|---|---|---|---|---|---|---|---|"]
    for tag, c in sorted(best.items()):
        b = c / "build" / "requirements"
        rd = json.loads((b / "readiness.json").read_text())
        dst = OUT / tag
        dst.mkdir(parents=True, exist_ok=True)
        for f in ("readiness.json", "frozen.json"):
            if (b / f).is_file():
                shutil.copy(b / f, dst / f)
        for f in ("REQUIREMENTS_NEEDED.md", "REQUIREMENTS_READINESS.md"):
            if (c / f).is_file():
                shutil.copy(c / f, dst / f)
        rs = rd["rounds"]
        qs = [q for r in rs for q in r.get("questions") or []]
        agree = ", ".join(f"{round(((r.get('agreement') or {}).get('rate') or 0) * 100)}%" if r.get("agreement") else "-" for r in rs)
        rep = sum(len((r.get("repairs") or {}).get("revised") or []) for r in rs)
        inp = "arm C document, nobody to answer" if tag.startswith("b227_s0c_") else "request, oracle from the hidden spec"
        rows.append(f"| {tag.replace('b227_', '')} | {inp} | {len(rs)} | {len(qs)} | {sum(bool(q.get('answer')) for q in qs)} | {agree} | {rep} | {rd.get('model_calls')} | "
                    f"{'frozen' if rd.get('frozen') else 'stopped: ' + str(rd.get('stop'))} |")
    (OUT / "table.md").write_text("\n".join(rows) + "\n")
    print(f"{len(best)} gate runs recorded in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
