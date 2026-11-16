# Design review benchmark: results (brief 84, phase 1)

Pre-registered in [prereg.md](prereg.md); pinned by [freeze.json](freeze.json). Held-out split: 16 designs (13 with planted issues, 14 issues; 3 controls). Raw reviews and the truth are in the private knowledge-bank repo; their hashes are in `private_records.sha256`. Everything below is read from `score_*_heldout.json` and `plan_scores.json`.

## Headline

| | Baseline (check suite alone) | Agent (suite plus reviewer) |
|---|---|---|
| Reviews | 16 (one per design) | 48 (3 per design) |
| Recall (issues found / issue-reviews) | 2/14 = 0.143 | 42/42 = 1.0 |
| Recall, bootstrap 95% over designs | [0.0, 0.385] | [1.0, 1.0] |
| False alarms | 3 | 146 |
| Precision (found / (found + false alarms)) | 0.4 | 0.223 |
| Precision counting advisory as false | 0.333 | 0.191 |
| False alarms on controls | 1 in 3 reviews | 36 in 9 reviews |
| Severity exact / within one | 0.5 / 1.0 | 0.643 / 1.0 |
| Tokens (provider-reported), total | 0 | 375676 over 48 reviews |
| Output tokens, total | 0 | 164609 |
| Wall seconds, total | 7.4 | 1259.6 |

Not run (agent): 0. Not run (baseline): 0. One agent slot gave an unusable reply and was re-launched once, as pre-registered.

Dollar cost is not reported: the plan reports none.

## Recall by class (agent / baseline)

| Class | Agent found / issue-reviews | Found in any / all 3 repeats | Baseline |
|---|---|---|---|
| async_reset_datapath | 3/3 | 1 / 1 (of 1) | 1/1 |
| cdc | 3/3 | 1 / 1 (of 1) | 0/1 |
| functional_defect | 3/3 | 1 / 1 (of 1) | 0/1 |
| missing_backpressure | 3/3 | 1 / 1 (of 1) | 0/1 |
| missing_constraint | 3/3 | 1 / 1 (of 1) | 0/1 |
| overflow_saturation | 3/3 | 1 / 1 (of 1) | 0/1 |
| protocol_violation | 3/3 | 1 / 1 (of 1) | 0/1 |
| scalability_limit | 3/3 | 1 / 1 (of 1) | 1/1 |
| state_not_reset | 3/3 | 1 / 1 (of 1) | 0/1 |
| tb_probe_race | 3/3 | 1 / 1 (of 1) | 0/1 |
| tb_racy_counter | 3/3 | 1 / 1 (of 1) | 0/1 |
| tb_same_edge_drive | 3/3 | 1 / 1 (of 1) | 0/1 |
| test_gap | 3/3 | 1 / 1 (of 1) | 0/1 |
| undocumented_hole | 3/3 | 1 / 1 (of 1) | 0/1 |

Groups: verification_environment_defects: agent 9/9, baseline 0/3; design_defects: agent 33/33, baseline 2/11.

Each class rests on one or two designs, so this is a detection table, not a rate. The reviewer's prompt carries a general checklist that names the four verification-environment classes and most design classes (checklist-aware, see prereg.md).

## Improvement-request plans (plan only)

Sound plans: 8 of 21 (0.381). Per request: P1 1/3; P2 0/3; P3 0/3; P4 3/3; P5 2/3; P6 0/3; P7 2/3.
The failures were of two kinds: runs with no usable plan, and requests the reviewer judged unmeasurable (or measurable) where the benchmark expected the opposite. The expected labels were the executor's, not fixed by any authority.

Other records: [usefulness_rating.md](usefulness_rating.md), [adjudication.md](adjudication.md), [leak_guard.txt](leak_guard.txt), [real/](real) (reviews of five of our own network blocks; the "produced by review" handovers were not committed), [AMENDMENTS.md](AMENDMENTS.md).

## Records

`prereg.md`, `freeze.json`, `preflight_agent_heldout.json` (pins); `score_agent_heldout.json`, `score_baseline_heldout.json`, `plan_scores.json` (scores); `private_records.sha256` (hashes of the raw reviews, kept in the private repo); `leak_guard.txt`; `usefulness_rating.md`; `adjudication.md`; `real/` (reviews of five of our own blocks).

## Reproduce

Needs the private benchmark (`FPGA_Design_Agent_Knowledge`, branch `b84-review`, `benchmark_private/review84`), Verilator 5.048, the OSS CAD suite, and Claude Code 2.1.321 on the plan. `python3 benchmark/review/run_bench.py --bench <review84> --arm agent --split heldout --k 3 --out <dir> --claude-bin <pinned>`, then `python3 benchmark/review/score.py --truth <review84> --reviews <dir> --arm agent --split heldout --k 3 --out results/84_review`. Reviews differ run to run; the committed scores are of the recorded run.

## Known gaps and limits

RTL scope only (no synthesis, simulation, coverage or mutation run); checklist-aware recall; each class rests on one or two designs; seven plan cases with executor-set labels; the scorer fixes after the harness review were not re-reviewed; one control bench was not perfectly clean (adjudication.md); the reviewer sees only the design directory, not files its proofs include.
