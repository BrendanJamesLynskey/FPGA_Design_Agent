#!/usr/bin/env python3
"""Part A of 82P5: replay agent/graph/repair.py: stage2_owners on evidence shaped like the 82P4 B r3 stage-2 failure, to show which
role is handed which text at each repeat count. No agent code is changed; the 'proposal' rows only edit the evidence dict.

    FDA_KNOWLEDGE=<private checkout> python3 benchmark/v2/runs/b82p5/posthoc/replay_stage2_owners.py   (from the repo root)

The evidence mirrors the recorded run: the first failing simulation test is an assertion between the bench and the DUT, the V2
verification gate also fails on `constrained_random_test_ran` (a consequence of the failing simulation, listed in the run's
build/verif/verif_gates.json) and `failing_tests` / `planned_tests_missing` (already treated as covered by the simulation failure).
"""
import copy
import json
import sys

sys.path.insert(0, ".")
from agent.graph.repair import stage2_owners  # noqa: E402

FF = {"test": "test_reset_and_scratch", "message": ["AssertionError: status 2 expected 0"], "where": "bench_v2_e_udp_endpoint.py:261", "cause": []}
EV = {"lint": {"ok": True}, "standards_fails": [], "constants": None, "contract": {"ok": True},
      "simulate": {"ok": False, "first_failure": FF, "text": "[first failure] test_reset_and_scratch ..."},
      "verif": {"reached": "V1", "first_failed": "V2", "stages": {"V2": {"checks": {
          "failing_tests": {"pass": False, "value": ["seed1:bench.test_a"], "threshold": []},
          "constrained_random_test_ran": {"pass": False, "value": False, "threshold": True,
                                          "why": "no passing test with 'random' in its name in seed1: name the constrained-random test so and run it"},
          "assertions_bound_zero_failures": {"pass": False, "value": [], "threshold": "bound in the run; no failure",
                                             "why": "a test failed in some seed: see failing_tests"}}}}},
      "verif_level": "V2", "spec_test": {}}


def show(title: str, ev: dict) -> None:
    print(f"## {title}")
    for rep in (0, 1, 2):
        owners, sig = stage2_owners(ev, repeat=rep)
        print(f"repeat {rep}:")
        for role, texts in owners.items():
            print(f"  {role:5s} <- {texts[-1][:130].replace(chr(10), ' ')!r}")
    print()


show("as recorded (the V2 consequence checks are listed as the Verifier's own failures)", EV)
alt = copy.deepcopy(EV)
for k in ("constrained_random_test_ran", "assertions_bound_zero_failures"):
    alt["verif"]["stages"]["V2"]["checks"].pop(k)
show("proposal P1a (evidence edit only): the two consequence checks are treated as covered by the failing simulation", alt)
