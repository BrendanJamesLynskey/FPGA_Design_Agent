# Joint closure loop: proof runs, registered before the first run (2026-11-14)

Design: `c13_hough_lines` course reference at origin/main (benchmark/course/tasks/c13_hough_lines/ref/rtl), 100 MHz,
Nexys A7-100T (xc7a100tcsg324-1), Vivado 2026.1. Reference build (no budget, `c13_ref_base`): WNS +2.633 ns, LUT 3070,
FF 1992, BRAM 2 tiles, DSP 0, 0.148 W on-chip; all 22 flow gates pass.

| Case | Seeded budget | Why this budget |
|---|---|---|
| A `c13_bram1` | `bram=1` | the reference keeps a second copy of the count memory only for a second read port; one tile is the smallest that holds the counts |
| B `c13_power145` | `power_w=0.145` | 3 mW below the reference (about 9 % of its 0.034 W dynamic power); the static 0.114 W cannot change |

Arms: one arm per case, the joint loop with the early check and the sign-off on (`--joint on --early on --signoff on`).
One run per case, so every number is an illustration, not a rate.

Model: `openai/gpt-6-luna` through OpenRouter, data collection denied; at most 6 iterations and $1.00 per case. G1 is
the task's hidden acceptance bench (Icarus), never the writer's own test. Power is Vivado's vectorless estimate.

Success for a case: the summary's `closure_claimed` is true: every goal met on the routed build, then the independent
bench again and all of the flow's gates passing on a build of exactly the accepted files. Anything else is reported
as not closed, with the best values and the strategies tried.

Stopping rules: the loop's own (iteration, cost and time limits; the stall rule of two tries per goal and strategy
class). No reruns to improve a result; a run that fails for an infrastructure reason (a lock, a crash) may be repeated
once, and the report says so.
