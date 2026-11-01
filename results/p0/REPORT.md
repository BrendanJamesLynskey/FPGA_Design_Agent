# P0: open-weight base screen (result: inconclusive, no base recommended)

Pre-registration: `results/p0/PREREG.md` (commit 6cd5647; deviations 1 and 2 in the same file). Runs: `results/p0/runs/`.
Descriptive summary: `results/p0/SUMMARY.md`, made by `results/p0/summarise.py` from the committed CSVs.

## Outcome

- **Recommendation: none.** Neither candidate has a valid run, so the selection rule cannot be applied. Luna (the
  F1B base, run 41152369833) remains the only reference.
- Every P0 run was **guard-truncated** (`run_budget_exhausted` on 42–65 of 86 problems), so every run is void under
  the pre-registered guard rule (deviations 1 and 2). Their pass counts are descriptive only.
- The screen was limited by the per-run guard: each in-flight or unreported call is charged $0.10 by the sweep
  guard, at 4 threads. Real spend was $0.27–$1.13 per run, but the guard tripped first. A usable screen needs guards
  of roughly $2–3 per run, or a lower in-flight charge in the sweep. Neither fits the $2.00 cap for two candidates.

## Runs

| Run | Model | Guard | Pass (descriptive) | Stop reasons | Provider-reported $ | Status |
|---|---|---|---|---|---|---|
| 41242996907 | qwen/qwen3-coder-30b-a3b-instruct | $0.90 | 13/86 | run_budget_exhausted 52 | 0.2657 | void (deviation 1) |
| 41247458070 | qwen/qwen3-coder-30b-a3b-instruct | $1.20 | 16/86 | run_budget_exhausted 42 | 0.3278 | void (deviation 2) |
| 41295140135 | qwen/qwen3.6-35b-a3b, reasoning low | $1.38 | 8/86 | run_budget_exhausted 65 | 1.1316 | void (deviation 2 rule) |

Served upstream providers (from the CSV `providers` column; quantisation is not recorded by the sweep): Q3C via
SiliconFlow and Amazon Bedrock; Q36 via CoreWeave, DeepInfra, AkashML, Parasail, DekaLLM and Phala. All calls went
through OpenRouter with `data_collection: deny`.

## Licence and fit (estimates; sources in PREREG.md)

- Both candidates: Apache-2.0 weights, public and not gated (Hugging Face API, 2026-10-31).
- Qwen3-Coder-30B-A3B (30.5 B): BF16 weights 61 GB. Qwen3.6-35B-A3B (36.0 B): BF16 weights 72 GB. Both fit one
  MI300X (192 GB) with LoRA; a separate vLLM rollout copy leaves about 70 GB (Q3C) and about 48 GB (Q36) for the KV
  cache and activations. These are arithmetic estimates, not measurements.

## Spend and reconciliation

- Key usage before this brief: 89.913455 (key_check 41242878106). After Q36: 91.676994 (key_check 41299852423).
  Brief spend: **$1.7635**, under the $2.00 cap.
- Provider-reported sum of the three runs: 0.2657 + 0.3278 + 1.1316 = 1.7251. The 0.0384 difference is unreported
  calls and rounding. Ledger: `results/spend_ledger.csv`.
- Account balance: $36.35 after the owner's top-up (key_check 41299852423); the $5.00 floor was not at risk.

## Method notes

- Dispatch: CVDP `main` at `d9e9ca4`, the same agent image as F1B (`aa7404c`), LangGraph harness, agentic split,
  86 M3b problems (SHA-256 checked), `deny_data_collection=true`, `seed_offset=0`.
- Reliability measures (`tools/reliability.py`) were not computed: every run is void, so they would not inform the
  pick. The traces are in the scratch area, not committed.
- Paired comparison with luna (`tools/ablate.py`) was not run, for the same reason.

## Gaps and what would change the answer

- A valid screen needs guards that do not truncate. At the sweep's current charge rule that means a $2–3 guard per
  run, which exceeds this brief's cap for two candidates. Options for the owner: raise the cap for the screen, or
  change the in-flight charge in the sweep (a CVDP change, not made here).
- Quantisation is not captured by the sweep. This needs a code change in CVDP (not made; another session was mid-experiment).
- Only one candidate pair was screened, with one run each. Results would be a screen, not a score, even if valid.
