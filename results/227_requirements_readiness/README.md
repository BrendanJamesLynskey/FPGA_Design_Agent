# Brief 227: requirements readiness, the reviewer test set, and the gate on our own designs

This folder holds the pre-registrations and the records for brief 227: the requirements reviewer measured on a labelled set of CVDP problems (a test set for the reviewer, never an evaluation of FPGA Force, owner decision
2026-11-25), the stage-0 readiness gate run on the six KR260 pilot designs of brief 209 with an oracle, and build runs of three of those designs from three kinds of input. The gate and its roles are described in
[docs/requirements_readiness.md](../../docs/requirements_readiness.md); the code is [flow/readiness.py](../../flow/readiness.py) and [agent/graph/readiness.py](../../agent/graph/readiness.py). Nothing here touched a board.

## Records

- [prereg_reviewer.md](prereg_reviewer.md): the pre-registration of the reviewer test (set, conditions, scoring, the pass line, power, threats), written before the first scored run, with one dated amendment for the post-hoc prompt.
- [reviewer_testset/results.csv](reviewer_testset/results.csv): one row per problem, condition and run (ids and our outputs only; the problem text, the reviewer's replies and the regex keys stay in a private folder).
  [reviewer_testset/scores.md](reviewer_testset/scores.md): the scores of [tools/reviewer_testset/score.py](../../tools/reviewer_testset/score.py) for each condition; the ids and groups are in [tools/reviewer_testset/ids.yaml](../../tools/reviewer_testset/ids.yaml).
- [prereg_arms.md](prereg_arms.md): the pre-registration of the arms on our own designs. [pilot_hidden_specs](pilot_hidden_specs/): the hidden full specs the oracle answers from and arm C appends (written for this brief by the executor, not owner-sourced, no test values).
- ARMS_RECORDS: see the sections below once the runs are in.

## Result in six lines, nulls first

(filled in below)

## Reproduce

```
python -m pytest -q flow/tests/test_227_readiness.py agent/tests/test_227_readiness_rounds.py tools/tests/test_227_reviewer_testset.py
python tools/reviewer_testset/score.py results/227_requirements_readiness/reviewer_testset/results.csv      # rewrites scores.md's tables from results.csv
python -m agent run <spec.md> --stop-after 0 --harness claude_code --interview oracle --oracle claude_code --hidden-spec <hidden.md> --readiness on --requirements loose
```

The reviewer runs need the CVDP dataset (not redistributed here), a private folder for the replies and keys, the pinned Claude Code CLI and the knowledge bank skill: see the header of
[tools/reviewer_testset/run.py](../../tools/reviewer_testset/run.py). The arm runs are [tools/requirements_arms/run_arm.sh](../../tools/requirements_arms/run_arm.sh).

## Known gaps and limits

(filled in below)
