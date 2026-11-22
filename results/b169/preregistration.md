# Brief 169: board pre-registration for the build `lat_cuts169` (EARLY_MAC = 1, FAST_PRE = 1). Written 2026-11-22 before any board time; NOTHING HAS RUN ON A BOARD.

Status: queued, not run. No board script is written (the brief says write no board commands); the planner or the owner writes one by copying `run_126_stage1.sh` once timing has closed (below) and this page has been read. Bitstream: build `lat_cuts169`, stamp **5a45b3bd**, `designs/b96_kr260_10g/lat_cuts169/build/base/kr260_10g_top.bit` (local, git-ignored); timing met (WNS +0.116 ns, WHS +0.011 ns, 29 of 29 gates, `report_cdc` 0 critical; README section Timing). Check the stamp before any board time.

## What is predicted, and from what
Baseline: the board result of run A on 2026-11-22 for `lat_all3_bypass` (stamp 9641284d), `results/b126/hw/20261122_145404/lat_all3_bypass/stage3.json` (read, not copied), per-link means over 100 restarts computed by `board_per_link.py`:
E 15.91, L 39.56, D (the register `d_last`) 7.86, so E + D (= L - E, the tick-to-trade) 23.77 clocks. Medians of the per-link minima, as the bench prints them: E 16, L 40, L - E 24 clocks = 148.1 ns net of fibre.

**Use L - E (= E + D), not L - 2E, as the headline.** Brief 126 predicted D = L - 2E = 6 from medians of minima; the register D of that same earlier run (97C `lat_all3`) was 7.19 on average (81 links 7, 19 links 8) while L - 2E from its medians was 6 (46 - 2 x 20). A median of L minus twice a median of E is biased low by about one clock; the per-link figures are not. See README, section "Why D came out 8".

The two cuts act only in fabric logic after the E path, so E should not move; each removes one clock from D in xsim (33 orders at phases 0 and 3100 ps, `sweep33/`, `sweep33b/`: EARLY_MAC 1.00, FAST_PRE 0.97, both 1.97; with only 8 orders per phase, `core_sim/`, the gearbox pause lands on one order and the means read 0.9, 1.0 and 1.8):

| Quantity (clocks of 6.2061 ns) | Run A measured (mean, per link) | Predicted `lat_cuts169` | Band (mean over 100 links) | Rule |
|---|---|---|---|---|
| E (echo, probe frames) | 15.91 | **15.9** | 15.5 to 16.3 | unchanged: probe frames use the registered start path and the unchanged receive stamp |
| D (register `d_last`) | 7.86 | **5.9** | 5.4 to 6.6 | D(run A) - 1.97 (xsim, both cuts) |
| L = 2E + D | 39.56 | **37.7** | 37.1 to 38.4 | 2E + D |
| **L - E = E + D (tick-to-trade)** | **23.77** (median-based 24, 148.1 ns net of fibre) | **21.8** (median-based 22, 22 x 6.2061 - 0.83 = **135.7 ns**; the mean 21.8 gives 134.5 ns) | 21.2 to 22.4 | E + D |

Per-link D takes values 6 to 8 (run A: 7 to 9) because the clock phase differs per lock; the mean is what is compared.

## Verdict lines (written now)
- **PASS:** every safety counter 0 in every restart (`safety_ok`), 100 of 100 and 20 of 20 locks, controllers done, no retry or give-up, operating conditions inside the window, order_ok equal to the orders sent, AND mean L - E over the 100 links at most 22.6 clocks (a saving of at least 1.2 clocks from 23.77).
- **WARN:** the same safety conditions and mean L - E between 22.6 and 23.3 (a saving of 0.5 to 1.2 clocks): at least one cut works, not both fully. Then build `EARLY_MAC` alone and `FAST_PRE` alone to separate them (two more builds; one bitstream cannot attribute).
- **FAIL:** mean L - E 23.3 or more (no saving), or any safety counter non-zero, `stale` or `late` or `poisoned` above 0 on an order that should have gone, a lost lock. A non-zero `stale` on a FAST_PRE frame means the live-field bus was not settled when the frame source sampled it (analysis in README): revert FAST_PRE.
- **ABORT, no verdict:** the bitstream's stamp differs from the one recorded, temperature or any rail outside the window at the start or end, the board's Linux not up.
- The result is judged on the per-link means; the median-based L - E is quoted beside it.

## Risk written down before the run
1. FAST_PRE adds the go pulse to a path ending in the PCS registers: timing closed in the one build made (+0.116 ns); one seed only.
2. The live-field bus margin shrinks from 3 to 2 clocks after the go pulse (README, section FAST_PRE); `stale` is the detector (it is checked later in the frame for FAST frames, so it still sees the sample the frame carries).
3. D depends on the clock phase per lock (the skew experiment in README): a few links may differ by a clock either way; the mean over 100 links is the test.
