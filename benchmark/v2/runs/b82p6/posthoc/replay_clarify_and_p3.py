#!/usr/bin/env python3
"""82P6 Part 1 replays that need the private run archives (the 82P5 planted run) plus the recorded visit-limit stops.

    FDA_KNOWLEDGE=<KB checkout> python3 benchmark/v2/runs/b82p6/posthoc/replay_clarify_and_p3.py <KB checkout>   (repo root)

1. The 82P5 planted run: its clarify stage's spec.yaml (the archive's) is checked at the clarify exit (CONST-ID-03 expected), and
   the archived final design is checked for the owner routing (holders of the wrong value, who is handed what at a persisting visit).
2. The stop reasons of the recorded 82P4 B r2 / B r3 and the 82P5 planted run, as this branch writes them (the recorded reason
   was "stage 2 visited more than 6 times" in all three).
"""
import json
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from agent.graph import repair  # noqa: E402
from agent.graph.stages import MACHINE, classify, constants_stage  # noqa: E402
from flow import derived_constants as DC  # noqa: E402

KB = Path(sys.argv[1])
ROOT = Path(".").resolve()
with tempfile.TemporaryDirectory() as td:
    rid = "20261120-140630-340a"
    troot = Path(td) / "root"                                  # build.yaml's source paths are relative to a repo root: rebuild that layout
    (troot / "runs").mkdir(parents=True)
    for n in ("shell", "boards"):
        (troot / n).symlink_to(ROOT / n)
    with tarfile.open(KB / f"results_private/benchmark/v2/runs/b82p5/artifacts/{rid}/run_dir.tar.gz") as t:
        t.extractall(troot / "runs", filter="data")
    d = troot / "runs" / rid / "v2_e_udp_endpoint"
    print("## 82P5 planted run: clarify-exit check on the run's spec.yaml and spec.md")
    for f in DC.spec_yaml_findings(d, troot):
        print(f"  {f['code']} {'BLOCK' if f['blocking'] else 'advice'} {f['where']}: {f['message']}")
    top = d / "rtl" / "v2_e_udp_endpoint_top.sv"          # the archive holds the last snapshot (shell ID right); visits 1-3 bound the planted word
    top.write_text(top.read_text().replace("= 32'h55455031,  // 'UEP1', shell ID register", "= 32'h55445031,  // 'UEP1', shell ID register"))
    print("## 82P5 planted run: the archived final design with the shell DESIGN_ID set back to the planted word, as at its visits 1 to 3 (model, bench, spec.yaml as archived)")
    t0 = DC.derive(d, troot)
    for f in t0["findings"]:
        print(f"  {f['code']} {'BLOCK' if f['blocking'] else 'advice'} {f['where']}: {f['message'][:160]}")
        print("   holders:", [(h["role"], h["file"], h["line"]) for h in f.get("holders", [])])
    base = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True}, "arch_approval": {"ok": True}, "standards": {"rules": []},
            "verif": {"reached": "V2", "stages": {}}, "verif_level": "V2", "standards_fails": [], "spec_test": {}}
    for label, persisted in (("first visit", False), ("persisting visit", True)):
        c = {"findings": t0["findings"], **({"persisted": True} if persisted else {})}
        owners, sig = repair.stage2_owners({**base, "constants": c})
        print(f"  {label}: owners {list(owners)}; classify -> {classify(MACHINE[2], constants_stage(c)[1])}")
        for r, tx in owners.items():
            print(f"     {r:5s} <- {tx[0][:150]!r}")

print("## stop reasons on the recorded visit-limit stops, as written by this branch")
fix = json.loads(Path("agent/tests/fixtures/b82p6_replay_evidence.json").read_text())
from agent.tests.test_82p6_repair_routing import _first_failure  # noqa: E402
for tag, rec in fix.items():
    s = rec["sim_failures"][-1]
    ev = {"lint": {"ok": True}, "standards_fails": [], "constants": None, "contract": {"ok": True},
          "simulate": {"ok": False, "first_failure": _first_failure(s), "text": s},
          "verif": {"reached": rec["verif"]["reached"], "first_failed": "V2", "stages": {"V2": {"checks": rec["verif"]["V2"]}}},
          "verif_level": "V2", "spec_test": {}}
    owners, sig = repair.stage2_owners(ev, repeat=2)
    why, det = repair.stop_diagnosis(2, 6, {"evidence": ev, "owners": owners, "sig": sig, "repeat": 4, "fails": ["simulate not passing"]})
    print(f"  {tag} (run {rec['run_id']}): was 'stage 2 visited more than 6 times'; now:\n    {why}")
