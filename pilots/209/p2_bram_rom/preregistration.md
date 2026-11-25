# Pre-registration: P2 ROM, RAM and march test

> Frozen 2026-11-25 02:42 GMT (from `date`) by the planner's go (2026-11-25). Changes after this point go in a dated addendum only.

Written 2026-11-24 21:09 GMT (from `date`), before any agent run of this design and before any board time. Never edited afterwards: a correction goes in a dated addendum at the end.
Brief 209 (`_handoff/fpga_agent/209_kr260_pilot_brief.md`). Spec: `spec.md`. Host check: `host/check_p2_bram_rom.py` (run by `run_pilot_board.sh p2_bram_rom`). Board: the owner's KR260, SRAM only.

Design ID register 0x000: `0x20920001`.

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
| 1 | `id`, `build_stamp`, `scratch_readback` | ID 0x20920001; BUILD equals `stamp.txt`; SCRATCH reads back |
| 2 | `rom_matches_file` | all 1,024 ROM words equal `data/rom_init.hex` (read first, with auto-increment) |
| 3 | `ram_powerup_values` | read before any RAM write after programming: word i is 0xC0DE0000 + i for all 1,024 (a re-run without reprogramming is invalid: INCONCLUSIVE) |
| 4 | `rom_random_access`, `ram_write_readback` | spot reads of ROM at 0, 1, 511, 512, 1023 correct; four RAM patterns read back |
| 5 | `march_200_passes_done`, `march_200_passes_errors` | 200 passes complete; MARCH_ERRS = 0 and MARCH_FIRST_ERR = 0xFFFFFFFF |
| 6 | `ram_all_zero_after_march` | all RAM words are 0 afterwards (March C- ends on the all-zero background) |
| 7 | `march_injected_fault_detected` | 3 passes with INJECT_FAULT give MARCH_ERRS >= 3 and a first-error address |
| 8 | `march_clean_again_after_fault` | 10 clean passes afterwards give 0 errors |

Expected: ROM words from the committed file; RAM power-up formula from the spec; March C- is deterministic, so a healthy block RAM gives exactly 0 errors.

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
