# 05k: generic mutation run on T1

This folder holds the one record made by brief 05k, the generic mutation tool (`flow/mutate.py --generic`): a run of
the design's own cocotb tests on Icarus against 21 mutants of `designs/t1_dimmer_counter`, read from its
`verif/mutants.yaml`. It was made to check that the generic mode gives the same score as the T1-specific run in `results/04f`.

## Records

| File | What |
|---|---|
| `mutation_t1_generic.json` | 21 candidates, all 21 evaluated: 21 killed, 0 survived, 0 timed out, 0 skipped, 0 invalid; score 100.0 %; baseline 140.6 s, wall 721.2 s; RNG seed 1 |

## Reproduce

From the repository root, on the T1 design (a heavy local job, about 12 minutes on one PC; take a heavy slot first;
no Vivado, board or paid agent run):

    python3 flow/mutate.py --generic designs/t1_dimmer_counter --max-mutants 21 --wall-s 3000 --json results/05k/mutation_t1_generic.json

The cap on mutants was raised to 21 and the wall cap to 3000 s for this run (the defaults are 20 mutants and 1500 s;
see [docs/verification.md](../../docs/verification.md) for the exact options). The exact command line used for the
committed file is not recorded in the folder.

## Known gaps and limits

- It ran the design's whole `tests/test_*_rtl.py` (seeds 1-3, Icarus only, no bound checkers), so it equals the
  bench-only score in `results/04f/mutation_t1.json`; the two agree at 21 of 21.
- The mutants are the hand-written ones in `verif/mutants.yaml`. The tool's generated-operator mode was not run on T1.
- One design, one seed. The run started before a later fix to the heavy-lock text, so its lock line used the old format.
