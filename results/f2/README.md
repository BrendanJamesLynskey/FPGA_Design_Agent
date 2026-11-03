# results/f2

Brief 05a: the agent core driven directly (no LLM) on T1 with real tools, by `python -m agent.core.smoke --hardware --record agent/tests/fixtures/t1_episode.json`.

| File | What |
|---|---|
| `core_smoke.json` | Phase 1: the scripted episode clarify -> ... -> bitstream through the core (lint, Icarus simulation, formal, check_constraints, Vivado to `post_synth`, then to the bitstream, gates, reports), with each step's time; the gates compared with `results/ultrafast/t1_dimmer_counter_base.json` (identical apart from `build_dir`). Phase 2: ILA build, `program` and `bringup` on the board with the policy checks active (stage, `power_ok` on wall power, budget), then a flash request that was refused. |
| `core_smoke_trace.jsonl` | The trace of that run (model-free: tool records only). |
| `core_bringup.json` | `flow/bringup.py`'s result for the run (same format as `results/f0b/t1_dimmer_counter_bringup.json`, which is left as committed). |

## Brief 05b: the Deep Agents agent, live with luna (`openai/gpt-6-luna`, OpenRouter, data collection denied)

Spend by key usage: $0.6427 for the whole brief (91.676994 -> 92.319662), within the $3 cap; see `results/spend_ledger.csv`.

| File | What |
|---|---|
| `agent_luna_run1.json` | `python -m agent run designs/t1_dimmer_counter/spec.md --interview oracle --review off`. **Null:** stages 0 and 1 passed. In 4 visits stage 2 never passed: the model's cocotb tests against its own blind model kept failing and the verification gates were never reached. No bitstream, so no board bring-up. 277 model calls, 7.78 M tokens, $0.2172 provider-reported, 0 unreported. The interview asked 8 questions; the oracle answered 1 and 7 took their defaults. |
| `agent_luna_run2.json` | The same with `--review on`; every decision was a scripted planner reply (not the owner). A **live rewind from stage 2 to stage 1** restored the files hash for hash (`verified: true`), and the run went on from stage 1. It stopped at stage 2 like run 1. The brief's rewind 6 -> 2 was not reachable. $0.0955. |
| `rewind_real_dcp.json` | Rewind on a copy of T1 with the real Vivado checkpoints. Stage 2 had `post_synth.dcp`; stage 6 added `post_route.dcp`, overwrote `post_synth.dcp` and edited the RTL. Rewinding to 2 restored `post_synth.dcp` byte for byte (SHA-256 equal), removed `post_route.dcp`, reverted the RTL and matched the manifest. Vivado 2025.2 opened the restored checkpoint (top `t1_dimmer_counter_top`, 1235 cells). |

## Brief 05c: agent fixes and the luna re-run

Spend by key usage: $0.2308 (92.321792591 -> 92.552426941), within the $1 cap; see `results/spend_ledger.csv`.

| File | What |
|---|---|
| `agent_luna_run3.json` | The same smoke as run 1 (`--interview oracle --review off`) after the four 05c fixes. **Null again at stage 2 (4 visits), but the failure moved:** the spec is valid YAML with integer cycle-count timing parameters, the model contract gate passes, and the cocotb bench now runs against the RTL and fails there. Run 1 died at 0 ns on a model/test API mismatch. The oracle answered 5 of 10 questions. No bitstream, so no bring-up. 271 turns, 6.89 M tokens, $0.2211 provider-reported, 0 unreported. An earlier attempt (`$0.0097`) stopped at stage 0 on a too-strict schema of mine (list-valued `timing`), fixed before the re-run. |

## Brief 05c: the Claude Code arm smokes (Max plan, no OpenRouter spend on the agent)

Headless `claude -p` 2.1.316, T1 dimmer, `--interview oracle --review off`, no prompt tuning. Cost is not reported by the plan: `plan_cost_estimate_usd` is Claude Code's own estimate. The only OpenRouter use is the luna spec oracle answering interview questions.

| File | What |
|---|---|
| `agent_cc_haiku_t1.json` | `--cc-model claude-haiku-5-5`. **Null at stage 1** (board-and-device-planning): 5 visits, `stage 1 visited more than 4 times`; no `build.yaml` passed `check_constraints`. 83 turns, 404 s, 6 CLI calls, plan estimate $0.0825, weekly usage 7% -> 7%. The init event lists only our three MCP tools and no skills or slash commands. |
| `agent_cc_opus_t1.json` | `--cc-model claude-opus-5-5`. **Null at stage 2** (rtl-design-creation): passed stages 0 and 1, 5 stage-2 visits without a passing simulate. 167 turns, 2324 s, 15 CLI calls, plan estimate $8.71, weekly usage 7% -> 8%. The gates tool crashed on a list-valued `registers` spec (`flow/verif_gates.py`), and the cocotb bench failed against the RTL (cause clipped). |

## Brief 05c follow-ups: reruns after the harness fixes

Fixes before these runs: one canonical spec shape (the gates crash), one design-path convention, a structured first failure from `simulate`. New files; the first-round files above are kept.

