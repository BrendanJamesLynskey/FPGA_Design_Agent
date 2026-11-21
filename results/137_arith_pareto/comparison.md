### Artix-7 xc7a35t-1, target 3.5 ns

| id | family | W/N | LUT | FF | Fmax synth | Fmax route | WNS route | lat clk | latency ns | Msps | err LSB | dyn mW | on front |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P01 | iterative | 14/12 | 161 | 86 | 178 | 196 | -1.60 | 15 | 76.5 | 13 | 8.18 | 6 | LT |
| P02 | iterative | 20/18 | 260 | 122 | 146 | 178 | -2.11 | 21 | 117.8 | 8 | 5.04 | 8 | LT |
| P03 | unrolled_k | 20/18 | 399 | 118 | 100 | 105 | -6.02 | 12 | 114.2 | 9 | 9.83 | 16 | LT |
| P04 | unrolled_k | 12/12 | 298 | 74 | 76 | 73 | -10.11 | 6 | 81.7 | 12 | 6.54 | 18 | - |
| P05 | unrolled_k | 18/16 | 1138 | 114 | 39 | 39 | -21.94 | 6 | 152.6 | 7 | 6.71 | 63 | - |
| P06 | pipelined | 10/10 | 324 | 354 | 367 | 301 | 0.18 | 12 | 39.9 | 301 | 6.17 | 36 | LT |
| P07 | pipelined | 20/18 | 1217 | 1249 | 324 | 270 | -0.20 | 20 | 74.0 | 270 | 5.04 | 122 | LT |
| P08 | pipelined | 14/12 | 530 | 571 | 351 | 286 | 0.00 | 14 | 49.0 | 286 | 7.97 | 63 | LT |
| P09 | pipelined_m | 18/16 | 915 | 383 | 130 | 128 | -4.32 | 8 | 62.5 | 128 | 11.91 | 76 | LT |
| P10 | pipelined_m | 12/12 | 472 | 278 | 194 | 199 | -1.54 | 8 | 40.3 | 199 | 4.63 | 41 | LT |
| P11 | pipelined_m | 22/20 | 1449 | 347 | 77 | 74 | -9.97 | 6 | 80.8 | 74 | 4.68 | 111 | LT |
| P12 | pipelined_m | 14/12 | 539 | 126 | 60 | 58 | -13.73 | 4 | 68.9 | 58 | 8.18 | 40 | LT |
| P13 | pipelined | 16/14 | 706 | 751 | 337 | 269 | -0.22 | 16 | 59.5 | 269 | 10.54 | 86 | LT |

default (2-anchor, 2025.2): RMS % error of prediction against Vivado (max abs in brackets)

| stage | LUT | FF | Fmax |
|---|---|---|---|
| post-synth | 14.7 (41.5), bias -0.1 | 3.4 (5.9), bias +1.7 | 13.6 (21.2), bias -4.3 |
| post-route | 15.5 (42.2), bias +0.0 | 3.4 (5.9), bias +1.7 | 7.3 (20.0), bias -0.8 |

refit m4 (51 points, 2025.2): RMS % error of prediction against Vivado (max abs in brackets)

| stage | LUT | FF | Fmax |
|---|---|---|---|
| post-synth | 14.5 (38.3), bias +1.1 | 3.0 (5.3), bias -0.2 | 13.2 (32.2), bias +0.7 |
| post-route | 14.3 (38.8), bias +1.0 | 3.0 (5.3), bias -0.2 | 10.7 (30.8), bias +4.6 |

Front of 10 points with at least 8.0 accuracy bits, area against latency: measured P01, P08, P12; the default model's front P01, P08, P12; measured front points the model's front would have dropped: none; model-front points that are not on the measured front: none.

Front of 10 points with at least 8.0 accuracy bits, area against throughput: measured P01, P08, P12; the default model's front P01, P08, P12; measured front points the model's front would have dropped: none; model-front points that are not on the measured front: none.

Spearman rank correlation, default model against measurement: luts_synth 0.977, luts_route 0.977, ffs_synth 1.0, ffs_route 1.0, fmax_mhz_synth 0.989, fmax_mhz_route 0.984, power_dyn_vs_luts+ffs 0.968

### Zynq UltraScale+ K26 (xck26), target 2.0 ns

| id | family | W/N | LUT | FF | Fmax synth | Fmax route | WNS route | lat clk | latency ns | Msps | err LSB | dyn mW | on front |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P01 | iterative | 14/12 | 144 | 86 | 529 | 503 | 0.01 | 15 | 29.8 | 34 | 8.18 | 8 | LT |
| P04 | unrolled_k | 12/12 | 286 | 74 | 213 | 192 | -3.20 | 6 | 31.2 | 32 | 6.54 | 24 | - |
| P07 | pipelined | 20/18 | 1206 | 1249 | 833 | 615 | 0.38 | 20 | 32.5 | 615 | 5.04 | 101 | LT |
| P09 | pipelined_m | 18/16 | 913 | 383 | 318 | 325 | -1.08 | 8 | 24.6 | 325 | 11.91 | 57 | LT |

default (2-anchor, 2025.2): RMS % error of prediction against Vivado (max abs in brackets)

| stage | LUT | FF | Fmax |
|---|---|---|---|
| post-synth | 9.0 (14.0), bias -2.3 | 3.6 (5.9), bias +2.3 | 64.0 (68.2), bias -63.9 |
| post-route | 5.9 (9.4), bias +1.6 | 3.6 (5.9), bias +2.3 | 59.9 (61.7), bias -59.9 |

refit m4 (51 points, 2025.2): RMS % error of prediction against Vivado (max abs in brackets)

| stage | LUT | FF | Fmax |
|---|---|---|---|
| post-synth | 6.5 (10.6), bias +0.6 | 3.2 (4.9), bias +1.4 | 62.3 (65.8), bias -62.3 |
| post-route | 7.2 (12.5), bias +4.7 | 3.2 (4.9), bias +1.4 | 58.0 (60.8), bias -58.0 |

Front of 3 points with at least 8.0 accuracy bits, area against latency: measured P01, P09; the default model's front P01, P09; measured front points the model's front would have dropped: none; model-front points that are not on the measured front: none.

Front of 3 points with at least 8.0 accuracy bits, area against throughput: measured P01, P07, P09; the default model's front P01, P07, P09; measured front points the model's front would have dropped: none; model-front points that are not on the measured front: none.

Spearman rank correlation, default model against measurement: luts_synth 1.0, luts_route 1.0, ffs_synth 1.0, ffs_route 1.0, fmax_mhz_synth 1.0, fmax_mhz_route 1.0, power_dyn_vs_luts+ffs 1.0

