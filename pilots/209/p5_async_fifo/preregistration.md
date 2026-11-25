# Pre-registration: P5 asynchronous FIFO soak

> Frozen 2026-11-25 02:42 GMT (from `date`) by the planner's go (2026-11-25). Changes after this point go in a dated addendum only.

Written 2026-11-24 21:09 GMT (from `date`), before any agent run of this design and before any board time. Never edited afterwards: a correction goes in a dated addendum at the end.
Brief 209 (`_handoff/fpga_agent/209_kr260_pilot_brief.md`). Spec: `spec.md`. Host check: `host/check_p5_async_fifo.py` (run by `run_pilot_board.sh p5_async_fifo`). Board: the owner's KR260, SRAM only.

Design ID register 0x000: `0x20950001`.

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
| 1 | `id`, `build_stamp`, `scratch_readback` | ID 0x20950001; BUILD equals `stamp.txt`; SCRATCH reads back |
| 2 | `inject_one_error` | after one INJECT: DATA_ERRS = 1, OVERFLOWS = 0, UNDERFLOWS = 0 |
| 3 | `slow_read_*` | with SLOW_READ: no errors, overflows or underflows; STALL_W > 0; OCC_MAX in [504, 512]; read rate 19.531 Mword/s +- 1 % (156.25 MHz / 8, over a 5 s window timed by the host); fill (written minus read) within 0 to 512 |
| 4 | `soak_duration` | at least 600 s of RUN, snapshots every 10 s |
| 5 | `soak_data_errors_zero`, `soak_overflows_zero`, `soak_underflows_zero` | all 0 at the last snapshot |
| 6 | `soak_writer_never_held_off` | STALL_W = 0 (the reader is 6.25 times faster than the writer) |
| 7 | `soak_write_rate`, `soak_read_rate` | each 25 Mword/s +- 0.5 % over the soak, from the sum of the deltas between consecutive snapshots (the 32-bit counters wrap every 171 s) and the host's monotonic clock |
| 8 | `soak_fill_within_depth_every_snapshot` | written minus read between 0 and 512 at every snapshot |

The 10-minute soak was chosen because one 10-minute soak at 25 MHz moves about 1.5 x 10^10 words; a CDC fault at one in 10^9 would show. Zero errors in it is not a proof of CDC safety; the build's CDC report is read next to it.
The 10-minute soak is an unattended soak: it runs only after a clean smoke run of this bitstream and with the owner's separate yes (house rule); the planner gives it at the visit. LEDs: none required.

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
