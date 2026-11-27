# Brief 214 report: cost routing by stage, escalation, and k-way attempts

Executor: Sonnet 5.5, 2026-11-26 to 2026-11-27 (stamped from `date`; report 2026-11-27 03:58:30 GMT). Branch b214-cost-routing (PR open, not merged). Records: `results/214_cost_routing/`
(prereg.md, order.tsv, runs/, mechanism.md, ab_runs.csv, paired_analysis.txt, env_faults/). Code: `agent/models/routing.py`, hooks in `agent/graph/run.py`, flags `--routing on` and `--kway K` (off by default), docs in `docs/role_models.md`.

## Nulls first
**No detectable effect on any graded outcome** (13 of the planned 18 runs; 3 or 4 pairs per comparison; ceiling in the pre-registration: only a gain of about 3 stage-2 visits or more could show).
The one stable signal is a cost one, and it points the wrong way for k-way: routing plus k = 3 cost more and took longer per run than control on the same design and replicate. **Defaults stay off.**
Escalation did **not** fire in the stage-1 visit-limit loops that 213 identified (2 of 7 routing-arm runs ended there with 0 escalated calls), so whether escalation breaks *those* loops is **not answered**; why is below.

## Done
1. **Routing table with escalation** (`ROUTING_TABLE`, tiers cheap = haiku-5-5 low, standard = today's model, strong = opus-5-5 medium, claude_code only). Default unchanged (`--routing off`). With `on`: a lint or design-standards-only repair of the Designer at stage 2 goes to cheap; after the same failure began two visits of a stage, the next visit goes to strong. Recorded per call (`role_usage.jsonl` `routing`: tier, reason, kind, streak, escalated, base model) and as `route` events. Opus is only the strong tier on `claude_code` (the Max plan); the API kind and OpenRouter are not routed (recorded as skipped).
2. **k-way attempts** (`--kway K`, off by default): at the third stage-2 visit (after two failed ones), once per run, K attempts each from the same snapshot of the design (restored before every attempt; run one after another, so isolation is by restore, not by parallel sandboxes), each evaluated by the stage-2 gates; the kept one is chosen by independent verdict, then gates passed, findings, LUTs, candidate number. Every candidate is in `kway.jsonl` with the `own_gates_only` label.
3. **Tests**: `agent/tests/test_214_cost_routing.py`, 19 tests (table applied, escalation trigger and reset, candidate selection and tie order, snapshot isolation, cost and tier recorded in role_usage and summary, flags and config round trip, k-way trigger once per run).
4. **Analysis**: reused `tools/ab/` (213's copy of CVDP's ablate/table plus the paired bootstrap) through `adapter.py`; `results/214_cost_routing/analyse.py` builds the manifest and `mechanism.md`.

## The measurement (pre-registered `prereg.md`, written before run 1)
Three pilot designs that sometimes pass (213's control passed 4 of 9), 3 arms, Sonnet 5.5 medium baseline on Claude Code 2.1.321 (plan estimate cost, no API spend), stages 0 to 2, V2. Run order a seeded shuffle (`order.tsv`).
**Deviations, all because of the machine and the plan:** (a) 13 of 18 runs were completed (runs 1 to 12 and 14; run 13 and 15 to 18 not run): the heavy slots were held by other sessions for hours at a time and weekly usage went 73% to 83%; the cap was set in `run_one.sh` (`FDA_LAST_RUN`) after the order was frozen, and run 14 had already started. Arms are unbalanced (control 6, routing 3, routing_kway 4). (b) The brief's "3 of the 11 development tasks" and the 209 failed designs were not used (reasons in the pre-registration). (c) Two runs (1 and 4) died on 2026-11-26 at about 23:27 GMT when the planner deleted the knowledge checkout `230-kb-pin`; they were **environment faults, not scored, and re-run** on `kb-prompts-pin` (same commit 5e2eab87); logs in `env_faults/`.

| arm | runs | own stage-2 pass | plan USD total | USD per run | USD per passed design |
|---|---|---|---|---|---|
| control | 6 | 4 | 14.83 | 2.47 | 3.71 |
| routing | 3 | 2 | 8.21 | 2.74 | 4.11 |
| routing_kway | 4 | 3 | 13.04 | 3.26 | 4.35 |

Own-check verdicts only (no independent check exists before the board visit); `stage 1 visit limit` stops (control 2, routing 1, routing_kway 1) are non-passes scored 7 visits.

Paired on (design, replicate), 95% bootstrap (`paired_analysis.txt`):
- stage-2 visits to pass, routing vs control: +0.33 (-2.00 to +3.00), n = 3 pairs; routing_kway vs control: -0.25 (-3.00 to +2.25), n = 4. No detectable effect.
- plan cost per run, routing vs control: -0.09 (-0.40 to +0.12), n = 3; routing_kway: +1.09 (-0.06 to +2.50), n = 4. No detectable effect.
- wall time, routing vs control: -203 s (-491 to -41), n = 3 (3 of 3 faster, sign test p = 0.25); routing_kway: +304 s (+30 to +466), n = 4 (3 of 4 slower, p = 0.62). Intervals exclude 0 on tiny n; exploratory, not a finding.

## Mechanism (the main evidence; `mechanism.md`)
- **Cheap tier** fired in 4 routing-arm runs (1, 2, 7, 12; one lint repair each on haiku-5-5 low, about 0.01 USD per call). In all 4 the stage-2 failure was still there at the next visit (each needed a third stage-2 visit), so the cheap visit did not clear the lint finding; it saved cents and bought no repair. At this sample, **cheap-for-lint-repair is not supported** (n = 4, no matched cheap-vs-standard control on the same failure).
- **Escalation to strong** fired in 4 of 7 routing-arm runs (runs 2, 4, 7, 12; 1 to 5 strong calls). Runs 2, 7 and 12 passed stage 2 on the escalated visit (lint repairs; 3 of 3), run 4 (the p1 design) needed two strong visits (a simulation repair) and passed on visit 5. Strong calls cost about 0.4 USD each at plan estimate against about 0.2 for Sonnet. Without a control that was cheap-first-then-standard these runs do not say how much of the fix was the strong model and how much was a second look; n = 4.
- **Escalation did not fire in the stage-1 loops.** Runs 8 and 14 (routing arms) ended on the stage-1 visit limit with 0 escalated calls: stage-2 lint, simulate and design-standards failures route back to stage 1, and the per-stage failure signature (the gate text with numbers removed) differed on each stage-1 entry (streak 1 on visits 2, 3 and 4), so it never reached 2 before the visit limit (4). Run 14's own stop message says "the same failure on 2 consecutive visits". The signature must use the failing gate names (as stage 2's `sig` does), not the text. This is a bug in this brief's trigger for bounced stages, found after the runs; not fixed here to keep the code frozen to the pre-registration. Two of the three stage-1-limit runs in the control arm (3 and 5) are the same loop class; 213's repeated-lint loops (213 runs 2, 4, 15) are therefore still untested against escalation.
- **k-way** ran in 3 of 4 routing_kway runs (runs 1, 2, 4; run 8 ended in the stage-1 loop before the third stage-2 visit). Candidates: run 1 9/9, 7/9, 9/9 gates (candidate 3 kept: fewer LUTs than 1), run 2 9/9 three times (candidate 1 kept by number), run 4 6/9 with 5 findings three times (candidate 1 kept; the loop was not broken by three strong attempts; passed on a later visit). **Every selection was own-gates-only** (no independent check applies to these benches), the candidates differed in gates in 1 of 3 rounds, and the k-way round added about 0.5 to 1.0 USD of plan cost per round (run 4 0.51, run 2 0.83, run 1 0.97). 226's warning holds: where all candidates look equal to the Designer's own gates, selection is arbitrary.
- No plan, rate or slot stop was scored as a failure; slot waits (up to hours) are not in wall time.

## Recommendation (from the numbers, with the ceiling stated)
- Keep `--routing` and `--kway` **off by default.** Nothing here supports changing the defaults: no outcome moved detectably, k-way costs more, cheap-for-lint did not repair.
- Worth another look: **escalation only** (no cheap tier), after fixing the trigger for bounced stages, on the loops of 213 (runs 2, 4, 15) and on the 12 packages of brief 227; **k-way only** once an independent selector exists for the benches (the regrade needs `step(inputs)` benches, brief 213's follow-up).

## How it was verified
- `pytest agent/tests/test_214_cost_routing.py`: 19 passed. Related suites (05f, 82p6, 05c2, 05g, claude_code_arm, 213, 234, 07a2 fix 4): 150 passed, 1 skipped. `test_99_prompts`: 30 passed against the KB at the pin. doccheck and CI: see the hand-back.
- Live: the mechanism was seen end to end in runs 1, 2, 4 (k-way) and 2, 4, 7, 12 (escalation, cheap tier).

## What is illustrative
13 runs on 3 small designs, own verdicts, unbalanced arms: it shows the mechanism works and what it costs, not a rate.

## Known gaps
- Escalation trigger in bounced stages (above). k-way attempts are sequential, restored from a snapshot, not parallel sandboxes. Escalation counts are in memory (a resume restarts them). The DOC step is not routed by this table (set the `doc` purpose in models.yaml). Only the `claude_code` kind is routed.
- 5 of 18 runs not run; no `anthropic_api` cost was measured (plan estimates only). The brief's 25 USD API cap was not touched.

## Gotchas
- A driver's `kill` of the parent leaves the while-loop subshell running; stop both PIDs. An access key is needed in the worktree's `.env` for agent runs (copied by the house-rule command, deleted at the end).
- A run that fails before a record exists must stop the series, not continue to the next run (the first driver did not, and was fixed).

## Follow-ups for the planner
1. Fix the bounced-stage failure signature (gate names) and re-test escalation on the 213 lint loops; brief 234's visit counting is the same area.
2. Decide whether to spend more on routing at all: the cheap tier gave nothing; strong-after-two looks the only promising piece.
3. Briefs 217 and 239 also touch stage-2 routing; this change is flag-gated in `node_work`/`run_subagent` and rebased on main at the final push.

## Course impact
None.
