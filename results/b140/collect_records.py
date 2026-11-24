#!/usr/bin/env python3
"""Brief 140: copy the records of finished builds into results/b140/builds/<name>/.

    python3 results/b140/collect_records.py eyescan=designs/b96_kr260_10g/eyescan default=designs/b96_kr260_10g dbg_xvc=designs/b96_kr260_10g/dbg_xvc

Per build: digest.json (flow.digest), gates.json (the gate record with the per-crossing and per-pin lists cut to their counts and the first few
entries), run.json, stages.txt, tool.txt, and for a debug build the lines of vivado.log the fixes print. The gate record is recomputed from the
build's own reports by flow/gates.py, so it carries the current gate code's verdicts."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "builds"


def trim(o, keep=5):
    if isinstance(o, dict):
        return {k: trim(v, keep) for k, v in o.items()}
    if isinstance(o, list):
        return [trim(x, keep) for x in o[:keep]] + ([f"... {len(o) - keep} more"] if len(o) > keep else [])
    return o


def main(args):
    from flow.digest import digest_build
    for a in args:
        name, path = a.split("=", 1)
        b = ROOT / path / "build" / "base"
        o = OUT / name
        o.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(ROOT / "flow" / "gates.py"), str(b), "--json", str(o / "gates_full.json")], capture_output=True)
        g = json.loads((o / "gates_full.json").read_text())
        (o / "gates_full.json").unlink()
        g["build_dir"] = path + "/build/base"
        (o / "gates.json").write_text(json.dumps(trim(g, 8), indent=1) + "\n")
        (o / "digest.json").write_text(json.dumps(digest_build(b), indent=1, default=str) + "\n")
        for f in ("run.json", "stages.txt", "tool.txt"):
            if (b / f).exists():
                (o / f).write_text((b / f).read_text())
        log = (b / "vivado.log").read_text(errors="replace")
        keep = [ln for ln in log.splitlines() if re.match(r"^(FLOW-DEBUG|xpm_cdc:|FLOW-STAGE)", ln)]
        (o / "flow_lines.txt").write_text("\n".join(keep) + "\n")
        print(name, "pass" if g["pass"] else "FAIL", g.get("first_failed_stage"))


if __name__ == "__main__":
    main(sys.argv[1:])
