# results/222_permission_modes: one real Claude Code run per permission mode (brief 222)

What this folder holds: the permission records of four real `--harness claude_code` runs of one small design (a 4-bit Gray-code counter on the Nexys A7 100T,
spec in the executor's scratch folder, `--interview off --review off --verif-profile prototype --max-usd 2`), one run per mode of
[docs/agent.md](../../docs/agent.md#permission-modes-brief-222). It measures what each mode asked and did. It does not measure the design: none of the four reached the
board step, so nothing here says anything about hardware.

Dates: 2026-11-25, between 18:44 and 20:54 (local, GMT). Code: this branch at the commit that holds this folder. Vivado 2026.1 for the stages that built.
No board, programmer or instrument was touched; no run reached stage 9's hardware pause.

## Records

- `records/<mode>_permissions.jsonl`: the run's decision log, every row: when, action, outcome (allowed, asked, granted, refused, approved, denied), who or which rule, stage.
- `records/<mode>_summary.json`: from the run's `summary.json`: stages visited, the stop reason, the permission block (mode, source, each distinct decision with its count), and the
  `config.json` permission spec the run started with. The Plan one also holds the run's `plan_estimate`.
- The runs themselves (`runs/<id>/`) are not committed (house rule: run directories stay out of the repository).

## Results

| Mode | Run | Model | Stages visited | Stop | Asked (stage: action) | Granted by | Distinct decisions logged |
|---|---|---|---|---|---|---|---|
| Plan | `20261125-184458-c031` | claude-haiku-5-5 | 0 0 1 1 | plan complete: the architecture is written and waiting for you; approving it is denied by mode plan. Resume in | nothing | nobody was asked | 3 (5 rows) |
| Ask | `20261125-200822-eeed` | claude-sonnet-5-5 | 0 1 1 2 2 2 3 4 5 6 7 8 9 9 9 9 9 | stage 9 visited more than 4 times; last failing gate: bitstream (debug build with the ILA): did not run | 0: use_knowledge_bank, 1: approve_architecture, 2: edit_design_files, 2: run_vivado | granted by owner (scripted answer) | 43 (64 rows) |
| Auto within limits | `20261125-193422-f677` | claude-sonnet-5-5 | 0 1 1 2 2 3 4 5 6 7 8 9 9 9 9 9 | stage 9 visited more than 4 times; last failing gate: bitstream (debug build with the ILA): did not run | nothing | nobody was asked | 27 (43 rows) |
| Full auto | `20261125-201049-78e6` | claude-sonnet-5-5 | 0 0 1 1 2 2 2 3 3 3 3 3 | stage 3 visited more than 4 times; last failing gate: post_synth:post_synth_no_unconstrained_endpoints (input  | nothing | nobody was asked | 10 (32 rows) |

How the questions were answered: a shell loop (not committed; a scratch file) answered every permission question "allow" and every review "approve", stopped at a hardware
approval (none was reached), and recorded the answer as `owner (scripted answer)`. The Ask run paused on two permission questions (stage 0; stage 2, which combined two actions) and on a review at the end of each stage.

What each run shows:

- **Plan** ran stages 0 and 1 (about 87 s of agent time), wrote the architecture files and `plan_estimate.json`, was **never asked anything**, left the architecture unapproved and stopped with
  `plan complete`. Its decision log has 5 rows: the knowledge bank allowed by the mode (four times, two stages, two visits each) and `approve_architecture` denied by the mode.
  The plan estimate (upper bound: stage limits and run caps, not a prediction) is in `records/plan_summary.json`.
- **Ask** stopped for a permission at stage 0 (knowledge bank), at the stage 1 review (the architecture, with `approve_stage`: one review interrupt) and at stage 2 (edit design files and Vivado, in one question: the stage-2 gate
  synthesises once simulation passes). After those grants it asked nothing more before stage 9, except the nine per-stage review approvals (`approve_stage` approved 9 times), and ran simulation without asking (`run_simulation`
  allowed by "mode ask", 4 rows).
- **Auto** was never asked anything. Its log has the knowledge bank, the edit, the simulation and Vivado allowed by "mode auto" at each stage it entered, and the architecture approved by the mode.
- **Full** (run with `--stop-after 8`) was never asked anything either and ended at stage 3 (a constraints gate failed on four visits), so it did not reach the stages where Full differs from Auto.

The board decisions (hardware approval asked in Ask and Auto; allowed by rule in Full) are **not** shown by these runs: they are tested in `agent/tests/test_222_permission_modes.py` with a scripted model and a fake
runner standing in for the programmer (the same stand-in the repository's episode test uses).

## Known gaps and limits

- **No run reached the stage-9 hardware pause.** Ask and Auto stopped at stage 9 on a failing debug (ILA) build, Full at stage 3 on a constraints gate; Plan stops at stage 1 by design. These are failures of the agent's design
  work, not of the permission code (the audit logs show no refused tool call in the final four runs), but they mean the board part of each mode is evidenced by tests with mocks and not by a run.
  The ILA-build failure is the same in two runs and is listed in the report as a follow-up.
- Full was run with `--stop-after 8` on purpose, so that Full auto could not touch the board.
- `spend_model_money` was never asked in these runs: a Claude Code run on the subscription reports no cost to the meter, so the $1.00 threshold is never reached (the stage caps on turns and time apply). The gate is tested
  with a scripted model that reports a cost.
- One design, one model per mode (Plan used Haiku; the rest Sonnet, after two earlier Ask attempts, below), one run each: this shows behaviour, not a rate.
- An earlier Ask run (Haiku, default verification) and two more (Haiku and Sonnet, prototype profile) stopped at the stage-2 visit limit. The cause was found: the stage-2 gate runs a Vivado synthesis, which my first version of
  the code had not listed among the stage's needs, so the tool gate refused it ("permission-not-granted", four times in the Haiku run's audit log). The code was fixed (`stage_actions`) and the Ask run above is the run after the fix.
  Those three runs' records are not committed.
- Times and costs: wall times in the summaries are those of the last process of a run (a resumed run has several); the plan-cost figures are Claude Code's estimates on the subscription, not a bill.

## Reproduce

Needs the access key, the private prompts (`FDA_PROMPTS_DIR`), Vivado 2026.1, a heavy slot for the Vivado stages, and the Claude Code CLI on the plan. With a one-page spec of the design in a folder of its own:

```
python -m agent run <spec.md> --name p222_gray --harness claude_code --cc-model claude-sonnet-5-5 --interview off --review off --verif-profile prototype --max-usd 2 --permissions <plan|ask|auto|full>
python -m agent resume <run-id> --reply '{"decision": "allow"}'     # each permission question; {"decision": "approve"} for each review (Ask)
```

Plan used `claude-haiku-5-5`; Full added `--stop-after 8`. The run directory's `permissions.jsonl` is the decision log copied here. A different design or model will stop at other places: the stage gates are the agent's own.
