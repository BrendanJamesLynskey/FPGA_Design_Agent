# results/b91: low-bit weight formats, measured

The recorded results for [designs/b91_lowbit](../../designs/b91_lowbit/README.md):

- two stages of validation-only rounds (eight formats, two shapes, three seeds; an activation-width sweep of two families);
- the pre-registered test-split scores of the 12 frozen networks, and a post-hoc seed-mean comparison;
- out-of-context, post-route builds on the K26 (`xck26-sfvc784-2LV-c`) and the Artix-7 100T (`xc7a100tcsg324-1`),
  Vivado 2026.1.

The data are the brief 87 synthetic splits, unchanged (digests checked by the brief 89 loader). There was no board run.

## Records

| File | What | Made by |
|---|---|---|
| `rounds/stage1.json`, `select.json`, `stage2.json` | validation accuracy per format, shape, activation width and seed; the selection rule's outcome | `python -m designs.b91_lowbit.lowbit.cli stage1 / select / stage2` |
| `frozen.json` | the 12 networks that are built and scored, with built seeds, committed before test scoring | `... cli freeze` |
| `models/` | the exported integers of every trained network (the RTL is generated from these) | `... cli stage1 / stage2` |
| `accuracy.json` | test accuracy per network and seed; paired differences against the 87 rule, trees and MLP, the 89 networks and TreeLUT | `python -m designs.b91_lowbit.lowbit.evaluate` |
| `accuracy_seedmean.json` | post hoc (not pre-registered): the same comparison on the per-session accuracy averaged over the three training seeds | `python -m designs.b91_lowbit.lowbit.seedmean` |
| `determinism.json` | each generated module against its twin over the test split and 20,000 random inputs, with the latency of every sample | `B91_RECORD=results/b91 pytest designs/b91_lowbit/tests` |
| `ooc/<k26\|a7>/<module>.json`, `ooc/*/reports/` | post-route LUT, FF, DSP, block RAM, WNS, WHS and pulse-width slack at the closed clock, every pass of the clock search, and the reports of the closed build | `python -m designs.b91_lowbit.ooc.ooc --part <part> --arms ...` |
| `summary.json`, `accuracy_vs_luts.svg`, `accuracy_vs_latency.svg` | the results table, the fronts and the figures, built only from the files above | `python3 results/b91/summary.py` |
| `tables.py` | prints the markdown tables of `docs/what_we_found.md` | `python3 results/b91/tables.py` |

## Reproduce

- **Software:** Python 3.12 with numpy 2.4.3, scikit-learn 1.9.1 and torch 2.15.0 (CPU); Icarus Verilog 12 and Verilator 5.
- **Run times:** stage 1 (48 networks) about 60 minutes on two workers; the RTL test about 6 minutes; each out-of-context
  build 3 to 10 minutes under a heavy slot; the whole clock search about 8 hours on the K26 and about 6 on the Artix-7.
- **Repeatability:** training is seeded and deterministic on this machine; the exported integers reproduce each network's
  recorded validation accuracy (a test).

## Known gaps and limits

- Everything is out of context: there is no clock buffer or jitter, and latency is quoted at no faster than 2.0 ns.
- The clock search stopped after at most four passes on the K26 and three on the Artix-7 (with one extra run of the
  modules that had not closed). A closed clock is a closed point, not the bound; a module that never closed is marked
  "not built" in the tables.
- The data come from one synthetic generator. The formats are not tuned individually.
