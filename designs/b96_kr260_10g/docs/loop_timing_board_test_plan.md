# Board test plan for loop timing and buffer bypass: for the owner to approve (brief 96F)

Status: **a plan only.** Nothing here has run or been built. Each stage that touches the board waits for the owner's yes (the board OK of 2026-11-10 and the 2026-11-19 decisions cover other runs, not these). Predictions come from `docs/loop_timing_feasibility.md` and `results/b96f/latency_prediction.json`; the GT part of them is from a third-party GTY figure and is **unconfirmed for this GTH**, so the first pass/fail limits are deliberately wide.

## Headline

1. **Stage 0 (paper, Vivado probe):** confirm the Wizard can build bypass and expose the fractional-N ports. 2. **Stage 1 (loopback, one board, no new hardware):** bypass-only build B1, sequencing and latency at a fixed frequency; predicted tick-to-trade for `rm_gp` 205 ns to about 177 to 187 ns (GT part only). 3. **Stage 2 (loopback):** the loop-timed build with the tracker (predicted tick-to-trade about 133 to 150 ns for the control build, 115 to 131 ns for all3), which in loopback has nothing to track: proves the sequencing, guards and idle-hold behaviour; **cannot prove tracking.** 4. **Stage 3 (the 10G NIC, a few weeks away):** frequency tracking at the NIC's real offset, holdover and restarts; the first independent check of interoperability. Loopback alone is not enough to approve the design.

## Stage 0: Wizard probe (no board; a heavy slot, Vivado 2026.1)

**Done 2026-11-20 by brief 96F1: `results/b96f1/wizard_probe/README.md`.** Result: the core validates with `TX_BUFFER_MODE 0` and `RX_BUFFER_MODE 0` and gains the buffer-bypass controllers' done and error ports (the controllers consume `txphaligndone`/`rxphaligndone` inside the core, so those are not ports: the pass condition below is met by the controllers' done output); dynamic fractional-N is not reachable through the core, so the loop-timing build uses a hand-instantiated `GTHE4_COMMON` (`LOCATE_COMMON = EXAMPLE_DESIGN`). Stage 1's build is `rm_gp_bypass` (`results/b96f1/`), pre-registration `results/b96f1/preregistration.md`, script `_handoff/fpga_agent/run_96f1_stage1.sh`.

