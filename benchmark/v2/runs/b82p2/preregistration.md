# b82p2: the agent builds the UDP endpoint development tasks, k = 3 (pre-registration)

Written 2026-11-16, before the first run, on branch `b82p2-agent-runs` (base: main `b76b4558`, the merge of PR #182).
Development measurement, not a scored held-out evaluation. Nothing here reads, lists or copies a held-out task.

## What is measured

The FPGA Design Agent building the five **development** tasks of domain E (the UDP command and telemetry endpoint family,
re-drawn by brief 82R) from their plain-English `spec.md`, 3 independent runs each (15 runs). The held-out family
(`crc32_unit`) is private and is not touched. The question: what fraction of runs produce RTL that passes the hidden
acceptance bench, how that differs between the four L1 tasks and the L2 endpoint, and where the failures sit.

| Order | Task | Level | Hidden bench |
|---|---|---|---|
| 1 | `v2_e_cmd_parser` | L1 | `benchmark/v2/tasks/v2_e_cmd_parser/hidden` |
| 2 | `v2_e_cmd_exec` | L1 | idem |
| 3 | `v2_e_tlm_pacer` | L1 | idem |
| 4 | `v2_e_resp_builder` | L1 | idem |
| 5 | `v2_e_udp_endpoint` | L2 (embeds the parser, executor and response builder) | idem |

Source of the list: the five `v2_e_*` tasks recorded as development by the `family_draw` entry of
`benchmark/v2/ledger.jsonl` (seq 54, 2026-11-15); `split.py verify` was ok at the base commit.

## Run order (fixed now, independent of results)

Phase A, the L1 tasks, repeat-major: for repeat 1, 2, 3, the four L1 tasks in the order above (12 runs). Phase B, the L2
task: `v2_e_udp_endpoint` repeats 1, 2, 3 (3 runs). "L1 first, then L2." The agent has no seed flag; a repeat is a fresh
launch (clean run directory, no memory between runs; the model samples as Claude Code does at its default).
Up to **two workers** at a time (claims by atomic `mkdir`), so two runs in flight at most.

## Configuration of every run (the dev default of the 07a2 and brief 20/24 runs; per-role settings as on main)

`python -m agent run <task>/spec.md --name <task> --board nexys_a7_100t --interview oracle --hidden-spec <task>/hidden/spec.yaml
--harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --oracle claude_code --oracle-cc-model claude-haiku-5-5
--review off --stop-after 2 --verif-level V2 --docs off`

- Profile `single`: every role (clarify, model, tests, RTL) on Claude Code, Sonnet `claude-sonnet-5-5`, effort medium; the
  interview oracle on Haiku `claude-haiku-5-5` answers from `hidden/spec.yaml` (never visible to the agent; the agent's tools
  are the MCP tools only). Harness arm: the main default H1. Knowledge bank: `FPGA_Design_Agent_Knowledge` at the pin of
  `knowledge/PACKS.md` (`2338b83`); the agent searches only the frozen library.
- Code: a detached worktree of main `b76b4558` (`FROZEN_SHA`); the driver refuses to start a run if HEAD differs or `agent/`,
  `flow/`, `shell/` or `benchmark/` is dirty. Claude Code CLI **2.1.321**, a real-file copy pinned first on PATH (SHA-256
  in `environment.txt`), auto-update off (`DISABLE_AUTOUPDATER=1` in `~/.claude/settings.json`); version checked before every launch.
- Scope: stages 0 to 2 (clarify, board and device planning, RTL design and verification). These are block-level sim tasks, so
  **no Vivado runs**: no heavy slot is taken; each run waits for load under 6 and more than 12 GB free, and is capped at 5 GB
  (`systemd-run --user --scope -p MemoryMax=5G`, `nice 10`). Deviations from "main's defaults", chosen before any run, for budget
  and because they cannot change the hidden-bench result: `--stop-after 2` (no synthesis, implementation, closure or board
  stages; a closure failure class therefore cannot appear in this measurement), `--verif-level V2` (the level of the 06c runs;
  V3 adds Verilator coverage and mutation runs of 15 to 35 minutes each), `--docs off` (no DOC step).
- Limits: the agent's own `RUN_LIMITS` and stage limits unchanged (300 turns, 6 stage-2 visits, a stage-2 visit 3,600 s); plus a
  hard wall limit of **3 h** per run enforced by the driver. A run killed by it is a failure of class "budget", not "not run".

## What counts as a pass

**Primary (per run): PASS = every test of the task's hidden acceptance bench passes** on the run's `rtl/`, scored by
`benchmark/tools/run_task.py` on Icarus (shell frozen, `scoring_env.py` run first), after the run ends. A run with no RTL, a
design that does not build under the bench, or a bench with a test failing is a failure. No LLM scores anything; the agent's own
testbench never counts.

Secondary, reported beside it, never replacing it: **gates-clean** = the stage-2 gates the agent itself reports passed
(`summary.json` `gates_last`); **escape** = hidden fail with gates-clean; **internal stop with hidden pass** (gates not clean
but hidden pass). Tests passed of tests total is also recorded.

## Metrics

- **pass@1** per task = k/3 (k = runs that pass); pooled over the four L1 tasks and over all five tasks (task mean, tasks as the
  unit); **pass@3** per task = at least one of 3 runs passes (1/0), and pooled the same way; the unbiased estimator at n = k = 3
  is the same as the plain fraction. Intervals: with 5 tasks no bootstrap is claimed; the report gives the per-task counts and,
  for pooled pass@1 over 15 runs, a Wilson interval labelled as ignoring clustering by task.
- **Cost:** the Claude Code CLI's own reported usage per call, summed per run by the agent (`summary.json`: `tokens`,
  `plan_cost_estimate_usd`, labelled plan-equivalent estimate: the Max plan has no per-call bill). No cost is estimated by hand.
  Weekly plan usage read with `usage_check.sh` before and after the whole measurement.
