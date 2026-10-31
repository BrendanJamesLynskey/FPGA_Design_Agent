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

## Deviation 1 (2026-10-31 01:31 UTC, after scored runs L1 and G1; committed before any further dispatch)

**What happened.** G1 (run 41153027220) stopped 67 of its 86 problems on `run_budget_exhausted` with only $0.2377
reported. The run guards above were set from expected spend alone, but the sweep's guard charges the $0.10
per-problem budget for every call whose cost is not yet reported, and every in-flight call counts as unreported
until it returns (the agent checkpoints before each call). At 4 threads that is up to $0.40 of charge on top of the
real spend, plus $0.10 for each call that ends unreported (G1 had 2). So a $0.60 guard trips at about $0.20 of real
spend. This is an error in this pre-registration's guard values, not the model's behaviour. L1 (guard $1.20, charge
$0.63 at the end) was not affected: none of its problems stopped on the guard.

**Change.** G1 is void (kept in the ledger, not in any table) and re-run as `G1` with seed_offset 0 again. The guards
become: G $1.20, D $2.00, X $1.50 (expected spend + $0.40 in-flight + $0.30 margin). A DeepSeek dispatch made with
the old $1.60 guard (run 41155696288) was cancelled about a minute into its Run step (correction, same session: it had
already made calls, $0.0176 reported plus 4 in flight); it is void, in the ledger, and in no table. Nothing
else changes: arms, settings, comparisons, measures and the selection rule are as above. The brief's $8 stopping
rule still counts the new guards.

## Deviation 2 (2026-10-31, after the re-run of G1; committed before any further dispatch)

**What happened.** The re-run of G1 (run 41155860445, guard $1.20) stopped 32 of 86 problems on
`run_budget_exhausted` with $0.4732 reported: GLM-5.3-Flash had 8 calls that never returned (abandoned at the
per-call deadline, so counted unreported and charged $0.10 each by the guard), and the in-flight charge came on
top. The guard rule of deviation 1 is still too tight for a model whose calls hang. The run is void (in the ledger,
in no table); its abandoned calls are a reliability finding and are reported as such, not scored.

**Changes.**
1. G's guard becomes **$3.00** (its real spend is about $0.75 a run; the guard only has to bound it). D keeps $2.00
   (D1 ended at a $0.75 charge with no unreported call).
2. **Arm X (MiniMax-M3.1-Flash) is dropped before any scored X run.** Under `deny_data_collection` its smoke was
   served by Parasail at $0.15 / $0.60 per M, above luna's list price, so it fails this pre-registration's own price
   filter as served; and the smokes and runs so far (key usage $2.05 of the $8 at 02:05 UTC) put 3 X runs (about
   $1.20 each, from the smoke's cost scaled by the luna and DeepSeek smoke-to-run ratios) plus D and G past the cap.
   The selection rule is applied to D and G only.
3. The Claude Code run (part 3) is dispatched only if, after D and G, the brief's key usage plus a $1.50 Claude Code
   guard is ≤ $8; otherwise it is not run and the report says so.
Nothing else changes.

## Deviation 3 (2026-10-31, after the third G1 attempt; the screen stops)

The third G1 attempt (run 41160464390, guard $3.00) is void under the pre-registered 402 rule: 15 of its 86
problem-runs stopped on HTTP 402 `in_flight_budget_exhausted`. A credits check (`key_check.yml` on
`f1b-model-screen`, run 41165420738) shows the cause: the OpenRouter **account** has $100 of credits purchased and
$100.19 used, so it is out of credit, although the key's own limit ($159) has $70.78 left. D3 (run 41160670998) lost
8 problem-runs (9.3%) to the same 402s at 02:52 UTC; under the 10% rule it stands, and a sensitivity table without it
is given. No further run can be made until credit is added, which is the owner's decision. The selection rule is
applied to the arms with valid runs (L and D); GLM has no valid run and is not evaluated; the Claude Code run is not
made.

## Deviation 4 (2026-10-31 ~09:50 UTC: the GLM arm resumed after credit was added; committed before its dispatches)

The owner added $10 of OpenRouter credit (account balance $9.81 at 09:47 UTC, `key_check` run 41190076245; key usage
unchanged at $88.219704). The GLM arm is run now; nothing else in this file changes except:

1. **Commit.** GLM runs are dispatched from CVDP `main` at `d9e9ca4` (PR #33 merged) instead of `aa7404c`. The only
   difference between the two is `key_check.yml` (the credits line); the last commit touching `agent/` or `docker/`
   is still `aa7404c`, so the agent image (`cvdp-rtl-agent:aa7404c…`), the sweep and every setting are those of L1 and
   D1–D3. Luna's run L1 stays the base; it is not re-run.
2. **Guards.** Each G run gets `run_budget_usd = min($3.00, $8 − this brief's key usage so far)`, set at dispatch
   (below about $2.30 the run is not dispatched, since that is the expected spend + $0.40 in flight + about 11
   abandoned calls). G runs go one at a time, so the $8 rule holds with one guard in flight.
3. **Stopping.** No dispatch if the account balance is below $3 (planner, 2026-10-31).
4. **Claude Code run (part 3)** of the pick only if it fits under $8 with margin after the G runs, with nothing else
   spending on the key.

## Deviation 5 (2026-10-31 ~14:40 UTC, after G3; written after its result was seen)

G1 (run 41190255842) and G2 (run 41196831612) completed with no guard stop and no 402. G3 (run 41204299796, guard
$2.81 = $8 − $5.19 by deviation 4) stopped 13 of 86 problems on `run_budget_exhausted`. GLM's calls hang (20–21
abandoned a run), each charged $0.10 by the guard, and the in-flight charge pushed it over. As with deviations 1–2,
G3 is **void** (in the ledger, not in the primary tables). It cannot be re-run: the brief's key usage is now $5.74,
which leaves $2.26, under the $2.30 floor of deviation 4. **The rule is applied to G with 2 runs (G1, G2).** A
sensitivity table adds G3's rows. Neither choice changes the outcome (see REPORT.md): G fails the reliability
condition with either. The Claude Code 86-problem run (part 3) is cancelled by an owner scope change (Claude Code runs
Anthropic models only, on the plan); none was dispatched.
