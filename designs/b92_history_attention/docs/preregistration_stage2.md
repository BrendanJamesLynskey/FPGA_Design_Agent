# Pre-registration, stage 2 (committed before `stage2 freeze` and before any test scoring of stage 2)

Written 2026-11-16 after the stage 1 gate passed (`results/b92/stage1_test.json`; stage 1 touched the test split of the
self-exciting generator once, with its own pre-registration). Stage 2 uses the self-exciting generator only (the question is whether
history helps a fabric-sized model where it can matter); the 87 generator is reported for stage 1 only.

## Arms, all with the same head (brief 91 `log4`, hidden 16 then 8, 4-bit codes, 30 epochs) except where stated
ref_current (the head on the 7 current features, no history), a1_decay (four channels x two shift-decay rates; the rate pair is the one with the
best mean validation accuracy over three seeds among (1,3), (2,4), (3,5), (4,6), ties to the first listed),
a2_win16 and a2_win8 (the last N token codes as head inputs), a3_top1 and a3_relu (tiny attention, N = 16, d = 4, m = 4; the
attention is trained with a throwaway float head, frozen, then the standard head is trained on its four output columns),
a4_lut (the 89 `lg_small` network on the a1 columns), ref_lut (`lg_small` on the current features), ref_mlp (87 MLP on the current
features, int8). Reference rows: trivial rule (validation-tuned), 87 trees on current features, 87 trees with lagfeat16 (both from stage 1).

## Selection and scoring
Three training seeds per arm (the attention arms use the seed for both stages). Built seed = best validation accuracy of the whole arm, ties to the
lower seed. Test split scored once, all seeds; the built seed's per-session accuracies are used for paired differences, 95% t-interval over
the 10 sessions. Decisions:
- An arm "beats" another only if the paired interval excludes zero. A history arm is "useful" if it beats ref_current and the trivial rule.
- **Attention is worth putting in the fabric only if a3_top1 or a3_relu beats a1_decay** (interval of the paired difference above zero).
  Otherwise the decaying sums are the answer and no attention RTL is built.
- Accuracy-per-cost front (stage 3): arms not dominated in (test accuracy, LUTs) among the arms that are useful; cost proxy before the
  builds = the generated adder-tree term count; hardware builds then give the real numbers.

## Stopping rules
No hyperparameter changes after `stage2_frozen.json` is committed. A bug found afterwards is fixed and re-run with both results kept.
