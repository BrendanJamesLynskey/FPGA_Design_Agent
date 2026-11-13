# results/course: run records of the course tasks

This folder holds the run records of the FPGA Design Agent on the development tasks of the course tier (`benchmark/course/tasks`),
written during briefs 07a1 and 07a2 and given their escape-rate fields by brief 08a. Each record is one agent run on one task;
`IMPROVEMENTS.md` is the log of the harness fixes each failing run led to.

## Records

| Path | What |
|---|---|
| `<task>/run_<n>.json` | One run of the agent on one task: harness, model, effort, interview and verification level, stage visits, gates, hidden-test score, outcome (pass, caught and repaired, escape, internal stop with hidden pass, or fail), escape level, cost estimate, wall time and tokens. 21 records over 11 development tasks (one folder per task) |
| `IMPROVEMENTS.md` | Per fix: the run that exposed it, the pull request and the re-run result; open items found by each run |
| `summarise.py` | Per-task pass counts, pass@1, pass@k, outcomes and means from the run records |

All 21 records are development-split runs through Claude Code with `claude-sonnet-5-5` at the V3 verification level, dated 6 to 9
November 2026. Pass means the hidden bench passed, whatever the agent's own gates did.

## Reproduce

- The summary table from the committed records: `python results/course/summarise.py [--split dev|held-out] [results/course]` (no tools, no model).
- The escape fields from a run directory: `python tools/run_record.py backfill results/course`.
- The runs themselves cannot be regenerated exactly: each one is a paid or plan-billed agent session, needs Vivado under a heavy slot, and the model's behaviour differs from run to run. The command is the agent's `python -m agent run` on the task's request with `--interview oracle`; the settings of each run are in its record.

## Known gaps and limits

- Single draws: most tasks have one to three runs, so these are illustrations, not rates, and the pass@1 figures from `summarise.py` rest on 21 runs in all.
- Development tasks only; the held-out split is scored elsewhere and is not in this folder.
- The agent stops at the stage-9 hardware pause: no run here programmed the board.
- Cost is Claude Code's own plan estimate, not a bill.
- The timing and area figures in the run records and in `IMPROVEMENTS.md` were measured on an earlier Vivado release and are not quoted by the published pages; the course reference builds on Vivado 2026.1 are in `../vivado_2026_1_remeasure/course_ref/`.
- Every escape found so far is classed as spec-interpretation; the classification was derived from each run's own files, not from a second reviewer.
