# Joint closure loop: area and power proof runs (Vivado 2026.1)

**Headline:** each seeded budget miss on the `c13_hough_lines` course reference was closed and signed off: 2 of 2 cases.
Each run is a single run, so the numbers below illustrate what happened; they are not rates.
- **Case A, block RAM budget of 1 tile:** closed in 3 iterations. The fix moved the count memories to LUT RAM: 0 BRAM,
  1,304 more LUTs, WNS +0.935 ns.
- **Case B, power budget of 0.145 W:** closed in 4 iterations. The fix gated data on the pipeline enables and moved
  the two multiplies onto DSP slices: 0.148 to 0.145 W, WNS +2.043 to +0.597 ns.

Model: `openai/gpt-6-luna` through OpenRouter, data collection denied. Total cost $0.0166 (provider-reported). Part:
xc7a100tcsg324-1 (Nexys A7-100T), 100 MHz. G1 is the task's hidden acceptance bench (5 tests, Icarus), never the
writer's own test. The cases, budgets and success rule were registered before the first run in
[PREREGISTRATION.md](PREREGISTRATION.md).

## Reproduce

```
FDA_BUILD_LOCK_CMD=<lock command> python3 -m agent.graph.closure_task benchmark/course/tasks/c13_hough_lines \
    --rtl benchmark/course/tasks/c13_hough_lines/ref/rtl --case c13_bram1 --budget bram=1 --max-iter 6 --max-usd 1.0
# case B: --case c13_power145 --budget power_w=0.145
```

## Records

Each folder holds:
- `history.jsonl`: every iteration, with the goal vector before and after, the plan, the diff and the early check;
- `closure_actions.jsonl`: the action log;
- `summary.json`: the stop reason, the sign-off and the costs;
- `llm_calls.jsonl`, `llm_replay.json`: the model calls;
- `rtl_final/`: the accepted RTL.

`c13_ref_base/` is the reference built once with no budget.

## Runs

| Case | Iter | Fix chosen | Result | WNS ns | LUT | FF | BRAM | DSP | Power W | Synth s | Impl s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| reference (`c13_ref_base`) | - | - | all gates pass | +2.633 | 3070 | 1992 | 2 | 0 | 0.148 | - | - |
| A `c13_bram1` | 0 | start | G3 not met | +1.901 | 3073 | 1992 | 2 | 0 | 0.149 | - | 1749 |
| A | 1 | `a_bram_merge` | reverted: BRAM 1, but timing broke | -4.474 | 3090 | 1891 | 1 | 0 | 0.129 | 447 | 1091 |
| A | 2 | `a_bram_merge` | reverted by the early check: synthesis still had 2 BRAM | - | - | - | 2 | - | - | 185 | not run |
| A | 3 | `a_lutram` | **accepted; every goal met; sign-off passed (22 of 22 gates)** | +0.935 | 4377 | 2094 | 0 | 0 | 0.163 | 286 | 644 |
| B `c13_power145` | 0 | start | G4 not met | +2.043 | 3077 | 1992 | 2 | 0 | 0.148 | - | 895 |
| B | 1 | `p_gate` | accepted (power improved) | +2.097 | 3065 | 2000 | 2 | 0 | 0.147 | 182 | 519 |
| B | 2 | `p_gate` | reverted: power worse | +2.054 | 3091 | 2000 | 2 | 0 | 0.148 | 216 | 348 |
| B | 3 | `p_gate` | reverted: power worse | +1.017 | 3072 | 2000 | 2 | 0 | 0.149 | 255 | 720 |
| B | 4 | `p_dsp` | **accepted; every goal met; sign-off passed (22 of 22 gates)** | +0.597 | 2904 | 1932 | 2 | 2 | 0.145 | 162 | 219 |

The seconds are wall time on a shared PC. The load average reached 19 during case A's start build, so the times are
not comparable with each other.

Model use: case A made 3 calls (21,261 tokens, $0.00715); case B made 4 calls (28,658 tokens, $0.009442).

## What the runs show

- **The early check saved one implementation run.** Case A's second attempt still synthesised to 2 BRAM tiles. It was
  undone after 185 s of synthesis, without placement or routing.
- **The joint judgement kept a fix from breaking another goal.** Case A's first attempt met the BRAM budget but missed
  timing by 4.474 ns, so it was undone. A loop that looked only at the area goal would have kept it.
- **Hard resources first, as far as the reports allowed:**
  - case A tried the shared block RAM (`a_bram_merge`, hard) twice before LUT RAM (`a_lutram`, soft);
  - case B's closing fix put the multiplies on DSP slices (`p_dsp`, hard).
- **What it cost:**
  - case A's fix spends LUTs, which were within budget (63,400 x 80 %), and raises the power estimate by 14 mW, which
    is within the 2.0 W board limit;
  - case B's fix spends 2 DSP slices and 1.446 ns of the timing margin.

  Neither fix adds latency: the bench's timing checks pass, and the writer's notes say 0 clocks. Latency was not
  measured separately.

## Known gaps and limits

- **Two cases on one design,** each run once. These are not rates.
- **The power numbers are Vivado's vectorless estimates.** Nothing was measured on the board. Case B met its budget
  with no margin: 0.145 W against 0.145 W, at a report resolution of 1 mW.
- **The runs used the code at f3cb9956, before the review fixes:**
  - timing judged at the spec clock;
  - clock edits undone;
  - the sign-off requiring a routed build.

  Neither run offered or changed an XDC, and both sign-offs read 22 gates from routed builds with bitstreams, so the
  fixes would not have changed these results. The action logs are in the schema before the `outcome` and `worsened`
  fields were added.
- **Case A did not find the better design.** One block RAM shared in time, with timing met, would have stayed in the
  hard resource; the loop settled for LUT RAM.
- **Not exercised in a live run:**
  - loop-back to the spec or architecture stage, which is tested with fakes only;
  - the joint plan with two goals unmet at once.
