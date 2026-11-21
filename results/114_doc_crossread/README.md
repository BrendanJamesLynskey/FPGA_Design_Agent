# Brief 114: blind document cross-read, pre-registered evaluation

This folder holds the evaluation of `flow/doc_crossread.py` ([docs/doc_crossread.md](../../docs/doc_crossread.md)), the check in which a reader model that sees only a vendor-document
excerpt writes the facts code depends on, and code compares them with the code. Brief 114 asked whether it would have caught the 96D five-word eye-scan driver, which was written from one
misreading of UG576 so that every test written beside it passed. The evaluation was pre-registered before any scored call ([PREREGISTRATION.md](PREREGISTRATION.md)): eleven cases
(three from the 96D history, four planted mistakes, four correct files), two reader models (Sonnet 5.5 and Haiku 5.5), three independent runs of each, 66 scored reader calls.

## Results

Plain headlines first, including what did not go as predicted. All tables, with every number from [results.json](results.json) / [results_v2.json](results_v2.json), are in [RESULTS.md](RESULTS.md).

- **The five-word driver is flagged.** On the 96D driver both models marked the code's missing addresses 0x0E7 to 0x0F5 in all 3 of 3 runs. Sonnet gave the word count (code has five, guide says ten) in 2 of 3 runs and Haiku in 3 of 3. In the one Sonnet run that gave no word count, the address rows still flagged it.
- **The ten-word driver agrees, with caveats.** No `disagree` row on the three mask attributes in 3 of 3 Sonnet runs and 1 of 3 Haiku runs. The two Haiku misses are the reader reading "ES_QUAL_MASK is 80 1s", a sentence of the guide's, as a number to hold against a ten-entry list: the guide says 80 there and 160 in its table for UltraScale+. Not a finding in the code.
- **The clock-phase condition is read by the reader and not found in the code.** All 6 runs (3 per model) listed the guide's sentence that wrong edge-scan results are remedied by asserting USE_PCS_CLK_PHASE_SEL and choosing ES_CLK_PHASE_SEL, and the comparison marked it `not_in_code`. The pre-registered prediction (at most 1 of 3) was wrong. It stands among 4 to 9 `not_in_code` rows in a Sonnet run, so the flag is only as useful as the reading of the report.
- **The four planted mistakes are all detected,** in 3 of 3 runs for each model and each mistake (swapped UART Lite offsets, a timer bit position, an ID reset value, an ID field width).
- **False positives on correct files, as pre-registered (frozen comparator):** of the 12 runs on the four correct files, Sonnet had a `disagree` row in 4 (f1 in 1 run, f4 in 3) and Haiku in 5 (f2 in 2, f3 in 3). **Every one of the 70 `disagree` rows on the correct files and the ten-word driver (Sonnet 14, Haiku 56) was a limit of the comparison or the reader, not a mistake in the code** (a bit range or an encoding judged against an address constant, a register's width against a field's, "80" against a list of ten). None of the four "correct" files turned out to be wrong.
- **Those false positives are removable and were removed after the fact.** Four rules added after reading the rows (listed as deviations in the pre-registration) take the same stored replies to 0 false-positive runs for Sonnet and, for Haiku, to the two h2 runs above; no detection changed. This is post-hoc and tuned on these rows: expect a few new kinds of false positive on other files.
- **Repeatability.** Detection of the four planted mistakes and the h1 addresses did not vary across runs. The h1 word count did for Sonnet (one run gave no word-count fact), and the facts a run lists vary a lot (median facts per run on the 96D excerpt: Sonnet 65 and 45, Haiku 118 and 140): silence is not agreement.
- **Cost.** Per reader call (medians per case), Sonnet took 8 to 65 s (the 12-page 96D excerpt: 65 s; a 3-page register map: about 25 s) and Haiku 16 to 182 s, because Haiku wrote about 3 to 7 times as many output tokens. The CLI's own plan-equivalent estimate was 0.02 to 0.21 USD a call for Sonnet and 0.002 to 0.03 for Haiku; the totals over 33 calls are in RESULTS.md. These are estimates, not charges (the Max plan bills nothing per call). Weekly usage read 48 % before the runs and 50 % after.
- **Reader validity.** Sonnet's quotations were found in the excerpt in all but 9 of 860 facts; Haiku's in all but 85 of 1 853 (one repair round used). The tool marks such facts and never trusts them.

### What it would and would not have caught in 96D

