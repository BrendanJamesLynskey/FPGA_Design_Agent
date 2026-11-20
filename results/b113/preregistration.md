# Pre-registration: the ML decision stage on the KR260 (brief 113, build rm_gp_ml)

Written 2026-11-20, before any board time and before the build was measured on a board. The numbers below are not to be changed after the run; a result outside them is reported as it is. Everything the
board will see is **synthetic**: our own mock feed format, the generator's frames, a loopback lead; no exchange, firm or product.

## Question
Does the ML decision stage (a one-instrument book, the brief 87 order-flow features and 30 boosted trees, behind the rule, `designs/b96_kr260_10g/rm_gp_ml`) add any clock to the optical-loopback tick-to-trade
of the KR260 10G build `rm_gp`, and does the model on the hardware give the classes the Python twin gives?

## Builds compared
- **Reference:** build `rm_gp` (RATE_MATCH 1, RM_OWN 1), board run 2026-11-19, `results/b96e/hw/20261119_231251/rm_gp/stage3.json`: E 21.0, L 54.0, D 12.0 clocks of 6.2061 ns (medians of the per-link minima over 100
  restarts). The same hardware without the stage.
- **Test:** build `rm_gp_ml`, in **shadow mode** (ML_CTRL bit 0 = 0, the reset value: the rule decides alone, the model only counts) for the stage-3 loopback sequence, then shadow and veto sweeps.

## Setting
Same board, module and fibre loopback lead (0.17 m; a different lead moves the reference by the difference, which the driver applies: E once, L twice), 0 ppm, SRAM only, wall power, `_handoff/board.lock` held with a text starting `113:` (the host bench accepts that prefix), the same stage-3 sequence
(`designs/b96_kr260_10g/host/b96_bench.py run_all`, 100 receive-datapath restarts, 5 feed frames and 5 probes a link), then the sweeps: 20 runs of 50 generator frames in shadow mode and 20 in veto mode, each after a
state reset (ML_CTRL bit 1). The generator's frame is ADD ask, price 99.50, size 1, instrument 1 (the tracked instrument at reset); the rule's threshold is the reset value 99.75, so every frame is a rule hit.

## Predictions (decided now)
Sources: whole-core xsim with AMD's real XPM macros, `results/b113/latency.json` (tick-to-trade 12.93 clocks without the stage, **identical to the hundredth with it, in shadow and in veto mode, at all four receive-clock
phases**: change 0.00 clocks) and the Python twin for the counters.
- **No clock added:** E, L and D medians equal the 96E run's, **within 1.0 clock** (the stamps have a one-clock resolution, medians half a clock; the receive-clock phase at each link-up is random). Predicted change: **0**.
  Tick-to-trade (L minus E) unchanged at 33.0 clocks (205 ns).
- **Counters equal the twin's, exactly, in every run.** The twin's stream for 50 identical frames after a reset: the first frame sees the empty book and the model says up, every later frame says down (the book then holds
  an ask and no bid). Shadow mode: n_obs 50, n_cls_down 49, n_cls_flat 0, n_cls_up 1, n_dec 50, n_veto 0, n_would_veto 49, 50 orders sent. Veto mode: the same classes, n_veto 49, n_would_veto 0, **1 order sent**
  (the first frame). n_late, n_race, n_drop 0; n_apply 50.
- 100 of 100 receive restarts lock; every safety counter 0; orders sent = fired = order_ok in the stage-3 run (shadow mode); operating conditions (die temperature, VCCINT, VCCAUX, VCCBRAM, PS rails) inside the
  recommended window at every sample.

## Decision (the same rule is `verdict()` in the driver, with unit tests)
- **ABORT** (stop, laser off, report): FEATURES (0x008) bit 8 is 0 or ML_ID (0x308) is not 0x01130001 (the loaded build is not rm_gp_ml), the link does not lock, no E or L reading.
- **FAIL:** any safety counter non-zero; any restart not locking; operating conditions outside the recommended window (the run is void until repeated inside it); any stage counter different from the twin in either
  sweep (the model on the hardware is not the model in the twin); n_late or n_race not 0; **E or L more than 2.0 clocks from the 96E reference** (the stage added or removed latency that simulation says it does not).
- **WARN:** everything above passes, but E or L is more than 1.0 and at most 2.0 clocks from the reference.
- **PASS:** all of it, with E and L within 1.0 clock of the reference and every stage counter equal to the twin's.

## Recorded, not judged
E, L, D spread across restarts; lock clocks; the stage's last feature word (MLV11, MLV12) and book view (MLV13) for the last run; the lead correction applied; the order count of each veto run.

## Not tested here
A feed that is not the generator's (the board has no other source: the model is bit-exact against the twin on a 350-frame mixed synthetic feed in simulation, `results/b113/twin/`), real-offset partners,
frames closer than 10 clocks, temperature extremes, the NIC.

## Analysis plan
Medians of per-link minima as 96E; the change is measured minus reference with the lead correction; no outlier removal; the verdict is printed by the driver and copied into the results folder with the raw
`stage3.json`, `sweeps.json` and `session.json`.
