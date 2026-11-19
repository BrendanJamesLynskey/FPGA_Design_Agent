# results/104A_combiner: the deterministic combiner for strategy options (brief 104A)

Brief 104's generator offers single changes and, in 12 recorded runs, never the cumulative ones (`agent_both`, `all3`, `hand_ref`). Brief 104A adds a combiner in code (`flow/options/combine.py`): it builds
cumulative options from the options that passed the checks, composes the gain bound by code, validates each result with the same per-option checks, ranks and caps. Rules and limits:
[docs/strategy_options.md](../../docs/strategy_options.md), section "The combiner".

## Status (read first)

- **The pre-registered live back-test was NOT run.** The agent's access gate needs `FDA_ACCESS_KEY`; it was not set in the executor's environment, and copying the key file into the worktree was refused by the permission classifier. The runner is ready
  (`run_backtest.py`): one command per prompt set, once the key is in the environment. There are therefore **no live results for the combiner in this folder**.
- What was done instead is labelled **supplementary**: the combiner applied, offline, to the single options that the twelve recorded brief-104 runs offered (`replay.py`, no model call). Result below.

## Records

- `preregistration.md`: the question, the combiner's rules, the arms, the two prompt sets (P1 pinned, P2 the original brief 104 prompts), the scoring and the replay; written and committed before any option was combined.
- `run_backtest.py`: `run P1|P2` (live, needs the key), `publish <kb checkout>` (raw replies to the private repository under `results_private/b104a_combiner/runs/`, public `record.json` with structured fields and `moved_to_kb.json`), `score`.
  The fixtures, the truth files and the scoring code are brief 104's, read in place (`results/104_strategy_options/backtest/`, `flow/options/backtest.py`; a test pins the scoring file's SHA-256).
- `replay.py`, `replay_results.json`, `REPLAY.md`: the supplementary replay (structured fields only; no option text).

## The replay result (supplementary, not a new model call)

Each recorded run's singles, then the combiner, then the unchanged scoring (counts of three runs per arm; "named" = agent_cdc, agent_both, all3):

| case / arm | named found before | after | agent_cdc / hand_ref / agent_both / all3 found | origin of the match |
|---|---|---|---|---|
| 10G latency, A | 1, 1, 1 | 1, 1, 1 | 3 / 1 / 0 / 0 | agent_cdc: model; hand_ref: combiner |
| 10G latency, B (blind) | 1, 1, 1 | 1, 1, 1 | 3 / 2 / 0 / 0 | same |
| 10G latency, A2 (exploratory prompt) | 1, 1, 1 | 1, 1, 1 | 3 / 3 / 0 / 0 | same |
| 10G latency, B2 (exploratory prompt) | 1, 1, 1 | 1, 1, 1 | 3 / 1 / 0 / 0 | same |
| c16 closure, A | | | not composable (a slack gain does not add) | no combined options |

- **`agent_both` and `all3` were not found in any of the 12 runs.** The combiner found `hand_ref` (cross_go + fs_start; measured cut 2) in 7 of 12 runs, always as a combined option and always with the measured 2 inside its range (the range's high end was 0 above the measurement in six of those and 1 above in one).
  The named-variant count did not change.
- **Why:** in all 12 runs the model offered `cross_go` alone, but never `decide` alone: it always bundled `decide` with `fs_start` and `mac_preamble` (or more) in one option. `agent_both` is cross_go + decide, so the combiner has no `decide` single to add. It
  combines what the model offers; if the model bundles stages, the individual stages are not available. Two ways to fix this, neither done (the combiner rule was pre-registered and not changed after seeing this): ask the model for one option per stage (a private prompt change), or split a bundled option into
  per-stage options in code with the stage file's bounds.
- The combined options for the 10G case are flagged as contract changes needing the owner's approval (they span components and include a clock crossing), by code.

## Reproduce

```
python3 -m pytest agent/tests/test_104a_combiner.py agent/tests/test_104_options.py        # needs the private prompts (FDA_PROMPTS_DIR) for the generator and CLI tests
python3 results/104A_combiner/replay.py <private KB checkout>/results_private/b104_options/runs
# live (needs FDA_ACCESS_KEY, the private prompts, claude 2.1.321):
python3 results/104A_combiner/run_backtest.py run P1 ; python3 results/104A_combiner/run_backtest.py run P2    # P2 with FDA_PROMPTS_DIR at the private commit 00acde95
python3 results/104A_combiner/run_backtest.py publish <private KB checkout> ; python3 results/104A_combiner/run_backtest.py score
```
Public run records are added with `git add -f` (the folder name `runs/` is git-ignored).

## Known gaps and limits

- No live run of the combiner (above). The replay uses singles produced before the combiner existed.
- The combiner only combines what the model offers; bundled stages cannot be separated.
- A composed gain is a sum of ranges, not a simulation of the combination; interactions (for example `cross_go` earlier plus `decide` combinational, which the 97 review noted narrows the bus margin) are not modelled. The measured replacement only applies to a design whose
  stage file has the stages of an earlier run.
- `designs/b96_kr260_10g/prior_runs.yaml` records the 97/97C variants, but today's stage file describes the rate-matched chain (no `cross_go`), so for that design they are listed and not used; a stage file for the default 97C build would activate them.
- Ranking keeps one combination per size plus the next best; a user may want a different one (the others are listed under `combiner.not_composable` as "valid, not in the best four").
