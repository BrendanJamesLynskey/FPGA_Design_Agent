# results/62a_closure: the closure loop and the design-time plan (brief 62A)

Vivado 2026.1, xc7a100tcsg324-1, whole-board builds with the test shell (`flow/run_vivado.sh`, 6 GB scope, heavy slots).
RTL writer: `openai/gpt-6-luna` through OpenRouter (`data_collection: deny`); cost is provider-reported. G1 is always the
task's hidden acceptance bench (`benchmark/tools/run_task.py`, Icarus), never the writer's own test. One run per case: these
are illustrations, not measured rates.

| Folder | What |
|---|---|
| `c13_orig_noplan/` | closure loop on the **original** c13 reference (fixture `agent/tests/fixtures/closure/c13_orig`), no plan |
| `c13_orig_plan/` | the same, with the design-time plan of `c13_plan_stage1/` (plan check in the goal vector) |
| `c13_orig_plan_unguarded/` | the first with-plan run, **invalid**: accepted a design whose core synthesis removed (multi-driven nets); `INVALID.json` says why. It is the record that led to the sim/synth guard |
| `c13_plan_stage1/` | the agent graph's stages 0-1 on c13's `spec.md` with `--design-plan`: spec.yaml, architecture.yaml with `datapaths`, TIMING_PLAN.md (`timing_plan.json` from the KB model at the commit in `kb_commit.txt`; `timing_plan_provisional.json` is what the gate wrote from a provisional model during the run) |
| `c13_write_noplan/`, `c13_write_plan/`, `c13_write_plan_r2/` | the RTL writer writing c13's core from spec.yaml, without and with the plan (`write_summary.json`); `c13_write_noplan/build_not_finished.json` is its build |
| `seed_c14_int8_dot_requant_150mhz/`, `seed_c16_montgomery_mult_200mhz/`, `seed_c11_nco_mixer_200mhz/` | seeded timing misses: development-task reference RTL with the board clock raised (`--clock-mhz`) |

Each closure folder: `history.jsonl` (goal vector before and after, strategy and why, the diff, the delta on every goal,
cost), `summary.json` (stop reason, unmet goals, iterations, cost), `llm_replay.json` (every model call), `rtl_final/`.
