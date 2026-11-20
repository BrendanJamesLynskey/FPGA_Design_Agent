# Brief 103S2: the navigator, stage 2 (records)

Stage 2 adds three things to [the navigator](../../navigator/README.md): start and stop an agent run with the command line's own guards (Start page), live progress of any run directory (Live page), and locked, read-only board actions (Board page). It also fixes three stage-1 display follow-ups (below). This folder holds the headless screenshots and their check. No agent run, Vivado session or board action was run to make them: the spawner and the board transport were fakes.

## Records

| File | Made by | Shows |
|---|---|---|
| `screenshots/<view>_wide.png`, `<view>_phone.png` | `NODE_PATH=<node_modules> node navigator/shoot_stage2.js <url> results/103s2_navigator/screenshots <handoff dir>`, against `python3 -m navigator.tests.demo_stage2` | Start (task form, project form, a started run, the "one at a time" refusal), Live (the run list with a synthetic active demo run, the detail view), Board (the page, the result of "all four reads", the refusal when `board.lock` is held), the Timing page's chain table, the Measurements capture table |
| `screenshots/check.json` | the same script | page errors, requests outside the service, pages wider than 390 px at 390 px, dialogs confirmed |

**Illustrative:** the Board results come from a fake transport that returns canned lines (a KR260 whose SYSMON is inside its limits and whose design reports FEATURES 0x7F); the Live page's active run is a synthetic run directory named `...-demo`; the usage figure and the heavy-slot script are fakes. Nothing on these screenshots was read from a board.

## What changed in the stage-1 pages

- **Timing:** the stage table is the `RATE_MATCH = 1` chain (13 clocks simulated). `latency_stages.yaml` now has a `chains:` list naming each recorded simulation and the build it is, and the page shows both: 13 clocks (the stage table) and 11 clocks for the default `RATE_MATCH = 0` build (`results/b96c/core_sim_default.json`), which has no stage table.
- **Measurements:** the capture table has a state column (SYNTHETIC / NO DATA / measured on the board), the TX drive, the 4T clock phase the self-test chose (96D3), and the eye width and height with their lower and upper bounds. A TX-drive sweep capture whose points are too shallow to vouch for the target depth says so instead of "no open row" (in 20261120_105134 the five TX-drive sweeps `tx_d8`, `tx_d16`, `tx_pre4`, `tx_post4`, `tx_post8` have 596 to 619 shallow points each and none open). The failed 20261119_231836 run reads "NO DATA". The banner no longer says the board eye is unmeasured.
- **96F1 bypass build:** `b96f1/rm_gp_bypass` is in the build table with its numbers (WNS +0.090 ns, WHS +0.010 ns, 6,878 LUT, 29 gates, Vivado 2026.1); a test pins them. No board session exists for it yet, so nothing is shown under Measurements.
- **96D `fake.py`:** a fresh synthetic scan records `settings.expected_points` (`scan.run_scan` writes it); a test generates one and checks the page reads it as complete.

## Tests

`python3 -m pytest navigator/tests` (stage 1: 19; stage 2: see the report). Start guards (usage at or above 90 % and a failed or stale check refuse, no heavy slot, one run at a time, every field check, Fable and Opus, option injection through the change request, the access gate), the slot released on every path including a failed spawn and a lock taken over by another session, stop signalling only the run's own process group (a bystander in another group survives) and refusing a pid that is not the recorded process, a restart releasing the slot of a run that has gone, live progress (stage, visit, cost, gates, audit tail, finished and idle states, bad ids, and a read of the owner's real CLI-started runs), the board actions with a fake transport (both locks held while it runs and released on success, refusal, error, timeout and interrupt; a held `board.lock` refused and left alone; no heavy slot releases the lock taken; a lock changed during the run not removed), and the safety proof: every generated script for every action and board contains no `program`, `write`, `set_property`, flash, eFUSE, laser or `source`, only the 14 allowed hardware commands, and only read scans of four read-only registers (bit 45 set, bit 44 clear); `check_tcl` refuses sixteen planted write or program lines; a syntax-tree walk of every navigator module finds no import of the programming flow, the bench drivers or the debug core; the constants (read-only registers, FEATURES bits, GT_STAT bits, recommended operating conditions) are checked against the register map and the bench modules they cite.

## Review

One Sonnet safety review (locks and slots, write paths, injection, XSS, traversal): 16 findings, all fixed or recorded; see the report. Fixes were re-tested (113 navigator tests) but not re-reviewed.

## Reproduce

Tests: `python3 -m pytest navigator/tests`. Service: `python -m navigator [--runs DIR]`, then open the printed address. Screenshots: `python3 -m navigator.tests.demo_stage2 --port 8793 --workdir <scratch dir>`, then `NODE_PATH=<node_modules> node navigator/shoot_stage2.js <printed address> results/103s2_navigator/screenshots <scratch dir>/handoff`.

## Known gaps and limits

- **No real board action has been run.** The register reads use the cable at its default clock: `jtag_regs.tcl` sets 1 MHz with `set_property PARAM.FREQUENCY`, which the brief's "no set_property on hardware objects" rule excludes here. If a real read fails with "no 0x58A0 marker", that is the first thing to look at (see the report's first-use steps).
- The register reads and SYSMON on the K26 are written from `jtag_regs.tcl`, `hw_list.tcl` and `sysmon_read.tcl`, whose K26 chain handling was measured on 2026-11-17; the navigator's copy has not run on a board. `get_hw_sysmons` on the K26's PL device is the least certain command.
- A run started from this page survives the navigator (its own session); the slot is released by a restarted navigator's reconcile, or by hand with the owner-checked command if the registry file was lost.
- One navigator run at a time (the limit is deliberate: the PC allows two heavy jobs in all). A run's project resume has no arm option (the CLI's `resume` has none).
- Live progress finds the run directory of a run started from this page by the run id its output printed (`resume` prints it), else by the one new directory with the task's name; two identical starts at once could be confused.
- Usage is read from `usage_check.sh` (weekly, all models); the stop is 90 % until the 23 Nov reset (`FDA_USAGE_STOP_PCT` for later); other limits (session, Fable) are not checked.
- **A run started with `--board`** can use the agent's own board tools (program, bring-up, capture; costed in `agent/core/security.py`). The navigator takes a heavy slot for it, not `board.lock`. Whether a navigator-started run may touch the board is a planner decision; today the agent's own gates decide.
