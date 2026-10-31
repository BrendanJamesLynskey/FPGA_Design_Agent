# F1B: the cheap-model screen

2026-10-31. Pre-registration: [PREREG.md](PREREG.md), committed (`3faca36`, 00:50:40 UTC) before the first scored
run (L1, created 00:50:51 UTC), with five dated deviations added as the runs went (the account ran out of credit
part-way; the owner added credit and the GLM arm was finished from CVDP `main` `d9e9ca4`, same agent image).
Harness: CVDP RTL Agent, agent image `aa7404c`, CVDP harness `8e894cf`, dataset `5b807d9`, the 86 M3b evaluation
problems (`tools/m3b_eval_ids.txt`, SHA-256 `de88c76a…af54bf`). Every number below is in a file in this directory;
`tables.sh` remakes every table from the committed CSVs with the CVDP tools at `aa7404c`.

## In short

- **Pick under the pre-set rule: luna (`openai/gpt-6-luna`).** Neither cheap candidate is eligible.
- **GLM-5.3-Flash: no detectable pass-rate difference, but unreliable, and not cheaper.** −4.1 points [−13.4, +5.8]
  (97.5% paired interval; better / worse / same 10 / 16 / 60, p = 0.33), pooled 99/172 = 57.6% (runs 59.3, 55.8%)
  against luna's 53/86 = 61.6%. Its reliability failures are **48.5 per 86** against luna's 17.0 (limit 22.0):
  calls that hang to the per-call deadline (12 and 20 in its two runs), `length` stops, empty and unreadable replies, loops. It
  also costs no less per problem (≥$0.0067 against ≥$0.0062: mandatory reasoning makes it use about twice luna's
  tokens) and takes a median 203 s per problem against 57 s. It fails the reliability condition.
- **DeepSeek V4.1 Flash (1017) is detectably below luna**: −12.4 points [−21.7, −3.5], 4 / 21 / 61, p = 0.0009;
  pooled 127/258 = 49.2%; ≥$0.0085 per problem; reliability failures 25.0 per 86. It fails both conditions.
- **MiniMax-M3.1-Flash was dropped before any scored run** (deviation 2): under `data_collection=deny` it was served
  at $0.15 / $0.60 per M, above luna's list price.
- **Claude Code can run a cheap model through OpenRouter's Anthropic-compatible endpoint** (two 5-problem smokes with
  GLM-5.3-Flash; 4 of 5 passed in the second). Cost is visible only through the key's usage, and data collection
  cannot be denied per request. The planned 86-problem Claude Code run was cancelled by an owner scope change
  (Claude Code runs Anthropic models only).
- **Spend: $5.74 of the $8 cap** (key usage $84.1755 → $89.9135), $1.65 of it on void runs.
- **Drift check: luna on this image (with `deny`) matches the six earlier arm-A runs**: +0.4 points [−6.6, +7.2].

## Arms and runs

| Arm | Model | Reasoning | Scored runs (run id: passed) | Void runs |
|---|---|---|---|---|
| L (base) | `openai/gpt-6-luna` | default | 41152369833: 53/86 | |
| D | `deepseek/deepseek-v4.1-flash-1017` | off | 41155862790: 43/86; 41158370012: 40/86; 41160670998: 44/86 | 41155696288 (cancelled) |
| G | `z-ai/glm-5.3-flash` | low | 41190255842: 51/86; 41196831612: 48/86 | 41153027220, 41155860445, 41204299796 (guard); 41160464390 (402) |
| X | `minimax/minimax-m3.1-flash` | low | dropped (deviation 2) | |

All LangGraph, `ubuntu-24.04-arm`, 4 threads, $0.10 per problem, 10 turns, self-check and lint on, 480 s cap,
`deny_data_collection=true`. L and D ran from `aa7404c`, G1–G2 from `main` `d9e9ca4`; both use agent image
`aa7404c` (the two commits differ only in `key_check.yml`). G has 2 scored runs, not 3: its third (G3) was cut on 13
problems by the run guard and could not be re-run within the cap (deviation 5). Per-problem rows: `runs/` (scored)
and `void/`. Candidates and the filter: [candidates.md](candidates.md).

