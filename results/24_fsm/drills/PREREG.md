# Brief 24 drill runs: pre-registration (written 2026-11-11 before the first run)

Development runs, not a scored evaluation: the drills `benchmark/drills/d24_registered_outputs` and `d24_no_extra_latency` are outside every
benchmark split.

- **Arm:** the dev default of the brief 20 drills: `--harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --oracle claude_code
  --oracle-cc-model claude-haiku-5-5 --interview oracle --review off`, Claude Code CLI 2.1.319 (a copy of the version in
  `~/.local/share/claude/versions`, first on PATH; auto-update is off in this session's environment where the runs start), verification level V2, the normal
  run limits. Knowledge bank at the public repo's pinned packs (`knowledge/PACKS.md`): the new FSM skills are NOT in that pin until the
  planner re-pins, so these runs measure the agent **without** the brief 24 skills (an anchor for a later run with them).
- **Runs planned:** 3 seeds per drill, one run at a time, each holding a heavy slot ("Vivado impl") for its whole run. The number actually run is limited
  by slot availability and the 70 % usage stop; whatever is not run is reported as not run, never as a result.
- **Graded by:** (1) the hidden acceptance bench on the agent's `rtl/` (`benchmark/tools/run_task.py`, Icarus); (2) `benchmark/drills/lib/grade_fsm.py`: the lag the pins
  follow and, for `d24_registered_outputs`, that every JB pin is driven by a flip-flop in the routed checkpoint. A seed passes when both pass.
- **Recorded per seed:** the choice (registered decode, lookahead, combinational), whether the agent's own tests reach every state and legal transition (a
  trace-based check on the reference's state names is not possible for the agent's RTL, so this is read from the agent's test list and V3 functional bins), and
  the cost as a labelled plan estimate.
- **Comparisons:** none beyond the per-seed table (3 or fewer runs per drill is not a measurement of a rate). Nulls first.
- **Stopping rules:** stop at 70 % of the 5-hour usage window; a harness failure (CLI version, slot refused) is re-run once and reported.
