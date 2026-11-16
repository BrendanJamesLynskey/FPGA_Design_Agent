# results/b89: a LUT-network generator, measured

These are the recorded results for [designs/b89_lutnet_gen](../../designs/b89_lutnet_gen/README.md):

- the diagnosis of the brief 87 LUT network;
- three design rounds of our own generator;
- the pre-registered test-split scores of three frozen networks and of the TreeLUT reference;
- out-of-context, post-route builds on the K26 (`xck26-sfvc784-2LV-c`) and the Artix-7 100T (`xc7a100tcsg324-1`),
  Vivado 2026.1.

The data are the brief 87 synthetic splits, unchanged (digests checked). There was no board run.

## Records

| File | What | Made by |
|---|---|---|
| `diagnosis.json` | experiments D0-D4 on the train and validation splits | `python -m designs.b89_lutnet_gen.diag.diagnose` |
| `rounds/r1.json`, `r2.json`, `r3.json` | the design rounds, three seeds per configuration, validation only | `python -m designs.b89_lutnet_gen.lutgen.explore r<N>` |
| `rounds/fanin.json` | the fan-in cost sweep (seed 0, validation only, exploratory, not a frozen arm) | `... explore fanin --seeds 0` |
| `frozen.json` | the three frozen arms and the rule that chose each, committed before test scoring | by hand from `rounds/r3.json` |
| `models/` | the tables of every frozen arm and seed, and of the fan-in sweep; the RTL is generated from these | `python -m designs.b89_lutnet_gen.lutgen.cli train` |
| `accuracy.json` | test accuracy per arm and seed, the paired differences against the 87 rule, trees, MLP and LUT network and TreeLUT seed 0, and tie shares | `python -m designs.b89_lutnet_gen.lutgen.evaluate` |
| `treelut/` | TreeLUT validation grid and choice, build record, and its own predictions on the test split and on the random inputs | `treelut_ref/run_treelut.py tune / build / score / random` |
| `determinism.json` | each generated module (and TreeLUT's Verilog) against its twin over the test split and 20,000 random inputs, with the latency of every sample | `B89_RECORD=results/b89 pytest designs/b89_lutnet_gen/tests/test_b89_rtl.py` |
| `ooc/<k26\|a7>/<module>.json`, `ooc/*/reports/` | post-route LUT, FF, DSP, block RAM, WNS, WHS and pulse-width slack at the closed clock, every pass of the clock search, and the reports of the closed build | `python -m designs.b89_lutnet_gen.ooc.ooc --part <part> --arms ...` |
| `summary.json`, `accuracy_vs_latency.svg`, `luts_vs_fanin.svg`, `iteration_history.svg` | the results table and the figures, built only from the files above | `python3 results/b89/summary.py` |

## Reproduce

- **Software:** Python 3.12 with numpy 2.4.3, scikit-learn 1.9.1 and torch 2.15.0 (CPU); TreeLUT in its own venv
  ([docs/treelut.md](../../designs/b89_lutnet_gen/docs/treelut.md)); Icarus Verilog 12 and Verilator 5 for the RTL
  tests.
- **Run times:**
  - a design round: about 2 minutes per configuration and seed, on two threads;
  - the RTL test: about 90 seconds;
  - each out-of-context build: 2 to 13 minutes, under a heavy slot.
- **Repeatability:** training is seeded and deterministic on this machine and library set. Re-training the frozen
  arms reproduced round 3's validation accuracies to four decimals.

## Known gaps and limits

- Everything is out of context: there is no clock buffer or jitter, and latency is quoted at no faster than 2.0 ns.
- The clock search stopped after three passes on the K26 and four on the Artix-7. A closed clock is a closed point,
  not the bound.
- `fanin4_comb` did not close on the Artix-7 within four passes.
- The data come from one synthetic generator.
