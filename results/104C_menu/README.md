# results/104C_menu: an order-independent menu rule for strategy options (brief 104C)

Brief 104B's splitter made `agent_both` and `all3` available in 6 of 12 live runs, but the offered menu (cap of four) still showed them 0 of 12 and 1 of 12, because ties among parts were broken by the model's listing order. Brief 104C replaces that with a rule that depends only on the *set* of the model's options and on the stage file, and tests it on fresh runs.
Rule and limits: [docs/strategy_options.md](../../docs/strategy_options.md), section "The menu rule". Pre-registration: [preregistration.md](preregistration.md) (committed with the frozen code before any live call, commit `a510993d`). Development replay: [REPLAY.md](REPLAY.md).

## Nulls first (fresh live back-test, 12 runs, offered options, unchanged scoring)

- **H1 `agent_both` offered in more than 0 of 12: met on the count (2 of 12), but not attributable to the rule.** On the same 12 fresh sets of model options the 104B rule (list-order ties) also offers `agent_both` in 2 of 12 (`fresh_counterfactual_104B_rule.json`).
- **H2 `all3` offered in more than 1 of 12: met on the count (7 of 12), not attributable to the rule.** The 104B rule offers it in 7 of 12 on the same options. In 5 of the 7 the matching option is the model's own: in these fresh runs the model offered the three-stage bundle itself (104A and 104B: once in 12 runs each). The runs differ from the earlier ones in what the model offered, not in what the rule did.
- **H3 met:** no offered option is outside the stage file's bounds (116 latency options checked by code).
- **H4 met:** for all 12 runs, 24 seeded shuffles of the model's options give the same offered splitter and combiner options, and the menu recorded at run time equals the rebuild. The 104B rule gives a different menu for some shuffle in 12 of 12 of the same runs.
- **S2:** `agent_cdc` offered 12 of 12; `hand_ref` offered **10 of 12** (104B: 9; the 104B rule on the same fresh options: 11, so the new rule costs one).
- **S1 availability (cap lifted):** `agent_both` 10 of 12, `all3` 10 of 12 (104B: 6 and 6), `hand_ref` 12 of 12. Available but not offered: `agent_both` in 8 of 10 runs.

| variant | 104A offered | 104B offered | fresh, 104B rule (counterfactual) | fresh, new rule | fresh available (cap lifted) |
|---|---|---|---|---|---|
| agent_cdc | 12 | 12 | 12 | 12 | 12 |
| hand_ref | 9 | 9 | 11 | 10 | 12 |
| agent_both | 0 | 0 | 2 | 2 | 10 |
| all3 | 1 | 1 | 7 | 7 | 10 |

Per arm (found of 3 for agent_both / all3 / hand_ref; origin of the match): P1 A: 0 / 1 (combiner) / 2 (model); P1 B (blind): 1 (combiner) / 1 (model) / 3 (combiner); P2 A: 1 (combiner) / 2 (model, combiner) / 2 (combiner); P2 B (blind): 0 / 3 (model) / 3 (combiner). Every found range contained the measurement; the high end above it was 0 to 2 clocks (all above 0 in the blind arms, as before). Details: [backtest/RESULTS.md](backtest/RESULTS.md), [backtest/results.json](backtest/results.json), one `record.json` per run under `backtest/runs/`.

## What this says

- The rule does what it was built for: the menu no longer depends on the order of the model's options (H4), and no option leaves the stage file's bounds (H3). That is a property of the code, tested by `agent/tests/test_104c_menu.py` (nine tests, including all 24 orders of four planted options, pool truncation, cap and bounds), and it holds on the 12 live records.
- It does not, by itself, surface `agent_both`: the diagnosis in 104B (ties broken by list order) was only part of the story. In the records the model's own bundles name many stages (for example `rx_descramble`), a truth-blind rule has no basis to prefer `decide`, and the cap of four decides. On the same fresh options the old and the new rule offer `agent_both` equally often (2 of 12) and the new one offers `hand_ref` once less (10 against 11).
- What changed `agent_both` and `all3` between 104B and 104C is the model's replies, not the rule (see H2). With k = 3 per arm, one model and one design, no significance is claimed.
- The development replay (30 recorded runs, [REPLAY.md](REPLAY.md)) predicted this: `agent_both` 0 and 1 of 12, `hand_ref` 6 and 5 of 12, both lower than the 104B rule's 11 and 9. On fresh runs `hand_ref` was 10, so the development numbers understated it.

## Files

- `preregistration.md`, `run_backtest.py` (run, publish, score), `replay.py` (offline, any rule, `--root` for another worktree).
- `replay_before_104B_rule.json`, `replay_candidate1_headroom_only.json` (the first candidate, dropped after its replay: disclosed in the pre-registration), `replay_final.json`, `REPLAY.md`: development replay on 30 recorded runs.
- `fresh_counterfactual_104B_rule.json`, `fresh_rebuild_final_rule.json`: the same fresh model options rebuilt with the 104B rule and with the final rule (offline).
- `backtest/`: `results.json`, `RESULTS.md`, `moved_to_kb.json` (SHA-256 of the raw replies in the private KB, PR 83), `runs/*/record.json` and `meta.json`.
