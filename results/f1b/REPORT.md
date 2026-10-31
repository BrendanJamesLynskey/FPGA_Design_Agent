# F1B: the cheap-model screen (incomplete: the OpenRouter account ran out of credit)

2026-10-31. Pre-registration: [PREREG.md](PREREG.md), committed (`3faca36`, 00:50:40 UTC) before the first scored
run (L1, created 00:50:51 UTC), with three dated deviations added as the runs went. Harness: CVDP RTL Agent branch
`f1b-model-screen` at `aa7404c` (image tag `aa7404c`), CVDP harness `8e894cf`, dataset `5b807d9`, the 86 M3b
evaluation problems (`tools/m3b_eval_ids.txt`, SHA-256 `de88c76a…af54bf`). Every number below is in a file in this
directory; `tables.sh` remakes every table from the committed CSVs with the CVDP tools at `aa7404c`.

## In short

- **DeepSeek V4.1 Flash (1017) is detectably below luna**: −12.4 points [−21.7, −3.5] (97.5% paired interval),
  better / worse / same 4 / 21 / 61, sign test p = 0.0009. Pooled pass@1 127/258 = 49.2% (runs 50.0, 46.5, 51.2%)
  against luna's 53/86 = 61.6%. It also costs more per problem (≥$0.0085 against ≥$0.0062) and has more
  reliability failures (25.0 per 86 against 17.0). It fails both parts of the selection rule.
- **GLM-5.3-Flash was not measured.** All three of its runs are void: the first two were cut short by run guards set
  too tight in the pre-registration (deviations 1 and 2), the third by HTTP 402 errors when the OpenRouter account
  ran out of credit (deviation 3). The void runs are descriptive only; they show calls that hang until the
  per-call deadline (8 and 11 abandoned calls in the second and third attempts, against 1 in luna's run and 1 in the three
  DeepSeek runs together).
- **MiniMax-M3.1-Flash was dropped before any scored run** (deviation 2): under `data_collection=deny` it was served
  at $0.15 / $0.60 per M, above luna's list price, and three runs did not fit the cap.
- **Pick under the pre-set rule, on the arms measured: luna (`openai/gpt-6-luna`).** No candidate with valid runs is
  eligible. This is not a full screen: GLM-5.3-Flash, the cheapest candidate, is untested.
- **Claude Code can run a cheap model through OpenRouter's Anthropic-compatible endpoint.** Two 5-problem smokes with
  GLM-5.3-Flash: Claude Code's tools ran (11–32 tool calls a problem), 4 of 5 problems passed in the second smoke,
  every problem ended on `submit`, no network flag. But the endpoint's message ids are not OpenRouter generation ids,
  so per-call cost cannot be read; the provider-reported cost is only the key's usage over a run. Claude Code's own
  cost figure, at Anthropic's prices, is far above that. The full 86-problem Claude Code run was not made.
- **Spend: $4.04 of the $8 cap** (key usage $84.1755 → $88.2197). The account itself is now at −$0.19.
- **Drift check: luna on this image (with `deny`) matches the six earlier arm-A runs**: +0.4 points [−6.6, +7.2],
  61.6% against 61.2%.

## Arms and runs

| Arm | Model | Reasoning | Scored runs (run id: passed) | Void runs |
|---|---|---|---|---|
| L (base) | `openai/gpt-6-luna` | default | 41152369833: 53/86 | |
| D | `deepseek/deepseek-v4.1-flash-1017` | off | 41155862790: 43/86; 41158370012: 40/86; 41160670998: 44/86 | 41155696288 (cancelled) |
| G | `z-ai/glm-5.3-flash` | low | none | 41153027220, 41155860445 (guard), 41160464390 (402) |
| X | `minimax/minimax-m3.1-flash` | low | dropped (deviation 2) | |

All LangGraph, `ubuntu-24.04-arm`, 4 threads, $0.10 per problem, 10 turns, self-check and lint on, 480 s cap,
`deny_data_collection=true`. Per-problem rows: `runs/` (scored) and `void/`. Candidates and the filter:
[candidates.md](candidates.md).

## Paired results ([paired_eval86.md](paired_eval86.md))

