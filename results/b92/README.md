# results/b92: order-flow history and tiny attention, measured

The recorded results for [designs/b92_history_attention](../../designs/b92_history_attention/README.md):

- two synthetic generators (the brief 87 one and a self-exciting variant) and their statistics;
- stage 1, the gate: do lagged features help the 87 trees (validation selection committed before the test run);
- stage 2: five history arms and four reference arms on the self-exciting data, one common head;
- stage 3: the generated RTL against its twin on every test event, and out-of-context post-route builds on the K26
  (`xck26-sfvc784-2LV-c`) and the Artix-7 100T (`xc7a100tcsg324-1`), Vivado 2026.1.

There was no board run. All data are synthetic.

## Records

| File | What | Made by |
|---|---|---|
| `gen_stats.json` | trade-sign and count autocorrelations, clustering, burst share of both generators | `python -m designs.b92_history_attention.hist.gen_stats` |
| `stage1_val.json` | validation accuracy of every stage 1 candidate; the gate candidate (committed before test scoring) | `python -m designs.b92_history_attention.hist.stage1 val` |
| `stage1_test.json` | the gate result: per-session test accuracy of every arm, paired differences, the sensitivity run | `... stage1 test` |
| `rounds/stage2_val.json`, `models/` | validation accuracy of every stage 2 network and seed; the exported integers of each | `python -m designs.b92_history_attention.hist.stage2 fit` |
| `stage2_frozen.json` | built seeds and the arm 1 rate set (committed before test scoring) | `... stage2 freeze` |
| `stage2_accuracy.json` | the pre-registered test scores, paired differences, attention against decaying sums | `... stage2 test` |
| `determinism.json` | each generated arm against its stream twin on all test events, random and extreme streams, latency of every event | `B92_RECORD=results/b92 pytest designs/b92_history_attention/tests` |
| `ooc/<k26\|a7>/<module>.json`, `ooc/*/reports/` | post-route LUT, FF, DSP, BRAM, slack at the closed clock; every pass of the clock search | `python -m designs.b92_history_attention.ooc.ooc --part <part> --arms ...` |
| `summary.json`, `*.svg` | the results table and figures, built only from the files above | `python3 results/b92/summary.py` |

## Reproduce
- Software: Python 3.12, numpy 2.4.3, scikit-learn 1.9.1, torch 2.15.0 (CPU); Icarus Verilog 12 and Verilator 5.
- Run times: generator statistics 1 minute; stage 1 about 45 minutes on two workers; stage 2 about 40 minutes; the RTL test about 8 minutes;
  each out-of-context build a few minutes under a heavy slot.
