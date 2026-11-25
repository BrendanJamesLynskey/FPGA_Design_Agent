"""Brief 157: run the labelled set (cases.json) against a checkout and write a record.

    python results/157_newcomer_cli/measure.py --env full|bare [--root <checkout>] [--out record.json] [--check]

Every case runs the real ``python -m agent ...`` in ``--root`` with no FDA_ACCESS_KEY, no FDA_PROMPTS_DIR and (the checkout being a
fresh clone) no ``.env``. ``--check`` exits 1 when any case fails its label. The script reads no key and writes only ``--out``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_case(case: dict, expect: dict, root: Path, py: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("FDA_ACCESS_KEY", "FDA_PROMPTS_DIR", "FDA_KNOWLEDGE")}
    t0 = time.time()
    try:
        r = subprocess.run([py, "-m", "agent", *case["argv"]], cwd=root, env=env, capture_output=True, text=True, timeout=240)
        rc, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = -1, "", "timeout"
    problems = []
    if rc != expect["exit"]:
        problems.append(f"exit {rc}, expected {expect['exit']}")
    for s in expect.get("stdout_has", []):
        if s not in out:
            problems.append(f"stdout lacks {s!r}")
    for s in expect.get("stderr_has", []):
        if s not in err:
            problems.append(f"stderr lacks {s!r}")
    for s in expect.get("stderr_not", []):
        if s in err:
            problems.append(f"stderr has {s!r}")
    for rx in expect.get("stdout_regex", []):
        if not re.search(rx, out, re.M):
            problems.append(f"stdout has no line matching {rx!r}")
    first = (err.strip().splitlines() or out.strip().splitlines() or [""])[0][:160]
    return {"id": case["id"], "class": case["class"], "argv": case["argv"], "expected_exit": expect["exit"], "exit": rc, "ok": not problems,
            "problems": problems, "first_line": first, "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["full", "bare"], required=True)
    ap.add_argument("--root", type=Path, default=HERE.parents[1])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    rows = [run_case(c, c[a.env], a.root.resolve(), sys.executable) for c in cases if c[a.env]]
    head = subprocess.run(["git", "-C", str(a.root), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True).stdout.strip()
    classes = {}
    for r in rows:
        k = classes.setdefault(r["class"], {"cases": 0, "passed": 0})
        k["cases"] += 1
        k["passed"] += r["ok"]
    rec = {"env": a.env, "root_head": head, "python": sys.version.split()[0], "cases": len(rows), "passed": sum(r["ok"] for r in rows),
           "by_class": classes, "rows": rows}
    text = json.dumps(rec, indent=1)
    if a.out:
        a.out.write_text(text + "\n")
    print(f"{a.env}: {rec['passed']}/{rec['cases']} cases match their label (root {head})")
    for r in rows:
        if not r["ok"]:
            print(f"  FAIL {r['id']}: {'; '.join(r['problems'])}")
    return 1 if a.check and rec["passed"] != rec["cases"] else 0


if __name__ == "__main__":
    sys.exit(main())
