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
