# b89 pre-registration (committed before the test split is scored)

Written after the three design rounds (validation only) and before any brief 89 model saw the test split. The commit
that adds this file precedes the commit that adds `results/b89/accuracy.json`.

## Data

The brief 87 splits, unchanged (`lutgen/data.py` checks the 87 SHA-256 digests): train seeds 1001-1020 (198,200
samples), validation 2001-2002 (19,820), test 3001-3010 (99,100, 10 independent sessions).

## Arms

Frozen in `results/b89/frozen.json`; each is trained with seeds 0, 1 and 2 by `lutgen/cli.py train`.

1. **`lg_add`** (round 3 `t_add_noh_3b_tree`): the round 3 configuration with the highest mean validation accuracy over its three seeds (ties to
   the smaller table size). This is the generator's result.
2. **`lg_small`** (round 3 `t_add_noh_3b_tree_k2`): the configuration with the smallest table size whose mean
   validation accuracy is within 0.002 of `lg_add`'s. It tests whether the cheaper network holds its accuracy.
3. **`lg_b87`**: round 3's `t_b87_shape`: the brief 87 network's shape (16x3 -> 8x3 -> 3x4, 2-bit codes) with the
   brief 89 training. It separates the effect of the training from the effect of the shape.
4. **TreeLUT** (reference, pinned commit `ad9e70a9ba1a74ccf8df97a3f7fcdc9137e68b21`): the configuration chosen on
   validation in `results/b89/treelut/tuning.json` (rule recorded there), seeds 0-2; seed 0 is built.

The **built seed** of each lutgen arm is the seed with the best validation accuracy (ties to the lower seed).
All three seeds' test accuracies are reported.

## Comparisons (test split, built seed, paired over the 10 sessions, 95% t-interval, t = 2.262)

- **Primary:** `lg_add` against the 87 trivial imbalance rule. The accuracy floor is met if the interval of the
  paired difference lies above zero.
- Secondary: `lg_add` and `lg_small` against the trivial rule (for `lg_small`), the 87 boosted trees, the 87 MLP and TreeLUT seed 0; `lg_b87` against the trivial rule
  and against the 87 LUT network (its per-session values from `results/b87/accuracy.json`, seed 0).
- "Approaches the trees" is read as: the paired difference to the 87 trees has an interval that includes zero or
  lies above it. A difference whose interval lies below zero is reported as worse, with its size.

## Hardware

Out of context, post-route, Vivado 2026.1, `xck26-sfvc784-2LV-c` and `xc7a100tcsg324-1`, one thread, by the 87 method
(input register in `ooc_wrap`; the clock search moves the period by WNS and pulse width until setup, hold and pulse
width all pass). Latency is quoted as clocks x max(closed period, 2.0 ns). Each lutgen arm is built `comb` and
`layer` (one module when they coincide); TreeLUT with its pipeline `[0, 1, 1]` plus our output register.

## Stopping rules

No change to any arm after this commit. If a bug in the twin, the RTL or the scoring is found after scoring, the fix
is made, both results are reported, and the original is not overwritten.
