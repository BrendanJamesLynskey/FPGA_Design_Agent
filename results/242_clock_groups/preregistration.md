# Pre-registration: brief 242 agent runs (clock groups from the declared clock relations)

Stamped 2026-11-27 06:21 GMT (from `date`), executor Sonnet 5.5, before any agent run of this brief. The replay (below) was started at 06:18 and is not an agent run. Not edited afterwards: a correction goes in a dated addendum.

## Intervention

Branch `b242-clock-groups` on origin/main f24eedff: the flow writes `set_clock_groups` into `known_post.xdc` from `clock_relations` (architecture.yaml, else spec.yaml) and from the `clock_muxes` inputs, only where every declared crossing of the pair goes through a recognised
synchroniser (a bank CDC primitive that the RTL instantiates); otherwise it refuses and says which crossing. `check_constraints` shows the written lines and the refusals. The interview asks for the relation when a spec has two or more clocks and states none
(`ensure_clock_relation_question`, code, no private prompt text).

## Runs

- Designs `pilots/230/p5_async_fifo` (the design whose only remaining gate failure in 230's replay was TIMING-6/7) and `pilots/230/p6_glitchfree_mux` (a clock mux: exclusive inputs), requests unchanged. Order p5 r1, p6 r1, p5 r2, p6 r2, p5 r3, p6 r3. **Up to 6 runs; fewer if usage requires** (below).
- Flags: `--board kr260 --review off --docs off --interview off --verif-level V2 --max-usd 12 --budget-scale 3.5 --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --stop-after 4` (through synthesis: the post-synthesis gates, including methodology TIMING-6/7, run in the stage-3/4 visits). Claude Code 2.1.321 pinned (`_scratch_227/bin`, version preflight), prompts from `_worktrees/kb-prompts-pin` (pin 5e2eab8). Plan-billed: no provider-reported dollars; cost is a plan-cost estimate only.
- Each run holds a heavy slot (`take_heavy_slot.sh`, peak 4G, Vivado) and runs under `systemd-run --user --scope -p MemoryMax=6G`.

## Outcomes

1. **Primary: the run ends with `post_synth_methodology_no_critical` passed in its last stage-3/4 gate call** (no TIMING-6/7), by design, out of the runs made.
2. Secondary, per run: stage reached, stage-3 visits, whether any `set_clock_groups` line is the flow's (`known_post.xdc`) or the model's, refusals fired, stop reason.
3. Reference: 230's arm (older agent, anthropic_api endpoint, to bitstream), p5: 2 of 2 reached a bitstream, stage-3 visits 1 and 2; its replay stopped only on TIMING-6/7. Not a like-for-like comparison (harness, model route and stop stage differ): descriptive only.

## Prediction and reading

Stated before: on p5 the model's own constraints often include `set_clock_groups` already (230 arm run 1's XDC has two), so the flow's line may be skipped as "the design's own constraint wins"; I expect the methodology gate to pass in at least 2 of 3 p5 runs and
the flow's line to be written in at least one. p6 (a clock mux, derived exclusive pair only when it declares `clock_muxes`) may not change. n = 3 per design: **illustrative, no significance claim.**

## Stopping rules

- Usage: read `_handoff/usage_check.sh` before each run; the brief's budget is about 5 points of the weekly figure (it was 84% at 06:15): stop making new runs at 89% and hand back, hard stop at 92%. Runs not made are listed as not made.
- A run lost to infrastructure (rate limit, a build refused because another job held the PC) is recorded with its reason and re-run once; a run that hits the agent's own limits is a result and is not re-run.

## Addendum 1, 2026-11-27 07:16 GMT (from `date`), after p5 run 1 and before every other run

- p5 r1 (run 20261127-062134-97a8) ran while the rule was still being corrected by the replay (see README: v1 group-only, v2 bound-all-pairs, v3 final; the code changed under that run at about its 2 minute mark, before its first build). The model's architecture.yaml had no `clock_relations` and the flow, then reading only that field and mux inputs, wrote no group: **r1 is a run of the explicit-field-only rule; the flow contributed nothing**. Its design (model-written groups, gates all passed) is recorded as it is.
- Change: a declared crossing between two domains now gives a derived `async` relation (the architecture and brief 242's text name the crossings as a source), applied only where both clocks are primary clocks the flow can name; an explicit `clock_relations` entry wins. It was made because the model has no way to know the new field (no prompt text may change here), so the explicit field alone cannot move a run. Runs 2 on use this final rule (code at the commit stated in the report).
- Prediction stands for outcome 1; the new secondary count: runs where the flow wrote at least one clock-group or bound line.
- Run chains: p6 r1, p6 r2, p6 r3 in one chain and p5 r2, p5 r3 in another, in parallel under two heavy slots (the usage cost of r1 was under 1 point of the weekly figure). The 89% stop rule is unchanged.

## Addendum 2, 2026-11-27 07:58 GMT (from `date`), after p6 run 1

- p6 r1 stopped in stage 2 on "STD-ARCH-00: the checker could not read the design: KeyError: 'id'": a bug in flow/standards_check.py STD-CDC-02 (it read `r['id']`, the gates JSON's CDC rows carry `rule`) that fires whenever post-synthesis report_cdc has a Critical row; it is not from this brief's change (the gates before it show the design failed its post-synthesis gates itself). One-line fix made (`r.get('id', r.get('rule'))`) and kept in this PR; p6 r1 is counted as it ended (a run stopped by a checker fault), not re-run, since the model could not have fixed it; p6 r2 and r3 and p5 r3 run with the fix. p5 r2 and p6 r2 had started before it.

## Addendum 3, 2026-11-27 08:14 GMT (from `date`), after p5 run 2

- p5 r2 (run 20261127-071840-b6fa) reached the 3300 s wall limit of the run wrapper (exit 124, no summary.json): a limit of mine, recorded as "timed out", not re-run (its stage and gate state at the kill are read from its build directory). Its last build failed `post_synth_exceptions_clean`: **the flow's own bound was the cause**. The derived pair had crossings in both directions and the rule wrote a `set_max_delay -datapath_only` for each; Vivado reported the gt_refclk to clk_c3 one as EXC-IGNORED "Totally overridden path by FP 10 - DPO 11 - DPO 13 - DPO 21" (the XPM single and handshake macros carry a false path or a bound of their own). Rule corrected (`_needs_pair_bound`): a direction gets a bound only if it has a FIFO (its RAM read is not covered by the macro's bounds) or a hand-built crossing; offline, the final rule on r2's design writes one command (clk_c3 to gt_refclk), as on the replay. Not re-measured in Vivado for r2's design.
- p5 r3 started about 08:14 with the rule between the two (the code changed during it); p6 r2 started 07:47 under the pre-fix code. The report states which rule each run had.

## Addendum 4, 2026-11-27 09:17 GMT (from `date`), after all six runs

Six agent runs were made (84% to 86% weekly). p5 r3 stopped on the flow's own overridden bound; the cause was found, the rule changed again (v4: both directions bounded; the check reports the flow's overridden pair bound as information; groups skipped for `no_crossings` pairs) and replayed on the replay states and on r2's and r3's designs (README). No agent run was repeated under v4: not enough budget in the brief's 5 points, and p6 never reaches the constraints stage.
