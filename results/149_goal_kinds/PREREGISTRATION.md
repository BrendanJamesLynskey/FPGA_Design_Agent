# Brief 149: pre-registration (written 2026-11-21 22:0x GMT, before the classifier changed)

Set: `labelled_requests.json`, 74 change requests, labels (kind, entry stage, or "question") written by the executor of brief 149
before any classifier change (the programme row asked for a different brief to write them; none was available, so the labels
were fixed first and are committed unchanged). 50 are `dev` (may be looked at while writing rules), 24 are `check` (random
split, seed 149; not to be used to tune). Entry-stage choices: area 1 (architecture resource budget), latency 1 (pipeline depth),
retarget 1 (device planning), fmax 3 and power 3 (constraints and the first Vivado build; closure can reopen RTL), language 2,
mapping 2, spec 0, arch 1, rtl 2, constraints 3, timing 6, board 9. Docs-only and vague requests: the right answer is a question
(docs-only is never guessed, `--kind docs`). These stage choices are the executor's judgement, not measured; the planner may change them.

Null result (stated before measuring): the goal classes do not improve entry-stage accuracy on this set (after <= before + 5
points on all 74), or they improve dev but not check. Expected before: only the requests that already hit an old keyword are
right (about 15 to 25 percent), and no request returns a question.

Measures: stage accuracy and kind accuracy (all, dev, check), silent stage-0 entries (stage 0 with no matched word), questions
returned. Pass: after-accuracy on `check` at least 80 percent, zero silent stage-0 entries, every request labelled "question"
returns a question. Rules are written once from the dev split and the J3 probes; the check split is run once after.
