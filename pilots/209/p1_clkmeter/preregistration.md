# Pre-registration: P1 clock frequency meter

> Frozen 2026-11-25 02:42 GMT (from `date`) by the planner's go (2026-11-25). Changes after this point go in a dated addendum only.

Written 2026-11-24 21:09 GMT (from `date`), before any agent run of this design and before any board time. Never edited afterwards: a correction goes in a dated addendum at the end.
Brief 209 (`_handoff/fpga_agent/209_kr260_pilot_brief.md`). Spec: `spec.md`. Host check: `host/check_p1_clkmeter.py` (run by `run_pilot_board.sh p1_clkmeter`). Board: the owner's KR260, SRAM only.

Design ID register 0x000: `0x20910001`.

## Build stamp the script will check

BUILD register 0x004 must equal the `build_id` (USR_ACCESS word) of the agent's build record for this design, which is not known before the agent has built it.
It is written to `stamp.txt` in this folder after the build (a dated addendum below, committed before the board visit). `run_pilot_board.sh` refuses to run without `stamp.txt`,
checks the stamp printed by `flow/program.py` after programming, and `host/run_check.py` compares register 0x004 with it. A mismatch is INCONCLUSIVE, never FAIL.

## Inconclusive (a setup fault, not a design fault)

The run is recorded as inconclusive and repeated, not counted, if any of these happens: the ID or BUILD register does not match (wrong bitstream or the bus does not answer);
programming or the JTAG chain fails; the board's operating conditions leave the limits that `flow/program.py` checks; the Vivado hardware manager dies or a bus read times out
(a Python exception in the host check); the board was not power-cycled or the PL overlay not unloaded as in the visit plan. A criterion that fails while ID, BUILD and the scratch register pass is a FAIL of the design.
A design that fails the agent's own gates never reaches this step and is recorded "did not reach hardware".

## Criteria (all must hold for PASS)

| # | Criterion | Pass if |
|---|---|---|
| 1 | `id`, `build_stamp`, `scratch_readback` | ID 0x20910001; BUILD equals `stamp.txt`; SCRATCH reads back six patterns |
| 2 | `gate_actual_equals_gate` | GATE_ACTUAL equals GATE_LEN exactly, for all nine measurements |
| 3 | `c3_frequency_within_100ppm` | mean of five one-second readings, f = COUNT x 156.25 MHz / GATE_ACTUAL, is 25 MHz +- 100 ppm (24,997,500 to 25,002,500 Hz) |
| 4 | `five_long_readings_agree` | max minus min of the five COUNTs is at most 100 (4 ppm) |
| 5 | `count_gate_<G>` for G = 156,250,000 (x5), 15,625,000, 1,562,500, 156,250, 31,250,000 | COUNT within 0.16 x G x (1 +- 100 ppm) +- 2 counts |
| 6 | `meas_done_counts` | MEAS_DONE rises by exactly 9 |
| 7 | `leds_off_at_end` | CTRL.LED_EN reads 0 at the end (LEDs off) |

Expected values: the C3 oscillator is nominally 25.000 MHz; the reference is taken as exactly 156.25 MHz (an unmeasured oscillator itself; the result is the C3 frequency *relative to it*).
Criterion 3 is the brief's pre-registered number. If it fails the reading is still recorded; the owner decides whether `board.yaml` gets the measured value.
Only after a PASS or FAIL run, the reading goes into `boards/kr260/board.yaml` `measured_on_board` (by the planner, not by this brief's executor).

## Runs and records (frozen plan, 2026-11-25 02:42 GMT)

- Agent: the pilot worktree's `agent/` at the merge of brief 209a (PR #336, head 1f3809be); the exact SHA of every run is in its record.
- Model: `anthropic_api`, claude-sonnet-5-5 for every purpose that can use it (`--model-config '{"default": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}'`), the owner's API credit. Never Opus, Fable or OpenRouter.
- Verification level: `--verif-level V2` for every run (V3 stalled at stage 2 on mutation score in 209a: a known agent gap, not tested here). Other flags: `--board kr260 --review off --interview off --max-usd 12`; interview is non-interactive and answers nothing by hand.
- Runs: 3 independent runs of this unchanged spec, in order; nothing is changed between runs. A failed run is a result, not an intervention. "First time" means run 1 only.
- Caps: 12 USD per run, 150 USD for the whole pilot (cost computed from the API usage in each `summary.json`/`role_usage.jsonl`); a run that could pass the total stops the pilot with BLOCKED.
- Record per run: gates passed (simulation against the Python model, check suite, timing after routing, bitstream built), Fmax, LUT/FF/BRAM/DSP, tokens, USD, wall time, interview summary (asked/answered/defaulted), interventions, the traceability output (`run<k>/trace.md`, `trace.json`, sign-off table), whether the generated `hw_checks.py` and the host check here pass against the run's mock bus. Per design: mean and spread (min, max).
- The run that goes to the board is the first of the three that reached a bitstream (decided before any board result is seen); the others are recorded.
- Heavy jobs: one run at a time under a heavy slot, `systemd-run --user --scope -p MemoryMax=<N+1>G nice -n 15`, with `FDA_HEAVY_LOCK` set to a private file per run.

## Addenda

(none)
