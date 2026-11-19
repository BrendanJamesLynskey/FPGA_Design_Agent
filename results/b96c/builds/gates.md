# 96C build gates (generated from builds/*/digest.json and run.json)

Built 2026-11-19 from git f47986f4 (Vivado 2026.1, xck26-sfvc784-2LV-c, 6G scope, 1 thread). Regenerate: `python3 results/b96c/gen_gates.py`.

| metric | control | all3 | ppm_ctl | ppm_all3 |
|---|---|---|---|---|
| LUT | 6613 | 6574 | 6728 | 6759 |
| FF | 15667 | 15654 | 15656 | 15660 |
| LUTRAM | 44 | 44 | 44 | 44 |
| BRAM tiles | 0 | 0 | 0 | 0 |
| WNS ns | 0.293 | 0.004 | 0.135 | 0.033 |
| WHS ns | 0.01 | 0.01 | 0.011 | 0.01 |
| period ns | 6.206 | 6.206 | 6.206 | 6.206 |
| power W | 0.928 | 0.947 | 1.102 | 0.93 |
| Tj C | 46.9 | 47.0 | 48.2 | 46.9 |
| DRC critical | 0 | 0 | 0 | 0 |
| methodology critical | 0 | 0 | 0 | 0 |
| wall s | 1278.1 | 1567.3 | 1324.2 | 1543.3 |
| scope cap hits | 0 | 989 | 2 | 1033 |
| scope swap peak MiB | 0 | 697 | 0 | 706 |
| scope anon peak MiB | 6002 | 6121 | 6009 | 6122 |
| gates true (of 29) | 29 | 29 | 29 | 29 |

Per-gate (T = true):

| gate | control | all3 | ppm_ctl | ppm_all3 |
|---|---|---|---|---|
| bitstream_present | T | T | T | T |
| cdc_no_critical | T | T | T | T |
| drc_clean | T | T | T | T |
| exceptions_clean | T | T | T | T |
| hold | T | T | T | T |
| io_timing_clean | T | T | T | T |
| methodology_no_critical | T | T | T | T |
| no_unconstrained_endpoints | T | T | T | T |
| post_place_hold | T | T | T | T |
| post_synth_cdc_no_critical | T | T | T | T |
| post_synth_cdc_structure_clean | T | T | T | T |
| post_synth_drc_clean | T | T | T | T |
| post_synth_exceptions_clean | T | T | T | T |
| post_synth_gt_drc_clean | T | T | T | T |
| post_synth_gt_lane_pins | T | T | T | T |
| post_synth_gt_rate_in_window | T | T | T | T |
| post_synth_gt_refclk_pin_quad | T | T | T | T |
| post_synth_gt_reset_sequence | T | T | T | T |
| post_synth_gt_user_clock_limit | T | T | T | T |
| post_synth_gt_user_clocks_timed | T | T | T | T |
| post_synth_io_constraints_clean | T | T | T | T |
| post_synth_methodology_no_critical | T | T | T | T |
| post_synth_no_unconstrained_endpoints | T | T | T | T |
| post_synth_resets_clean | T | T | T | T |
| post_synth_resources_in_range | T | T | T | T |
| power_junction_ok | T | T | T | T |
| pulse_width | T | T | T | T |
| rtl_methodology_no_critical | T | T | T | T |
| setup | T | T | T | T |
