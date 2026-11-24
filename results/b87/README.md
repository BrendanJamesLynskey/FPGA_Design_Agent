# results/b87: decision models in the trading path

Recorded results for [designs/b87_ml_trading](../../designs/b87_ml_trading/README.md): small decision models (boosted
trees, an MLP built by hand and by hls4ml, a LUT network) trained on synthetic order flow, built post-route on the
K26 (xck26-sfvc784-2LV-c, Vivado 2026.1, out of context), checked bit for bit against their integer models over the
whole test split, and one of them placed behind the 58A rule table in simulation. Synthetic data only; no board run.

## Records

| File | What | Made by |
|---|---|---|
| `accuracy.json` | every arm's test accuracy (three training seeds; seed 0 is the one built), quantised and float, the paired difference against the trivial rule, the data digests, and the market-making back-test | `python -m designs.b87_ml_trading.model.evaluate --out results/b87` |
| `models/` | the integer models the RTL is generated from (seed 0) and the trivial rule's thresholds | same |
| `determinism.json` | each hand-RTL arm against its integer model over all 99,100 test samples, and the latency of every sample (minimum = maximum) | `B87_RECORD=results/b87 pytest designs/b87_ml_trading/tests/test_b87_rtl.py` |
| `hls4ml_csim.json`, `hls4ml_synth/` | the hls4ml arm: C simulation against the integer model over the test split; the Vitis HLS run and its report | `python -m designs.b87_ml_trading.model.hls4ml_arm --synth` |
| `ooc/<arm>.json` | post-route LUT, FF, DSP, block RAM, WNS and WHS at the clock each arm closed at, and every pass of the clock search | `python -m designs.b87_ml_trading.ooc.ooc` |
| `integration/` | the 58A trigger_core with the boosted-tree arm behind the rules: stage clocks with the model off and on, and the fabric's features and classes against the Python twin | `B87_RECORD=$PWD/results/b87/integration pytest designs/b87_ml_trading/tests/test_b87_integ_rtl.py` |
| `published_jsc.json` | the published points of the research report's figure 8 (jet tagging, not trading), with sources | copied from the report's build data |
| `summary.json`, `latency_vs_accuracy.svg` | the results table and the chart, built only from the files above | `python3 results/b87/summary.py` |

## Reproduce

- Python 3.12 with numpy 2.4.3, scikit-learn 1.9.1, torch 2.15.0 (CPU) and, for the hls4ml arm, hls4ml 1.3.0;
  Icarus Verilog 12 and cocotb 2.0.1 for the RTL tests.
- `evaluate` takes about 17 minutes on one core pair; the RTL test about 80 seconds; each out-of-context build two to
  six minutes under a heavy-job slot.
- Everything is seeded; the data digests in `accuracy.json` identify the splits.

## Known gaps and limits

- The data are synthetic, from one generator with a planted signal; accuracies say nothing about a real market.
- Out-of-context results: no I/O, no placement against the rest of a design; the 58A integration is simulation only.
- The back-test's fill model is an assumption; its differences are within noise and it is not a decision criterion.
- Only seed 0 of each model is built in hardware.

## Change log

- 2026-11-24 (brief 201): the out-of-context runs have no clock buffer; on the K26 (-2LV) a BUFGCE limits a real clock to 725.2 MHz ([flow/fmax_cap.py](../../flow/fmax_cap.py), [results/201_fmax_cap](../201_fmax_cap/README.md)). The trivial rule `imb_rule` closed at 0.55 ns (`closed_at_mhz` 1818.2, a pulse-width-limited point of a two-LUT block); `summary.json` rows now also carry `fmax_capped_mhz` (725.2 for that arm), `fmax_bound` and `fmax_clock_buffer_mhz`, and `closed_at_mhz` stays the raw figure. `gbt_pipe` (645.2) and `lutnet` (512.8) are below the limit. No latency changes: latency was already quoted at no faster than 2.0 ns (500 MHz).
