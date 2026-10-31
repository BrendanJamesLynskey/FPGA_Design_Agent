# P0 pre-registration: screen open-weight bases for fine-tuning

Written and committed before the first P0 dispatch (2026-10-31, ~21:20 UTC). Nothing below changes after the first
scored run id. This is a **screen**: one run per candidate, not a scored result. CVDP's identical runs vary by about
±3 points on the 86 problems, so differences smaller than that are ties.

## Question

Which open-weight base should P1 fine-tune (SFT, then GRPO)? The base is needed before F3 records the Opus traces
(they should use the base's chat and tool-call format), and RL needs a base that already solves some problems
(zero reward gives no gradient). F1B chose a model to deploy (luna, not open-weight); P0 chooses a model to train.

## Candidates

| Arm | Model (OpenRouter) | Weights (Hugging Face) | Licence | Parameters | Context | List $/M in / out |
|---|---|---|---|---|---|---|
| Q3C | `qwen/qwen3-coder-30b-a3b-instruct` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | Apache-2.0 | 30.5 B total (MoE, about 3.3 B active), BF16 safetensors | 262,144 | $0.07 / $0.28 |
| Q36 | `qwen/qwen3.6-35b-a3b` | `Qwen/Qwen3.6-35B-A3B` | Apache-2.0 | 36.0 B total (MoE, about 3 B active), BF16 safetensors | 262,144 | $0.10 / $0.90 |

Sources (read 2026-10-31 from the public Hugging Face API, `huggingface.co/api/models/<id>`, field `cardData.license`
and `safetensors`; the model cards are `huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct` and
`huggingface.co/Qwen/Qwen3.6-35B-A3B`). Both repos are public and not gated. Last-modified dates on the Hub:
2025-12-03 (Qwen3-Coder) and 2026-04-24 (Qwen3.6). OpenRouter prices and parameters: the public
`openrouter.ai/api/v1/models` list, 2026-10-31.

Not run:
- `qwen/qwen3.8-27b` (dense; reasoning defaults to xhigh; output $2.30/M). Excluded by the brief ("not now").
- Any model in F1B's shortlist (DeepSeek V4.1 Flash, GLM-5.3-Flash, MiniMax-M3.1-Flash). They were measured in F1B
  and are not re-screened here.
- Luna (openai/gpt-6-luna) is not re-run: its F1B base run L1 (run 41152369833, CVDP `aa7404c`) is the reference.

Reasoning: Q3C lists no `reasoning` parameter, so it runs at `default` (no field sent). Q36 lists `reasoning`; it
runs at `low` (the lowest effort it accepts, as F1B's GLM and MiniMax arms did), because F1B showed always-on reasoning
multiplies tokens. No reasoning sweep is run (spend).

## Memory fit (one AMD MI300X, 192 GB HBM3; estimate, not measured)

| Model | BF16 weights | LoRA adapter (rank 64, all linear layers, order of 0.5–1 GB) | Second weight copy for a separate vLLM rollout engine | Headroom with a separate engine |
|---|---|---|---|---|
| Q3C (30.5 B) | 61.1 GB | about 1 GB | 61.1 GB (total 122 GB) | about 70 GB for KV cache, activations and optimiser state |
| Q36 (36.0 B) | 71.9 GB | about 1 GB | 71.9 GB (total 144 GB) | about 48 GB for KV cache, activations and optimiser state |

Weights are 2 bytes per parameter. A colocated engine (vLLM sleep mode, sharing the trainer's weights) needs one copy
and leaves more room. Both fit on one MI300X; Q36 with a separate engine is the tighter case and is the one to check
first when P1 runs. Activation memory for long agent traces (tens of thousands of tokens) is not estimated here.

## Problems and harness

- The 86 evaluation problems of CVDP M3b: `tools/m3b_eval_ids.txt` in `BrendanJamesLynskey/CVDP_RTL_Agent`, SHA-256
  `de88c76a626e93c80288eacf08036e6ce460049a10cceec464ccbcced1af54bf` (86 ids, one comment line), checked at
  `main` `d9e9ca4`.
- LangGraph harness (`harness=langgraph`), `split=agentic`, CVDP `main` at `d9e9ca4`. The agent image is the one
  F1B used: the last commit that touches `agent/` or `docker/` is `aa7404c` (verified 2026-10-31), and `d9e9ca4`
  changes only `key_check.yml`, so the image is the same as F1B's and as luna's base run L1.
- Settings as F1B's arm A and D/G: `runner=ubuntu-24.04-arm`, `threads=4`, `budget_usd=0.10` per problem (the
  default), `max_turns=10`, self-check and lint on, 480 s wall cap, no memory, no pack,
  `deny_data_collection=true`, `seeds=1`, `seed_offset=0`.
- Dispatch (per arm, one at a time):

```
gh workflow run sweep.yml -R BrendanJamesLynskey/CVDP_RTL_Agent --ref main -f harness=langgraph \
  -f model=<model> -f split=agentic -f runner=ubuntu-24.04-arm -f threads=4 -f reasoning=<default|low> \
  -f seed_offset=0 -f deny_data_collection=true -f run_budget_usd=<guard> \
  -f ids=$(grep -v '^#' tools/m3b_eval_ids.txt | paste -sd,)
```

Run guards: F1B's lesson (`04_f1b_report.md`, "the run guard charges $0.10 per in-flight call") is that a guard must
be at least expected spend + $0.40 (in flight) + $0.10 per abandoned call. Expected spend per run is taken from
luna's L1 ($0.53) scaled by list price: Q3C about $0.35, Q36 about $0.70 (reasoning `low` adds output tokens).
Guards: **Q3C $0.90**; **Q36 $1.40** (or less if the brief's cap leaves less: `min($1.50, $2.00 − spend so far)`,
and not dispatched below $1.00).

## Runs

| Arm | Runs | Seed offset | Guard | Order |
|---|---|---|---|---|
| Q3C | 1 | 0 | $0.90 | first |
| Q36 | 1 | 0 | as above | second, only after Q3C's run has finished and been logged |

Two sweeps may be in flight by the rule, but the spend cap is checked with the guards of both, so the two are run
one after the other. Base comparison: luna L1 (`results/f1b/runs/L1_41152369833.csv`).

## Measures (per run)

- Pass rate: the harness's `raw_result.json` rule (collect.py rows; pass = every test result 0).
- Problems solved at least once: with one run per arm this is the pass count; the intersection with L1's passes is
  reported as well.
- Reliability: `tools/reliability.py` at the same CVDP commit, from the uploaded traces (the same seven measures as
  F1B; a failure is a problem-run with any measure non-zero; failures per 86).
- Tokens and $ per problem (provider-reported usage, `summary.json`).
- **Provider that served each call**: the CSV's `provider` column (from the generation lookup).
  **Quantisation**: the sweep does not record the quantisation that served a call, and CVDP's code is not to be
  changed (another session is mid-experiment on its Claude Code path). Recorded instead: the provider names, and
  the `provider_name` field of OpenRouter's generation lookup for a sample of generation ids, if the lookup returns
  it. Where the lookup does not return quantisation, the report says so.

## Selection rule (applied to the two arms; luna as the reference)

1. **Eligible** candidate: its pass count is not below luna's by more than 3 problems (the CVDP noise band), and its
   reliability failures per 86 are not more than luna's + 5.
2. **Pick** the eligible candidate with the most problems solved at least once. If the two solved counts are within
   3 problems of each other (a tie within the noise), prefer the one with fewer reliability failures per 86. If still
   tied, prefer the lower pooled $ per problem.
3. If no candidate is eligible, the report recommends neither and says why. Luna is not a P0 option (it is not
   open-weight).

The paired interval (`tools/ablate.py --level 0.975`, base L1) is reported for scale only and does not change the
pick.

## Spend and stopping rules

- Cap for this brief: **$2.00** of OpenRouter key usage (change in `usage`, from `key_check.yml` before the first
  dispatch and after the last run). Stop with `BLOCKED:` if the account balance would fall below **$5.00**
  (the account balance, from the `/api/v1/credits` line of `key_check.yml`; the key's `limit_remaining` is not the
  binding figure, F1B's 402s came from the account).
- Before the first dispatch the key check read: key usage $89.913455, key `limit_remaining` $69.09, account balance
  $8.11 (run 41242878106, 21:17 UTC). Headroom under the two rules: $2.00 (the cap binds).
- A sweep is dispatched only if this brief's key-usage spend so far plus its own guard is ≤ $2.00, and the
  account balance is ≥ $5.00 at dispatch.
- Every dispatch goes into `results/spend_ledger.csv` with its provider-reported spend, and the brief's key-usage
  change is reconciled with the ledger's sum.
- A run is **void** and re-run once if more than 10% of its problem-runs stop on `llm_error` from a provider-wide
  failure (HTTP 402 or 429 on most calls), as in F1B. No other run is dropped. A re-run needs budget to be left.
- Nothing changes after the first scored dispatch. No tuning, no extra reasoning levels, no extra seeds.

## Deviations

(none yet)