| File | What |
|---|---|
| `agent_cc_haiku_t1_run2.json` | Claude Code, `claude-haiku-5-5`. **Null at stage 1** again (5 visits), but the path errors are gone. Cause: the model (own port names and guessed pins in `design.xdc`; `check_constraints` reported FDA-CON-1/3/4 each visit and it did not converge). 75 turns, 329 s, plan estimate $0.0761, weekly usage 8% -> 8%. |
| `agent_cc_opus_t1_run2.json` | Claude Code, `claude-opus-5-5`. **Null at stage 2.** Simulation passed on a visit (a first for the arm); the stage failed at V1: verilator `-Wall` UNUSEDSIGNAL in the RTL, an invalid YAML flow sequence in `verif/testplan.yaml`, and a later bench rewrite that failed simulate. 180 turns, 2883 s, 16 CLI calls, plan estimate $9.87, weekly usage 8% -> 9%. |
| `agent_luna_run4.json` | Deep Agents, luna, `--interview oracle --review off`. **Null at stage 2** (stage 1 passes). Gates stopped at V1 `spec_items_traced 5/32`. 268 turns, 2174 s, $0.2246 provider-reported, key usage 92.562367 -> 92.788861 ($0.2265). |

## Brief 05c2: finishing T1 (fixes from the 05b/05c nulls; luna 7 reaches the first bitstream)

Spend by key usage: about $1.23 of the $1.50 cap (luna runs 1-6 $1.0385 from summaries, luna 7 $0.1941); Claude Code runs are plan-billed. See `results/spend_ledger.csv`. The PC crashed at ~18:30 on 2026-11-02 (swap storm during a network switch); one Opus run was interrupted by it.

| File | What |
|---|---|
| `agent_luna_05c2_run1.json` to `agent_luna_05c2_run6.json` (+ `_summary.json`) | Deep Agents, luna, T1, oracle, review off. Each stop is attributed to harness or model in its verdict; runs 1-5 exposed harness defects (stale verif evidence, stage-9 ordering, probes.yaml schema, a prepare.py import, hidden cocotb failures), all fixed with tests. Run 6 is a model-vs-RTL disagreement at stage 2. |
| `agent_luna_05c2_run7.json` | **First run to reach a bitstream through the agent**: stages 0-8 and both stage-9 builds pass every Vivado gate (base 15/15, ILA 16/16, WNS +0.528 ns, 0.14 W, Tj 42.5 C), verification at V1. Paused at stage 9 awaiting hardware approval; the board was not programmed (V2 seeds/V3 have no agent tool). Owner decision pending. |
| `agent_cc_haiku_05c2_run1_crash.json`, `agent_cc_haiku_05c2_run2.json` (+ summary), `agent_cc_haiku_05c2_run3.json` | Claude Code Haiku. Run 1 crashed in the interview (fixed). Run 2 passed stage 1 and stopped at stage 2. Run 3 stopped at stage 1: the model never wrote `build.yaml` and `check_constraints` was blocked on it; tool fix recorded (not rerun live). |
| `agent_cc_opus_05c2_run1.json` (+ summary), `agent_cc_opus_05c2_run2_interrupted.json` | Claude Code Opus. Run 1 passed stage 2 and stopped at stage 3 on a systemd user-bus environment defect (fixed). Run 2 was interrupted by the PC crash and is not a result. |

## Brief 05e: board bring-up of luna run 7

| File | What |
|---|---|
| `agent_luna_05c2_run7_bringup.json` | First agent-designed bitstreams on the Nexys A7 (SRAM only, wall power). Design as written: power_ok, discover, program_base (DONE high), **uart_tests 3/3 pass**, program_ila pass, then **ila_captures fail**: the agent's `hw_checks.py` uses an `OR` trigger on a probe Vivado splits over 4 hw_probes (Labtools 27-3239). A diagnostic copy with `AND` (agent files not edited): both ILA captures pass (counter==10, brightness==90 at position 768), then **still_alive fails**: the agent's RTL hard-wires `.BUILD_STAMP(32'h0)`, so the ILA build reports stamp 0. Harness fixes (PR #17): design dir on the UART-test PYTHONPATH, import/collection errors route to stage 9, `ila.load_capture` handles equal hw_probe names, dry check flags `OR`/constant BUILD_STAMP. |

## Brief 05d: the Taylor additions

`agent_luna_05d.json`: three live luna T1 episodes (`--interview oracle --review off --verif-level V1`) with the new gates active, **all null at stage 2**; $0.5094 by key usage (cap $1). Stages 0 and 1 passed every time and the architecture approval was written as `auto`. Run 1 failed on the model's tests and on two defects of mine (standards rule STD-CDC-01 refused a shell module; a finding in the frozen architecture was routed to the RTL writer), both fixed with tests before run 2. Run 3 passed lint, simulation and V1 (after the proof-method gate caught a formal job that does not exist) and then failed Vivado elaboration of the model's RTL; the build output was not in the RTL writer's repair text, fixed with a test and not rerun. No build reached post-synthesis, so the resource gate, the post-synthesis standards rules and the sign-off table were not exercised live.

`scripted_review_on_05d.json`: the scripted review-on run (scripted model, fake runner, scripted owner replies, no spend): the architecture gate pauses, a hand edit made while stage 2 is paused is committed as `owner` and listed in the ledger. `review_pages_05d/`: screenshots of the upgraded review pages in light and dark, desktop and phone (390 px, no overflow, no page error). `stage2_*` is built by `tools/review_demo.py` from the T1 reference design's real evidence; `scripted_stage1_*` is the scripted run's own page (its gates are the scripted runner's).