- **Wall time** per run (driver clock), turns, stage-2 visits, simulate calls.
- **Failure profile** per failed run by the **stage** where it stopped and a **class** from the fixed list: spec reading,
  RTL, verification (the agent's tests or gates), closure (cannot occur at stop-after 2), tool, harness, budget. The class is
  assigned after reading the run's logs and the hidden bench's failing test, and the report quotes the evidence.

## Rules fixed in advance

- **Every run is reported.** None is dropped, cherry-picked or re-run for a better result. An **infrastructure failure** (CLI
  version block, PC crash or OOM kill of the whole scope before the agent's first model turn, container failure) is reported
  "not run" with its evidence and replaced by **one** re-launch of the same slot, labelled; a run that reached its first model turn and
  then fails is a failure, whatever the reason.
- **No changes to agent, knowledge, prompts or benchmark during the 15 scored runs.** Bugs found are written down.
  The retrospective fixes come after all runs, and the re-run of the failed cases is post-hoc, labelled as such, never merged into
  the primary table.
- **Usage:** `_handoff/usage_check.sh` before each launch; no new launch at **70%** weekly (all models) (the brief's cap this
  week); runs in flight finish. Fable 0%. Paused, the remaining runs continue in the same order; the report says which were
  not run, never as results.
- Scoring has its own light lock; one score at a time.
- **Held-out hygiene:** the run uses only the five public development tasks. The harness copies no `ref/` or `hidden/` file
  to the agent; `hidden/spec.yaml` reaches only the oracle process.

## Amendment 1 (2026-11-16 15:58, harness only; before the third run's result; no effect on scoring)

The first driver version never created `records/`, so the two first runs (`v2_e_cmd_parser` r1, `20261116-134454-d48e`, and
`v2_e_cmd_exec` r1, `20261116-134601-83c4`) finished, were scored and archived under `artifacts/`, and then the workers crashed
writing the record. Both workers were restarted and the two records rebuilt from the finished run directories with
`driver.py rebuild` (scoring repeated on the same RTL; wall time = run-directory creation to `summary.json` mtime, so it is a
reconstruction and the record says so). The two workers stood idle from about 14:32 to 15:58; that is lost wall time, not a result.
Nothing about the agent, knowledge, prompts, benchmark or the runs' configuration changed.
