# Newcomer CLI: what works without the key, and `agent doctor` (brief 157): measured results

Brief 157 (review item F8 of brief 147's flow-improvement review) makes the first minute on a fresh clone work: `--help`, `models show`,
`resume <design-dir> --dry-run` and a new `python -m agent doctor` run with no access key, while every command that calls a model, writes a design
or reads private material still stops at the gate. The labelled set is [cases.json](cases.json); [measure.py](measure.py) runs it against a
checkout and writes a record.

## Null result and prediction, written before any measurement

Written 2026-11-22 before the labelled set was run on either checkout. Before the change (origin/main at 17b4dd19) `main()` calls the gate before argparse, so
the prediction is: every `--help`, `models show` and `--dry-run` case exits 2 with the gate message and the case fails its label; the `doctor` cases fail
(`doctor` is not a command); only the cases that are meant to be refused pass. After the change the prediction is that every case passes in both
environments. A pass count after the change that is not the whole set is reported as a failure of the change, not adjusted away.

## Measured

Each row is one run of [measure.py](measure.py) on a clone with no `.env`, no `FDA_ACCESS_KEY` and no private prompts: "before" is origin/main at 17b4dd19, "after" is this branch at ccd6df4c, with the same labelled set. A case passes when the command line gives its label's exit status and text. The `full` environment has the agent and graph extras installed; `bare` has `pyyaml` and `pyserial` only (Python 3.12.3). Records: `before_full.json`, `after_full.json`, `before_bare.json`, `after_bare.json`.

| Environment | Cases | Before: passing | After: passing |
|---|---|---|---|
| full | 32 | 14 | 32 |
| bare | 31 | 0 | 31 |

By class, with the extras installed (before, after): `--help` 0 and 11 of 11; `--dry-run` 0 and 2 of 2; `models show` 0 and 2 of 2; `doctor` 0 and 3 of 3; commands that must stay refused 14 and 14 of 14. The 14 refusals that passed before are the cases that are meant to fail the same way after: no gated command became reachable.

Without the extras, before the change, every command line (including a refusal) ended in a Python traceback (`ModuleNotFoundError`, `jsonschema`) because `agent.core` was imported before argparse. After the change `--help` and `doctor` answer, `run` still exits 2 with the gate message, and `models show` and the design dry run say which package is missing (exit 2).

The null prediction above held: before the change only the refusals passed on the full install. After the change every case passed in both environments, so no case needed an adjusted label. The unit tests
([agent/tests/test_157_newcomer_cli.py](../../agent/tests/test_157_newcomer_cli.py), [agent/tests/test_94_access.py](../../agent/tests/test_94_access.py)) hold the same cases, a grid proving exactly two command shapes are exempt, and a test that forces the exemption wrong and shows
`resume` and `models check` still stop inside themselves.

## Records

- [cases.json](cases.json): the labelled set (32 command lines, each with the exit status and text it must give in the `full` and `bare` environments; written before the change was measured).
- `before_*.json`, `after_*.json`: one row per case: command line, expected and actual exit status, any mismatch, the first line printed, seconds.
- [measure.py](measure.py): the runner (`--env full|bare`, `--root`, `--out`, `--check`).

## Reproduce

```bash
python results/157_newcomer_cli/measure.py --env full --root <a clean clone> --out record.json    # extras installed
python results/157_newcomer_cli/measure.py --env bare --root <a clean clone> --out record.json    # a venv with pyyaml and pyserial only
```

No heavy slot, no Vivado, no model call, no key. CI runs both as the `newcomer-cli` job (no secrets are given to it). Each clone must have no `.env` (a developer's own `.env` supplies a key and the refusal cases then fail on purpose).

## Known gaps and limits

- `doctor` on a machine that has Docker runs `docker image inspect` and, when Vivado is present, `vivado -version` (up to 90 s). The labelled set runs one probing `doctor` and checks only that the lines exist, because their status depends on the machine.
- `doctor` repeats three rules in standard-library code (the prompts path, the Vivado path, the image name) so that it runs without the extras; a unit test compares each with the code that decides.
- The prompt manifest is compared with the pin only when a valid key is present (it is private material), so `doctor` without a key reports "n/a" there.
- With the extras missing, `<command> --help` prints the top-level command table, not that command's options.
- `review --no-judge` reads a design and calls no model but is still gated (the brief's exemption list is help, dry runs and `models show`); `improve --analyse-only` likewise.
- A local `.env` hides the refusals from the labelled set. The unit tests hide it themselves.
- Run on this PC only; the CI job's first run is the check on a hosted runner (see the pull request).
