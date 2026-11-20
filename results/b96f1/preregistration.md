# Pre-registration: GT buffer bypass on the KR260 (brief 96F1, build rm_gp_bypass)

Written 2026-11-20, before any board time, before the build was measured on a board. The numbers below are not to be changed after the run; a result outside them is reported as it is.

## Question
Does bypassing both GT elastic buffers (TX and RX, Wizard auto mode, TXUSRCLK from the QPLL through TXPROGDIVCLK, RXUSRCLK the recovered clock) shorten the optical loopback path on the KR260, and does the link stay safe?

## Builds compared
- **Reference:** build `rm_gp` (RATE_MATCH 1, RM_OWN 1, ENT_SYNC 1), board run 2026-11-19, `results/b96e/hw/20261119_231251/rm_gp/stage3.json` (stamp 98577dbc): E 21.0, L 54.0, D 12.0 clocks of 6.2061 ns (medians of the per-link minima over 100 restarts), 100 of 100 locks, safety counters 0, fibre lead 0.17 m (one way 0.8324 ns).
- **Test:** build `rm_gp_bypass` (this folder's `builds/rm_gp_bypass`): `rm_gp` with TX_BUFFER_MODE 0 and RX_BUFFER_MODE 0 and nothing else changed in the datapath. The elastic buffer rm_gp stays: it still does the receive-to-transmit crossing.

## Setting
Same board, same module and fibre loopback lead (0.17 m; a different lead moves the reference by the difference, which the driver applies: E once, L twice), 0 ppm (a loopback has no offset: the rate matcher's slip path is not exercised), SRAM only, wall power, laser on only during the measurement. Driver: `designs/b96_kr260_10g/host/b96f1_bypass.py` through `_handoff/fpga_agent/run_96f1_stage1.sh`. Same bench as 96E (`b96_bench.run_all`: 100 receive-datapath restarts, 5 probe frames and 5 armed orders per restart), then 20 resets of the whole GT, which also re-run the TX controller (the receive restarts re-run only the RX one).

## Predictions (decided now)
Source: `results/b96f/latency_prediction.json` and the 96F note. The GT buffer figure is a third-party GTY number, UNCONFIRMED for this GTH: the measurement is the point.
- **E falls by 2.9 to 4.5 clocks:** E median 16.5 to 18.1 (from 21.0).
- **L falls by 5.8 to 9.0 clocks** if D is unchanged (L = 2E + D): L median 45.0 to 48.2 (from 54.0). Tick-to-trade (L minus E) from 33.0 to 28.5 to 30.1 clocks (177 to 187 ns, from 205 ns).
- **D unchanged:** 12.0 within 1 clock (the decision path is not touched).
- 100 of 100 receive restarts lock; 20 of 20 full GT restarts lock; both controllers done and neither error flagged at every link-up; every safety counter 0; orders sent = fired = order_ok.

## Decision (the same rule is `verdict()` in the driver, with unit tests)
- **ABORT** (stop, laser off, report): the loaded build is not rm_gp_bypass (FEATURES bit 6 is 0), the link does not lock, alignment never completes, or any restart corrupts a frame.
- **FAIL:** any safety counter non-zero; any receive or full restart not locking; a controller error flag; a link up with a controller not done; operating conditions outside the recommended window at any sample (the run is void until repeated inside it); **E not falling by at least 1.5 clocks** (the bypass did not take effect, or the GT estimate is wrong: report, do not tune).
- **WARN:** everything above passes and E falls, but by less than 2.9 or more than 4.5 clocks.
- **PASS:** all of it, with the E fall inside 2.9 to 4.5.

## Recorded, not judged
E, L and D spread across restarts against 96E's (E minima 21 to 22: spread 1; L minima 53 to 55: spread 2): bypass should make the latency more repeatable, so a smaller spread is evidence for it, but it is not a gate. Lock clocks (96E: median 176, range 68 to 277); time to link-up after a full GT reset (host clock, coarse); GT_BUF TXBUFSTATUS and RXBUFSTATUS fields (meaningless with the buffers bypassed, UNCONFIRMED); the controllers' done bits; SYSMON at the start, the end and every fifth full restart (the 96E windows: Tj 0 to 85 C, VCCINT 0.698 to 0.742 V, VCCAUX 1.746 to 1.854 V, VCCBRAM 0.825 to 0.876 V).

## Not tested here
Tracking or loop timing (the later V2 build), a real frequency offset, the TX phase-interpolator ppm controller (the Wizard sets TXPIPPMPD_VAL = 1 in the bypass configuration: the ppm registers have no effect in this build), temperature extremes, the NIC. Bypass only moves the clock-domain structure inside the GT; whether a recovered-clock path has more jitter than the buffer's is not measured by E, L and D.

## Analysis plan
Medians of per-link minima, as 96E; the drop is reference minus measured, with the lead correction; no outlier removal; the verdict is printed by the driver and copied into the results folder with the raw `stage3.json`, `full_restarts.json` and `session.json`. A WARN or FAIL is followed by a report, not by a parameter change in the same session.
