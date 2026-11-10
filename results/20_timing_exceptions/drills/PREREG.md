# Brief 20 drill runs: pre-registration (written 2026-11-10, before the first run)

Development runs, not a scored evaluation: the drills are outside every benchmark split (`benchmark/drills/README.md`).

- **Drill:** `d20_slow_fsm_ramp` (part A). Part B drills (ADC/DAC I/O delays, virtual clock, jitter) are not built in this PR.
- **Arm:** the dev default, as in the 07a2 development runs: `--harness claude_code --cc-model claude-sonnet-5-5 --cc-effort
  medium --oracle claude_code --oracle-cc-model claude-haiku-5-5 --interview oracle --review off`, Claude Code CLI 2.1.319 (a copy
  of the installed version, first on PATH; `agent/claude_code_arm/arm.py` accepts it). Verification level **V2** (the level used
  for the 06c runs), so the runs spend on the constraints stage rather than on the V3 mutation runs; the normal run limits
  (`RUN_LIMITS`) otherwise.
- **Runs:** 3 seeds (runs 1-3), one at a time, each holding heavy slot 1 ("Vivado impl") for the whole run, `FDA_VIVADO_MAX=2` so a
  slot-2 synthesis probe of another session does not refuse the agent's build. A run ends at the stage-9 hardware pause (no board).
- **Knowledge:** the knowledge bank at its main commit (the pinned packs, which already hold `xdc-exceptions-right-and-masking` and
  `procedures/ultrafast/constraints`); the run's knowledge-use log must show a constraints skill loaded or searched.
- **Graded by:** (1) the hidden acceptance bench (`benchmark/tools/run_task.py`, Icarus) on the agent's RTL; (2)
  `benchmark/drills/lib/grade_constraints.py` on the agent's routed build. A seed passes when both pass. Recorded per seed:
  the agent's exception lines, the grader's checks, the choice (multicycle or pipeline), any wrong exception the agent wrote
  even if a gate caught it and it was repaired (from the run's build history).
- **Stopping rules:** stop launching at 70 % of the 5-hour usage window; a run that fails for a harness reason (CLI version,
  slot refused) is re-run once and reported.

## Amendment 1 (2026-11-10 18:40, after run 1, before run 2)

- Run 1 (`20261110-172635-9d14`) showed that `load_skill(["constraints"])` returned only
  `vendor/ross_distilled/constraints/xdc-constraints-basics`: `agent/core/bank.py` read one vendor set, so
  `vendor/amd_constraints` (the exceptions, I/O-delay and clock skills) never reached the agent. Runs 2 and 3 run with
  `VENDOR_SETS = ("ross_distilled", "amd_constraints")`; run 1 is reported as the run without those skills.
- Run 1's in-run exception gate read a multicycle dump from an earlier `flow/mcp_paths.tcl` (it failed to parse the
  agent's wrapped `get_cells` query and the gate then ignored the error). Run 1 is graded on a re-dump of its routed
  checkpoint with the final Tcl; dump errors now fail the gate.
