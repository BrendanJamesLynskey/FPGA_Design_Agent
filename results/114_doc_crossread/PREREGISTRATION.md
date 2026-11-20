# Brief 114: pre-registration (written before any scored model call)

Date: 2026-11-20. Code under test and the frozen files are listed with their SHA-256 at the end; any change to them after the first scored run is a deviation and is
listed under "Deviations" below, with the reason.

## Question

Would a reader that sees only the vendor document, followed by a comparison done by code, have caught the 96D mistakes, and what does it cost and how often does
it cry wolf? Specifically: (1) the five-word eye-scan driver at its 96D commit against UG576; (2) the same check on the ten-word driver; (3) the clock-phase condition
that only the board revealed; (4) four planted register-map mistakes and four correct files in other designs.

## Cases (cases.json; code files in cases/<case>/code/)

| Case | Code | Document | Role |
|---|---|---|---|
| h1_96d_five_word | `flow/eyescan/hw.py` and `designs/b96_kr260_10g/model/eyescan.py` at commit 854cb409 (the 96D driver: five-word masks) | UG576 v1.7.1 pp. 226-234, 462-464, 503, 511 | history: must be flagged |
| h2_96d2_ten_word | the same two files at 253d73c6 (96D2: ten words) | the same excerpt | history: must agree |
| h3_clock_phase | the same files as h2 (before the 96D3 clock-phase fix) | the same excerpt; a different topic | history: report only; expected hard |
| p1_uartlite_stat_ctrl_swapped | `amd_ip_probe/tb/tb_uartlite.sv` with STAT and CTRL offsets swapped (planted) | PG142 pp. 9-11 | planted address mistake |
| p2_timer_load_bit | `amd_ip_probe/tb/tb_timer.sv` with LOAD = 0x40 for 0x20 (planted; collides with ENIT0) | PG079 pp. 14-17 | planted bit-position mistake |
| p3_zb_accel_id_reset | `zb_accel_regs.h` with the ID reset 0x64b30101 and VERSION reset 0x101 (planted) | the block's own generated datasheet `zb_accel_regs.md` | planted reset-value mistake |
| p4_zb_accel_version_width | `zb_accel_regs.h` with ID.VERSION width 8 and mask 0xff for 16 and 0xffff (planted) | the same datasheet | planted width mistake |
| f1_uartlite, f2_timer, f3_gpio | `tb_uartlite.sv`, `tb_timer.sv`, `tb_gpio.sv` as committed | PG142, PG079, PG144 (pp. 22-26) | correct: false-positive check |
| f4_zb_accel | `zb_accel_regs.h` as generated | `zb_accel_regs.md` | correct: false-positive check |

The planted files are single labelled edits of real files (cases/p*/code/PLANTED.txt): the mistakes are synthetic, not from history. Only h1 to h3 are real history.
The four correct register files are real but not hand-checked in advance against the documents: a `disagree` on one is adjudicated afterwards (below) and may turn out to be a true finding.
The documents are the owner's local copies under `_amd_docs/` (never committed); the record keeps each excerpt's SHA-256 and the PDF's SHA-256.
Topics and targets are in cases.json, written before the runs; they name no value, no code identifier and no error.

## Arms and repeats

- **A:** the `doc_crossread` purpose on `claude-sonnet-5-5`, effort medium, Claude Code on the subscription (the built-in default). **B:** the same with `claude-haiku-5-5`.
- Three repeats of every case in each arm (33 reader calls per arm); every call is independent (nothing cached across calls). One repair round is allowed inside a call
  (JSON not parsable, or more than a quarter of the quotations not found); a call that raises an infrastructure error is re-run once and both attempts are recorded.
- Run order: arm A in full, then arm B. `_handoff/usage_check.sh` before each arm; **stop at 90 % of the weekly all-models allowance** (it read 48 % on 2026-11-20 before the runs).
  Sonnet and Haiku only; no Fable or Opus.

## Scoring (by code, score.py; nothing is scored by a model)

A *row* is one document fact compared with the code. A row counts for detection only if its status is `disagree` **and its quotation was found in the excerpt** (`quote_ok`).

- **h1:** *word count flagged* = a `disagree` row of kind `word_count` for a subject containing QUALIFIER, QUAL_MASK or SDATA_MASK with document value 10. *Addresses flagged* = a
  `disagree` row of kind `address` for such a subject with a document address in 0x0E7..0x0F5. Each is scored on its own; the planted bug is "detected" when both are.
