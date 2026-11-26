# Brief 217 pre-registration: evidence-keyed repair memory (harness arm R4)

Written 2026-11-26 21:21:08 GMT (from `date`), before any agent run of this brief. Changes after this point go in a dated addendum at the end, never in place.
Branch b217-repair-memory. An intervention on our own designs, not a benchmark score: no CVDP problem is used as an evaluation (owner, 2026-11-25); the 215
benchmark runs are evaluated on in the replay but never recorded from.

## What is tested
`--harness-arm ...,R4`: on a stage-2 repair visit the harness hands the repairing role at most 3 records whose trigger equals the failure's evidence key
`(gate, finding_id, signature_class)` on all three fields (exact match, never text similarity); records come from the knowledge bank's `repairs/`, an optional
folder (`FDA_REPAIR_RECORDS`) and the run's own staging. The retrieval (keys, pool size, records offered) is written to the run.

## Step 1: replay first (brief 226 proposal 4; zero agent tokens)
`tools/repair_memory/replay.py` over the recorded runs with per-gate snapshots (209, 209a, 213, 224 pilots and 215): make records from every other run's
transitions, match each failing stage-2 evaluation, report reach, the recurring-failure share and a ceiling.
- Hold-outs: leave-one-run-out and leave-one-design-out (both reported).
- Records are made only from sources 213, 209, 209a, 224. 215 (public benchmark) runs are evaluated on, never recorded from.
- **Ceiling** = the number of stage-2 visits that could be saved if every matched recurring evaluation were fixed by its record, per run (upper bound; nothing else changes).
- A failed simulate is unkeyed in the replay (the snapshot holds no simulator output); the report counts it.

## Decision rule (stated now)
The live A/B (control H1 against H1,R4 on pilot designs) is **skipped** when the replay's ceiling on the primary outcome, on the pilot designs only (all sources but 215),
is below the smallest detectable effect of that A/B. Smallest detectable effects, from 213's 9 pairs and 226 section 4:
- primary outcome **stage-2 visits to pass**: about **1.7 visits** per run (3 designs x 3 runs per arm);
- pass rate (secondary): **23 to 26 points** at 6 designs x 3 runs; 16 to 18 points at 12 packages.
If the rule skips the A/B, the live work is **one demonstration run** (not scored, n = 1, labelled so): it shows that the arm fires end to end in a real run
(a record written, a retrieval logged, the injected text in the repair prompt). It is not an effect estimate.

## If the A/B is run (plan only; not run unless the rule says so)
- Items: pilot designs that sometimes pass from a separate baseline run (the 209 baseline); never designs selected for failing (regression to the mean).
- Arms: control H1; treatment H1,R4. One change per arm (R4); an arm that changes two things is exploratory. Records from the run's own design family are excluded
  (`FDA_REPAIR_MEMORY_EXCLUDE_RUNS`) for the runs they came from.
- Outcomes, graded first: stage-2 visits to pass (primary); repair rounds per stage; requirements evidenced at V2; WNS or Fmax where a build runs; Vivado runs; plan-estimated cost; own stage-2 pass rate secondary.
- Hygiene: plan-limit, rate-limit and slot-refused stops get their own stop reason and are re-run, never scored as failures; run order and budget-guard order randomised (seeded);
  paired by (design, replicate); paired bootstrap through `tools/ab/paired_numeric.py`; nulls first, "no detectable effect" never "no effect".
- Independent check: none before the board visit; every pass is an own-check verdict.
- Recurring lint findings (213 runs 2, 4 and 15: five to six identical consecutive failures despite the repeat hint) are named evaluation items.

## Stopping rules
Weekly usage 92% (owner's current schedule; the brief's 75% was raised by the planner): stop and report `BLOCKED:`. Usage is checked at the start and before each batch.
Pinned Claude Code 2.1.321 (the checked copy in `_scratch_213/bin`, SHA-256 426c3381...), auto-update off, knowledge repo at the pin for prompts.

## Addendum 2026-11-26 (from `date`)
The demonstration run was queued for a heavy slot from 21:28 and cancelled at 22:18 GMT, still unplaced (two other sessions' runs held both slots and one was ahead in the queue). It was not made; nothing else in this pre-registration changed. The replay and the decision rule are as written.