## Paired results ([paired_eval86.md](paired_eval86.md))

| Comparison | Effect [97.5%] | Better / worse / same | Sign test p |
|---|---|---|---|
| G − L (primary) | −4.1 [−13.4, +5.8] | 10 / 16 / 60 | 0.327 |
| D − L (primary) | −12.4 [−21.7, −3.5] | 4 / 21 / 61 | 0.000911 |
| L − luna_old (drift; [drift_eval86.md](drift_eval86.md)) | +0.4 [−6.6, +7.2] | 18 / 11 / 57 | 0.265 |
| G − luna_old (secondary; [vs_luna_old_eval86.md](vs_luna_old_eval86.md)) | −3.7 [−12.4, +4.8] | 17 / 23 / 46 | 0.43 |
| D − luna_old (secondary) | −12.0 [−21.1, −3.5] | 12 / 26 / 48 | 0.0336 |
| G with void G3 − L (sensitivity; [sensitivity_G123_eval86.md](sensitivity_G123_eval86.md)) | −8.1 [−17.4, +1.6] | 11 / 26 / 49 | 0.0201 |
| D without D3 − L (sensitivity; [sensitivity_D1D2_eval86.md](sensitivity_D1D2_eval86.md)) | −13.4 [−23.3, −4.1] | 3 / 19 / 64 | 0.000855 |

| Arm | Pooled pass@1 | $/problem | $/solved | Median wall | Tokens |
|---|---|---|---|---|---|
| L | 53/86 = 61.6% | ≥$0.0062 | ≥$0.0100 | 57 s | 2.47 M |
| G | 99/172 = 57.6% | ≥$0.0067 | ≥$0.0116 | 203 s | 10.34 M |
| D | 127/258 = 49.2% | ≥$0.0085 | ≥$0.0173 | 21 s | 14.26 M |
| luna_old (M3c + M3d arm A, 6 runs) | 316/516 = 61.2% | ≥$0.0065 | ≥$0.0106 | 63 s | 16.30 M |

≥: some calls' cost was not reported (1 for L, 34 for G, 9 for D), so the cost is a lower bound. GLM's list price is
a fifth of luna's, and most of its calls went to providers at $0.02–0.05 per M input (OpenInference, Wafer); a
quarter went to dearer ones (InferenceNet, CoreWeave, Particle AI: up to $0.15 / $0.50). Its cost comes from volume:
about 60k tokens per problem against luna's 29k, since it reasons on every call. Providers per call are in the CSVs.

## Reliability ([reliability.md](reliability.md); counts from the traces by `tools/reliability.py`)

Problem-runs affected (events):

| Arm | Problem-runs | unparsable | invalid_edit | length | empty | provider_err | loop | cap_stop | Failures | Per 86 |
|---|---|---|---|---|---|---|---|---|---|---|
| L | 86 | 1 (1) | 17 (45) | 1 (1) | 0 | 1 (1) | 5 (14) | 2 (2) | 17 | 17.0 |
| G | 172 | 16 (16) | 39 (61) | 21 (34) | 18 (28) | 34 (34) | 35 (63) | 26 (26) | 97 | 48.5 |
| D | 258 | 1 (1) | 30 (37) | 4 (4) | 0 | 9 (9) | 22 (45) | 31 (31) | 75 | 25.0 |

GLM fails on every measure: per 86 problems it has 17 provider errors (hung calls, abandoned at the deadline, and 2
malformed responses), 10.5 `length` stops, 9 runs with empty replies and 8 with unreadable ones, against 0–1 of each
for luna. This is the failure the HW Design Space Agent saw with cheap Qwen models. DeepSeek is reliable at the call
level but loops on a failing edit until the turn cap (31 cap stops in 258). The limit for a candidate is L's
17.0 + 5 = 22.0 per 86. The void runs ([reliability_void.md](reliability_void.md)) agree: 57–81 per 86 for GLM.

