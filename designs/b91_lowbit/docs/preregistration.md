# b91 pre-registration (committed before any network is trained and before the test split is scored)

The commit that adds this file precedes every trained model and every test score of brief 91. The test split is read
only by `lowbit/evaluate.py`, which is run after `results/b91/frozen.json` is committed.

## Data

The brief 87 splits, unchanged (`lutgen/data.py` of brief 89 checks the 87 SHA-256 digests): train seeds 1001-1020
(198,200 samples), validation 2001-2002 (19,820), test 3001-3010 (99,100; 10 independent sessions).

## Formats, shapes, seeds

- Formats: `binary_t3`, `binary_t7` (thermometer inputs, 3 or 7 thresholds per feature), `ternary`, `int4`, `mxfp4`,
  `log4`, `log4_nz`, `log4p1` (definitions: `docs/design.md` section 3).
- Shapes: `h16x8` (hidden 16 and 8) and `h8` (hidden 8), then 3 score neurons.
- Activation and input-code width A = 4 (binary: 1) in stage 1. 30 epochs, seeds 0, 1, 2.

## Selection rule (validation only)

1. Per format: the shape with the higher mean validation accuracy over the 3 seeds (ties to the smaller network); the
   **built seed** is the seed with the best validation accuracy in that shape (ties to the lower seed).
2. Family representative: binary = `binary_t3`/`binary_t7`; log4 = `log4`/`log4_nz`; each other format is its own family.
   The representative is the member with the higher mean validation accuracy at its selected shape.
3. **Activation sweep** (A = 2 and 8, same shape, 3 seeds) for the two non-binary families whose representatives have
   the highest mean validation accuracy at A = 4 (ties by format name). The selected A of a swept family is the one with
   the highest mean validation accuracy (ties to the smaller A). Binary has 1-bit activations, so it is not swept.
4. The networks that are built and scored are listed in `results/b91/frozen.json`: each format's selected network at
   A = 4, plus the A = 2 and A = 8 networks of the two swept families.

## Metrics

Test accuracy per session (10 sessions); mean over the 3 seeds, and the built seed's. 95% t-interval (t = 2.262, 9
degrees of freedom). Hardware (out of context, post-route, Vivado 2026.1; `xck26-sfvc784-2LV-c` and
`xc7a100tcsg324-1`; one thread; the 87 wrapper and the pulse-width-aware clock search of brief 89): closed period,
latency = clocks x max(closed period, 2.0 ns), LUT, FF, DSP, BRAM. Each frozen network is built `comb`; the A = 4
networks also `layer`. If the time or the heavy slots do not allow every build, the report states what was not built.

## Comparisons (test split, built seed, paired over the 10 sessions)

References from committed per-session values: the 87 trivial rule, the 87 boosted trees, the 87 MLP
(`results/b87/accuracy.json`); the 89 networks `lg_add`, `lg_small`, `lg_b87` (built seeds) and TreeLUT seed 0
(`results/b89/accuracy.json`).

- **Primary:** the best format by validation accuracy against the trivial rule (useful if the interval is above zero).
- Every frozen network at A = 4 against the trivial rule, the 87 trees, `lg_small` and `lg_add`.
- The accuracy-per-LUT and accuracy-against-latency fronts over all built networks plus the 89 networks and the 87
  trees (their K26 numbers from `results/b87/summary.json` and `results/b89/summary.json`); a network is on the front if
  no other has both higher-or-equal accuracy and lower-or-equal cost with one strict.
- **The honest comparison:** a format "beats the 89 LUT network" only if its test accuracy is not below `lg_small`'s
  (paired interval not entirely below zero) at fewer LUTs or lower latency on the K26. Otherwise we say it does not.

## Stopping rules

No change to any network, shape, seed or the rule after this commit. A bug found in the twin, the RTL or the scoring
after test scoring is fixed, both results are reported and the original is not overwritten.
