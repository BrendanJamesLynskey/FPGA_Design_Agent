# 27b_p1: phase 0 of the project agent on two specs

This folder holds the records of brief 27B P1: the project agent's phase 0 (a requirements pass and a decomposition and
contracts pass, with a language-model drafter and a language-model oracle that answers only from a hidden spec) run on
two development specs, the video median pilot and the `c12_nexys_pwm_audio` task. Ten runs are kept, in the order made,
with the checks of their files against facts fixed before the runs. Every row is a single run.

## Records

| Path | What |
|---|---|
| `results.md`, `results.json` | the summary table, one section per run, the harness changes made between runs, and the reference checks; written by `summarise.py` |
| `<spec>/` (`pilot1_run1` to `pilot1_run6`, `pilot1`, `c12_pwm_audio_run1`, `c12_pwm_audio_run2`, `c12_pwm_audio`) | one run: `phase0/` (`session.json` with check result, tokens and cost, `llm_calls.json`, `oracle_log.json`, `pass1_requirements.json`, `pass2_contracts.json`, `replay.json`), `design.yaml`, `modules/`, `system/` (the user's words and the system files), `stdout.txt` |
| `pilot1_run3/` | the run that stopped: only `phase0/` and `stdout.txt` |
| `prepare.py`, `summarise.py` | set up the two projects (development-split sources only), and build `results.md` from the runs' own files |

## Reproduce

    python results/27b_p1/prepare.py
    python -m project spec <dir> --interview oracle --hidden-spec <oracle file> --record <file>
    python results/27b_p1/summarise.py

`summarise.py` regenerates `results.md` and `results.json` from the committed run files with no network. The runs
themselves need paid model calls through the provider the file names (drafter and oracle `openai/gpt-6-luna`, about
$0.02 to $0.05 per run as the provider reported); the drafter is stochastic, so a rerun gives different modules and
counts. The exact command lines of the ten runs are not recorded in the folder; the options of `python -m project spec`
are in `project/cli.py`. The oracle files written by `prepare.py` are not committed.

## Known gaps and limits

- Each row is one run of a stochastic drafter; the decomposition changed from run to run (the Modules column of results.md: 3 modules in pilot1_run1, 7 in pilot1_run2), so counts are per run, not a rate.
- The oracle answers only from the hidden specs, which do not state many contract-level fields, so most assumptions are "not specified"; a person would answer more.
- The harness was changed between runs after reading a run (`results.md` lists the changes), so the runs are not of one harness version; `pilot1` and `c12_pwm_audio` ran with the final harness, and the last column re-checks every run's files with today's checker.
- Owner choice 2 (the median latency) was lost in the oracle set-up in pilot1_run6, and in pilot1 ("run 7" in results.md) choice 1 held on one of two stream links only.
- A quote proves the words are in the spec, not that the value matches; no review step for quoted fields, no review of the decomposition, no test-plan pass and no interactive approval of each pass were built.
- Development-split subjects only; nothing measures changes the contracts would have prevented.
