# results/vivado_2026_1_remeasure: published numbers re-measured on Vivado 2026.1 (brief 49)

The owner, 2026-11-11: "all published material from now on should refer only to this Vivado release" (2026.1). Brief 49
re-measured on **Vivado 2026.1** (`/opt/Xilinx/2026.1`, free Basic licence tier) every Vivado number the site, the READMEs and
the docs quote, or withdrew it. Runs: 2026-11-11 and 12, on the build PC, under heavy slots, each Vivado in a 6 GB scope.
Reports here have dates, hosts, command lines and local paths removed.

Re-measured result folders (each has its own README and says how it compares with the earlier release):

| Folder | What |
|---|---|
| [f0a_2026_1](../f0a_2026_1/README.md), [f0b_2026_1](../f0b_2026_1/README.md) | T1 base and ILA builds and the board bring-up (brief 48's builds and board run, collected here) |
| [20_timing_exceptions_2026_1](../20_timing_exceptions_2026_1/README.md) | exception, I/O-timing and clock-uncertainty fixtures: all three tables identical |
| [16_cdc_gate_2026_1](../16_cdc_gate_2026_1/README.md) | CDC fixtures: table identical |
| [24_fsm_2026_1](../24_fsm_2026_1/README.md) | FSM controller variants: synthesis identical, 3 of 12 routed variants moved |
| [project_parity_2026_1](../project_parity_2026_1/README.md) | project-mode parity probes: every verdict the same |
| [19_ipgen_2026_1](../19_ipgen_2026_1/README.md) | the IP-generation worked examples |
| [33_vivado_speed_2026_1](../33_vivado_speed_2026_1/README.md) | build speed by thread count and the build cache |

In this folder:

| File | What |
|---|---|
| `collect.py` | writes the three JSON files below from the builds (`python3 results/vivado_2026_1_remeasure/collect.py <xpm before dir> <xpm after dir>`) |
| `dev_rebuilds.json` | six development runs whose saved designs were kept (`runs/<run_id>/<task>`, not committed), rebuilt with today's flow and test shell (`FDA_BUILD_CACHE=0 flow/run_vivado.sh runs/<id>/<task> base`). The site shows these, not the run records' own figures. The other runs' designs were not kept, so their timing and area are withdrawn from the site |
| `xpm_probe.json` | the QR1 probe (two clocks, `xpm_cdc_single`, `xpm_cdc_gray`) built to route with and without `flow/xpm_cdc.tcl` (`FDA_XPM_CDC=0`, a switch added for this measurement): -1.364 ns with 5 failing endpoints, then +8.891 ns, the same as the earlier release |
| `b30_hil_audio.json` | `designs/b30_hil_audio` base build and the per-instance utilisation the `ip_lib` READMEs quote (frame_crc 275 LUT, was 274; the others identical) |
| `b2_builds.json` | the four read-only board self-check designs built on 2026.1: every gate passes (not programmed) |
| `course_ref/` | `benchmark/tools/ref_build.py` whole-board builds of four development course tasks the course's project pages quote. `c13_hough_lines` missed 100 MHz by 0.166 ns here (setup gate fails); the reference was then amended and meets it by 2.565 ns ([../61_c13_amend_2026_1](../61_c13_amend_2026_1/)) |
| `lint/` | a probe: `synth_design -lint -file` still writes a text table on 2026.1, and the Tcl interpreter is 8.6.13 |
| `cells/` | the course's lesson 1.2 cell census on the 2026.1 blink checkpoint: identical |

Withdrawn rather than re-measured (not re-run, so not shown on the published pages): the QoR-assessment scores (the report does not
run on the Basic tier), the timing and area of development runs whose designs were not kept, the soak rig's own build figures and
its `report_cdc` verdicts on two rig-only mutants, the highest board power and junction temperature across the board checks (bitstreams
from the earlier release), the paired cost of the UltraFast reports, the FSM I/O study on real pins, the pblock count on the rig, and
the brief 35 clock-pessimism figures in the course. Board and instrument outcomes (UART tests, captures, audio, frames) and agent-run
outcomes (hidden tests, turns, hours, cost) are not Vivado numbers and are kept as recorded; where their bitstreams came from the
earlier release the pages say so without naming it.
