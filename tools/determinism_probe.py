#!/usr/bin/env python3
"""Brief 107 level 1: how often are repeated requests identical at temperature 0 (pre-registered in
results/107_deterministic/preregistration.md)? Sends fixed prompts N times to one chat endpoint through the model resolver.

    python tools/determinism_probe.py OUT.json [--model openai/gpt-6-luna] [-n 10]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROMPTS = [
    "Write a SystemVerilog module `popcount8` with input [7:0] a and output [3:0] n that counts the set bits. Code only.",
    "In one paragraph, explain why a two-flop synchroniser reduces metastability but does not remove it.",
    "List five checks a reviewer should make on an AXI4-Lite slave register block, one line each.",
    "Give the SystemVerilog for a 4-deep synchronous FIFO status flags block (empty, full) with a 3-bit count. Code only.",
    "Rewrite as a numbered list of steps: 'Open the project, run synthesis, check the timing report, then generate the bitstream.'",
]
ARMS = {"A_temperature0_seed": {"temperature": 0, "seed": 1234}, "B_temperature0.2_default": {"temperature": 0.2}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("-n", type=int, default=10)
    a = ap.parse_args()
    from agent.models.resolver import chat_client
    result: dict = {"model": a.model, "endpoint": "openrouter", "n": a.n, "arms": {}}
    for arm, opts in ARMS.items():
        client = chat_client("rtl", model=a.model, endpoint="openrouter", options={**opts, "max_tokens": 256})
        rows = []
        for i, p in enumerate(PROMPTS):
            texts, provs, fails = [], collections.Counter(), 0
            for _ in range(a.n):
                r = None
                for _try in range(2):
                    try:
                        r = client([{"role": "user", "content": p}])
                        break
                    except Exception as e:                      # a failed call is counted, never a key or message
                        last = type(e).__name__
                if r is None:
                    fails += 1
                    continue
                texts.append(r.text)
                provs[r.provider or "?"] += 1
            c = collections.Counter(hashlib.sha256(t.encode()).hexdigest()[:12] for t in texts)
            top = c.most_common(1)[0][1] if c else 0
            rows.append({"prompt": i, "calls": len(texts), "failed": fails, "distinct": len(c), "identical_rate": round(top / len(texts), 3) if texts else None,
                         "providers": dict(provs)})
            print(arm, rows[-1], flush=True)
        done = [r for r in rows if r["calls"]]
        result["arms"][arm] = {"options": opts, "prompts": rows,
                               "mean_identical_rate": round(sum(r["identical_rate"] for r in done) / len(done), 3) if done else None,
                               "fully_identical_prompts": sum(1 for r in done if r["distinct"] == 1)}
    a.out.write_text(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
