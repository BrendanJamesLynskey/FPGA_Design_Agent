# Pre-registration: 97C's three latency cuts plus the GT buffer bypass on the KR260 (brief 126, build lat_all3_bypass)

Written 2026-11-20, before any board time with this build and before the build was measured on a board. The numbers below are not to be changed after the run; a result outside them is reported as it is.

## Question
Do the two measured improvements add? 97C's `lat_all3` (default receive path, three logic cuts, GT buffers on) was the fastest tick-to-trade board run, and 96F1b's `rm_gp_bypass` (rate matcher kept, GT buffers bypassed) cut E by 4 clocks. `lat_all3_bypass` has the cuts and the bypass together.

## The two measured runs the prediction is made from (medians of the per-link minima over 100 link restarts, clocks of 6.2061 ns, 0.17 m fibre lead, same board and module)

| Run | Build | E | L | D = L - 2E | L - E | file |
|---|---|---|---|---|---|---|
| A | `lat_all3` (GT buffers on, default path, three cuts), 97C 2026-11-18 | 20.0 | 46.0 | 6.0 | 26 | `results/b97c/hw/20261118_194221/all3/stage3.json` |
| B0 | `rm_gp` (GT buffers on, own rate matcher), 96E 2026-11-19 | 21.0 | 54.0 | 12.0 | 33 | `results/b96e/hw/20261119_231251/rm_gp/stage3.json` |
| B1 | `rm_gp_bypass` (the same with both GT buffers bypassed), 96F1b 2026-11-21 | 17.0 | 46.0 | 12.0 | 29 | `results/b96f1/hw/20261120_215255/rm_gp_bypass/stage3.json` |

The bypass changed E by B1 - B0 = **-4.0 clocks**, L by **-8.0** (twice E: the loop crosses the transceiver twice) and D by **0**.

## Arithmetic (which terms add)
The bypass acts only inside the transceiver: the TX phase FIFO and serialiser path, and the RX elastic buffer and PMA-to-PCS path. The three cuts act only in fabric logic (the decision, the order's early MAC start, the go-pulse crossing's output register). They sit in different terms, so the effects should add:
- **E (one pass through MAC, PCS, GT, module, fibre, GT, PCS, MAC)**: E(A) + (E(B1) - E(B0)) = 20.0 - 4.0 = **16.0**. The prediction band is the AR 68177 reading, **E falls by 3.4 to 4.4 clocks** (`results/b96f1/preregistration.md`, amendment 2026-11-20; the 96F1b measurement, 4.0, is inside it): E median **15.6 to 16.6**, so 16.0 or 16.5 in practice.
- **D (receive-start stamp of the feed to transmit start of the order)**: unchanged by the bypass (B1 - B0 = 0), so D(A) = **6.0**, band 5 to 7 (one clock of counter resolution either way). The one place a change is possible: the default path crosses the decision from RXUSRCLK2 to TXUSRCLK2 by a pulse crossing whose latency depends on the phase between the two clocks, and the bypass changes how that phase is set at each lock. B1 did not test this (rm_gp has a rate matcher, not the pulse crossing).
- **L = 2E + D**: 2 x 16.0 + 6.0 = **38.0**, band **37.2 to 39.2**.
- **Tick-to-trade, board definition L - E (minus the fibre's 0.83 ns, which is part of E and L but is not on the pin-to-pin path)**: 38.0 - 16.0 = **22 clocks = 22 x 6.2061 - 0.83 = 135.7 ns**, against 26 clocks (160.5 ns) for `lat_all3` and 29 (180 ns) for `rm_gp_bypass`. Equivalently T2T = E + D (one trip through the transceiver path plus D): 16.0 + 6.0. Band 21.6 to 22.6 clocks (about 133 to 139.5 ns); the counter resolves one clock (6.2 ns).

## Predictions (decided now)
- E median 15.6 to 16.6; L median 37.2 to 39.2; D from the medians 5 to 7; L - E about 22 clocks (about 135.7 ns).
- 100 of 100 receive restarts lock; 20 of 20 full GT restarts lock; both buffer-bypass controllers done and neither error flagged at every link-up; no retry and no give-up expected (a retry that recovers is recorded, not judged); every safety counter 0; orders sent = fired = order_ok = 500 over the 100 restarts.
- Operating conditions inside the recommended window at the start, the end and every fifth full restart (die temperature, VCCINT, VCCAUX, VCCBRAM).

## Decision (the same rule is `verdict()` in `designs/b96_kr260_10g/host/b126_all3_bypass.py`, with unit tests)
- **ABORT**: the loaded build has the GT buffers on (FEATURES bit 6 = 0) or is rate-matched (bit 3 = 1); the link does not lock; alignment never completes; no E or L reading.
- **FAIL**: any safety counter non-zero; any receive or full restart not locking; a controller error flag; a controller that gave up; a link up with a controller not done; operating conditions outside the window (the run is void until repeated inside it); **E not falling by at least 1.5 clocks** against 20.0 (the bypass did not take effect); **L - E not below 26** (the combination is not faster than `lat_all3`). A different fibre lead is corrected for (E once, L twice).
- **WARN**: all of the above pass, but E falls by less than 3.4 or more than 4.4 clocks, or D leaves 5 to 7.
- **PASS**: all of it, E fall inside 3.4 to 4.4 and D inside 5 to 7. (L - E then lies between 20.6 and 23.6 clocks, the sum of the two bands; the predicted value is 22.)

## Recorded, not judged
E, L and D spread across restarts against run A (E minima 19 to 20, L minima 45 to 47) and run B1 (E 17 to 18): the bypass narrowed E's spread in B1; lock clocks; time to link-up after a full GT reset (coarse); GT_BUF TXBUFSTATUS and RXBUFSTATUS (meaningless with buffers bypassed); retry counts; SYSMON at the start, end and every fifth full restart.

## Not tested here
A real frequency offset (a loopback has none; the default path has no rate matcher, so a partner with a ppm offset would only change how often the pulse crossing sees each phase: not exercised); the TX phase-interpolator ppm controller (the Wizard powers it down in the bypass configuration); temperature extremes; the NIC; whether the order frame is acceptable to an exchange (the early start of the MAC preamble before the decision is final is `lat_all3`'s own design, with its FCS-poison safety, not changed here).

## Analysis plan
Medians of per-link minima, as 96E and 97C; the drop is the reference minus the measured, with the lead correction; no outlier removal; the verdict is printed by the driver and copied into the results folder with the raw `stage3.json`, `full_restarts.json` and `session.json`. A WARN or FAIL is followed by a report, not by a parameter change in the same session.
