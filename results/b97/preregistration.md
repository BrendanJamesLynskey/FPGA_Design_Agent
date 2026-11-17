# Brief 97 agent before/after: protocol (written 2026-11-17 12:36, before the first paired run finished)

Question: do the latency tools and the skill text change what the agent achieves on the same design with the same budget?

- Design: `designs/b96_kr260_10g` at commit `9f4305aa26bab5c69ecbca8312374960d623ede2` (a fresh git worktree per run; only `rtl/*.sv` is edited).
- Arms: **A1** = file tools + `edit_file` + `measure` + `latency_path` + `latency_budget` + the skill text (private KB, `prompts/latency/`). **A0** = the same minus the
  two latency tools and the skill text (the agent as it is on main: it must find the path from the RTL). Same prompt skeleton and task text.
- Model: `openai/gpt-6-luna` (OpenRouter, provider-reported cost, `data_collection: deny`) for every run. k = 2 runs per arm (A0_1, A0_2, A1_1, A1_2).
- Budget per run: at most 3 visits, 18 model turns per visit, USD 1.00; stop after two visits with no kept change. `measure` at most 3 times per visit.
- Outcome (the flow's, never a model's): final measured tick-to-trade clocks of the bench-and-twin-passing design (baseline 11). Secondary: visits and
  dollars to the first kept change, number of reverted attempts, whether the kept change survives the post-route build (slack and utilisation).
- Comparison: per arm, the clocks of the 2 runs; stated as a difference with no inference beyond "k = 2" (no significance claim is possible).
- Known confound, stated before the runs: the skill text names techniques (merging stages, shortening a crossing, starting from the earlier event),
  so A1 is partly told what to try; the comparison measures the tools-plus-text bundle, not the tools alone. A0 reading `docs/design.md` can see the
  register table, which A1 can see too.
- Before this protocol: two smoke runs (`smoke_A1`, `smoke2` on the same commit and on its predecessor) fixed the loop's mechanics (an `edit_file` tool was
  added after a whole-file rewrite in the first smoke failed the bench). Their results are reported as smoke, not as part of the comparison.

## Addendum, 2026-11-17 13:06 (written before the round-2 runs finished; round 1 had ended: all four runs reached 9 clocks with the same two edits)

Round 1 could not separate the arms: the bench-gated space of easy changes was exhausted by both. Round 2 starts from the round-1 result so that the
next change is harder to find. Everything else as above (model, budget, k = 2 per arm, outcome, no inference).

- Start state: commit `9f4305aa` with `designs/b96_kr260_10g/rtl` replaced by the round-1 final RTL (`designs/b96_kr260_10g/lat_agent_both/rtl`: `trade64.fire` combinational,
  `u_p_go` `REG_OUTPUT` 0; 9 clocks) and the stage file updated by hand for that structure (decision register 0 clocks, crossing 3 clocks); the exact overlay is
  `results/b97/round2_start.patch`. Baseline 9 clocks.
- What a win looks like: fewer than 9 clocks with the bench and the twin passing. The one such change known to the planner of this experiment is the hand
  reference's (the order frames only start the MAC one clock early, `lat_hand_ref`), which both arms' round-1 attempts missed because their version started *every*
  frame early and failed the cut-frame bench.
- The expected result is a null; it is reported as one.
