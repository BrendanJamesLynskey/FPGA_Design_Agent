# `eval-1`: pre-registration

Committed 2026-11-09, before any scored run. The agent under test is the commit that adds this file, tagged `eval-1`.
Amendments after this commit are not allowed except as dated notes made before the first scored held-out run.

Sources for the method:
- the owner's **Agent Evals Explained** (agent-evals-explained.vercel.app): tasks, not runs, are the unit; unbiased
  pass@k and pass^k; Wilson/exact or bootstrap intervals, never Wald; small gaps are ties; paired comparisons;
  graders and leakage checked; harness and cost reported with the score;
- the **CVDP project's** practice (`the CVDP RTL Agent's M3k report`, `m3k/preregistration.md`): written
  pre-registration on a branch before any scored dispatch, one primary question, per-problem pass rate over 3 runs,
  paired bootstrap over problems (2,000 resamples) with an exact sign test beside it, a stated decision rule, a planned
  interval width, pre-declared handling of infrastructure errors, every run linked, cost reconciled;
- lessons from the CVDP project's evaluations (section 8).

## 1. What is measured, and on what

- **Agent under test:** FPGA_Design_Agent at tag `eval-1`. Claude Code arm,
  model `claude-sonnet-5-5`, effort medium; interview oracle `claude-haiku-5-5` via Claude Code; Claude Code CLI
  version recorded per call; Vivado 2025.2; Verilator 5.048; Icarus 12.0; cocotb 2.0.1. Board Nexys A7-100T
  (xc7a100tcsg324-1), 100 MHz.
- **Tasks:** the 19 held-out tasks: 8 from benchmark v1 (`benchmark/split.yaml`, seed 20261103) and 11 from the course
  tier v1.3 (`benchmark/course/split.yaml` and `split_c9_c12.yaml`, seed 20261106). The split was drawn by a fixed
  seed before any agent run; manifests (SHA-256 per file) are frozen; `freeze.py verify --private` must report 0
  mismatches before the first run.
- **Runs:** 3 independent runs per task (57 runs), each from a clean checkout, a fresh run directory and no memory
  between runs. Order: fixed in advance by `docs/eval/eval1_run_order.py` (seed 20261109; list in section 9), so tasks are not run
  easiest first.
- **What the agent sees:** only the task's `spec.md` and the board pack. Hidden tests, models, reference RTL and
  `hidden/spec.yaml` are never visible to it; the oracle answers questions from `hidden/spec.yaml` with a verbatim
  quote check, and every question and answer is logged.

## 2. Grader

- The task's hidden cocotb acceptance tests (`run_task.py`), written before any agent run against an independent golden
  model, scored on Icarus as the benchmark defines. Deterministic: no language model grades anything.
- The grader itself is checked: every task's reference passes, and every task's mutants (5-8 per task) fail
  (`check_task.py`); results are in the frozen benchmark.
- A run **passes** only if every hidden test passes. Partial credit (tests passed of total) is reported beside it.

## 3. Primary results (fixed before any run)

1. **Per-task pass counts, k of 3,** for all 19 tasks, in one table, with every run's ID, commit and log link.
2. **pass@1** = mean over tasks of k/3, with a **95% interval from a bootstrap over tasks** (2,000 resamples), so
   tasks, not runs, are the unit. Wilson on the 57 runs is shown beside it for contrast and labelled as ignoring
   clustering.
3. **pass@3** (at least one of 3) and **pass^3** (all 3), unbiased estimators, same bootstrap.
4. **Escape rate** = runs where the agent's own checks (V0-V3 and post-route gates) all passed but the hidden tests
   failed, divided by runs whose own checks passed; with the bootstrap interval; each escape classified by the check
   level that should have caught it (V0, V1, V2, V3, post-route, spec interpretation, harness).
5. **Catch-and-repair rate**: runs where an internal gate failed, the agent repaired it, and the hidden tests passed.

## 4. Secondary results (reported, not decided on)

QoR of passing designs (WNS at 100 MHz, LUT, FF, DSP, BRAM, power) against the reference where a reference build
exists; wall time; tool runs (simulate, mutate, build); tokens and plan-cost estimate per run and per solved task;
stage visits; where runs stopped; split by v1 and course tier, and by difficulty.

## 5. Rules fixed in advance

- **No changes during the evaluation.** The agent, knowledge bank, prompts and benchmark stay at `eval-1` until all 57
  runs are scored. A bug found during the evaluation is written down and fixed afterwards, and the fix is measured as
  `eval-2` on the same tasks.
- **Infrastructure failures:** see section 8, item 1 (reported as "not run", never rerun into the primary result).
- **All runs are reported.** No run is dropped, cherry-picked or rerun for a better result.
- **Who reads held-out material:** the agent never does; the executor running the evaluation reads only scores and
  logs; held-out task text stays private until the results are published, then follows the v1 publication rule.
- **Contamination checks:** the knowledge bank contains none of the held-out spec phrases (`bank_grep`: 0 hits), and
  the v1 contamination probe results are cited. The course tasks were written in November 2026.

## 6. Comparisons (later, separate pre-registrations)

`eval-2` (independent spec-only test generation) and the baseline arms will each get their own pre-registration with
one primary comparison: paired by task on the same 19 tasks, per-task pass-rate differences, a paired bootstrap interval
over tasks (2,000 resamples) and an exact sign test beside it; **better** or **worse** only if the 95% interval excludes
zero, otherwise "no detectable effect" with the interval's ends stated. Planned width from this evaluation's spread.

## 7. What the report will contain

A "How this was evaluated" section first, written for a sceptical reader: this document's rules in plain words, the
exact commands, the commit and manifest hashes, the tool versions, the run order, every run linked, the
runs reported as "not run", then the results tables, then limitations (19 tasks give wide intervals; one board; one model;
an LLM oracle stands in for the user during the interview; Icarus is the scoring simulator).

## 8. Amendments from the CVDP session's lessons (2026-11-09, before any scored run)

Adopted from the CVDP project's practice:
1. **Errors are "not run", never rerun into the primary**. A run that
   ends for an infrastructure reason (CLI version block, PC crash, container or network failure before the agent's
   first turn, OOM kill of a tool process) is reported as not run with its evidence; the task's count becomes k of the
   runs that ran. Repeats, if any, are a separate descriptive set, labelled, never merged into the primary table.
2. **Smoke first:** two development tasks run end to end on `eval-1` before any held-out run, to check the run record
   (every field of `tools/run_record.py`), that scoring ran, and that the oracle log exists. Smoke results are reported
   separately.
3. **Every constant was chosen on development tasks only** (V3 floors, mutation caps, timeouts, clarify triggers);
   the report says so and lists them with the commit that set each.
4. **One run per invocation, logged:** each of the 57 runs is a separate launch with its own run id and log; a
   checker confirms 57 run records exist before analysis, so nothing is silently skipped.
5. **Cost:** plan usage read with `usage_check.sh` before and after the whole evaluation, reconciled with the sum of
   per-run plan-cost estimates (the Max plan has no per-call bill).
6. **Power and runs per task:** with 3 runs many tasks will be 0/3 or 3/3. The planned half-width of pass@1 is taken
   from the development runs' spread and stated here before the first held-out run. Decision (planner): 3 runs per
   task, as budgeted; if the realised 95% half-width exceeds 15 points, 2 more runs per task are added to **all** tasks
   (a width rule, fixed now, not a result-direction rule) and the report shows both.

   **Amended 2026-11-09 (planner, before any scored run), replacing the width rule above.** Planned width, computed
   from the 21 development runs on 11 tasks (per-task pass rates 0.5, 1, 1, 0, 0.6, 0, 1, 1, 0.67, 1, 1), by
   simulation (400 draws of 19 tasks, task-level bootstrap of 1,000; script `tools/planned_width.py`, seed 20261109):
   expected 95% half-width of pass@1 = **±17.5 points with 3 runs, ±17.0 with 5, ±16.4 with 10** (90th percentile
   ±20). The width comes from tasks differing in difficulty, not from run-to-run noise, so extra runs per task barely
   narrow it; the width rule would spend ~38 runs for half a point. It is withdrawn: **3 runs per task, fixed.** The
   report states the planned and realised widths and says plainly that on 19 tasks a single pass rate is only known to
   about ±17 points; precision comes from paired comparisons (each task is its own control, which cancels difficulty)
   and, later, from more tasks, not from more runs.
7. **Comparisons (eval-2, baselines):** report discordant counts (better / worse / tie per task) prominently; primary
   = paired bootstrap over tasks (reusing `the CVDP project's `tools/ablate.py``, 2,000 resamples) with the exact sign test
   beside it; secondary = a task-clustered permutation test. For `eval-2`, a golden test proves which request paths
   are unchanged, and a free offline replay on development tasks shows how often the new bench step fires before any
   held-out spend.
