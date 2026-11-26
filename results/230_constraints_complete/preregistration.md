# Pre-registration: brief 230 labelled arm (constraints complete before synthesis)

Written 2026-11-26 09:47 GMT (from `date`), before any agent run of this arm. Not edited afterwards: a correction goes in a dated addendum at the end.
Brief 230. Control: the recorded arm 2 of brief 224 (`control_224_arm2.json`, from `runs/` of the 224 worktree).

## Intervention (one thing, labelled)

The branch `b230-constraints-complete`: the flow writes the constraints it knows (`known_pre.xdc`, `known_post.xdc`), a build is refused before
Vivado when a top port has no constraint (FDA-CON-14), and the gates tool explains unconstrained endpoints with the line to add.
No prompt text changed. Everything else is the agent at origin/main 70d53121 (the control ran at b1394eed; the changes between them are
listed in the report: this is not a like-for-like agent).

## Runs

- Designs: `pilots/224/p4_fir_dsp`, `p5_async_fifo`, `p6_glitchfree_mux` (the three designs of 224's arm, specs unchanged), 3 independent runs each, in the order run 1 of each design, then run 2, then run 3.
- Settings as 224's arm: `--board kr260 --review off --interview off --verif-level V2 --max-usd 12 --budget-scale 3.5`, model config `{"default": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}`,
  knowledge repository at the same pin as the control (5e2eab8). Not `--harness claude_code`: the control used the default harness with the anthropic_api endpoint, and a comparison needs the same settings (the brief's own words: "same settings as 224's arm").
- Cap: 50 USD real (token cost at list prices as in 224), checked before each run; a run that could pass it is not started. A run stops at its own 12 USD cap or the stop rules of the agent; that is an outcome, not an intervention.
- Heavy slot per run through `take_heavy_slot.sh`, `FDA_HEAVY_SLOT` exported, `systemd-run --user --scope -p MemoryMax=7G`.

## Outcomes (graded first; pass rate second)

1. **Primary: stage-3 (constraints) visits per run**, from `run_record.json` stage_visits (control: 4, 4, 0, 2, 4, 0, 0, 4 for the 8 runs; mean 2.25, 5 runs entered stage 3).
2. Furthest stage reached (ordinal 1 to 9), per run.
3. Real USD per run (provider-reported usage).
4. Secondary: runs that reach a bitstream; runs stopped on `post_synth_no_unconstrained_endpoints`; runs stopped on a stage visit limit.
5. Descriptive: the stop reason of every run.

## Power, stated in advance (rules of brief 226)

3 designs by 3 runs = 9 runs against the control's 8: a paired comparison has n = 3 design pairs. A binary outcome (bitstream reached: control 1 of 8) cannot show anything below an
effect of about 50 points. The graded primary (stage-3 visits, control sd about 2 over 8 runs) can show a difference of about 2 visits per run only if it is consistent across the three designs;
anything smaller is not detectable. The result is therefore **illustrative**: it reports numbers and stop reasons, not a significance claim. The control ran an older agent (see above) and the same
pin, so a difference is a difference of this branch plus the changes between the two agents.

## Stopping and nulls

State nulls first in the report. If the arm is stopped by the cap before the 9th run, the report says which runs were not made. A run that stops for a reason unrelated to constraints (a reply cut off, a standards loop) is
counted as it is. Interventions during the arm: none.

## Addendum 2026-11-26 10:49 GMT (from `date`), before any run

origin/main moved while this was built: brief 234's PR #351 (4ee72255) merged. The branch now contains it (a merge commit), so the arm's agent also has 234's changes (writing limit 64000, turn cap by design size, fresh visits after a route back,
stop diagnosis); the control ran without them. The intervention is therefore "brief 230 plus brief 234", and any difference cannot be attributed to 230 alone. Nothing else changes. Knowledge pin unchanged (5e2eab8).
The code is frozen from here to the end of the arm; the agent_sha of each run is in its record. Unit tests, test_99_prompts and doccheck were run before this addendum.

## Addendum 2026-11-26 12:35 GMT (from `date`): the first run found a defect; the arm restarts

The arm's first run (p4 run 1, agent 8685b4556d5f, record `pilots/230/p4_fir_dsp/v1_aborted_run1`) stopped at 7.50 USD on `post_synth_exceptions_clean`:
`set_false_path -from [get_clocks usr_cclk]`, a line the flow wrote into known_pre.xdc, was reported EXC-IGNORED ("Totally overridden path by FP 7": the `xpm_cdc`
macro the design reads the USR_ACCESS word through already cuts those paths), and the model cannot edit the flow's file. That is a defect of the intervention, not an outcome of the model.
Fix (committed before any further run): the flow no longer writes a false path from `usr_cclk`; after a failed gate with EXC-IGNORED the `gates` output says which flow
files exist and how to make a flow line go away. Also in this commit: flow/build_cache.py keys the flow-written XDC files by content and ignores the directory in their paths (CI test_33 failed without it).
Decision: the aborted run stays in the ledger and counts toward the 50 USD cap; the arm restarts from p4 run 1 with the fixed agent, so the nine runs of the arm all use one version.
The aborted run is reported separately as "v1, aborted", not as an arm run. Everything else in this pre-registration is unchanged. The code is frozen from here to the end of the arm.

## Addendum 2026-11-26 15:03 GMT (from `date`): second defect; the arm restarts again

The v2 run of p4 run 1 (agent a9e58791, record `pilots/230/p4_fir_dsp/v2_aborted_run1`, 7.77 USD) reached stage 4 once, then stopped: `stage 1 visited more than 4 times; last failing gate: check_constraints failed`.
The stage-1 exit check runs `check_constraints`, which now also reported FDA-CON-14 (the design's top had two clock ports, `clk_25` and `clk25`, only one constrained: a true finding); the stage-1 role cannot fix
constraints, so the stage looped. Fix: `check_constraints` reports FDA-CON-14/15 only from the constraints stage on; the `build` tool still refuses to start Vivado on one. The aborted run stays in the ledger and in the cap
(now 15.27 USD spent before the restart, so about 34 USD, about four runs, remain). The arm restarts as v3 from p4 run 1; its runs are the arm. Everything else is unchanged; code frozen again.
