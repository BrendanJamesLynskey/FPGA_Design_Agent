# CDC soak rig: results (brief 11b, phase 2a; no board runs)

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