- **Would have caught:** the five-word driver, at the commit where it was written, from the guide alone, with a run of about a minute. The fake board and the cocotb stand-in were built from the same reading; the check does not run them, it reads the driver's own constants, so their agreement is irrelevant.
- **Would have shown, not caught:** the clock-phase requirement. It is a prose condition; the report lists it as stated by the guide and absent from the code. Someone has to read the line and decide it matters.
- **Would not have caught:** anything not stated in the excerpt given to it (the check cannot see a page nobody passed in); numbers inside function bodies, `case` tables or generated code; behaviour (timing, ordering, the 4T phase actually being right); a mistake the guide itself makes or contradicts (the 80-against-160 sentence above).

## Records

| File | What |
|---|---|
| [PREREGISTRATION.md](PREREGISTRATION.md) | cases, arms, scoring rules, predictions, stated limits, frozen hashes, deviations |
| [cases.json](cases.json), `cases/<case>/code/` | the case definitions (documents, pages, topics, targets) and the code files (the 96D drivers at the two commits, the register files, the four planted copies with `PLANTED.txt`) |
| `runs/<arm>/<case>_r<k>.json` | one scored call each (arm A = Sonnet 5.5, B = Haiku 5.5): the rows, the code facts' counts, usage, prompt hashes. A quotation is kept only on `disagree` rows |
| `runs/B/failed_before_fix__f4_zb_accel_r3.json` | the call that failed twice on the comparator exception (see the deviations) |
| `runs_v2/<arm>/...` | the same stored reader replies re-compared with the post-hoc rules |
| [results.json](results.json), [results_v2.json](results_v2.json), [RESULTS.md](RESULTS.md) | the pre-registered scoring of `runs/` and of `runs_v2/`, and every table |
| `score.py`, `rescore.py`, `run_eval.py`, `make_tables.py`, `build_cases.py` | the scoring rules, the post-hoc re-compare, the runner, the table writer, the case builder |

All reader facts, every quotation and every raw reply are in the private knowledge repository, `results_private/b114_doc_crossread/` (they hold excerpts of AMD documents: short quotations,
never the PDFs). The AMD PDFs are the owner's local copies and are not in any repository; each record keeps the excerpt's SHA-256 and the PDF's.

## Reproduce

No Vivado, no board, no heavy slot. Needs the private knowledge repository checked out (`FDA_PROMPTS_DIR=<knowledge>/prompts`), the owner's key file in `.env` (the agent's entry gate), the Claude Code token file, and the local PDFs under `_amd_docs/`.

```
python3 results/114_doc_crossread/build_cases.py                       # rebuild cases/ from git and the four planted edits
python3 results/114_doc_crossread/run_eval.py --arm A --priv-dir <knowledge>/results_private/b114_doc_crossread   # 33 live calls, about 5 minutes
python3 results/114_doc_crossread/run_eval.py --arm B --priv-dir <knowledge>/results_private/b114_doc_crossread   # 33 live calls, about 15 minutes
python3 results/114_doc_crossread/score.py                              # results.json
python3 results/114_doc_crossread/rescore.py --priv-dir <knowledge>/results_private/b114_doc_crossread \
  && python3 results/114_doc_crossread/score.py --runs results/114_doc_crossread/runs_v2 --out results/114_doc_crossread/results_v2.json
python3 results/114_doc_crossread/make_tables.py                        # RESULTS.md
python3 -m pytest flow/tests/test_114_doc_crossread.py                  # the no-model tests
```

A new live run will not reproduce `runs/` exactly: the reader is a model, and these runs are samples. `runs/` was produced by the comparator of the pre-registration commit; use that commit for it.

## Known gaps and limits

- Eleven cases, three runs each, one document family (AMD), one reader family (Claude): the figures are small-sample and say what happened, not a rate.
- Only the 96D cases are from history. The four planted mistakes are single-number edits of real files, the easy end of what a person makes; the four "correct" files were not hand-checked against the documents beforehand.
- The 96D code is Python with module-level tables, the best case for the code side. A register map written as `case` statements or constants inside functions is not read ([docs/doc_crossread.md](../../docs/doc_crossread.md)).
- The comparison is by name tokens. A document name the code spells differently shows as `not_in_code`; an address found only by value is marked and weaker.
- The post-hoc comparator rules were tuned on these runs.
- Haiku wrote far more facts and output tokens than Sonnet for the same excerpt; its per-call plan estimate is lower but its time is higher, and its false-positive rows were more numerous.
- No dollar figure exists: Claude Code on the subscription reports an estimate only. The model table (brief 108) can route the purpose to another endpoint; none was tried.
- The agent tool `doc_crossread` is registered but no stage or role is offered it; it was tested without a model call.

## Course impact

None for the course lessons; the 96D lesson (a model's test shares its misreading) already stands in the journal.
