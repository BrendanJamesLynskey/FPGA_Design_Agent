# Pre-registration: the per-stage splitter back-test (brief 104B)

Written 2026-11-20 (local time) before any live call of this brief. It is committed together with the frozen code (`flow/options/split.py`, `flow/options/combine.py`, the CLI and tests). After that commit,
neither the splitter nor the combiner, the prompts, the scoring code (`flow/options/backtest.py`, unchanged from brief 104; its SHA-256 is pinned by a test) or the case files change before the runs are done.

## Question

Brief 104A's combiner found `hand_ref` in 9 of 12 b96 runs and `all3` once, but `agent_both` in 0 of 12, because the model never offered `decide` alone: it always bundled it with other stages. Does splitting bundles into per-stage
options in code, from the stage file's bounds, make `agent_both` and `all3` appear, with a gain range that contains the measurement, **without** the analysis or the splitter seeing the measured results?

## The splitter (fixed here; `docs/strategy_options.md`, "The splitter")

- Input: the model's options that passed every check. A **bundle** is a latency option touching two or more stages. Output: per-stage **parts** (`origin: splitter`, ids `S1`...), at most 8 in all, then the 104A combiner (version 2: the pool is the model's unsplit options plus the parts, at most ten; the parts of one bundle together count at most that bundle's high end; **the cap of four combined options and the ranking are unchanged**).
- Part bound by code: `high` = the checker's ceiling for the unit's stages, at most the bundle's own high; `low` = `max(0, bundle low - the other units' high ends)`. A part that is not backable is dropped with a reason. Scope: the unit's components only. Each part passes `schema.check_single`.
- Coupling: stage-file `coupled_with`, or one bundle interface change on a component holding two or more of its stages (those stay one unit); an interface change on a component none of the bundle's stages live in stops the split of that bundle. Today's stage files have no `coupled_with`.
- The bundle itself stays offered; in the combiner's pool it is replaced by its parts. A stage set the model already offers alone is not duplicated.

## Back-test (same design as brief 104A; the only change is the splitter)

| case | arm | what the model sees | runs (k) |
|---|---|---|---|
| `b96_10g_pre97`, "lower latency" | A | stages with `technique` and `removable_clocks` | 3 per prompt set |
| `b96_10g_pre97` | B | blind: no technique or removable hints | 3 per prompt set |
| `c16_montgomery_200mhz`, "the design misses timing at 200 MHz: improve its timing" | A | the digest of the failing build | 3 (P1 only) |

Prompt sets: **P1** the prompts pinned in `agent/core/prompts_pin.json` (private KB commit `38708ce6`); **P2** the original brief 104 prompts (KB commit `00acde95`, `FDA_PROMPTS_UNPINNED=1`), case 1 arms A and B only. 15 live runs (9 P1, 6 P2), sequential, Sonnet (`claude-sonnet-5-5`) through the `options` purpose of the model table (endpoint `claude_code`), Claude Code 2.1.321 pinned as a copy of the binary first on the PATH (checklist steps 1 to 3; the version is checked before each run), no Vivado, no board, no heavy slot. None added or dropped after seeing a result, except an infrastructure re-run (CLI timeout or authentication), recorded as such. `_handoff/usage_check.sh` before the first run and between case and arm groups; stop at 90 % weekly (owner decision 21) and hand back with what exists.

## Scoring

The unchanged `flow/options/backtest.py`, on the options the run offered (model, splitter and combiner options alike; the report adds, per found variant, which origin matched). Counts per arm over three runs; no significance claim at k = 3. Nulls first.
The measured values are in `truth/`, which the analysis, the splitter and the combiner never read.

## Hypotheses (primary; from the brief; counted over the 12 b96 runs, offered options, the combiner's cap of four)

- **H1** `agent_both` is found in more than 0 of 12.
- **H2** `all3` is found in more than 1 of 12.
- **H3** No offered option is outside the stage file's bounds (every latency option's high end at most the checker's ceiling for its stages and scope; low at most high). Checked by code on every offered option.
- **H4** The range's high end above the measurement is reported for every found variant, as in 104A (0 to 1 clock above).

Secondary (reported, not pass/fail):
- **S1 availability.** The same unchanged scoring on the options the splitter and combiner could build with the cap of four lifted (every valid combination; code only, run on each run's model options at publish time): how often `agent_both` and `all3` are *available* but not *offered*.
- **S2 no regression.** `agent_cdc` in 12 of 12 and `hand_ref` offered in at least 9 of 12 (104A's level).
- c16 closure: no combined options (slack is not composable), as in 104A; nothing is split (a slack option is not split).

## What the offline replay already says (labelled; development data, not a result of this test)

The splitter and the combiner were applied offline, with no model call, to the model's own options of the fifteen recorded 104A runs (`REPLAY.md`). That replay was seen before this pre-registration: with the cap of four, `agent_both` was offered in 0 of 12, `all3` in 2 of 12 (104A: 1), `hand_ref` in 11 of 12 (104A: 9); with the cap lifted, `agent_both` was available in 8 of 12 and `all3` in 8 of 12 (104A: 1 and 1). The reason the cap hides them: many parts tie on composed gain (each 0 to 1 clock), so the best-of-size rule picks among ties by the model's order. I kept the cap and the ranking unchanged on purpose, as the brief says "the existing combiner", rather than tune them on the same runs. **The expected live outcome is therefore H1 not met, H2 marginal, S1 high**; the live runs test whether live bundles behave like the recorded ones and measure availability on fresh replies. Not claimed: that a combined option is a discovery (it is a menu entry built from what the model offered and the stage file's bounds), or that the gains are predictions (sums of ranges; interactions are not modelled).