8. **Leak guard for anything published:** held-out run logs contain the oracle's quotes from `hidden/spec.yaml`, so
   nothing from a held-out run is published before the results are; then a scan in the style of
   the CVDP project's `tools/leak_guard.py` (80-byte windows of private text) runs over everything to be published.
9. **Amendments** to this document are dated, give the reason, and are made only before the first scored run.

## 9. Execution

- **Smoke (not scored):** `c9_median3x3` and `c15_pq_search` (development tasks) on `eval-1`, end to end, before run 1.
- **Pace:** up to two agent runs at a time, each under a 6 GB memory cap, with at most one Vivado process across both
  (`FDA_VIVADO_MAX=1`). Runs follow the order below whatever their results; if the weekly plan allowance runs short,
  the remaining runs continue after the reset in the same order. Pausing never depends on results.
- **Amended 2026-11-09 17:15 (planner, before the first held-out run; pace only, no effect on scoring):** up to
  **three** agent runs at a time, with at most two Vivado processes across them (`FDA_VIVADO_MAX=2`; a two-build
  trial on this PC kept at least 12 GB free). While `c13_histogram_equaliser` or `c13_stereo_disparity` is in flight
  (large image designs, 10-12 GB in Vivado), that run gets a 12 GB cap and at most one other run goes beside it.
  Reason: the PC used under 9 GB with two runs; the order and every rule above are unchanged.
