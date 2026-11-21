# results/104B_split: the per-stage splitter for bundled strategy options (brief 104B)

Brief 104A's combiner found `agent_both` in 0 of 12 live runs because the model never offers `decide` alone. Brief 104B adds a splitter in code (`flow/options/split.py`) that derives per-stage options from the model's bundles, bounded by the stage file, and gives them to the 104A combiner.
Rules and limits: [docs/strategy_options.md](../../docs/strategy_options.md), section "The splitter". Pre-registration: [preregistration.md](preregistration.md) (committed with the frozen code, commit `b48450b1`, before any live call).

## Nulls first (live back-test, 15 runs, offered options, unchanged scoring)

- **H1 not met:** `agent_both` was offered in **0 of 12** b96 runs (104A: 0 of 12).
- **H2 not met:** `all3` was offered in **1 of 12** (104A: 1 of 12); the hypothesis was "more than 1".
- **H3 met:** no offered option is outside the stage file's bounds (120 latency options checked by code).
- **H4:** over the 22 found variant matches (agent_cdc 12, hand_ref 9, all3 1) the range's high end was 0 above the measurement in 14 and 1 above in 8 (all 8 in the blind arm B of P1 and P2; the same 0 to 1 as 104A); every found range contained the measurement.
- **S2 (no regression):** `agent_cdc` 12 of 12 (twice offered by a splitter part because the model had not offered `cross_go` alone); `hand_ref` 9 of 12 offered (104A: 9; the offline replay had predicted 11).

## The finding behind the nulls: availability versus the menu

With the combiner's cap of four lifted (every valid combination; the same unchanged scoring; code only), the splitter makes the pair available:

| variant | 104A offered | 104B offered (cap 4) | 104B available (cap lifted) |
|---|---|---|---|
| agent_cdc | 12 | 12 | 12 |
| hand_ref | 9 | 9 | 12 |
| agent_both | 0 | **0** | **6 of 12** (arm A: 5 of 6; blind arm B: 1 of 6) |
| all3 | 1 | **1** | **6 of 12** |

- Where it is not available the model never named `decide` anywhere (mostly the blind arm B), or offered no bundle to split. The splitter cannot create a stage the model does not mention; no bundle was refused for coupling in the live runs.
- Why the available options are not offered: the parts all tie (each 0 to 1 clock), and the combiner's rule (best of each size, cap four) picks among ties by the model's order. This was visible offline before the live runs (`REPLAY.md`: offered 0 of 12 for agent_both, available 8 of 12) and was left unchanged on purpose, so the live runs test the pre-registered rule. A ranking or menu rule that does not depend on the order of ties is the next fix; it needs a new pre-registration.
- The replay (development data, seen before the pre-registration) and the live runs agree in kind: available is high for arm A, low for the blind arm; offered is near 104A's.

## Records

- `preregistration.md`, `replay.py`, `REPLAY.md`, `replay_results.json`: the offline replay on the model's own options of the fifteen 104A runs (raw replies: private KB, `results_private/b104a_combiner/runs/`).
- `run_backtest.py`: `run P1|P2 [case [arm]]` (live), `publish <kb checkout>`, `score`. `backtest/RESULTS.md`, `backtest/results.json`: scores; `backtest/runs/*/record.json`: structured records (no option text); `backtest/moved_to_kb.json`: pointer and SHA-256 of every raw file, in the private repository under `results_private/b104b_split/runs/` (KB PR #82).
- Run conditions: Sonnet (`claude-sonnet-5-5`) through the `options` purpose (endpoint `claude_code`), Claude Code 2.1.321 as a pinned copy (SHA-256 `426c3381...bf61f`), auto-update off, version checked before every run; P1 prompts at KB `38708ce6`, P2 at `00acde95`; 15 of 15 runs exit 0, none re-run. Weekly usage 47 % before and after (the usage report rounds to whole percent).

## Reproduce

```
python3 -m pytest agent/tests/test_104b_split.py agent/tests/test_104a_combiner.py agent/tests/test_104_options.py     # needs the private prompts (FDA_PROMPTS_DIR) for some tests
python3 results/104B_split/replay.py <private KB checkout>/results_private/b104a_combiner/runs
python3 results/104B_split/run_backtest.py run P1 ; python3 results/104B_split/run_backtest.py run P2                      # needs FDA_ACCESS_KEY, the private prompts, claude 2.1.321
python3 results/104B_split/run_backtest.py publish <kb checkout> ; python3 results/104B_split/run_backtest.py score
```
Public run records are added with `git add -f` (the folder name `runs/` is git-ignored).

## Known gaps and limits

- Offered results are unchanged from 104A; the gain is in availability, which is a secondary, labelled measure (the same scoring on a record with the cap lifted), not the pre-registered primary.
- Part ranges are bounds (0 to the stage file's removable clocks), not predictions; their risk text is the bundle's. Gains are sums of ranges; interactions (for example `cross_go` earlier plus `decide` combinational) are not modelled.
- The coupling rules are fired only by planted tests: today's stage files have no `coupled_with`, and no live bundle had a coupled pair. Rule 3 (an interface change on a component none of the bundle's stages live in) stopped splits in the replay (two 104A bundles); in the live runs none.
- k = 3 per arm: no significance claims. One model (Sonnet) and one design.
