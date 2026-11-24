#!/usr/bin/env python3
"""82P6 Part 1 replay of P1 on the recorded 82P4 B r2 and B r3 stage-2 failures (fixture made by extract_replay_evidence.py):
which role is handed which text at repeat 0, 1 and 2, with the code of origin/main at the 82P5 merge (ddc62aa5, the 82P4 and 82P5
code) and with this branch.

    python3 benchmark/v2/runs/b82p6/posthoc/replay_p1.py   (from the repo root; FDA_KNOWLEDGE set for the prompt text)
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from agent.graph import repair as NEW  # noqa: E402

FIX = json.loads(Path("agent/tests/fixtures/b82p6_replay_evidence.json").read_text())
BASE = "ddc62aa5"


def old_module():
    src = subprocess.run(["git", "show", f"{BASE}:agent/graph/repair.py"], capture_output=True, text=True, check=True).stdout
    f = Path(tempfile.mkdtemp()) / "repair_old.py"
    f.write_text(src)
    spec = importlib.util.spec_from_file_location("repair_old", f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def first_failure(text: str) -> dict:
    lines = text.splitlines()
    msgs = [l.strip() for l in lines[1:] if l.strip().startswith("AssertionError")]
    frames = [l.strip() for l in lines if 'File "' in l]
    return {"test": lines[0].replace("[first failure] ", "").strip(), "message": msgs[:3], "where": None, "cause": [], "frames": frames}


def evidence(rec: dict, sim_text: str) -> dict:
    checks = {k: v for k, v in rec["verif"]["V2"].items()}
    return {"lint": {"ok": True}, "standards_fails": [], "constants": None, "contract": {"ok": True},
            "simulate": {"ok": False, "first_failure": first_failure(sim_text), "text": sim_text},
            "verif": {"reached": rec["verif"]["reached"], "first_failed": rec["verif"]["first_failed"], "stages": {"V2": {"checks": checks}}},
            "verif_level": "V2", "spec_test": {}}


def show(mod, title: str, ev: dict) -> None:
    print(f"## {title}")
    for rep in (0, 1, 2):
        owners, sig = mod.stage2_owners(ev, repeat=rep)
        print(f"repeat {rep}:")
        for role, texts in owners.items():
            t = " || ".join(x[:110].replace("\n", " ") for x in texts)
            print(f"  {role:5s} <- {len(texts)} text(s): {t!r}")
    print()


OLD = old_module()
for tag, rec in FIX.items():
    for i, s in enumerate(rec["sim_failures"][:1]):                        # the first recorded failing simulation of the run
        ev = evidence(rec, s)
        print(f"# {tag} (run {rec['run_id']}), recorded simulation failure {i + 1}: {ev['simulate']['first_failure']['test']}")
        print("V2 failed checks as recorded:", [k for k, c in rec["verif"]["V2"].items() if not c.get("pass")])
        show(OLD, f"before: origin/main {BASE}", ev)
        show(NEW, "after: this branch", ev)
