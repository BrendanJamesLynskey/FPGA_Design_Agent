# Pre-registration: the design-review benchmark (brief 84, phase 1)

Written and committed on 2026-11-16, before any held-out review was run. It follows `docs` rules of the project
(`agent_learning_strategy.md` sections 1 to 4 and 6, and the eval run checklist). The hashes that pin everything it names
are in `freeze.json`, made by `benchmark/review/freeze.py` at the commit that carries this file.

## Question

Given a design the agent did not write, how many of its planted problems does the review mode find, how many false alarms does
it raise, and what does the judgement layer add over the check suite alone?

## Materials

- **Benchmark:** 20 small SystemVerilog designs in the private knowledge-bank repo (`benchmark_private/review84/`), written in
  our own code. Each design has its own testbench, which passes. 16 contain planted problems (18 in all) and 4 are clean controls.
  Classes: clock-domain crossing; asynchronous reset in a datapath; protocol violation (data not held while stalled); off-by-one in
  a counter; missing clock constraint; undocumented interface behaviour; test gap; a functional defect (writes while full);
  missing back-pressure; overflow without saturation; state with no reset; a parameter limit that breaks silently; and the four
  verification-environment classes (a comparison that passes on X, a racy cycle counter, a DUT input driven on the clock edge it
  is sampled, a driver and probe that misread latency by one). Ground truth, authoring copies and probes stay private.
- **Splits, drawn by family** (`agent_learning_strategy.md` 12 and 12b): development = 4 designs (one cdc, one counter, one
  verification-environment defect with a second defect in the DUT, one control); held out = the other 16 (14 planted issues in 13
  designs, 3 controls). The leak guard (`benchmark/tools/task_leak.py`, frac 0.3) found 0 hits between development and held-out in
  both directions (`leak_guard.txt`). Within the held-out set it found two families (the four latency-bench designs; two
  arithmetic designs); each family is held out as a unit.
- **Prompt tuning** used the development split only, two rounds (versions 1 and 2, both recorded in the private results). The
  reviewer's system prompt is frozen at version 2; its hash is in `freeze.json`. The prompt holds a general review checklist,
  including the four verification-environment classes by name. That is the checklist a reviewer would use, written from the
  brief and general knowledge, not from any benchmark design; it also means recall on those four classes tests whether the
  reviewer applies a checklist it has been given, not whether it would think of them unprompted.
- **Arms:** (A) baseline: the check suite alone at RTL scope (`python -m agent review --no-judge`; lint with Verilator 5.048, the
  design-standards check, the reset elaboration with Yosys and slang, the AXI rules; the CDC report, methodology, DRC and timing
  checks need a synthesised design and do not run at this scope). Deterministic, so one run per design. (B) agent: the same suite
  plus the judgement layer, one reviewer call: `claude-sonnet-5-5` through Claude Code 2.1.321 (binary copied and hashed; auto-update
  off), effort medium, no tools, no web. k = 3 repeats per design.
- **Real designs** (not scored): the five 63D network blocks in `ip_lib` on `main`, one review each, with an independent
  usefulness rating (below). Never the 88 branch.

## Measures (all by code, `benchmark/review/score.py`; no model produces a score)

Matching rule: in the scorer's docstring, hashed in `freeze.json`. In short: a reviewer's finding found an issue when its category is
accepted by the issue and its place is inside the issue's region (a region is the whole statement or block that holds the defect,
fixed from the authoring markers before any held-out run; two lines of tolerance); a whole-file issue also needs one of its
keywords; a check's finding counts only through the tool signals listed for that issue. One finding per issue. Info findings are
ignored. Minor style or documentation findings that match nothing are advisory, not false alarms. Everything else unmatched is a
false alarm, counted strictly.

- **Recall** per class and overall = issues found / (issues x repeats); also found in at least one and in all three repeats. Wilson
  intervals per class; a bootstrap over designs (2000 resamples, seed 84) for the overall figure.
- **Precision** = found / (found + false alarms). **Control false alarms** per control review.
- **Severity accuracy**: exact, and within one level, among found issues.
- **Cost** is what the provider reported: tokens (input, cache, output) and wall seconds per review, and the total. The plan reports
  no price; none is invented.
- **Paired comparison** agent against baseline on the same designs: per-design recall difference, mean and design-level bootstrap interval.

## Expectations (stated before the run, not decision thresholds)

- The baseline finds little: the asynchronous reset and a lint width warning, near nothing else, because most planted problems
  are about meaning or about the testbench, and the checks that see clock crossings need a synthesised design.
- The agent finds most design defects and some of the verification-environment ones; its precision is the open question. Precision
  below 0.5 would mean the review costs the reader more time than it saves; that is reported as it falls.
- Power: 13 designs with planted issues and 3 repeats. Differences in overall recall below about 0.25 cannot be told from noise; a
  per-class figure rests on one or two designs and is a detection table, not a rate.

## Rules for the run

- No change to the prompt, the scorer, the truth regions, or the pipeline after the first held-out review is launched. A bug in the
  measuring instrument found later is fixed with a dated amendment (`AMENDMENTS.md` in this folder), the old numbers kept and
  labelled.
- Pace: three reviews at a time, each its own `claude -p` call; scoring one arm at a time after all runs of that arm are in.
- A slot with no usable result (error, timeout, a reply that is not JSON) is re-launched once. If it still has none it stays NOT RUN
  and counts as missed in the denominator (`--drop-missing` is never used for a headline).
- After scoring, unmatched findings at major or critical on the agent arm are read in code (not by a model) and each is judged real
  or not by the executor from the design text; real unplanted defects are listed in `adjudication.md` and reported separately. They
  never change recall or precision above.
- Usage: the weekly figure is read before each launch; stop at 88 percent.

## Secondary tests

1. **Improvement-request plans** (restate, assess, order; plan only): 7 requests with known outcomes in the private benchmark, 3
   repeats. A plan is sound for a request when all its code checks pass: measurable or one question as expected; an acceptance test
   when measurable; a dependency on the review finding that matches the named planted issue, and that finding ordered before the
   request; the entry stage set. Reported as sound / not sound per request with Wilson intervals. Carrying the plans out, and the
   comparison with "just do it", are phase 2.
2. **Independent usefulness rating** (a human-check substitute): one Sonnet sub-agent with written criteria rates a sample of reviews
   (findings real, important, actionable; what a senior engineer would have raised). Its ratings are reported as its ratings, apart
   from the scores above.
3. **Correctness review of the scorer** by a second Sonnet sub-agent, with one fix round; done before the held-out run.

## Harness review and fix round (done before the held-out run)

An independent Sonnet reviewer read the scorer, runner and pipeline and probed the scorer against the real truth. Findings acted on:
- false credit from wide regions plus category-only matching: every issue now carries keyword groups (a finding must contain all words of
  one group); ranges over 10 lines count only their first line; category lists widened where a sensible label was refused;
- a stale kept review (design hash or prompt version differing from the manifest or frozen prompt) is NOT RUN;
- the scorer lists which checks did not run per review; Wilson intervals are labelled per-run (repeats of a design are not independent;
  the design-level bootstrap is the headline interval); `precision_incl_advisory_as_false` is reported beside precision.
Not changed, disclosed: the reviewer's prompt carries a general checklist that names the four verification-environment classes and most
design classes, so held-out recall measures checklist following on this taxonomy, not discovery of unknown kinds of defect (reported
as "checklist-aware"). The fixes were not re-reviewed (unreviewed after fixes, practice 2.1).
