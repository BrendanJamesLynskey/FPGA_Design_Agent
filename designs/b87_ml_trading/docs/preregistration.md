# Pre-registration: decision arms on synthetic order flow

Written before the first scored run (the test split had not been evaluated). Smoke checks before this were run on
the train and validation splits only.

## Data

- Generator `model/lobsim.py`, parameters as committed (`Params()` defaults), described in `docs/data_model.md`.
- Splits by seed: train sessions 1001-1020, validation 2001-2002, test 3001-3010; 10,000 events per session, the
  first 50 dropped, the last 40 have no label.
- Label: sign of the mid-price change 40 events later (down, flat, up).

## Arms

| Arm | Model | Hardware form |
|---|---|---|
| majority | the most common training class | none |
| imbalance rule (trivial rule) | thresholds on the imbalance bucket, tuned on validation | none |
| no-ML market-making rule | the inventory-penalised quoting rule (`model/mm_backtest.py`) | scored in the back-test only |
| (a) boosted trees | scikit-learn gradient boosting, 10 rounds x 3 classes, depth 3, learning rate 0.3, subsample 0.8 | hand RTL, fully combinational and one clock per tree level |
| (b) MLP | 7-16-8-3, ReLU, int8 weights, uint8 activations, quantisation-aware fine-tuning | hand RTL and hls4ml (Vitis HLS) |
| (c) LUT network | our generator: 2-bit input codes, layers 16x3, 8x3, 3x4 (neurons x fan-in) | hand RTL generated from truth tables |

Three training seeds (0, 1, 2) per ML arm; seed 0 is the model built in hardware.

## Comparisons and decisions

1. Primary: test accuracy of each ML arm (quantised, seed 0) against the imbalance rule, paired over the 10 test
   sessions, 95% t-interval of the difference. An arm whose interval does not exclude 0 is reported as **not
   useful** on this data.
2. Quantised against float accuracy and the agreement between their predictions.
3. Back-test: P&L of the quoting rule with each forecast minus the no-ML rule, paired over test sessions. The
   back-test's fill model is an assumption, so this is illustrative and is not a decision criterion.
4. Hardware: latency in clocks and ns at the clock each arm closes at post-route (out of context, xck26-sfvc784-2LV-c,
   Vivado 2026.1), initiation interval, resources, WNS; the cycle count over the whole test split.

## Stopping rules

- The test split is evaluated once with these settings. If a bug is found afterwards, the fix and the re-run are
  recorded as such, with the earlier result kept.
- No hyperparameter is changed after seeing test results.
