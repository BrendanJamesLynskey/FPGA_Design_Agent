# Pre-registration, stages 0-1 (committed before any test split is scored)

Written 2026-11-16, before `stage1 val` was run. The test split of either generator has not been read by any code at this point
(the generator statistics `results/b92/gen_stats.json` use the test *sessions' event streams* only for autocorrelations of trade
signs and counts, never a label or a model; this is declared here).

## Data
- 87 generator, unchanged: train 1001-1020, validation 2001-2002, test 3001-3010.
- Self-exciting variant `hist/hawkes_sim.py`, parameters as committed: train 5001-5020, validation 6001-6002, test 7001-7010.
  10,000 events a session, 50 dropped at the start, 40 unlabelled at the end. Label as 87 (sign of the mid change 40 events later).

## Arms (both generators)
- (a) 87 trees on the 7 current features: GradientBoostingClassifier, 10 rounds x 3 classes, depth 3, learning rate 0.3, subsample 0.8.
- (b) the same trees on current + `lagfeat` N in {4, 8, 16}, or current + `lagprim` N in {4, 8, 16} (six candidates).
- Training seeds 0, 1, 2 for each. Predictions are the float model's (the integer thresholds of the 87 quantisation are exact on integer features).

## Selection and gate
1. Train on the train split; score validation only.
2. Gate candidate = the (family, N) among the six with the highest mean validation accuracy over the three seeds; ties to the smaller N.
   Written to `results/b92/stage1_val.json` and committed before the test run.
3. Test (once): per-session accuracy (10 sessions) averaged over the three seeds, for all arms. Gate statistic = gate candidate minus (a) on the
   self-exciting generator, 95% t-interval over the 10 sessions (df 9, t = 2.262).
4. **Gate passes iff the interval lies above zero.** If it does not, stage 2 and later are not run and the report says
   "history adds nothing here", with this evidence.
5. Reported, not gating: the same difference on the 87 generator; all six candidates against (a); a sensitivity run with histogram
   gradient boosting (100 rounds, depth 4, lr 0.1) for (a) and the gate candidate.

## Stopping rules
- No hyperparameter or generator parameter is changed after the validation selection is written. A bug found later is fixed and the
  re-run recorded beside the original.
