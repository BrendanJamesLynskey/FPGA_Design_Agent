# Brief 227: requirements readiness, the reviewer test set, and the gate on our own designs

This folder holds the pre-registrations and the records for brief 227: the requirements reviewer measured on a labelled set of CVDP problems (a test set for the reviewer, never an evaluation of FPGA Force, owner decision
2026-11-25), the stage-0 readiness gate run on the six KR260 pilot designs of brief 209 with an oracle, and build runs of three of those designs from three kinds of input. The gate and its roles are described in
[docs/requirements_readiness.md](../../docs/requirements_readiness.md); the code is [flow/readiness.py](../../flow/readiness.py) and [agent/graph/readiness.py](../../agent/graph/readiness.py). Nothing here touched a board.

## Records

- [prereg_reviewer.md](prereg_reviewer.md): the pre-registration of the reviewer test (set, conditions, scoring, the pass line, power, threats), written before the first scored run, with one dated amendment for the post-hoc prompt.
- [reviewer_testset/results.csv](reviewer_testset/results.csv): one row per problem, condition and run (ids and our outputs only; the problem text, the reviewer's replies and the regex keys stay in a private folder).
  [reviewer_testset/scores.md](reviewer_testset/scores.md): the scores of [tools/reviewer_testset/score.py](../../tools/reviewer_testset/score.py) for each condition; the ids and groups are in [tools/reviewer_testset/ids.yaml](../../tools/reviewer_testset/ids.yaml).
- [prereg_arms.md](prereg_arms.md): the pre-registration of the arms on our own designs. [pilot_hidden_specs](pilot_hidden_specs/): the hidden full specs the oracle answers from and arm C appends (written for this brief by the executor, not owner-sourced, no test values).
- [arms/runs.csv](arms/runs.csv) and [arms/](arms/): one row and one record folder per arm run (summary, per-role usage, verification gates, the readiness record and the requirements report where the run had them); [gate_pilots/table.md](gate_pilots/table.md) and
  [gate_pilots/](gate_pilots/): the stage-0 gate on the six pilots (with the oracle) and on the three arm C documents (nobody to answer). [arms_setup_fault/](arms_setup_fault/) and [gate_pilots_setup_fault/](gate_pilots_setup_fault/): the first batch, invalid because of a flag (see below), kept as evidence.
- [flow/tests/fixtures/readiness/freqmeter](../../flow/tests/fixtures/readiness/freqmeter/spec.yaml): the frequency meter of research 228 section 8(e), reduced to a window of 8 cycles, with the recorded model replies (`replies.json`) that take it through the formal flow in CI.

## Result in six lines, nulls first

1. **The pre-registered v1 reviewer fails its own test.** On the 10 fact-missing positives it flagged 9 (90%, 95% interval 60% to 98%) and named the missing fact in 6 (60%, 31% to 83%); on the 23 negatives it left only 7 unflagged (30%, 16% to 51%), about 3.3 blocking questions per sound problem. Pass line was 70% named and 80% specificity: **fail**, on both.
2. **The knowledge-bank skill adds nothing measurable over the public topic list**: `fallback` (no skill) gives 9/10 flagged, 6/10 named, 8/23 negatives unflagged; `kb` (the skill) 9/10, 6/10, 7/23. The skill was written after the planner's brief and report 226 section 7 were read, so even this is an upper bound for a skill written blind.
3. **A calibrated v2 prompt (post hoc, exploratory, not confirmatory) halves the pointless questions**: 38 blocking questions on the negatives against 75 for v1, specificity 10/23 (43%, 26% to 63%), recall flagged unchanged (9/10), named 5/10. It still flags 13 of the 23 sound problems: a "sound" problem is one whose hidden test did not check an unstated fact, and nearly every request leaves some fact unstated, so a reviewer cannot be both useful and silent on them. On 49 unlabelled agentic problems v2 flagged 25 (a flag rate, not a score).
4. **Stage 0 does not converge reliably.** On the six pilots with an oracle answering from a hidden spec: 1 of 6 reached a frozen set in the final batch (p5) and 2 of 6 (p3, p5) in the batch before it, run with `--no-shell`; the others stopped at the 4-round limit or because the oracle could not answer a scenario question (it may only quote the hidden spec). Reader agreement per round moves between 46% and 100% and is not monotone: an answer can open a new ambiguity. On the three arm C documents, written to be complete, the gate (nobody answering) still raised 1, 8 and 2 questions: a document one author calls complete is not one two readers read alike.
5. **Build arms: 0 of 18 runs passed the stage-2 gate set in either arm** (A: the request, no user; C: the request plus every answer; 9 runs each, 3 designs, 3 repeats, 0/9 with a 95% interval of 0% to 30%). Arm B stopped at stage 0 in all 3 builds (the gate had not frozen p3). The failures are the flow's gates, not requirements: lint and design standards (9 runs), the independent spec-only bench judged wrong by triage after two repairs (7 runs), a simulation assertion (2 runs). **So the headline question, "can the agent reliably build from a very clear requirement?", is answered "no, not through this gate set on these designs", and the cause is in build and verify, not in requirements** (nothing reached a point where a requirement could be the cause). No board check was made.
6. A **setup fault** was found and fixed on the way: the first 21 arm runs used `--no-shell` and all failed at `check_constraints`; they are kept apart and not used. Two real bugs of the gate were found by live runs and fixed (the oracle needs a `default` on a question; an unreadable reader reply was counted as a disagreement).

## What was measured, in detail

### The reviewer test set ([reviewer_testset/scores.md](reviewer_testset/scores.md))

66 labelled problems (10 headline positives, 2 borderline, 6 test-reaches-into-implementation, 23 negatives; 25 undiagnosed candidates run and described only), 2 runs of the primary condition, 1 of the others, Sonnet 5.5 effort medium on the plan, Claude Code 2.1.321 pinned. Run-to-run: the same flag on 40 of 41 problems (`kb`) and 39 of 41 (`kb_v2`). Eight replies that were not valid JSON in the whole set (about 2% of calls) were logged privately, not scored and re-run.

| Condition (run 1) | Fact-missing recall, flagged | Named | Negatives not flagged | Blocking questions on negatives | Findings per problem |
|---|---|---|---|---|---|
| `kb` v1 (pre-registered, primary) | 9/10 | 6/10 | 7/23 (30%) | 75 | 6.2 |
| `fallback` v1 (no skill) | 9/10 | 6/10 | 8/23 (35%) | 70 | 5.5 |
| `kb_v2` (post hoc) | 9/10 | 5/10 | 10/23 (43%) | 38 | 2.0 |
| `fallback_v2` (post hoc) | 9/10 | 6/10 | 11/23 (48%) | 32 | 2.1 |

Scored apart: the borderline pair was flagged 2/2 in every condition (named 1/2); group C (the test reads names inside the implementation) was flagged 6/6 with v1 and 5/6 with v2 and "named" 3/6 to 4/6, which is the reviewer asking for internal names, not a finding about the test. Which positives were missed: `cvdp_agentic_DES_0003` is not flagged by any condition (a given file the hidden build does not compile cannot be seen from the text); `rc5_0001` and `sync_serial_communication_0001` are flagged but the fact is named only sometimes.
Intervals, power and threats are in [prereg_reviewer.md](prereg_reviewer.md): with 10 and 23 problems two reviewers closer than about 30 points cannot be told apart, so the rows above are descriptive. "Named" is a regex over the blocking findings against keys written before the run: a reviewer that names the fact in other words counts as flagged but not named.

### The gate on the pilot designs ([gate_pilots/table.md](gate_pilots/table.md))

`--interview oracle --oracle claude_code --readiness on --requirements loose --stop-after 0`, one run per design, reviewer v2, the oracle answering from the hidden specs of [pilot_hidden_specs](pilot_hidden_specs/) (written by the executor, not owner-sourced). In the final batch: p5 frozen after 3 rounds; p1 and p2 stopped at the 4-round limit; p3, p4 and p6 stopped because the oracle could not answer what remained (a probe disagreement about a scenario the hidden spec does not quote, or a gap). The batch before it (run with `--no-shell` and before the hidden specs named the modules; kept in `gate_pilots_setup_fault/`) froze p3 and p5. The model calls of the gate (reviewer, probes, readers, repairs, amender) were 9 to 20 per design; the Clarifier and the oracle calls are outside that count.
Mechanical repairs (compound rows split by the amender without a question to the user) were 6 to 10 rows per design: the Clarifier writes compound requirements that the brief 53 gate would also send back.

### The arms ([arms/runs.csv](arms/runs.csv))

Pre-registration: [prereg_arms.md](prereg_arms.md) with its amendment. Plan-cost estimate (not provider-reported): A $28.88, C $24.90, B $1.50 for the three stage-0 stops, $55.28 in all (the account's weekly meter went from 59% to 71% over the whole brief, shared with other sessions).

| Arm | Runs | Passed the gate set | Failure classes (code rule, stop reason and the spec-test state; checked by reading the stop detail of each) |
|---|---|---|---|
| A: request, no user | 9 | 0 | tool (lint, design standards, constraints) 3; testbench wrong (the independent bench judged wrong twice, never the design) 4; functional (a simulation assertion) 2 |
| B: gate with oracle, then build | 3 | 0 (none built) | requirement missing: the gate stopped at stage 0 in all 3 |
| C: request plus every answer | 9 | 0 | tool 6; testbench wrong 3 |

By design the picture is the same (p1_clkmeter, p2_bram_rom and p3_crc_engine all 0 of 3 in A and in C). "Passed" here means the end of stage 2 at V2 with the independent spec-only bench not failing; it is the project's gate set and not ground truth, and **there is no independent check of the built behaviour**: the pilots' host checks need a loaded board, and a simulation harness for them was not built. Hardware is pending.
What the arms can and cannot say: A and C fail the same way, so the missing requirements are not what stops these designs; 18 runs at 0 cannot show that a requirement never matters (a design that does reach the end would show it), only that the gates dominate here. The A against C comparison, the paired difference and the cross-table were therefore not computed (all zero). The 209 pilots reached a bitstream in 7 of 18 runs with the API harness and no spec-test; this brief's runs add the independent bench and use the Claude Code harness, so the two are not comparable.

### The English-to-formal step, one smoke measure

The frequency meter of research 228 section 8(e), reduced to N = 8, goes through `flow/sva_req.py` with real models (Sonnet 5.5 low as writer, Haiku 5.5 low as reader): 8 requirement rows, of which 4 proved with a reachable trigger (reset, next-cycle, same-cycle, handshake), 1 **vacuous** (the saturation row: a trigger that cannot happen at N = 8, the vacuity trap 228 predicted), 1 unusable (the cross-clock accuracy row: no clock relation is stated, so it is simulation-only), and 2 rejected by the code comparison although the property was right by hand (a window of exactly 8 cycles written as a chain of `$past` terms, flagged for numbers the requirement does not give; "valid stays low", flagged as a dropped negation). By hand all 7 properties said what the requirement says; the code comparison's false rejections, 2 of 7, are the finding. n = 7 hand-picked port-level rows written by the planner: this is **not** a re-measurement of the 0.46 published for FVEval NL2SVA-Human and says nothing about it. Brief 218 measured 3 of 38 candidate pilot rows carrying evidence because the requirements are stated at registers, not ports.

## Reproduce

```
python -m pytest -q flow/tests/test_227_readiness.py agent/tests/test_227_readiness_rounds.py tools/tests/test_227_reviewer_testset.py
python tools/reviewer_testset/score.py results/227_requirements_readiness/reviewer_testset/results.csv      # the tables of scores.md
python -m agent run <spec.md> --stop-after 0 --harness claude_code --interview oracle --oracle claude_code --hidden-spec <hidden.md> --readiness on --requirements loose
tools/requirements_arms/run_arm.sh <A|B|C> <design> <k>        # one arm run (needs the scratch folder named in its header)
python tools/requirements_arms/record.py --runs runs --out results/227_requirements_readiness/arms; python tools/requirements_arms/gate_table.py
```

The reviewer runs need the CVDP dataset (not redistributed here), a private folder for the replies and keys, the pinned Claude Code CLI and the knowledge bank skill: see the header of
[tools/reviewer_testset/run.py](../../tools/reviewer_testset/run.py). The arm runs are [tools/requirements_arms/run_arm.sh](../../tools/requirements_arms/run_arm.sh).

## Known gaps and limits

- **No independent check of built behaviour, no board.** The arms' pass criterion is the project's gate set, which the 215 cross-table shows is not a reliable proxy; the hardware column is pending and the owner's board visit is the first real check.
- **The arms cannot say how much of a failure is requirements**: nothing passed in either arm. The next step is to fix what blocks stage 2 on these designs (lint and design-standard findings in the generated top, a spec-test bench that triage judges wrong twice), then repeat A against C. B was not built because the gate froze none of p3 in its three attempts.
- **The hidden specs are the executor's, not the owner's**, and were written after reading the pilot requests; they were extended once (names of the top and core modules) before any of the final runs. Arm C's documents are not gate-clean (the gate raised 1, 8 and 2 questions on them).
- **One run per pilot design for the gate**; it is stochastic (p3 froze in one batch and not in the other). Two batches exist; the earlier ran with `--no-shell` and is kept in `gate_pilots_setup_fault/`.
- **The reviewer test has 10 headline positives**; the "named" decision is a regex written by the executor; the checklist skill and the keys were written after reading report 226 section 7; v2 was written after the v1 result and is not confirmed; the dataset is public; 8 of about 370 reviewer replies were not valid JSON and were re-run.
- **Not built**: a formal consistency check of the structured layer, realizability (advisory only, per research 228), and the owner's own pre-build questions in the knowledge-bank skill (the planner records them). The fixture's WaveDrom diagram for a requirement comes from `flow/sva_req.py` when a cover trace exists; no diagram was shown to a person.
- **The oracle may only quote**: scenario questions from the readers often have no quotable answer, which stops a benchmark run that a person would have continued.
- **Spend**: Claude Code on the plan, no API credit. One batch of 9 oracle answers (the first smoke run) went to the OpenRouter `luna` model through the default `oracle` purpose before `--oracle claude_code` was set; under a cent, recorded here for the spend ledger.
