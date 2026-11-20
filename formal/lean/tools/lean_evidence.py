#!/usr/bin/env python3
"""Compute the evidence record for the Lean theorems of this project from a real `lake build` (brief 124).

Writes a JSON list, one entry per theorem: its requirement tags (the `-- req:` comment line above it), the statement's SHA-256
(text up to `:= by`, whitespace-normalised), the axioms it depends on (from `#print axioms`), and a status computed, never typed:
  proved             the build succeeded and the kernel alone checked it: axioms only propext, Classical.choice, Quot.sound
  proved_bv_decide   as above, plus `<name>._native.bv_decide.ax_*` axioms: part of the argument is a SAT certificate that
                     `bv_decide` checks with compiled code (the Lean compiler is then in the trusted base); a lower tier
  failed             the build failed
  unsound            it depends on `sorryAx` or any other axiom
This is a proposal for a `formal_lean` proof method in the traceability matrix (flow/traceability.py is not touched here).

  python3 formal/lean/tools/lean_evidence.py [--out results/124_lean/lean_evidence.json]
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

LEAN = Path(__file__).resolve().parent.parent
ALLOWED = {"propext", "Classical.choice", "Quot.sound"}
NATIVE = re.compile(r"\._native\.bv_decide\.ax_\d+_\d+$")


def theorems(text: str) -> list[dict]:
    out = []
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"theorem (\S+)", ln)
        if not m:
            continue
        reqs = []
        j = i - 1
        while j >= 0 and not re.match(r"(theorem|def|namespace|end)\b", lines[j]):
            r = re.search(r"req:\s*([A-Za-z0-9_, \-]+)", lines[j])
            if r:
                reqs += [x.strip() for x in r.group(1).split(",") if x.strip()]
            if lines[j].lstrip().startswith("/--"):
                break
            j -= 1
        stmt = ""
        for k in range(i, len(lines)):
            stmt += lines[k] + "\n"
            if ":= by" in lines[k]:
                break
        stmt = re.sub(r"\s+", " ", stmt.split(":= by")[0]).strip()
        out.append({"theorem": m.group(1), "line": i + 1, "req": reqs, "statement_sha256": hashlib.sha256(stmt.encode()).hexdigest()})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(LEAN.parents[1] / "results" / "124_lean" / "lean_evidence.json"))
    a = ap.parse_args()
    src = LEAN / "Cksum" / "Spec.lean"
    text = src.read_text()
    ths = theorems(text)
    probe = text.replace("\nend Cksum", "\n" + "\n".join(f"#print axioms Cksum.{t['theorem']}" for t in ths) + "\nend Cksum")
    src.write_text(probe)
    try:
        p = subprocess.run(["lake", "build"], cwd=LEAN, capture_output=True, text=True, timeout=1800)
    finally:
        src.write_text(text)
    log = p.stdout + p.stderr
    ok = p.returncode == 0
    for t in ths:
        m = re.search(r"'Cksum\.%s' depends on axioms: \[(.*?)\]" % re.escape(t["theorem"]), log, flags=re.S)
        t["axioms"] = sorted(x.strip() for x in m.group(1).split(",")) if m else ([] if re.search(r"'Cksum\.%s' does not depend" % re.escape(t["theorem"]), log) else None)
        if not ok or t["axioms"] is None:
            t["status"] = "failed"
        elif "sorryAx" in t["axioms"] or any(x not in ALLOWED and not NATIVE.search(x) for x in t["axioms"]):
            t["status"] = "unsound"
        elif any(NATIVE.search(x) for x in t["axioms"]):
            t["status"] = "proved_bv_decide"
        else:
            t["status"] = "proved"
    rec = {"schema": "fpga-design-agent/lean-evidence/v0-proposal", "toolchain": (LEAN / "lean-toolchain").read_text().strip(),
           "build_ok": ok, "kernel_axioms": sorted(ALLOWED), "native_axiom_pattern": NATIVE.pattern, "theorems": ths}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps({t["theorem"]: t["status"] for t in ths}))
    return 0 if ok and all(t["status"] in ("proved", "proved_bv_decide") for t in ths) else 1


if __name__ == "__main__":
    sys.exit(main())