- **h2:** passes a run when no `disagree` row has such a subject (a false positive on the mask facts). Any `disagree` row at all is also counted and adjudicated.
- **h3:** *reported*, with no pass mark: does any row (any status) name USE_PCS_CLK_PHASE_SEL or ES_CLK_PHASE_SEL, and what status does it get. Expected: the reader may list it as a condition; the
  comparison says `not_in_code`, which is the flag that matters.
- **p1:** a `disagree` row of kind `address` for STAT, CTRL, STATUS or CONTROL. **p2:** a `disagree` row of kind `bit_range` for LOAD. **p3:** a `disagree` row of kind `reset_value` whose subject is ID.
  **p4:** a `disagree` row of kind `bit_range` or `width_bits` for ID.VERSION.
- **f1-f4 false positives:** the number of runs with at least one `disagree` row, and the number of such rows. Every such row is then read against the document by the executor and
  classed: *reader error* (the document does not say it), *comparison limit* (a name or a unit the comparison got wrong) or *true finding* (the code is wrong). Only the first two count as false positives.
- **Cost:** per reader call, from the CLI's own report: seconds, input tokens (uncached, cache-created, cache-read), output tokens, and the plan's cost estimate (not a dollar charge). Reported per case as medians.
- **Repeatability:** for each target, how many of the three runs detect it; a target is *stable* when all three agree. Also the share of facts whose quotation was found, the repairs used and facts per run.

## Predictions (for the record)

h1 flagged on both counts in at least 2 of 3 Sonnet runs; h2 with no mask false positive in at least 2 of 3; h3 reader mentions the clock-phase attribute in at most 1 of 3 (the topic is generic and the
document states it in one sentence); planted cases detected 3 of 3 when the reader lists the field at all; false-positive rows on correct files few but not zero (name matching is by tokens);
Haiku below Sonnet on quotation validity and detection. These are expectations, not pass marks. The "pass" the brief asks for is h1 flagged and h2 agreeing.

## What counts as a null

If h1 is flagged in fewer than 2 of 3 runs in both arms, the tool would not have caught the 96D bug reliably, and the report says so first.

## Stated limits (known before the runs)

Names are matched by tokens; constants inside function bodies and register maps written as `case` statements are not read; the h1 and h2 code are Python with module-level tables, the best case for the
code side; the planted mistakes are single-number edits of real files, which is the easy end of what a human makes; one document family (AMD) and one reader family (Claude) were tried.

## Frozen files (SHA-256 at the pre-registration commit)

- `flow/doc_crossread.py`: `d2e29424a6e490732b7a6bbb7cf039d819fd5532487b473b4e3c7571e3d66874`
- `results/114_doc_crossread/cases.json`: `bcb2c336bd6b4747c86a3783936e3d53468c873806e3a880c2fc704379d25c34`
- `results/114_doc_crossread/score.py`: `062b6ee13b8bda800ecea1df1a3ae5f1a2007e38afe007327fc38e82f538ee3c`
- `results/114_doc_crossread/run_eval.py`: `075c5613ab2922320c5ac7abf85e9471a5ade07d91efdba85d555f3ea7e82061`
- `results/114_doc_crossread/build_cases.py`: `8e58677ca5ee3436d268c50f69fddb9f1a70eb1c4df39ecf22085b6e0fe416c3`
- `agent/models/config.py`: `190956abf1a21efa68942718825d0d2f436d37a9be5e744550d635f6f3fc7028`
- `results/114_doc_crossread/cases/` (all files, in path order): `477e76741e397badc99b295e67d1755192c284ee930614dafea87195f3377cb6`
- private prompt `graph/doc_crossread/system` (knowledge repository commit c5d37ede): `39849fdea6851c68b57cbc6484d6dfa51dd282578308280247bb31ed1dd2a4e3`
- private prompt `graph/doc_crossread/user` (knowledge repository commit c5d37ede): `222a588489bd69b7822fd12b58bb36ef2f1933edd2f34e29b4f09b31c2f710ae`
- private prompt `graph/doc_crossread/repair` (knowledge repository commit c5d37ede): `c5de7b5659596e3b49e746badb81f31d85cf3ba8bec0d5ff020cd4161f53f400`

## Deviations after the first scored run

(none yet)
