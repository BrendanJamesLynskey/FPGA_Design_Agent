# Closure loop and design-time plan: results

When a design passes simulation but misses timing, area or power, the closure loop edits the RTL, re-checks simulation
on an independent bench, rebuilds and repeats. It stops when every goal holds, or with a report of what it tried. The
design-time plan chooses DSP and block RAM use and pipeline depth before the first build. How it works, terms and the
commands: [docs/closure_loop.md](../../docs/closure_loop.md).

**Result: c13_hough_lines closed in one iteration both with and without the plan. Seeded timing misses closed 1 of 3
(c16); c14 and c11 stopped at the 5-iteration limit at -5.270 ns and -1.569 ns. One run per case: these are
illustrations, not rates.**

Setup: Vivado 2026.1, xc7a100tcsg324-1, whole-board builds with the test shell (`flow/run_vivado.sh`). The RTL writer
is `openai/gpt-6-luna` through OpenRouter, and cost is what the provider reported. G1 is always the task's hidden
acceptance bench (`benchmark/tools/run_task.py`): tests written from the task's specification, which the RTL writer
never sees.

## Closure runs

| Case | Clock | WNS start → end (ns) | Iterations (kept / undone) | Stop | DSP start → end | Added latency | Cost |
|---|---|---|---|---|---|---|---|
| c13_hough_lines original, no plan | 100 MHz | -0.225 → **+0.610** | 1 (1 / 0) | all goals met | 0 → 3 | +3 clocks | $0.0025 |
| c13_hough_lines original, with the plan | 100 MHz | -0.177 → **+2.054** | 1 (1 / 0) | all goals met | 0 → 2 | +4 clocks | $0.0032 |
| seed: c16_montgomery_mult | 200 MHz | -0.615 → **+0.064** | 1 (1 / 0) | all goals met | 0 → 0 | 0 | $0.0012 |
| seed: c14_int8_dot_requant | 150 MHz | -24.601 → -5.270 | 5 (3 / 2) | iteration limit | 2 → 2 | not measured | $0.0151 |
| seed: c11_nco_mixer | 200 MHz | -4.401 → -1.569 | 5 (1 / 4) | iteration limit | 2 → 2 | not measured | $0.0134 |
| hand fix of c13, for comparison (PR #134) | 100 MHz | → +2.565 | by hand | - | 0 → 0 | +2 clocks | - |

**Notes on the table**

- Latency is measured. `latency/run_latency.py` counts the clocks `busy` stays high per point in Icarus and
  checks that every cell's count matches the original; the result is in `latency/latency.json`.
- Two builds of the unchanged c13 RTL gave -0.225 and -0.177 ns. Placement noise at this size is about 0.05 ns.
- The no-plan arm bought its LUT and FF savings against the hand fix (159 LUT, 58 FF fewer) with 3 DSP slices.
- The with-plan arm starts with G3 unmet: the plan put the two multiplies on DSP slices, and the original RTL has none.
  Its first repair was the plan's own mapping.
- Seeds are development-task reference RTL with the board clock raised (`--clock-mhz`).
- c16's change is a carry-save adder (no DSP). The run recorded the strategy as `t_dsp_map` because it ran before the
  "carry runs" fix; under the current rules the path is classified as an adder chain.

## Design-time plan and the RTL writer

- **Plan.** The agent graph's stages 0 and 1 on c13's `spec.md`, with `--design-plan`, cost $0.026 (`c13_plan_stage1/`).
  The plan put both multiplies on DSP slices and the count memory in block RAM, in 6 register stages, before any build.
- **RTL written with the plan:** 0 of 6 attempts passed the hidden bench (`c13_write_plan/` 2 attempts,
  `c13_write_plan_r2/` 4 attempts), so there is no first build with the plan.
- **RTL written without the plan:** it passed the bench at once, but kept the 1,536 counts in flip-flops, and its build
  did not finish inside the 6 GB memory cap (`c13_write_noplan/build_not_finished.json`).

## What this does not show

- **No rate.** Each case ran once with one model.
- **The plan's latency of 6 clocks** is what the plan implies, not a measurement.
- **The in-graph loop** (`--closure on`, stage 6) is tested with fakes only.
- **No calibration rows** (planned stage against routed path) exist yet. The c13 architect named an instance the
  reference RTL does not have.
- **Not run:** the comparison of first-build WNS and resources with and without the plan on 2 or 3 other development
  designs.
- **G5 (the board) was not run**, and area and power strategies are not offered yet.
- **Two runs predate the synthesis guard and the carry-run rule:** c13 without the plan, and the c14 seed. The last
  build of every run was scanned afterwards, and c11's accepted design was rebuilt and scanned too (`synth_scan.json`:
  no multi-driven nets, nothing removed). The build directory keeps only the last build, so c14's earlier accepted
  builds are not covered.
- **`c13_orig_plan_unguarded/` is not counted.** It is an early with-plan run that accepted a design whose core
  synthesis had removed: two always_ff blocks drove the same registers, which Icarus allowed and Vivado tied to ground.
  `INVALID.json` says why. That run is the reason for the synthesis guard.

## Files

| Folder or file | What |
|---|---|
| `c13_orig_noplan/`, `c13_orig_plan/` | the two c13 arms; the original RTL is `agent/tests/fixtures/closure/c13_orig/` |
| `c13_orig_plan_unguarded/` | not counted (see above) |
| `c13_plan_stage1/` | spec.yaml, architecture.yaml with `datapaths`, and the plan |
| `c13_plan_stage1/TIMING_PLAN_model_a.md`, `timing_plan_model_a.json` | the plan the with-plan run was given (delay model version a) |
| `c13_plan_stage1/TIMING_PLAN.md`, `timing_plan.json` | the same architecture planned with model version b, the recalibrated one |
| `c13_write_noplan/`, `c13_write_plan/`, `c13_write_plan_r2/` | the RTL-writer arms |
| `seed_*` | the seeded timing misses |
| `latency/` | the busy-clock latency check and its result |
| `calibration/` | the raw reports of the delay-model calibration build (model version b), with the date, host and command lines removed |
| `synth_scan.json` | the synthesis scan of each run's last build |

Each closure folder holds:
- `history.jsonl`: per iteration, the goal vector before and after, the strategy and why it was chosen, the diff, the
  change on every goal, and the cost;
- `summary.json`: the stop reason, unmet goals, iterations and cost;
- `llm_replay.json`: every model call;
- `rtl_final/`: the RTL as the run left it.

## Reproduce

- A closure case: `python3 -m agent.graph.closure_task benchmark/course/tasks/c13_hough_lines ...` (other tasks the same way; the
  full arguments are in [docs/closure_loop.md](../../docs/closure_loop.md)). Each run needs whole-board Vivado 2026.1 builds
  under a heavy slot and paid calls to `openai/gpt-6-luna` through OpenRouter; results can differ on a re-run.
- The plan: `python3 -m flow.timing_plan <design dir>`, or `python -m agent run <spec.md> --design-plan --closure on`.
- The latency check is `python3 results/62a_closure/latency/run_latency.py` (simulation only).

## Known gaps and limits

The section "What this does not show" above is the list of limits: one run per case, no rates, the plan's 6-clock latency
not measured, the in-graph loop tested with fakes, no calibration rows, no first-build comparison on other designs, no
board run, and two runs that predate the synthesis guard.