Read, in an in-memory project, the Wizard 1.7 properties that mention buffer mode, bypass, `TXOUTCLKSEL`, `TX_PROGCLK_SEL`, QPLL fractional-N, and the optional dynamic ports; build the 56A configuration with `TX_BUFFER_MODE 0` and `RX_BUFFER_MODE 0` (brief 97's probe failed). **Pass:** the core validates and lists `txphaligndone`, `txdlysresetdone`, `rxphaligndone`; **and** either dynamic fractional-N ports are available or a hand-instantiated `GTHE4_COMMON` path is chosen. **Fail:** stop and report; stages 1 to 4 change.

## Stage 1: B1 bypass only, loopback (one board; `board.lock`; no new hardware)

Build `rm_gp_bypass` (called `bp_rm` here before it was built): 96E `rm_gp` plus RX and TX buffer bypass (`TXOUTCLKSEL` 101, auto alignment). Same fibre loopback as 96C/96E.
- Steps: 100 restarts; per restart record `TXPHALIGNDONE` and `RXPHALIGNDONE` sequence and time, block lock, E, L, D; `GT_BUF` status (the buffer-status bits are meaningless in bypass: record, do not judge); SYSMON at start, end and every 5 s (operating conditions are evidence); 20 s dwell with armed orders.
- **Pass:** 100 of 100 restarts reach both align-done flags; every restart `safety_ok` (the nine safety counters 0, orders sent = fired = `order_ok`); SYSMON inside the DS925 windows used in 96C; E, L, D reproducible within +-1 clock across restarts (bypass should make latency deterministic: **record the spread; a smaller spread than 97C's 100-restart distribution is the evidence**).
- **Predicted (GT part unconfirmed):** E falls by 2.9 to 4.5 clocks (18 to 28 ns); tick-to-trade (L - E) of the `rm_gp` control build falls from about 33 clocks (205 ns) to about 28.6 to 30.2 clocks (177 to 187 ns), because B1 keeps the +2.3-clock buffer. **Fail** if E does not fall by at least 1.5 clocks (the bypass did not take effect or the GT estimate is wrong: report, do not tune); **warn** outside the predicted range.
- Abort and report if the link does not lock, alignment never completes, or any restart corrupts a frame.

## Stage 2: loop-timed build, loopback (one board; `board.lock`)

Build `lt_v2`: B1 plus the tracker (acquisition from RXV27/28, SDM writes, quarter-clock detector) and the direct crossing. **In loopback the recovered clock is our own, so the correct outcome is u staying put.**
- Tests: (a) sequencing: FREE_RUN, BLOCK_LOCK, FREQ_ACQ, PHASE_LOCK, LOCKED in order, `lt_*` counters as specified in section 6 of the feasibility note; (b) latency at u = 0 against stage 1 and 97C (the direct crossing's saving); (c) the holdover guard: inject a phase kick (a debug register adds a bit slip) and confirm `lt_guard_hits` rises, u stays within 5 ppm of its acquired value, and the state falls back to HOLDOVER and the buffered crossing without a lost or corrupted frame; (d) 20 s and then 10 min soaks at u = 0 with the trading path armed; (e) 100 restarts.
- **Pass:** every counter of the design 0 except the deliberately injected `lt_guard_hits`; `late`, `stale`, `order_bad` 0 across every crossing switch; u within +-0.01 ppm of its acquisition value without the kick (the loop is not wandering); the direct crossing's latency within the predicted range (tick-to-trade about 133 to 143 ns for the control build, 115 to 125 ns for all3 with V1; V2 about 7 ns more); **fail** if u moves more than 1 ppm with no injection (the unobservable-error hazard, section 8).
- **Cannot be shown here:** tracking, bandwidth, window logic, holdover behaviour against a real drifting source. Report as not tested.

## Stage 3: the 10G NIC (after it is installed; `board.lock`; owner supplies the NIC and cable)

The 96E real-offset plan (option B) is the setting. First, with the existing `rm_ctl` and `rm_gp` builds, measure the NIC's offset with RXV27/28 (0.1 ppm): if |offset| is below about 5 ppm the offset test is not informative for the rate-matched builds (`docs/real_offset_plan.md`), but loop timing's near-zero window behaviour is then the thing to test.
- Tests with `lt_v2`: acquisition (offset measured to 0.1 ppm, window selected, lock time); tracking over a soak of at least 1 h with the NIC idle and 1 h with traffic; the NIC's offset drift over temperature (record SYSMON and the NIC's own temperature if it reports one); NIC reset and link flap (partner TX off: expect HOLDOVER, buffered crossing, re-acquisition); our own restart 100 times; a fibre unplug of 10 s; frames in both directions with the NIC as source and sink (interoperability: block lock, FCS, minimum IFG).
- **Pass:** phase excursion (`lt_phase_over`) within +-2 ns of the set point (or the limit the stage 1 and 2 results and XAPP1276 justify); **zero** data errors (every safety counter 0) over the soaks; every loss-of-lock event counted and recovered to LOCKED within 1 s plus the acquisition window; u inside the window with `lt_sat_ticks` 0; no window hop for a partner at least 10 ppm from the nominal; for a partner within 10 ppm, the hop count reported (a result, not a failure, if TXPI bias is not built).
- **Fail and stop:** any corrupt frame in LOCKED; loss of lock without a counted HOLDOVER; u at the window edge for more than 1 s.
- Both ends must not loop-time: the NIC is a normal NIC (confirm it is not configured for SyncE slave).

## Order and approvals

Stage 0 needs a heavy slot only. Stages 1 and 2 need one board slot each, **one stage at a time**, the owner's yes for each build before it runs (new bitstreams of a new design variant), SRAM only, wall power, the usual limits (2.0 W, Tj 85 C). Stage 3 waits for the NIC. Stage 2's CDC decision (a direct crossing is a CDC-1 case; owner decisions 3 and 9 of 2026-11-19: no waiver, decided case by case) must be taken before the RTL for it is written.

## Reproduce

Nothing in this plan has run; the predictions are `python3 results/b96f/latency_prediction.py results/b96f/latency_prediction.json`.
