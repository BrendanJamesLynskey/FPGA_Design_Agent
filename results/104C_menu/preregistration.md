# Pre-registration: the order-independent menu rule, fresh back-test (brief 104C)

Written 2026-11-20 (local time) before any live call of this brief, committed with the frozen code (`flow/options/combine.py` version 3, `flow/options/split.py` version 2, `agent/tests/test_104c_menu.py`, the runner and the docs). After that commit, neither the rule, the splitter, the prompts, the scoring code (`flow/options/backtest.py`, unchanged, its SHA-256 is pinned by a test) nor the case files change before the runs are done.

## Question

Briefs 104A and 104B broke the combiner's ties by the model's listing order, which is why the offered menu showed `agent_both` 0 of 12 and `all3` 1 of 12 although the splitter made them available in 6 of 12. Does a menu rule that does not depend on the order of the model's options change what is offered, on **fresh** runs (new model calls, not the 104A/104B records)?

## The rule (fixed here; `docs/strategy_options.md`, "The menu rule")

Ranking of combined options, each key only breaking ties of the earlier ones: measured earlier; higher composed mid-gain; fewer components; no owner approval; **more model support** (sum over the touched stages of how many of the model's own options name the stage); **more timing headroom** (leximin on the stage file's post-route setup slack, a stage without a figure ranks last); a content key (chain positions, components, gain bounds). Pool truncation by content. Splitter bundle order by content. Cap of four, best-of-each-size, the checks and the scorer unchanged.

**History, disclosed.** The rule was argued before any replay. A first candidate with headroom only (no support key) was replayed on the development data (30 recorded runs of 104A and 104B) and regressed `hand_ref` offered (4 of 12 and 3 of 12 on the 104A and 104B options; the 104B rule gave 11 and 9). I then added the support key ahead of headroom, with the argument above, and did not change the rule again after the second replay. The final rule is therefore **development-informed**; the fresh runs below are its test. The development numbers (`replay_*.json`, `REPLAY.md`) are reported as development, not as a result.

## Back-test (fresh runs; same design, arms and prompts as 104A and 104B)

| case | arm | what the model sees | runs (k) |
|---|---|---|---|
| `b96_10g_pre97`, "lower latency" | A | stages with `technique` and `removable_clocks` | 3 per prompt set |
| `b96_10g_pre97` | B | blind: no technique or removable hints | 3 per prompt set |

Prompt sets: **P1** the pinned prompts (`agent/core/prompts_pin.json`, private KB commit `38708ce6`); **P2** the original brief 104 prompts (KB `00acde95`, `FDA_PROMPTS_UNPINNED=1`). 12 live runs (6 P1, 6 P2), sequential, Sonnet (`claude-sonnet-5-5`) through the `options` purpose (endpoint `claude_code`), Claude Code 2.1.321 pinned as a copy (SHA-256 `426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f`, `DISABLE_AUTOUPDATER=1`, version checked before each run), no Vivado, no board, no heavy slot. Fresh means each run is a new model call into a new run directory; 104A/104B replies are not reused. None added or dropped after seeing a result, except an infrastructure re-run (CLI timeout or authentication), recorded as such. `_handoff/usage_check.sh` before each group of runs; stop at 90 % weekly and hand back with what exists.

**Second design.** The brief asks for a second design that has a stage file. None exists: `latency_stages.yaml` exists only for `b96_kr260_10g` (searched on `origin/main` and on every remote branch). The c16 closure case has no stage file and only slack gains, which are not composable, so it exercises neither the splitter nor the combiner and is not rerun. **The limit: one design, one model, k = 3 per arm.**

## Scoring

The unchanged `flow/options/backtest.py` on the options each run offered (model, splitter and combiner). Counts over 12 runs and per arm. Nulls first. Truth is in `truth/` (brief 104), which the analysis, the splitter and the combiner never read.

## Hypotheses (primary; counted over the 12 b96 runs; offered options; cap of four)

- **H1** `agent_both` is offered in more than 0 of 12.
- **H2** `all3` is offered in more than 1 of 12.
- **H3** No offered option is outside the stage file's bounds (high end at most the checker's ceiling for its stages and scope; low at most high). Checked by code on every offered option.
- **H4** The menu is invariant to the order of the model's options: for every run, 24 seeded shuffles of its model options give the same offered splitter and combiner options (content: origin, stages, scope, gain bounds), and the menu recorded at run time equals the rebuild.

Secondary (reported, not pass/fail): **S1** availability with the cap lifted (as 104B). **S2** `agent_cdc` offered in 12 of 12, and `hand_ref` offered compared with 104B's 9 of 12 (a drop is reported as a regression). **S3** on the fresh model options, the 104B rule's menu (offline, same code with the old ordering) for comparison. `in_range` and the high end above the measurement per found variant, as before.

## What the development replay already says (labelled; not a result of this test)

On the 30 development runs the final rule gives, offered: `agent_both` 0 of 12 (104A options) and 1 of 12 (104B options); `all3` 2 and 1; `hand_ref` 6 and 5 (the 104B rule on the same options: 11 and 9 for `hand_ref`, 0 and 0 for `agent_both`, 2 and 1 for `all3`); the menu changed with the order of the model's options in 0 of 30 runs (the 104B rule: 24 of 30). **The expected live outcome is therefore: H3 and H4 met; H1 not met or marginal; H2 not met or marginal; S2 `hand_ref` below 9 of 12.** The reason is in the pool: the model's own bundles name many stages (for example `rx_descramble`), and a truth-blind rule has no basis to prefer `decide`; the cap of four then decides. Not claimed: that a menu entry is a discovery, or that the gains are predictions.
