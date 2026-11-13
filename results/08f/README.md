# 08f: spec-test role, offline replays against saved designs

This folder holds the offline replay records from brief 08f (`eval-2` build): the spec-test role, which writes its own
cocotb bench from the spec alone, was run once per saved final design from earlier course runs, with no RTL repair, to
see whether it would have caught the bugs a hidden bench later found. No Vivado, board or fresh agent run was used for
the design under test.

## Records

| Path | What |
|---|---|
| `<label>/` (nine folders: `c14_tiny_cnn_fix7`, `c10_run1_reconstructed`, `c11_nco_mixer_run2`, `c12_pwm_run2`, `c14_int8_run1` to `run5`) | per replay: `result.json` (gate verdict, state, history), `meta.json` (the known hidden result of that run), `claude_code_calls.jsonl`, and `spectest/` (the generated `spec_ref.py`, `spec_bench.py` and pytest entry) |
| `<label>.log` | the replay's console output |

Summary from the replays (the table is in the brief's report, not in this folder): of the two escapes the brief named,
one was caught (tiny CNN: `design_wrong`); counting three further saved escapes, one of five. No correct design was
failed (0 of 4). `c10_run1_reconstructed` was rebuilt from the report because its run directory was not kept.

## Reproduce

    python3 tools/spectest_replay.py replay <run_dir> [--task-dir DIR] [--label NAME] [--out results/08f]
    python3 tools/spectest_replay.py table results/08f

`replay` calls the spec-test role (one headless Claude Code call, so it needs a paid agent run) on a saved run
directory; the saved run directories of the course runs are not in the repository, so the replays cannot be
regenerated from the repository alone. `table` joins the replays with the hidden results.

## Known gaps and limits

- Nine replays only, one role call each; the loop limit of 2 was not exercised beyond one `design_wrong` per replay.
- The `c10` replay is a reconstruction (reference RTL altered to the earlier fault, interview rebuilt from the report), not the real run-1 design. It was missed because the spec does not say that unused register bits read 0, which a spec-only reader cannot know.
- The tiny CNN catch relied on the sign rule appearing in the data file and old `spec.md` wording.
- Two bench repairs fired, both for the role's own mistakes; four of the five known escapes were missed (the bench passed against a faulty design, or failed first and was repaired into a pass).
- The switch `--spec-tests` is default off; no end-to-end agent run with it on is recorded here.
