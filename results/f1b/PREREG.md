# F1B pre-registration: the cheap-model screen

Written and committed before the first scored dispatch (2026-10-31). Nothing below changes after the first scored
run id. The planner checks this file's commit time against the runs' creation times.

## Question

Which cheap model does the FPGA agent use in F2–F3? Measured on CVDP's frozen problems with the CVDP RTL Agent's
LangGraph harness, against `openai/gpt-6-luna` (the CVDP base). Secondary: can Claude Code run a cheap model through
an Anthropic-compatible endpoint, so a later cheap-vs-Opus comparison can hold the harness fixed?

## Problems

The 86 evaluation problems of CVDP M3b: `tools/m3b_eval_ids.txt` in `BrendanJamesLynskey/CVDP_RTL_Agent`, SHA-256
`de88c76a626e93c80288eacf08036e6ce460049a10cceec464ccbcced1af54bf` (86 ids, one comment line). CVDP harness
`8e894cf`, dataset revision `5b807d9`, as in M3b–M3g.

## Candidates, and why (chosen before any scored run)

The filter (`tools/models.py --search` and the public model list, 2026-10-31): open weights (a public Hugging Face
repo), tool calling and structured output listed by OpenRouter, a context of at least 128k, a list price at or below
luna's ($0.10 / $0.50 per M input / output tokens). Kimi K3 is excluded (owner). The shortlist from the filter
(about 30 models) was narrowed to the recent agentic/coding models of the large open-weight families:

| Arm | Model | Weights | List $/M in / out | Context | Why |
|---|---|---|---|---|---|
| D | `deepseek/deepseek-v4.1-flash-1017` | `deepseek-ai/DeepSeek-V4.1-Flash`, MIT | $0.15 / $0.60 (doubled weekdays 01–04 and 06–10 UTC) | 1M | named by the brief; measured in M2 on an older image (41–43 of 92). Above luna's list price, kept as the named reference |
| G | `z-ai/glm-5.3-flash` | `zai-org/GLM-5.3-Flash`, MIT | $0.022 / $0.124 | 1M | the cheapest recent agentic/coding model that passes the filter; 40 providers |
| X | `minimax/minimax-m3.1-flash` | `MiniMaxAI/MiniMax-M3.1-Flash` | $0.075 / $0.30 (15–01 UTC; doubled 01–15 UTC) | 1M | the newest (2026-10-17) open-weight agentic model under luna's price |

Not chosen: Nemotron 3.5 Lightning (3B active parameters), Qwen3.7 Flash (no public weights found, no structured
output listed), the older Gemma 3/4, Llama, Mistral Small, gpt-oss and Qwen3 models (older or smaller than the
three above).

## Settings

Every LangGraph arm: CVDP M3c/M3d arm A's settings except the model and the reasoning setting:
- LangGraph harness, `ubuntu-24.04-arm`, 4 threads;
- the M2 defaults: $0.10 per problem, 10 turns, self-check and lint on, 480 s wall cap; no lessons memory, no pack;
- **`deny_data_collection=true`** on every arm, luna too (house rule: request `provider: {data_collection: "deny"}`).
  This narrows the providers OpenRouter may route to; the providers that served each call are in the CSVs.
