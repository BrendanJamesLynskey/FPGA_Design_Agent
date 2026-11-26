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
