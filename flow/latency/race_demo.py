#!/usr/bin/env python3
"""Measure lat_pipe (true latency 3 clocks) with the planted racy-counter bench and its repair, two ways each, and record
results/189_verification_rules/latency_race.json (brief 189 item 7). Needs Icarus Verilog. Advisory."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "flow" / "tests"))


def main() -> int:
    import test_189_latency_crosscheck as T
    from flow.latency import crosscheck as X
    rows = []
    with tempfile.TemporaryDirectory() as d:
        for racy, what in ((0, "planted race, counter process written first"), (1, "planted race, stamp process written first"), (2, "repaired: non-blocking counter")):
            rec = T._measure(Path(d), racy)
            rows.append({"variant": racy, "what": what, "counter_clocks": rec["methods"][0]["value"], "simulator_time_clocks": rec["methods"][1]["value"],
                         "true_latency_clocks": T.TRUE_LATENCY, "findings": [f["code"] for f in X.check_record(rec)]})
    rec = {"enforced": False, "simulator": "Icarus Verilog 12.0", "design": "flow/tests/fixtures/latency_race", "rows": rows}
    out = ROOT / "results" / "189_verification_rules" / "latency_race.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1) + "\n")
    for r in rows:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