- Reasoning: luna `default` (arm A's); DeepSeek `off` (its M2a pick); GLM and MiniMax `low`. Both of the last two
  require reasoning (no `none`) and default to `max`; `low` is the lowest effort each accepts. No reasoning pick is
  run for them (spend).

Agent image and sweep: `CVDP_RTL_Agent` branch `f1b-model-screen` at commit `aa7404c` (also the image tag: the last
commit that touches `agent/`); every scored run is dispatched from that commit. The branch adds two options,
both off by default, and the reliability tool; with the options off the agent is M3c's arm A.

```
gh workflow run sweep.yml --ref f1b-model-screen -f model=<model> -f split=agentic -f runner=ubuntu-24.04-arm \
  -f threads=4 -f reasoning=<r> -f seed_offset=<0|1|2> -f deny_data_collection=true -f run_budget_usd=<guard> \
  -f ids=$(grep -v '^#' tools/m3b_eval_ids.txt | paste -sd,)
```

## Runs

| Arm | Runs | seed_offset | Run guard (`run_budget_usd`) |
|---|---|---|---|
| L: luna (base), on this image | 1 | 0 | $1.20 |
| D: DeepSeek V4.1 Flash 1017 | 3 | 0, 1, 2 | $1.60 each, dispatched at weekend or weekday base-price hours |
| G: GLM-5.3-Flash | 3 | 0, 1, 2 | $0.60 each |
| X: MiniMax-M3.1-Flash | 3 | 0, 1, 2 | $1.20 each, dispatched 15:00–22:00 UTC (base-price hours) |
| C: Claude Code + the pick, via OpenRouter (if the endpoint smoke works) | 1 | 0 | $2.00 |

At most 2 sweeps in flight. The CVDP base runs on older images (M3c arm A, 3 runs; M3d arm A, 3 runs) are not reused
as the base: this image differs (M3g's code, the F1B options, `deny`). They give the drift comparison only.

## Comparisons

All paired over the 86 problems with CVDP's `tools/ablate.py --ids tools/m3b_eval_ids.txt --level 0.975` (paired
bootstrap over problems, 97.5% interval, exact sign test); nulls first in the report.

- **Primary:** D − L, G − L, X − L.
- **Drift (secondary):** L − luna_old, where luna_old = the 6 earlier arm-A runs (M3c `A1..A3`, M3d `A1..A3`).
- **Secondary:** each candidate − luna_old (6 runs), to show how much the 1-run base moves the conclusions.
- **Claude Code (secondary, descriptive):** C − (the pick's LangGraph runs), paired, 97.5%; this changes the harness
  only.

## Reliability measures

From the uploaded traces with `tools/reliability.py` (`f1b-model-screen`), per problem-run: `unparsable` (an edit
reply with no readable block, or an unreadable reflect decision), `invalid_edit` (a write the agent refused: bad
path, a diff that does not apply), `length` (finish reason `length`), `empty` (empty replies), `provider_err` (a call
that raised, or a stop on `llm_error`), `loop` (an edit turn repeating the previous edit's reply, or a second edit in
a row that changed nothing), `cap_stop` (a stop on `max_turns`, `wall_time`, `budget`, `cost_unreported` or
`run_budget_exhausted`). A problem-run with any of them non-zero is a **reliability failure**; per arm, failures per
86 = failures / problem-runs × 86.

## Selection rule

A candidate is **eligible** if both hold:
1. its pass rate is not detectably below luna's: the upper end of its primary 97.5% interval (candidate − L) is ≥ 0;
2. its reliability failures per 86 are ≤ L's + 5.

The pick is the eligible candidate with the lowest pooled provider-reported $ per problem (a lower bound "≥" counts
at its value). If none is eligible, the pick is luna. Ties on cost (within $0.0005 per problem) go to the higher
pooled pass@1.

## Claude Code endpoint (part 3)

Smokes (≤ $0.50 together, not scored) with `harness=claudecode -f claude_endpoint=openrouter` on GLM-5.3-Flash and 5
of the M1 problems. The first (run 41150974037, image `2d0f0d5`) ran Claude Code's tools and solved 2 of the 3 it
reached, but its per-call cost lookup failed (the endpoint's message ids are not generation ids), which tripped the
guard; `aa7404c` takes cost and the guard from the key's usage instead, and a second smoke checks that. It **works**
if Claude Code's tool calls run (non-zero tool calls, files written, a `submit` stop) and the key's usage shows the
cost. If it works, run the
pick once on the 86 in Claude Code (`claude_endpoint=openrouter`, 4 threads, default 60 Claude Code turns, 480 s
cap); if the pick is luna, luna is run. It is dispatched with no other sweep of this brief in flight, so the key's
usage change over the run is its provider-reported cost (per-problem key readings overlap at 4 threads and are not
used as costs). If it does not work, record why and stop that part. Data collection cannot
be set per request through Claude Code; that is a known gap of this arm.

## Spend and stopping rules

- Cap for this brief: **$8** of key usage. `key_check.yml` before the first dispatch; stop if `limit_remaining`
  < $40.
- A sweep is dispatched only if this brief's spend so far (by key usage, `tools/key_usage.py` before/after in each
  run's summary) plus the run guards of every sweep in flight, this one included, is ≤ $8.
- Every dispatch goes into `results/spend_ledger.csv` with its provider-reported spend; the brief's total key usage
  change is checked against the ledger's sum.
- A run is **void** and re-run once if more than 10% of its problem-runs stop on `llm_error` from a provider-wide
  failure (an HTTP 402/429 balance or rate error on most calls), as M3c's first set was. No other run is dropped.
- No other runs, no tuning, nothing changed after the first scored dispatch.
- Not done here: Claude models on the plan (the CVDP ladder exists), heavy split, more runs of luna.
