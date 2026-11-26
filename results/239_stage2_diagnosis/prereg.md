# Brief 239: pre-registration of the stage-2 re-measure (written before any re-run)

Stamped 2026-11-26 21:13 GMT (`date`), executor Sonnet 5.5. The census and the bench verdict (`census_table.md`, `report.md` section "The independent bench") were done from records only; no run of this brief exists yet.

## Question

Do the fixes of this brief, taken together, raise the share of the pilot designs that reach the end of stage 2 (own gates) under the same flags as brief 227's arm A?

## Cells

- Designs **p1_clkmeter, p2_bram_rom, p3_crc_engine** (`/home/brendan/Claude_sandbox/_scratch_227/pilots/<d>/spec.md` and `data/`, the request as the user wrote it), **3 repeats each: 9 runs**, tags `b239_<design>_r<k>`.
- Flags exactly as `tools/requirements_arms/run_arm.sh A` (brief 227): `--stop-after 2 --verif-level V2 --spec-tests --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --board kr260 --review off --docs off --max-usd 12 --budget-scale 3.5 --interview off --requirements loose` (so `--readiness off`; no `--no-shell`). Claude Code 2.1.321 pinned (`_scratch_227/bin`, version preflight), knowledge bank at the pinned commit of `agent/core/prompts_pin.json`, code at this branch's head.
- One run at a time, in the order p1 r1, p2 r1, p3 r1, p1 r2, ... Each run takes a heavy slot (the stage-2 gate builds the rtl stage in Vivado, about 2 minutes and 4 GB) and runs under `systemd-run --user --scope -p MemoryMax=6G`.

## Outcomes

- **Primary: stage-2 own pass** = the run ends with every stage-2 exit gate passed (lint, model contract, simulate, design standards, derived constants, V2, the rtl flow stage): `stop` is `done`, or the stop reason is only the independent bench's `unresolved` or `design_wrong`. Count out of 9.
- Secondary, each per run and in total: the independent spec-only bench verdict (clean pass, design_wrong, bench_wrong, unresolved, not reached) reported **separately** from the primary; stage-2 visits; stage-1 bounces (entries of stage 1 after stage 2); repeated identical lint findings (a stage-2 event whose lint finding equals the previous visit's); plan-cost estimate (not provider-reported: the runs are plan-billed) and wall time.
- Baseline, from records already on disk (`baseline_runs.csv`, same definitions): brief 227 arm A (same flags, earlier code): **4 of 9** own pass, 0 of 9 with the independent bench clean; the pooled earlier runs (213 all, 227 A and C): 14 of 36. Mean stage-2 visits and lint repeats are in the same file.

## Predictions and what would count

- Stated before the runs: of the 22 earlier runs that did not own-pass, the findings of the last stage-1 or stage-2 failure were only the three rules fixed here in 13, included one of them in 6, and none in 3 (`last_blocker.csv`); all 22 met one of them at some visit. Taking the 13 as recoverable, 14 + 13 = 27 of 36 (75%) would have passed, so own pass is expected at **7 of 9 or more**; the independent bench should no longer die at elaboration for a missing `data/jtag_bus.sv` (7 of the 18 runs of 227).
- Reading: 7 or more of 9 is an improvement worth stating; 5 or 6 is "no clear change from 4 of 9 given the sample"; 4 or fewer is a null and the report says so first.
- Tests, all descriptive: Wilson 95% intervals; Fisher's exact test (one-sided) of the 9 against 4/9 (arm A) and against 14/36 (pooled). With 9 runs only a rise to 9 of 9 reaches p < 0.05 against 4 of 9; no significance is claimed beyond that.

## Stopping rules

- Weekly usage: read `_handoff/usage_check.sh` before each run; stop and hand back at 92%.
- A run that hits the agent's own limits (visit limit, turn or cost cap) is a result of its class and is never re-run. A run lost to the infrastructure (the plan's rate limit, a Vivado build refused because another job held the PC, a crash of the wrapper) is recorded with its reason and re-run once; the first attempt stays in `results/239_stage2_diagnosis/runs_attempts.csv`.
- No gate is weakened for a run and no rule changed after the first run; a fault found during the runs is recorded and fixed after the 9 are in.

## Threats to validity

- The earlier runs came from different code (briefs 213 and 227 ran from 04:26 to about 20:00 on 26 November; brief 231's lint policy landed at 09:09) and a different knowledge-bank checkout for 227 (a skill added); the re-run is on one tree and the pinned bank, so the comparison is before and after, not a controlled A/B.
- The fixes land together and cannot be separated by this measure. n = 9, one model and one harness; the models' own variation between repeats is large (earlier repeats of the same cell differed from a pass to a stop at stage 1).
- The independent bench is a model and shares the model family; its verdict is not ground truth. There is still no board check of built behaviour.
