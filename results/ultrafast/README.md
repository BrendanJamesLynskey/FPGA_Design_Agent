# results/ultrafast

Build results for brief 04e: T1 (`designs/t1_dimmer_counter`, **base** variant, the same sources as F0A, build
stamp `dfd4624e`) rebuilt with `flow/run_vivado.sh designs/t1_dimmer_counter base` through the staged flow
(`flow/build.tcl` with the UltraFast stage reports; `flow/gates.py` grouped by stage), then collected with
`flow/summarise.py designs/t1_dimmer_counter --out results/ultrafast`. Vivado 2025.2, local build PC, working tree
of branch `ultrafast-gates` on top of `20e0aeb`.

| File | What |
|---|---|
| [t1_dimmer_counter.md](t1_dimmer_counter.md) | The summary table: every stage and gate, timing, utilisation, power with its environment, run time per stage, memory |
| `t1_dimmer_counter_base.json` | Everything the table is made from: `gates` (flow/gates.py, with `stages`) and `run` (the runner's run.json) |

## Against F0A (`results/f0a/t1_dimmer_counter_base.json`, same sources)

| | F0A | 04e | Change |
|---|---|---|---|
| every stage / gate | post_route + bitstream pass (other stages not run) | rtl, post_synth, post_place, post_route, bitstream all pass; first failed stage: none | +3 stages, +6 gates |
| setup WNS / TNS (ns) | 3.911 / 0.0 | 3.911 / 0.0 | identical |
| hold WHS / THS (ns) | 0.106 / 0.0 | 0.106 / 0.0 | identical |
| pulse width WPWS (ns) | 4.5 | 4.5 | identical |
| LUT / FF / CARRY4 / IOB / BUFG | 495 / 488 / 29 / 55 / 1 | 495 / 488 / 29 / 55 / 1 | identical |
| DRC / methodology / CDC | 0 errors; XDCH-2 x54 warnings; all paths safely timed | same | identical |
| bitstream (bytes) | 674,216 | 674,216 | identical |
| post-synthesis WNS (ns) | - | 4.602 | new |
| QoR assessment score, after synthesis / after routing | - | 5 / 5 ("Design runs will meet timing"; one REVIEW item that does not affect the score: Max LUT Combined 46.6 % > 20 %) | new |
| post-placement WHS (ns) | - | -0.027 (gate: > -0.5) | new |
| RTL-stage methodology | - | 0 critical, XDCH-2 x54 warnings (the same rule as after routing) | new |
| power: total / dynamic / static (W) | 0.133 / 0.036 / 0.097 | 0.150 / 0.036 / 0.114 | static +0.017 W (see below) |
| junction temperature (C) | 25.6 (Vivado's defaults: 25 C ambient, medium heat sink, 250 LFM, a medium 10x10 in 12-15 layer board; thetaJA 4.6 C/W) | 42.7 (board environment: 40 C ambient, still air, no heat sink, thetaJA 18.2 C/W) | the gate now accepts it |
| Vivado wall time (s) | 187.0 | 191.0 | +4.0 |
| Vivado peak RSS (MiB) | 2,525 | 2,693 | +168 |
| scope peak anonymous memory (MiB) | 1,898 | 2,071 | +173 |
| scope peak charged memory (MiB) | 1,979 | 2,277 | +298 |
| 6 GB cap hits / OOM kills | 0 / 0 | 0 / 0 | - |

Per-stage durations (s, from `run.stages_s`): F0A read 15.4, synth 79.5, opt 10.5, place 5.8, phys_opt 0.4, route
35.2, reports 4.7, bitstream 29.5. 04e read 13.4, **elaborate 26.1, rtl_reports 0.8**, synth 47.5, **synth_reports
8.4**, opt 3.7, place 6.1, phys_opt 0.3, **place_reports 0.7**, route 35.8, reports 5.1 (now including the post-route
`report_qor_assessment`), bitstream 29.6. The added reports cost about 10 s; the separate elaboration cost 26 s but
the `synth_design` that followed ran 32 s faster than F0A's, so the whole build took 4 s longer. One build each; the
usual run-to-run variation of a few seconds applies.

**Why the power figures changed.** F0A's `report_power` used Vivado's default thermal environment (a medium heat
sink, 250 LFM airflow, a medium 10x10 in 12-15 layer board, 25 C ambient; thetaJA 4.6 C/W), which put the junction at 25.6 C. Since 04c the
flow runs `set_operating_conditions` with the board's environment from `boards/nexys_a7_100t/board.yaml` (still
air, no heat sink, a small 4-7 layer board, 40 C ambient) before `report_power`, and the power gate refuses a
report made with the defaults. Static power rises with junction temperature (UG949 ch. 2 "Static Power"), so the
same netlist now reports 0.114 W static instead of 0.097 W, 0.150 W total instead of 0.133 W, and a junction of
42.7 C. Dynamic power (0.036 W, vectorless) is unchanged. Both are far inside the 2.0 W / 85 C wall-power limits.
