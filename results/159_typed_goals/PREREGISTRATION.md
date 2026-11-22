# Brief 159: pre-registration (written 2026-11-22 03:3x GMT, before any goal code was written)

Set: `labelled_changes.json`, ten scripted goal changes on three committed designs that have a handover:
`t1_dimmer_counter` (5), `b58a_trigger` (3), `b96_kr260_10g` (2). The brief asked for "t1, one library entry, b96 subset": library
entries (`ip_lib/*`) have no handover and `resume` refuses them, so `b58a_trigger` (which carries latency measurements) stands in.

Each change has a label `required`, written here from the committed measurements (the handover `measurements:` lists) and
the entry-stage table of brief 149, not from the planner that will be built:

- `"met"`: the committed, fresh measurement already satisfies the new bound. The right plan re-runs nothing for the goal.
- an integer N: the measured value fails the bound (or the change is a clock, power or device change the committed build cannot show),
  and the earliest stage whose evidence goes stale is N (area and latency 1, fmax 3, power 3, retarget inside one device
  family 3, retarget across families 1). These stage numbers are the executor's judgement (as in 149), not measured.

Arms compared (all dry runs, no model call, no Vivado, no spend):

- full re-run: every change enters at stage 0 (10 stages, one build);
- F1: the entry stage of brief 149's `classify_change` on the goal text (the code on origin/b149-goal-kinds);
- F5: the `agent revise` plan.

Measures: stages re-run (sum over the ten), builds (one when the entry is at or before stage 3), plans that keep stale evidence
("unsound": entry later than `required`, or a `met` label where the evidence does not meet the bound), plans equal to the label
(exact). The hidden-bench pass rate of the resulting designs is NOT measured: it needs a model run and Vivado, which this brief
may not spend. The stand-in is soundness: a plan never keeps evidence that the change made stale, so a re-run from the plan's entry
sees every gate a full re-run would.

Null result (stated before measuring): F5 re-runs no fewer stages than F1 on these ten (F5 total within 5 percent of F1's), or F5
has any unsound plan. Expectation: F5 equals F1 on the six "not met" changes except where a retarget stays in one family, and saves
the full entry cost on the three "met" changes (C01, C06, C09); F1 and a full re-run have no way to say "already met".
Pass: F5 unsound 0 of 10, F5 total stages re-run at least 15 percent below F1's, and every plan equal to its label.

Parked judgement calls that could be wrong: the retarget-in-family stage 3 (nothing ran to confirm that RTL survives a package
change), and the use of one measured build as evidence for a bound (a different seed or tool version can move a LUT count).
