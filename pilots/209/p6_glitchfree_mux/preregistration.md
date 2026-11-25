# Pre-registration: P6 glitch-free clock multiplexer

> Frozen 2026-11-25 02:42 GMT (from `date`) by the planner's go (2026-11-25). Changes after this point go in a dated addendum only.

Written 2026-11-24 21:09 GMT (from `date`), before any agent run of this design and before any board time. Never edited afterwards: a correction goes in a dated addendum at the end.
Brief 209 (`_handoff/fpga_agent/209_kr260_pilot_brief.md`). Spec: `spec.md`. Host check: `host/check_p6_glitchfree_mux.py` (run by `run_pilot_board.sh p6_glitchfree_mux`). Board: the owner's KR260, SRAM only.

Design ID register 0x000: `0x20960001`.

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
| 1 | `id`, `build_stamp`, `scratch_readback` | ID 0x20960001; BUILD equals `stamp.txt`; SCRATCH reads back |
| 2 | `b_div_in_range`, `start_state` | B_DIV in 1..8; after configuration SEL = 0, MUX_ERRS = 0, SWITCH_COUNT = 0 |
| 3 | `freq_*_sel0` | with clock A: FREQ_COUNT = gate x 1 (gate counted in C3 cycles) +- 200 ppm +- 2 counts |
| 4 | `freq_*_sel1` | with clock B: FREQ_COUNT = gate x 6.25 / B_DIV +- 200 ppm +- 2 counts (200 ppm = the sum of two crystal tolerances; the reading of P1 is context, not an input) |
| 5 | `all_switches_completed` | for all 1,000 random requests (seed 2096), ACTIVE_SEL equals the request and SWITCHING is 0 within 1 s |
| 6 | `mux_domain_errors_zero`, `..._at_end` | MUX_ERRS = 0 after the 1,000 switches and after the last two measurements |
| 7 | `switch_count_equals_changes` | SWITCH_COUNT = number of requests that changed the selection (including the first switch to B), computed by the host from the same seed |
| 8 | `mux_counter_moves` | MUX_COUNT differs between two snapshots 50 ms apart |
| 9 | frequency after every 100th switch | ten 0.1 s measurements, each as in 3 or 4 for the clock then selected |

Expected values: A is the C3 clock counted against itself (so it checks the mux path, not the oscillator); B follows the GT reference clock divided by B_DIV.

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

### Addendum 2026-11-25 02:45 GMT: cost accounting

The 12 USD per-run cap is enforced by the agent as 240 calls at its 0.05 USD per-call ceiling (`anthropic_api` calls report tokens, not dollars). Real dollars are computed from the token counts at Sonnet 5.5 list prices per million tokens: input 2, output 10, cache read 0.10, cache write (5 min) 2.50 USD (split recorded when the run's records have it; otherwise all tokens counted as input plus output by role, and said so). A run that stops at the cap is a pre-registered outcome "stopped at cost cap", not an intervention. Pilot stop rule: no run starts if the cumulative real total is above 130 USD; a run above 20 USD real stops the pilot for the planner. The agent SHA of every run is recorded with the run.

### Addendum 2026-11-25 02:51 GMT: model options

The API answered the first launch with HTTP 400 "`temperature` is deprecated for this model" (claude-sonnet-5-5), so every run sets `options: {temperature: null}` (unset) in the same `--model-config`; all other options stay the agent's defaults (max_tokens 8192, timeout 180 s, one retry). This is a model-configuration setting, not an intervention. The agent also needs the pinned private prompts: `FDA_KNOWLEDGE` points at a checkout of the knowledge repository at the pinned commit 5e2eab87.
