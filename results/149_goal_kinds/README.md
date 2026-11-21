# Brief 149: goal kinds in the change classifier (review item F1)

`python -m agent resume <design> "<change>"` chose its entry stage by keywords; a request with no known word silently re-ran
from the interview (stage 0). Brief 149 adds goal classes and turns an unmatched request into a question.

Files: `PREREGISTRATION.md` (written before the change, with the null result), `labelled_requests.json` (74 requests, labels
fixed before the change), `measure.py` (no model call, no Vivado), `measure_before.json`, `measure_after.json`,
`measure_after2.json`.

## Result (entry-stage accuracy: the stage the classifier returns equals the label; a question is right only for a request
labelled "question")

| Run | all 74 | dev 50 | check 24 | silent stage 0 | questions returned |
|---|---|---|---|---|---|
| before (main at 2fdba7dd) | 16/74 (21.6 %) | 7/50 (14.0 %) | 9/24 (37.5 %) | 53 | 0 |
| after, first rules | 69/74 (93.2 %) | 47/50 (94.0 %) | 22/24 (91.7 %) | 0 | 8 |
| after, plus the docs-only rule | 70/74 (94.6 %) | 47/50 (94.0 %) | 23/24 (95.8 %) | 0 | 9 |

- The null result (no gain beyond 5 points) is rejected: 21.6 % to 94.6 % on all 74.
- The pre-registered pass is: check at least 80 %, zero silent stage-0 entries, and every request labelled "question" gets a
  question. The first two hold for both "after" rows; the third (9 of 9 questions) holds only for the second row (8 of 9 in the first).
- Second row: `fix the typo in the README` (a check item) reached the RTL class through the word "fix". The docs-only rule
  (docs words plus only the generic words fix or comment is a question suggesting `--kind docs`) was written after seeing
  that miss, so the check split is no longer untouched for that one item; the first-rules row is the clean number
  (22/24 on check).
- The before check split scores higher (37.5 %) than dev (14.0 %) only because the random split put
  more old-class requests in it.

## Still wrong after the change (4 of 74)
- R57 (check) "refactor the state machine, same behaviour": labelled rtl stage 2, got spec stage 0 (matched behaviour)
- R63 (dev) "the setup slack is negative, fix the closure": labelled timing stage 6, got rtl stage 2 (matched fix)
- R64 (dev) "add an ILA probe on the FIFO write pointer": labelled board stage 9, got rtl stage 2 (matched ila, probe, (a change verb: the RTL changes too))
- R65 (dev) "run the board test again after the change": labelled board stage 9, got rtl stage 2 (matched board test, (a change verb: the RTL changes too))

All four are rules that existed before brief 149 and are kept: the earliest match wins, so a behaviour word ("behaviour",
"interface") sends a latency or refactor request to stage 0 or 2; "fix" is an RTL word; a change verb ("add", "change")
under a board or timing word means the RTL changes too (`tests/test_68_document_resume.py`). They are conservative (an
earlier stage re-runs more), never a silent skip.

## What is a judgement
The entry stage per class (area 1, latency 1, retarget 1, fmax 3, power 3, language 2, mapping 2) is the executor's choice,
recorded in `PREREGISTRATION.md`; the accuracy measures agreement with those labels, not whether the stage is the best one for
a real design. The 74 requests are the executor's wording, not a sample of real users. No model, no Vivado, no cost.