- **Tool versions** (recorded per run as well): Claude Code CLI 2.1.319, Icarus Verilog 12.0, cocotb 2.0.1, Vivado
  2025.2, Verilator 5.048 (in the `fda-sim` container).
- **Run order** (19 held-out tasks x 3, seed 20261109):

```
 1. t2_ascii_console run 1
 2. c15_topk_stream run 1
 3. c10_cic_decimator run 1
 4. t2_uart_regs run 1
 5. t1_combo_lock run 1
 6. c12_pdm_decimator run 1
 7. t2_ascii_console run 2
 8. t1_stopwatch_lap run 1
 9. t2_uart_regs run 2
10. c16_sha256_uart run 1
11. c12_pdm_decimator run 2
12. c16_sha256_uart run 2
13. c11_fm_discriminator run 1
14. t1_stopwatch_lap run 2
15. t2_adxl362_fifo run 1
16. t1_breathe_rgb run 1
17. t2_uart_regs run 3
18. c14_binarised_dense run 1
19. t1_reaction_timer run 1
20. t2_adxl362_fifo run 2
21. c9_rgb2ycc run 1
22. t2_vga_800x600 run 1
23. c16_sha256_uart run 3
24. c13_stereo_disparity run 1
25. t1_stopwatch_lap run 3
26. t2_adxl362_fifo run 3
27. c16_health_test run 1
28. t1_reaction_timer run 2
29. c13_histogram_equaliser run 1
30. c14_binarised_dense run 2
31. c15_topk_stream run 2
32. c14_binarised_dense run 3
33. c15_topk_stream run 3
34. c13_stereo_disparity run 2
35. c15_nexys_vector_search run 1
36. t1_combo_lock run 2
37. c13_histogram_equaliser run 2
38. c12_pdm_decimator run 3
39. c10_cic_decimator run 2
40. c11_fm_discriminator run 2
41. c9_rgb2ycc run 2
42. t1_breathe_rgb run 2
43. c15_nexys_vector_search run 2
44. t2_ascii_console run 3
45. t1_reaction_timer run 3
46. c15_nexys_vector_search run 3
47. c9_rgb2ycc run 3
48. c10_cic_decimator run 3
49. t2_vga_800x600 run 2
50. c13_stereo_disparity run 3
51. c16_health_test run 2
52. c16_health_test run 3
53. c11_fm_discriminator run 3
54. t2_vga_800x600 run 3
55. t1_combo_lock run 3
56. c13_histogram_equaliser run 3
57. t1_breathe_rgb run 3
```
