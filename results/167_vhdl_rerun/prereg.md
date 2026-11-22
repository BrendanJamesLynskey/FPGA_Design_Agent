# Brief 167 pre-registration: does brief 153's stage-2 fix explain brief 55's 0 of 4 end-to-end VHDL runs?

Written 2026-11-22 (clock, `date`) by the brief 167 executor (Sonnet sub-agent), **before the first run**. Committed before any run.

## Question and hypotheses

Brief 153 found that the stage-2 plan's "has RTL" test (`agent/graph/run.py` `stage2_plan`) and the closure snapshot looked only at
`rtl/*.sv`. For a VHDL design the plan saw no RTL on every visit, so the Designer (`rtl` role) was told to write fresh, never to repair.
Brief 153 fixed both (`flow.sources.design_rtl`). Brief 55's end-to-end VHDL runs passed 0 of 4.

- **H1 (mechanism).** With the fix (arm B) the `rtl` role repairs on stage-2 visits after the first; without it (arm A) it rewrites.
- **H2 (outcome).** Arm B passes more hidden benches than arm A on the same tasks.
- Null for both: no difference between arms.

## Arms

- **A: code before 153.** Detached worktree at `33896b29` (origin/main at the time; brief 55's VHDL support included, 153 not).
  `/home/brendan/Claude_sandbox/_worktrees/167-armA`.
- **B: code with 153.** Branch `b167-vhdl-rerun`, from `origin/b153-vhdl-parity` (PR #282 is not merged; brief 156 is not in it).
  `/home/brendan/Claude_sandbox/_worktrees/167-vhdl-rerun`. The only agent-graph difference is the two sites above; B also has 153's
  flow-check changes (lint of VHDL by GHDL feeds back the same way; checks read VHDL), which are part of "code with 153".
- Same knowledge bank in both: the private repo at `5e2eab87` (both arms' `knowledge/PACKS.md` pin it; checkout
  `/home/brendan/Claude_sandbox/_worktrees/167-kb`, via `FDA_KNOWLEDGE` and `FDA_PROMPTS_DIR`).
- Brief 55's own records are **not** used as arm A: they ran `openai/gpt-6-luna` through OpenRouter; this brief runs Anthropic
  models on the plan only (brief 167 rule), so a fresh arm A is the only fair control. Brief 55's 0 of 4 is quoted as history only.

## Tasks and runs

- The two tasks brief 55 ran end to end: `t1_gray_stepper`, `t1_sync_fifo_regs` (`benchmark/tasks/<t>/spec.md`).
- Command (identical in both arms, run from the arm's own checkout):
  `python -m agent run benchmark/tasks/<t>/spec.md --hdl vhdl --stop-after 2 --verif-level V1 --harness claude_code --cc-model claude-haiku-5-5 --cc-effort medium --max-usd 0.75`
  (brief 55's flags with the harness changed from deepagents/luna to Claude Code/Haiku; plan-billed, so `--max-usd` is the agent's own
  estimate cap, not a spend).
- **Model set: Haiku 5.5 only** (the cheapest of the allowed Sonnet/Haiku set; every role, `--profile single`). No Fable, no Opus, no OpenRouter.
- **Runs per arm:** the usage left (weekly 88% at 14:40 on 2026-11-22, reset Mon 2026-11-23 01:00) probably allows 1 run per task
  per arm. Order, one run at a time: G-A, G-B, F-A, F-B (G = gray stepper, F = sync fifo), the **round 1**. A **round 2** (same
  order, same flags) only if the weekly reading before it is at most 93%. A round 3 only if at most 91%. If round 1 does not complete,
  the result says so. The target of 3 per arm per task is **not expected to fit**; fewer runs make the verdicts weaker, never stronger.
- Runs are interleaved A then B per task so a drift in the day's load or the CLI hits both.

## Measures (all from committed run records; no model scores anything)

- **Pass:** the task's hidden bench on the run's RTL: `python -m flow.vhdl_score benchmark/tasks/<t> --rtl <design>/rtl`, run from
  arm B's checkout for both arms (the frozen scorer; the same code scores both). Pass = every test passes (as in brief 55).
- **Rewritten against repaired** (H1), from the run's `role_usage.jsonl`: take the `role: "rtl"` entries of stage `rtl-design-creation`
  with `visit >= 2` (the visits after the first). For each, `repair: true` is a repair, `false` a fresh write. Report R (repairs) and
  W (fresh) per run, and the repair share R/(R+W). A run with no second visit contributes nothing to H1 and is listed as such.
  Also reported: `files_written`/`files_changed` of those entries.
- Other facts reported, not tested: the stop reason, stage-2 visits, tool-call counts, turns, wall time, and the plan-cost estimate.

## Decision rules (fixed now)

- **H1 confirmed:** in every arm-A run that has a second stage-2 visit R = 0, and in at least one arm-B run R > 0.
  **Refuted:** an arm-A run has R > 0, or no arm-B run with a second visit has R > 0. **Inconclusive:** otherwise (for example no run reaches a second visit).
- **H2 confirmed:** B's passes exceed A's passes and no task pair has A passing where B fails. **Refuted:** B's passes are not above A's.
  **Inconclusive:** B > A with a reversed pair, or fewer than 2 complete runs per arm. With n this small, any verdict is a direction, not a rate.
- A run that ends NOT RUN or PREFLIGHT_FAIL is not a pass and not a fail; it is reported and re-run once when usage allows.

## Pace, caps and pins (eval checklist)

- One agent run at a time. Each run takes a heavy slot (`take_heavy_slot.sh`, text prefix `167:`, `peak 8G`, text says "Vivado": the stage-2 exit
  needs a Vivado elaboration), under `systemd-run --user --scope -p MemoryMax=8G` and `nice -n 15`. Released only if its text starts `167:`.
- Scoring takes its own light lock `/home/brendan/Claude_sandbox/_scratch_167/score.lock` (noclobber), one run at a time, no heavy slot (GHDL + Icarus only).
- Per-run wall cap 90 min (the run is stopped with the process group if it exceeds it and recorded as such). Stop flag
  `/home/brendan/Claude_sandbox/_scratch_167/STOP`: the driver checks it before each launch.
- Weekly usage (`_handoff/usage_check.sh`) read before each run and about every 30 minutes; at 97% or more: commit, push, report draft, end `BLOCKED:`.
- **CLI pinned:** Claude Code 2.1.321 (in the agent's accepted list), copied to `_scratch_167/bin/claude`, SHA-256
  `426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f`; `_scratch_167/bin` first on PATH; version compared before each launch
  (mismatch: PREFLIGHT_FAIL line, no record, stop flag). `DISABLE_AUTOUPDATER=1` already set in `~/.claude/settings.json`.
- Other tools as found: GHDL from `~/.local/bin/ghdl`, Vivado under `/opt/Xilinx`, repo venv `FPGA_Design_Agent/.venv`; no installs during the runs.
- Records: each run's `runs/<id>/` directory is copied (role_usage.jsonl, run.json-style summary, the design's `rtl/` and `spec.yaml`, no keys) to
  `results/167_vhdl_rerun/records/`. `agent/tests/test_99_prompts.py` runs before any push of them. Private transcripts, if any, go to a Knowledge PR.