| Comparison | Effect [97.5%] | Better / worse / same | Sign test p |
|---|---|---|---|
| D − L (primary) | −12.4 [−21.7, −3.5] | 4 / 21 / 61 | 0.000911 |
| L − luna_old (drift; [drift_eval86.md](drift_eval86.md)) | +0.4 [−6.6, +7.2] | 18 / 11 / 57 | 0.265 |
| D − luna_old (secondary; [vs_luna_old_eval86.md](vs_luna_old_eval86.md)) | −12.0 [−21.1, −3.5] | 12 / 26 / 48 | 0.0336 |
| D (D1, D2 only) − L (sensitivity, not pre-registered; [sensitivity_D1D2_eval86.md](sensitivity_D1D2_eval86.md)) | −13.4 [−23.3, −4.1] | 3 / 19 / 64 | 0.000855 |

| Arm | Pooled pass@1 | $/problem | $/solved | Median wall | Tokens |
|---|---|---|---|---|---|
| L | 53/86 = 61.6% | ≥$0.0062 | ≥$0.0100 | 57 s | 2.47 M |
| D | 127/258 = 49.2% | ≥$0.0085 | ≥$0.0173 | 21 s | 14.26 M |
| luna_old (M3c + M3d arm A, 6 runs) | 316/516 = 61.2% | ≥$0.0065 | ≥$0.0106 | 63 s | 16.30 M |

≥: some calls' cost was not reported (1 for L, 9 for D), so the cost is a lower bound.

The DeepSeek result agrees with M2 on an older image (41–43 of 92 against 52–53 for luna). It is quicker per problem
(median 21 s) but stops on the turn cap far more often (30 of 258 problem-runs against 1 of 86).

## Reliability ([reliability.md](reliability.md); counts from the traces by `tools/reliability.py`)

Problem-runs affected (events):

| Arm | Problem-runs | unparsable | invalid_edit | length | empty | provider_err | loop | cap_stop | Failures | Per 86 |
|---|---|---|---|---|---|---|---|---|---|---|
| L | 86 | 1 (1) | 17 (45) | 1 (1) | 0 | 1 (1) | 5 (14) | 2 (2) | 17 | 17.0 |
| D | 258 | 1 (1) | 30 (37) | 4 (4) | 0 | 9 (9) | 22 (45) | 31 (31) | 75 | 25.0 |

Per 86 problems, D has more loops (7.3 against 5) and many more cap stops (10.3 against 2): DeepSeek repeats a
failing edit until the turn cap. Its 9 provider errors include D3's 8 HTTP 402s (the account's credit, not
DeepSeek). Neither model gave an empty reply; both rarely gave an unreadable one. The rule's reliability limit for
a candidate is L's 17.0 + 5 = 22.0 per 86; D's 25.0 is over it.

Void GLM runs, descriptive only ([reliability_void.md](reliability_void.md)): provider errors on 2, 8 and 26
problem-runs (the last mostly 402s), `length` stops on 3–6 and empty replies on 3–6 per run, against 0–1 for luna.

## The pick

Under the pre-set rule (PREREG, "Selection rule"): D is not eligible (its interval's upper end, −3.5, is below 0,
and its 25.0 reliability failures per 86 exceed 22.0). G was not measured. **The rule's answer on the measured arms
is luna** ([pick.txt](pick.txt)). For F2–F3 that means luna, unless credit is added and GLM-5.3-Flash is run
(3 runs, about $0.75 each by its void runs' spend, with a guard of at least $3).

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
- **The 86-problem run was not made** (no credit). Its cost is not known; smoke 2 suggests GLM in Claude Code makes
  many more calls than the LangGraph agent (12–33 a problem).

## Spend ([../spend_ledger.csv](../spend_ledger.csv))

Key usage $84.175459 before the first dispatch, $88.219704 after the last: **$4.0442**. Provider-reported LangGraph
spend over every dispatch, void and smoke included, $3.8437; the remainder, $0.2005, is the Claude Code smokes plus
any billed calls whose cost was not reported. Void runs cost $1.0985 of it (G $1.0809, D $0.0176).

## Known gaps

- GLM-5.3-Flash, the cheapest candidate, has no valid run; MiniMax-M3.1-Flash none.
- Luna has one run on this image (the pre-registered design); the drift check against six earlier runs is null.
- D3 lost 8 problem-runs to the account's 402s; it stands under the 10% rule, and the conclusion holds without it.
- The reliability measures are defined by this brief's tool, not validated against hand labels; `invalid_edit` is
  mostly diffs that do not apply, which the agent then retries.
- The Claude Code arm's cost can only be read per run, from the key, and only with nothing else using the key.
