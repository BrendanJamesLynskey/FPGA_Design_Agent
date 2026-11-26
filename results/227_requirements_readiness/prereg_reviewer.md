# Brief 227: pre-registration of the reviewer test (written before any reviewer run)

Stamped 2026-11-26 14:31 GMT (`date`), executor Sonnet 5.5. Owner decision (2026-11-25): CVDP is **not** an evaluation of FPGA Force; it is a labelled test set for the
requirements reviewer, and the reviewer passes if it flags the deficient problems and names the missing fact and does not flag the sound ones.

## Question

Does the requirements reviewer (`agent/graph/readiness.py`, `REVIEWER_SYSTEM`, Sonnet 5.5, effort medium, the Claude Code CLI on the plan) flag, from a request alone, the CVDP problems
whose hidden tests check a fact the problem never gives, name that fact, and leave the sound problems unflagged?

## Set (ids in `tools/reviewer_testset/ids.yaml`; labels from `reports/226_cvdp_lessons_report.md` section 7)

- Positives, **fact missing** (headline): group A (7) and D (3 of 4; `cvdp_agentic_binary_search_tree_algorithms_0014` is in both D and E in report 226 and is counted on neither side) = **10**.
- Positives, borderline (B, 2) and test-reaches-into-implementation (C, 6): **reported apart**, not in the headline. C scores the reviewer on a defect of the test, which no requirement could name.
- Negatives: E hard (2) and F easy (21) = **23**.
- Candidates G (25 held-out, never solved, undiagnosed): the reviewer is run on them and the flags are **described, never scored**.
- The correction of report 226: the two empty-file passes (`cvdp_copilot_scrambler_0018`, `cvdp_copilot_elevator_control_0033`) come from brief 215's null control, not the CVDP project's records; they are not in this set.

## What the reviewer is given

The problem text as the builder gets it (prompt, the files given with their contents cut to 15,000 characters each and 60,000 in all, the files to produce) and the checklist. **Never** the hidden tests, the
harness or any counterfactual. Same system prompt as the product's reviewer. No requirement rows (the request is the whole of the spec), no interface table, no compliance assessment.

## Conditions and repeats

1. `kb`: the checklist is the knowledge-bank skill `procedures/requirements-review/pre-build-review` (KB PR #108, branch b227-requirements-review). **Primary.** 2 runs per problem (all 66 problems; G once).
2. `fallback`: the public topic list (`FALLBACK_CHECKLIST`), 1 run per problem (A to F). A control for what the bank skill adds.
Run 1 of each problem is the pre-registered primary result; run 2 is used for run-to-run agreement only.

## Scoring (code only; no model produces a score)

- `flagged` = the reviewer's verdict is `not_ready`, which the code sets if and only if at least one finding is blocking (the model's own verdict word is ignored).
- `named` = at least one regex of the private key file matches the text (missing fact + question) of a blocking finding. The keys were written from report 226 section 7 before the run;
  file `labels_private.yaml`, SHA-256 `c1c6a204cd3f8a76adafc001255f2b72db4ef509dd5c2025438064c5a60e28c8` (private, not in git). A regex is a blunt measure of naming: a reviewer that names the fact in other words counts as
  flagged but not named; the flagged column is always shown beside it.
- Recall (flagged) and recall named on the headline positives; specificity on the negatives (all, hard, easy); precision at this set's own prevalence (stated); 95 % Wilson intervals; the two trivial reviewers
  (flag everything, flag nothing) for context; blocking questions that changed nothing (blocking findings on negatives, and on positives without the fact named).
- **Pass line** (set before the run): recall named >= 70 % on the headline positives **and** specificity >= 80 % on the negatives, as point estimates. With n = 10 and n = 23 the intervals are wide
  (10 of 10 has a lower bound of 72 %; 7 of 10, 40 %; 23 of 23, 86 %; 18 of 23, 58 %), so the report says "passes", "fails" or "cannot say" from the intervals as well: it **cannot say** when the point
  estimate passes and the interval's lower bound is under 50 %.

## Power (stated in advance)

Ten positives and twenty-three negatives cannot tell two reviewers apart that differ by less than about 30 points; the test answers whether the reviewer is useful at all (clearly above flag-nothing and
flag-everything), not which prompt is better. The `kb` against `fallback` difference is reported descriptively (paired by problem), not as a significant effect.

## Known threats (stated now)

- **Contamination of the skill.** The checklist skill was written after the planner's brief and report 226 section 7 were read; its items 9 (defaults) and 10 (names, files, build target) are general practice but
  overlap the kinds of fact in group A and D. The `fallback` condition (which has no such items) shows how much the skill adds; the `kb` recall is an upper bound for a skill written blind.
  The skill was **not** seeded from problem text, and no problem was opened before the skill and the keys were written.
- **Public dataset**: the model may have seen CVDP. A reviewer that flags a problem from memory of the benchmark rather than from the text cannot be told from one that reads it.
- **Labels are from counterfactual re-runs of one agent family**: a "sound" problem is one that was always solved, not proven unambiguous; a fact missing from a problem that no test checks is not a deficiency here.
- **Sampling**: one model, one prompt, medium effort, 2 runs; the problems are not a random sample.

## Run discipline

Claude Code 2.1.321 pinned (`_scratch_227/bin/claude`, SHA-256 `426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f`, first on PATH), `DISABLE_AUTOUPDATER=1` set in `~/.claude/settings.json`; version checked before each launch;
3 calls at a time; a failed call (plan limit, timeout, reply that is not JSON) is logged privately, **not scored**, and re-run. Weekly usage is read at the start and about every 30 minutes; stop at 92 % (owner plan 2026-11-26).
Problem text and replies stay in `_handoff/fpga_agent/227_private/`; only ids and our outputs are committed.
