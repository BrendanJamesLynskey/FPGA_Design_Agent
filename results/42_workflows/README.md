# Brief 42: does changing the harness around the model change what the agent costs and achieves?

**Result.** On 4 tasks, 3 repeats, 4 arms (A0 baseline, H1, H2, H9; 48 valid runs of 51, one low-cost model), no arm meets the
pre-registered adopt rule. H1 (context management) used 33 % less cost (paired median, interval excludes 0) and 18 % less wall
time than the baseline and 66 % fewer tokens (interval includes 0), with no loss of hidden-test passes. H9 (typed digests) saved
16 % of cost, below the 30 % bar. H2 (hang protection) showed no difference. Two of the four tasks are never passed by any arm.

## The question and the arms

The role agents are a LangGraph pipeline of Deep Agents roles (clarify, model, tests, RTL) around one model. The harness is
everything around it: tools, context handling, limits. Each change is a flag (`--harness-arm`); the baseline graph is untouched.

| Arm | Change |
|---|---|
| A0 | the baseline. deepagents 0.7.32 already summarises at about 170,000 tokens (fixed fallback: our model reports no context size); its large-result offload (20,000 tokens) never fires behind our 20,000-character clip |
| H1 | the RTL role's large tool results go to a file with a head-and-tail preview; summarisation triggers at 40,000 tokens, keeping 10 messages |
| H2 | a static check refuses a cocotb bench with an unbounded event-waiting `while`; `simulate` runs under a wall-clock watchdog (180 to 900 s from the bench's declared sim-time budget) and a hang returns the test and the simulation time |
| H9 | large `build`, `gates`, `simulate` and `lint` results become a deterministic typed summary digest plus a path; new tool `report_digest` (stage 3 and later only) |

Not run: the other arms of the brief (H3 to H8, A1 to A6) and the four extension tasks.

## Design

Pre-registered before any run ([prereg.md](prereg.md), with dated amendments). Tasks: `t1_gray_stepper`, `t1_debounce_bank`
(development split) and the two brief 24 drills `d24_registered_outputs`, `d24_no_extra_latency` (outside every split). Every
run stops after stage 2 (`--stop-after 2 --verif-level V1`): RTL, tests and simulation, no Vivado. Model `openai/gpt-6-luna` on
OpenRouter for every role. Each (task, repeat) is a block with all four arms, in a rotated order. Scored by the task's hidden
test bench; no model scores anything. Tokens and cost are provider-reported. Intervals are percentile bootstraps of the paired
difference over blocks (10,000 resamples, seed 20261111).

## Headline (all three repeats, 12 blocks; [analysis.md](analysis.md))

| Arm | Hidden-bench passes | Median tokens | Paired change vs A0: tokens | cost | wall time |
|---|---|---|---|---|---|
| A0 | 5 of 12 | 13.3 M | baseline | baseline | baseline |
| H1 | 5 of 12 | 6.1 M | -65.6 %, interval includes 0 | -32.8 %, excludes 0 | -18.1 %, excludes 0 |
| H2 | 6 of 12 | 13.7 M | -1.7 %, includes 0 | -1.5 %, includes 0 | -2.1 %, includes 0 |
| H9 | 6 of 12 | 10.4 M | -32.8 %, includes 0 | -16.1 %, excludes 0 | -6.0 %, includes 0 |

The pre-registered rule says the primary metric "tokens per run (and cost)" must improve by 30 % with an interval excluding 0.
That wording was not fixed as one reading: on tokens alone H1 fails (interval includes 0), on cost it passes. Both readings are
in analysis.md; nothing was adopted.

## Caveats

- **Two tasks are never passed.** `t1_gray_stepper` and `t1_debounce_bank` passed 0 of 6 runs in every arm (one partial run of
  1 of 9 hidden tests). The pass counts above come from the two drills only; those two tasks compare cost and time.
- **Few blocks.** 12 blocks (10 or 11 for tokens and cost: runs ended by the hard 5,400 s limit have no provider-reported total).
  The intervals are close to the observed range. H1's wall-time interval includes 0 once the two blocks with a hard-limit run are
  left out ([-819, +104] s). Wall time is also affected by load from two workers and other sessions.
- **Post hoc tests.** The sign-test p-values in analysis.md were not pre-registered and are not corrected for the 9 arm-by-metric
  tests (0.05 / 9 = 0.0056); none passes that bar.
- **Undercounted cost.** A malformed provider response is retried and its usage is dropped, so cost and tokens are slightly low,
  mostly in A0.
- **H2 was not measured against a hang.** The baseline had one hang in 12 runs and H2's watchdog fired in one run (four times),
  but the agent re-ran the same hanging simulation and the run reached the hard limit. The watchdog doubles its limit for
  coverage runs (1,200 s), which made it slow. One hang per arm is not a rate.
- **H9's `report_digest` tool was not used.** Stage 2 has no Vivado report and the tool is offered with `report` only; the runs
  measure the digests that replace large simulate, lint and gates results.
- Three runs were lost to malformed provider responses before a retry was added (excluded, re-run); a retry for every arm was
  added afterwards (amendment 3). Two valid runs did not build under the bench's Icarus (`built: false`).

## What comes next

1. A stall rule (the same failure or hang repeated ends the visit: arm H4) and removing the doubled limit for coverage runs.
2. A drill that hangs on purpose, so H2 can be measured.
3. A trial of H1 as a default on tasks a model can pass.
4. The remaining arms of the brief.

## Files

[prereg.md](prereg.md) (amendments 1 to 7) · [analysis.md](analysis.md) (written by [analyze.py](analyze.py)) · [runs.md](runs.md) and
[runs.jsonl](runs.jsonl) (one record per run) · [driver.py](driver.py) · [repair_records.py](repair_records.py) · [scores/](scores/) ·
[environment.txt](environment.txt) · the spend is in [../spend_ledger.csv](../spend_ledger.csv) (brief `42_harness`).
