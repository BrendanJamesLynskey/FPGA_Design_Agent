# Pre-registration: scored runs of the F3 benchmark (brief 06c)

**Status: DRAFT, 2026-11-04.**
- Written by the planner (Claude Opus 5.5) before any scored run.
- The items marked **[owner]** are the owner's to confirm. Each carries the planner's recommended default.
- Once the owner agrees, the merge commit of this file is the registration: nothing below changes after the first
  scored run.
- Any later deviation is reported as a deviation, with its reason, next to the results.

## 1. Question

On natural-language FPGA design tasks for a real board (Nexys A7-100T, Vivado 2025.2):
- How often does each agent arm produce a design that passes the hidden acceptance tests and closes the build flow?
- At what cost and time?
- Do the arms differ?

## 2. Benchmark

F3 benchmark **v1.2** (`benchmark/`; frozen, manifest checked by `benchmark/tools/freeze.py verify`).
- **Tasks:** 24 tasks in two tiers (T1, T2). The split (`benchmark/split.yaml`, SHA-256 `1cf56ebd…68bcc`) holds out 8:
  - T1: breathe_rgb, combo_lock, reaction_timer, stopwatch_lap;
  - T2: adxl362_fifo, ascii_console, uart_regs, vga_800x600.
- **Development tasks:** the other 16 tasks may be used to tune the agent up to the freeze point in section 6.
  **Only the held-out 8 are scored.**
- **Review:** the tasks were written by Claude Opus 5.5 (brief 06a). They were reviewed by a second model (Claude Sonnet
  5.5, brief 06a3) on the owner's instruction, then fixed in v1.2 (brief 06a4). This is a **model review, not a human
  review**, and every report says so.
- **Reference board check:** every reference design passed its board check on the Nexys A7 (v1.1: 24/24).

## 3. Arms **[owner]**

All arms use the same graph, gates, roles, knowledge bank, prompts and tool layer. Only the model and harness differ.

| Arm | Harness | Model(s) | Account |
|---|---|---|---|
| A | Deep Agents (`--harness deepagents`, profile `single`) | openai/gpt-6-luna for every role | OpenRouter |
| B | Claude Code (`--harness claude_code`) | claude-sonnet-5-5 for every role | Max plan |
| C (optional) | Claude Code | claude-opus-5-5 for every role | Max plan |

- **Recommended:** A and B. Run C on the T1 held-out tasks only, if the usage budget in section 7 allows.
- **Interview:** the interview oracle is openai/gpt-6-luna for every arm (it answers from `hidden/spec.yaml`, as in
  05c–05j).
- **Not allowed:** Fable or Opus through OpenRouter.

## 4. Fixed settings

- **Command:**
  ```
  python -m agent run <task>/spec.md --interview oracle --hidden-spec <task>/hidden/spec.yaml --review off --stop-after 8
  ```
  The arm's `--harness`/`--cc-model` flags are added.
- **Verification level: `--verif-level V2` for every arm** (owner decision, 2026-11-04). V3 (coverage and mutation)
  is reported as a secondary, unscored measurement where the run reaches it.
- **Limits and stop rule:** the run limits are the defaults of the agent commit frozen in section 6. A stage visited
  more than 4 times stops the run, as now.
- **Tools:** Vivado 2025.2, Icarus 12.0, Verilator 5.048 (sandbox image `fda-sim:2`), cocotb 2.0.1.
- **Resource rules:** one heavy slot per run; a run is never retried because it failed.
- **Repeats: 3 independent runs per task per arm [owner].** Seeds are not controllable for hosted models, so a
  repeat is a fresh run.

## 5. Outcomes

**Primary: task pass.** A run passes a task only if all of these hold:
1. the run ends with all gates of stages 0–8 passing (`gates_last` all true), including the post-route timing and QoR
   gates;
2. the bitstream exists;
3. the agent's final RTL passes **every** test of the task's hidden acceptance bench: `benchmark/tools/run_task.py <task>
   --rtl <run's rtl dir>`, Icarus, the frozen bench.

**Secondary:**
- the hidden acceptance pass rate per run (tests passed / tests);
- the stage the run stopped at, and the stopping gate;
- the board check on the Nexys A7, for passing runs only, by the same flow as the reference board check (SRAM only,
  wall power, ≤ 2.0 W). This is reported, not part of the pass;
- post-route WNS, LUT, FF, BRAM and DSP;
- the plan-cost estimate (arm B/C) or the provider-reported cost (arm A), plus wall time and turns;
- where reached, V3 coverage and mutation score.

## 6. Freeze point

- **What is frozen:** the agent commit used for every scored run is named here before the first one: `<commit>`.
  It is the `main` head after the PRs merged up to the owner's go.
- **Development work before it:** done on the 16 development tasks only. Results there are diagnostics and are
  reported as such.
- **After the freeze:** no change to the agent, prompts or knowledge bank until all scored runs finish.

## 7. Budget and order **[owner]**

- **Size:** 8 tasks × 3 repeats × 2 arms = 48 runs, plus up to 12 for arm C.
- **Measured costs:**
  - a Claude Code Sonnet run on T1 is about $2–3 plan estimate and 30–40 minutes;
  - Deep Agents is about $0.15–0.35 on OpenRouter.
- **Expected usage:** arm B is about 24 Sonnet runs, roughly 10–15% of a weekly Max allowance (estimate, to be checked
  against `usage_check.sh` after the first 4). Arm A is about $10 of OpenRouter credit.
- **Schedule:** interleave arms task by task (A1, B1, A2, B2, …) so a stop on budget leaves comparable partial results.
  Stop when the weekly figure reaches the schedule's threshold, and resume after the reset.
- **Timing:** start after the weekly reset of 9 Nov.

## 8. Analysis

Small numbers; the plan says so.
- **Per arm:** the pass rate over 24 runs with a Wilson 95% interval, and per task the number of passes out of 3.
- **Between arms:** the paired difference in per-task pass rate (B − A), with a 95% bootstrap interval over tasks
  (10,000 resamples, seed 20261109).
- **No significance claim beyond the interval.** With 8 tasks, a difference whose interval spans zero is reported as
  "no clear difference".
- **Per tier:** T1 and T2 are reported separately as well as together.
- **Failures:** every failed run is classified by the stopping gate and its owner role, and the classification is
  published with the results. Harness faults found during scoring are reported as harness faults, and the run still
  counts as a fail.
- **Publication:** after scoring, the held-out `spec.md` files are published (FROZEN.md rule); the hidden benches stay
  private.

## 9. What the results will not show

- **Not a measure of the models alone.** Each arm is the model plus its harness. Claude Code and Deep Agents differ in
  their tool loops, so the comparison is between arms as built.
- **Not general.** The results hold for one board, one Vivado version and 8 small tasks.
- **Single reviewer.** The benchmark was written and reviewed by models, not by a human expert.

---
Planner sign-off: Claude Opus 5.5 (Session A), 2026-11-04. Owner confirmation: pending.
