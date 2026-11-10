# CDC soak rig: results (brief 11b, phase 2a; brief 11c fixes)

Every number below comes from a file in this folder.

## Simulation (cocotb + Icarus, metastability injection, reset storms)

| File | Run |
|---|---|
| [cdc_rig_sim.json](cdc_rig_sim.json) | 3 copies a variant (a->b far, b->a near, a->c boundary), 4 epochs + the Tj-stop readout, seed 11, one forced extra event in copy 0 (C1) |
| [cdc_rig_sim_seed2.json](cdc_rig_sim_seed2.json) | the same without the forced event, seed 23 |
| [cdc_rig_quick.json](cdc_rig_quick.json) | 1 copy a variant, 2 epochs (the CI setting) |

All three: every correct variant 0 errors and 0 lock-ups (except the copy with the forced event, which counted it);
every mutant predicted to fail in seconds caught (M5 and M10 in their b->a copies excepted, where the mechanism
cannot act); M1, M1b, M6a, M6b 0 errors; M4 errors in all three copies. These are model results (injection inside a
1 ns window; M4 and M6b/M6c delays modelled), not hardware rates.

## Brief 11c: focused simulations of the three smoke-run findings ([11c/](11c))

`sim/scenario.py` runs chosen variants with real clock ratios, staggered clock starts and storms (3 copies a variant:
a->b, b->a, a->c; errors listed per epoch, so an error at epoch 0 that never grows shows as a constant). `base` means
the 11b RTL (origin/main 7858765 and its successors up to db9e16c) under the new bench; `new` the 11c RTL.

| File | What | Result |
|---|---|---|
| [s1_startup_base.json](11c/s1_startup_base.json) | C1-C7, M1, M1b, M6a; clk_c and clk_f start 100 us after clk_a | every a->c copy: exactly 1 error at epoch 0, constant in epochs 1-2 (as on the board); a->b, b->a: 0 |
| [s1_startup_new.json](11c/s1_startup_new.json) | the same, 11c RTL | all 0 |
| [s2_c13_base_hb7687.json](11c/s2_c13_base_hb7687.json) | C13, storms, b at 65 MHz, 11b RTL, plain model | 0 errors in 162 reset events: the plain simulation does not reproduce the board |
| [s2_c13_legacy_hb7687.json](11c/s2_c13_legacy_hb7687.json), [s2_c13_legacy_hb15625.json](11c/s2_c13_legacy_hb15625.json) | 11b C13 with its checker's re-arm modelled as two flops sampling one asynchronous signal (`CDC_C13_LEGACY`, metastability injection), b at 65 / 32 MHz | a->b 1-2 errors, a->c 3, b->a 0 in about 160 events each (the board's directions) |
| [s2_c13_new_hb7687.json](11c/s2_c13_new_hb7687.json), [s2_c13_new_hb15625.json](11c/s2_c13_new_hb15625.json), [s2_c13_new_hb5102.json](11c/s2_c13_new_hb5102.json) | 11c C13, b at 65 / 32 / 98 MHz | 0 errors, 0 lock-ups, one relock per event (162-165) in every direction |
| [s3_m6_base_lut1.0.json](11c/s3_m6_base_lut1.0.json), [lut0.93](11c/s3_m6_base_lut0.93.json), [lut0.5](11c/s3_m6_base_lut0.5.json), [lut0.3](11c/s3_m6_base_lut0.3.json) | M6a/b/c, 11b RTL (8 padded stages for M6c), a padded stage modelled at 1.0 (the 11b model), 0.93 (slow corner), 0.5 (typical), 0.3 ns (fast corner) | M6c caught at 1.0 and 0.93 ns, 0 at 0.5 and 0.3 ns (the board saw 0); M6a, M6b 0 throughout |
| [s3_m6_new24_lut0.5.json](11c/s3_m6_new24_lut0.5.json), [lut0.4](11c/s3_m6_new24_lut0.4.json), [lut0.3](11c/s3_m6_new24_lut0.3.json) | the same, 11c RTL (24 padded stages for M6c, tear check) | M6c caught at all three (tens of thousands of errors a 400 us epoch); M6a, M6b 0 |

These are model results (injection inside a 1 ns window; padded-stage delay a modelled constant), not hardware rates.
The per-copy routed delays that fix the modelled stage delay: bit 11 against bit 0 of the small build's M6c (8 stages)
is 12.859 against 5.378 ns at the slow corner (0.93 ns a stage) and 4.780 against 2.347 ns at the fast corner
(0.30 ns a stage) in [delays_paths_small.csv](delays_paths_small.csv) of the 11b build.

## Vivado 2025.2, xc7a100tcsg324-1, default directives

| | Small build (28 copies) | Full build (352 copies) |
|---|---|---|
| Summary | [build_small.json](build_small.json) | [build_full.json](build_full.json) |
| report_cdc summary | [cdc_summary_small.rpt](cdc_summary_small.rpt) | [cdc_summary_full.rpt](cdc_summary_full.rpt) |
| Per-copy delay and skew | [delays_copies_small.csv](delays_copies_small.csv) | [delays_copies_full.csv](delays_copies_full.csv) |
| Per-endpoint delays | [delays_paths_small.csv](delays_paths_small.csv) | [delays_paths_full.csv](delays_paths_full.csv) |

The design's 536 copies reached 85 % of the LUTs after synthesis and did not place
([util_synth_design536.rpt](util_synth_design536.rpt), [place_fail_design536.txt](place_fail_design536.txt)); the
full build uses about two thirds of each count (`tcl/rig_map.tcl`).