## The pick

Under the pre-set rule (PREREG, "Selection rule"):
- G: condition 1 holds (the interval's upper end, +5.8, is ≥ 0); condition 2 fails (48.5 > 22.0). Not eligible.
  With the void G3 added, still not eligible (57 per 86 in that run alone).
- D: both fail (upper end −3.5 < 0; 25.0 > 22.0). Not eligible.

**No candidate is eligible, so the pick is luna** ([pick.txt](pick.txt)). For F2–F3: luna for the cheap-model arms.
GLM-5.3-Flash's pass rate is close enough that it may be worth a later look with retries on hung calls, but that
would be a harness change, not this screen.

## Claude Code with a cheap model (part 3)

| Smoke | Run | Image | Problems | Result | Cost |
|---|---|---|---|---|---|
| 1 | 41150974037 | `2d0f0d5` | 5 (3 ran) | DES_0003 pass, axis_to_uart fail (wall cap), barrel_shifter pass; 2 skipped by the guard | $0.0286 by key usage |
| 2 | 41152301551 | `aa7404c` | 5 | 4 of 5 pass, all `submit`, 11–32 tool calls each, wall 24–305 s | not separable (it overlapped L1); with smoke 1, at most $0.2005 |

- **It works**: with `ANTHROPIC_BASE_URL=https://openrouter.ai/api`, the OpenRouter key as `ANTHROPIC_AUTH_TOKEN`
  and an empty `ANTHROPIC_API_KEY`, Claude Code 2.1.310 ran `z-ai/glm-5.3-flash` for every model call (the stream
  names only that model), used Read/Edit/Write/Bash, and edited and tested designs. No network flags.
- **Cost is reported only at the key level.** Every assistant message id was `msg_…`, and OpenRouter's generation
  endpoint knows none of them, so smoke 1's per-call lookup failed and its unreported-call charge tripped the run
  guard. `aa7404c` reads the key's usage before and after each problem and guards on the key's usage since the run's
  first problem. Claude Code's own `total_cost_usd` (Anthropic prices) was $0.23–1.56 per problem in smoke 2, while
  the key's whole change over both smokes, less everything else, is at most $0.20 for 8 problems.
- **Data collection** cannot be set per request through Claude Code; this arm cannot meet the `deny` house rule
  except through account-level OpenRouter settings.
- **The 86-problem run is cancelled by an owner scope change** (2026-10-31): Claude Code runs Anthropic models only,
  on the Max plan; LangGraph and Deep Agents use OpenRouter. None was dispatched. The smokes stay as the finding.

## Spend ([../spend_ledger.csv](../spend_ledger.csv))

Key usage $84.175459 before the first dispatch, $89.913455 after the last: **$5.7380**. Provider-reported LangGraph
spend over every dispatch, void and smoke included, $5.5351; the remainder, $0.2029, is the Claude Code smokes plus
any billed calls whose cost was not reported. Void runs cost $1.6445 of it (G $1.6269, D $0.0176). The account ran out
of credit at 03:20 UTC ($100 purchased) and the owner added $10; GLM's runs after that ran alone on the key, and each
run's key change matches its reported spend to $0.0022.

## Known gaps

- G has 2 scored runs, not 3 (deviation 5); MiniMax-M3.1-Flash has none.
- Luna has one run on this image (the pre-registered design); the drift check against six earlier runs is null.
- D3 lost 8 problem-runs to the account's 402s; it stands under the 10% rule, and the conclusion holds without it.
- The run guards were set too tight four times (deviations 1, 2, 5): the sweep charges $0.10 for each in-flight or
  unreported call, which a model with hanging calls runs up quickly.
- The reliability measures are defined by this brief's tool, not validated against hand labels; `invalid_edit` is
  mostly diffs that do not apply, which the agent then retries.
- Claude Code with a non-Anthropic model is outside the owner's rule; only the smokes exist.
