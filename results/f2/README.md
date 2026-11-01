# results/f2

Brief 05a: the agent core driven directly (no LLM) on T1 with real tools, by `python -m agent.core.smoke --hardware --record agent/tests/fixtures/t1_episode.json`.

| File | What |
|---|---|
| `core_smoke.json` | Phase 1: the scripted episode clarify -> ... -> bitstream through the core (lint, Icarus simulation, formal, check_constraints, Vivado to `post_synth`, then to the bitstream, gates, reports), with each step's time; the gates compared with `results/ultrafast/t1_dimmer_counter_base.json` (identical apart from `build_dir`). Phase 2: ILA build, `program` and `bringup` on the board with the policy checks active (stage, `power_ok` on wall power, budget), then a flash request that was refused. |
| `core_smoke_trace.jsonl` | The trace of that run (model-free: tool records only). |
| `core_bringup.json` | `flow/bringup.py`'s result for the run (same format as `results/f0b/t1_dimmer_counter_bringup.json`, which is left as committed). |
