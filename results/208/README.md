# 208: clock multiplexing, the AMD way, measured

Brief 208 (2026-11-24) asked what AMD's documents say about clock multiplexers, what Vivado 2026.1 actually does with
each way of building and constraining one, and what the agent must check. This folder holds the plan, every design,
script and report, and the measured table. The pre-registration (written before any run) is
[preregistration.md](preregistration.md); each expectation is answered below.

Tools: Vivado 2026.1 (build 6511674) and xsim 2026.1 with the unisim library; Quartus Prime Lite 25.1std (build 1129).
Parts: `xc7a35tcpg236-1` (7 series, "a7") and `xck26-sfvc784-2LV-c` (Zynq UltraScale+, "k26"); Quartus arms on Cyclone V
`5CEBA4F23C7` and MAX 10 `10M50DAF484C7G`.

## Records

| Path | What |
|---|---|
| `preregistration.md` | sources read, expectations per arm, stopping rules; written before the first run |
| `designs/mux_top.v` | two clocks into one BUFGMUX or BUFGMUX_CTRL; unrelated (two ports) or related (one MMCM); UG949 Fig. 101 paths A/B/C switchable (`INTERACT`) |
| `designs/mux_lut.v` | an RTL clock mux (`sel ? clk1 : clk0`), and the same with a constant select |
| `designs/casc.v` | BUFGCTRL trees from seven MMCM outputs: balanced 4:1 and 3:1 (UG949 Fig. 67), a chain of N (Fig. 69 for N=7) |
| `designs/pwr.v` | 512 registers gated by a BUFGCE, or the same with a fabric clock enable |
| `designs/clk_switch_safe.v` | the safe-switch protocol around one BUFGCTRL (liveness watch on a reference clock, IGNORE only for a dead input) |
| `xdc/` | the base constraints and one file per constraint arm (`arm_*.xdc`) |
| `tcl/run_jobs.tcl`, `tcl/jobs_*.txt` | the runner (one Vivado session per list) and the job lists actually run |
| `tcl/clock_mux_dump.tcl` | the netlist dump the check reads (copied to `flow/clock_mux_dump.tcl`) |
| `tcl/analyse.tcl` | second pass on the checkpoints: BUFGCTRL sites, per-input insertion delay, power with activity on the enable |
| `tcl/jobs_review*.txt`, `tcl/redump.tcl` | after the correctness review: three more constraint arms, the cascade bisection, and the re-dump of every checkpoint with the revised `clock_mux_dump.tcl` (the dumps under `records/` and the check's fixtures are from that revision) |
| `sim/` | xsim benches: `tb_bufgctrl.v` (e1 to e3), `tb_safe_switch.v` (protocol), `tb_lutmux.v` (c3) |
| `quartus/` | the Quartus arms: designs, SDC, `sta.tcl`, `run_quartus.sh` |
| `records/a7/<arm>/`, `records/k26/<arm>/` | every text report of every arm (check_timing, clocks, clock_interaction, methodology, cdc, timing_summary, exceptions, utilization, power, the dump). Reports over 300 kB keep their first 400 lines (they say so) |
| `records/sim/*.log` | the xsim logs (lines `SCEN ...` are the results) |
| `records/quartus/<arm>/` | Quartus fit summary, messages and Timing Analyzer reports |
| `records/analyse/analyse.tsv` | the second-pass measurements |
| `records/gotchas/` | tool failures met on the way (a report_clock_networks segfault) |
| `measured.json` | every number below, extracted from `records/` by `summarise.py` |

Arm names: `u_` unrelated clocks, `r_` related (MMCM) clocks; `none` no mux constraint; `srclog`/`srcphys`/`async`
`set_clock_groups -logically_exclusive`/`-physically_exclusive`/`-asynchronous` on the two **source** clocks;
`genphys`/`genlog` generated clocks on the mux output (UG949 p. 174 template) with `-physically_exclusive`/`-logically_exclusive`;
`gennog` generated clocks with no group; `case` `set_case_analysis` on the select; `noint_` the same RTL with no path A/B/C;
`ctrl_` BUFGMUX_CTRL instead of BUFGMUX. The stage in brackets is the netlist the numbers come from.

## Measured

### (a, b) Two clocks through a BUFGMUX: what each constraint style shows and hides

Paths A, B and C exist (`INTERACT=1`) unless the arm says `noint`. "Hidden" = endpoints that are real in hardware but
that the constraint removes from timing.

| Arm | multiple_clock | Summary WNS (ns), failing endpoints | report_cdc crossings | methodology (TIMING) | Verdict of the check |
|---|---|---|---|---|---|
| a7 u_none [route] | 33 | -6.630, 33 | 2 (68 rows, all Critical) | TIMING-6 x2, -7 x2 (CW), -16 x32 | CLKMUX-NO-GROUPS |
| a7 u_srclog [route] | 0 | **+0.419, 0** | **0** | none | CLKMUX-SRC-GROUPED |
| a7 u_srcphys [synth] | 0 | identical to u_srclog [synth] in every report | 0 | none | CLKMUX-SRC-GROUPED |
| a7 u_async [synth] | 0 | -0.113, 2 (clk0 to clk0 only) | 2 (37 rows) | TIMING-9 x1 | CLKMUX-SRC-GROUPED |
| a7 u_genphys [route] | 0 | -7.027, 32 (clk0 to clk1mux, the real crossing) | 4 | TIMING-6 x4, -7 x4, -16 x32 | pass |
| a7 u_genlog [synth] | 0 | identical to u_genphys [synth] in every report | 4 | as genphys | pass |
| a7 u_gennog [synth] | 33 | -6.913, 32 | 6 | **TIMING-56 x1** | CLKMUX-NO-GROUPS |
| a7 u_case [synth] | 0 | -0.113, 2; the clk1 mode is not timed at all (only clk0 reaches the mux output) | 1 | TIMING-6, -7 | CLKMUX-CASE (advisory) |
| a7 u_noint_none [synth] | 33 | +0.084, 0 | 2 | TIMING-6, -7 | CLKMUX-NO-GROUPS |
| a7 u_noint_srclog [synth] | 0 | +1.000, 0 | 0 | none | pass (correct: no path A/C) |
| a7 u_noint_genphys [synth] | 0 | +0.750, 0 | 1 (the select) | TIMING-6, -7 | pass |
| a7 u_ctrl_genphys [route] | 0 | -7.027, 32 | 4 | as genphys | pass |
| a7 r_none [route] | 33 | -6.724, 32 | 0 (related clocks) | TIMING-16 x32 | CLKMUX-NO-GROUPS |
| a7 r_srclog [route] | 0 | **+0.295, 0** | 0 | none | CLKMUX-SRC-GROUPED |
| a7 r_genphys [route] | 0 | -6.609, 32 | 0 | TIMING-16 x32 | pass |
| a7 r_noint_srclog [route] | 0 | +0.688, 0 | 0 | none | pass |
| a7 u_fp [synth] (`set_false_path` both ways between the sources) | 0 | -0.113, 2 (clk0 to clk0 only) | 2 | | CLKMUX-SRC-GROUPED |
| a7 u_inclgen [synth] (generated clocks, then groups over `-include_generated_clocks` of each source) | 0 | -0.113, 2 | **0** | | CLKMUX-SRC-GROUPED |
| a7 r_inclgen [synth] | 0 | -0.155, 2 | 0 | | CLKMUX-SRC-GROUPED |
| k26 u_none [route] | 33 | -6.030, 32 | 2 | TIMING-6, -7, -16 x32 | CLKMUX-NO-GROUPS |
| k26 u_srclog [route] | 0 | **+0.010, 0** | **0** | none | CLKMUX-SRC-GROUPED |
| k26 u_genphys [route] | 0 | -7.754, 32 | 4 | TIMING-6, -7, -16 x32 | pass |
| k26 u_gennog [synth] | 33 | -4.514, 32 | 6 | **TIMING-56 x1** | CLKMUX-NO-GROUPS |
| k26 r_srclog [synth] | 0 | +1.759, 0 | 0 | none | CLKMUX-SRC-GROUPED |
| k26 r_genphys [synth] | 0 | -5.021, 32 | 0 | | pass |

The other k26 arms (srcphys, genlog, async, case, noint_*) gave the same pattern as on a7; their rows are in
`measured.json`.

**What the wrong style hides.** With groups on the source clocks (`srclog`, `srcphys`, or `-asynchronous`), the 34
clk0-to-clk1 and 65 clk1-to-clk0 endpoints of a7 u_srclog are "Ignored" in report_clock_interaction. They include path
A, a real crossing from clk0's own registers into the mux fanout while clk1 is selected (WNS -6.63 ns unconstrained,
-7.03 ns with the correct constraint), and the BUFGMUX select's own setup check against clk1. The timing summary then
passes (+0.419 ns), report_cdc lists nothing, and the methodology report loses TIMING-6/7. With related clocks the
same mistake turns a -6.61 ns failure (r_genphys) into a pass (r_srclog, +0.295 ns). Every gate the flow had before
this brief passes the srclog arms: `multiple_clock` is 0, there is no Critical Warning, and report_cdc is empty.
`-asynchronous` removes the same paths from timing but report_cdc still lists the crossings, and the flow's advisory
`async_clock_groups_review` (brief 105A) fires. A `set_false_path` between the sources (report_clock_interaction:
"False Path", "Ignored") hides the same timing and also keeps report_cdc. The UG949 p. 173 form that groups
`-include_generated_clocks` of each source, added on top of the generated-clock template, groups clk0 with clk1mux:
the crossing taken when clk1 is selected is "Ignored" and report_cdc goes empty, as with the source groups.

**What the select is timed against.** Vivado times the select (f2). For a BUFGMUX, which Vivado retargets to a
BUFGCTRL driving CE0/CE1 with S0/S1 tied high, `sel_r` to `CE1` is a clk0-to-clk1 setup check with a 3.333 ns
requirement on the rising edge (report `timing_to_bufctl_route.rpt`). For a BUFGMUX_CTRL the same path goes to S1
against the **falling** edge of clk1 (UG472: S is sampled on the falling edge). A CE-select from one clock domain is
therefore a cross-clock setup check that cannot be met reliably when the clocks are unrelated. On S it only decides
whether one extra pulse of the old clock passes (UG472).

### (c) RTL clock mux

| Arm | Netlist | Methodology | Placement and routing | Simulation |
|---|---|---|---|---|
| a7 lut [route] | LUT3 driving a BUFG that synthesis inserted (`clkm_BUFG_inst`); no BUFGMUX inferred | **TIMING-14** x1 (CW), TIMING-6/7 | completed, no error | (c3) 40 select changes at times unrelated to the clocks: **40 runt pulses**, down to 25 ps |
| a7 lut_tied [route] | the LUT is gone: one BUFG | none | completed | |
| k26 lut [place] | LUT3 into BUFG, as on a7 | TIMING-14 (CW), TIMING-6/7 | placed, no error | |
| k26 lut_tied [place] | no LUT | none | placed | |

Synthesis neither refuses the RTL mux nor maps it to a clock buffer. It builds a LUT and puts a BUFG after it, and the
only signals are TIMING-14 in report_methodology and the glitch in simulation.

### (d) BUFGCTRL cascades

| Arm | Result |
|---|---|
| a7 bal4, bal3, chain7 [route]; chain8, chain12, chain13, chain14 [place] | placed |
| **a7 chain15, chain16, chain17** | **placement failed**: `Place 30-120 Sub-optimal placement for a BUFG-BUFG cascade pair` (rule `rule_cascaded_bufg`: cascaded BUFGs must be adjacent and cyclic), then `Place 30-99 IO Clock Placer failed`; chain15 also listed `rule_mmcm_bufg` (an MMCM driving a BUFG must be in the same half of the device) |
| k26 bal4, bal3, chain7, chain8 [place] | placed |
| **k26 chain9** | **placement failed**: the same Place 30-120, with 15 x `Place 30-1161 Could not place all instances for rule` |

On UltraScale+ the limit is the cascade ring of eight (UG572): 8 placed, 9 failed. On 7 series the ring is 16 per
half (UG472), but in this design, where one MMCM feeds every stage, 14 placed and 15 failed. The likely reason is that
the MMCM's BUFGs must share its half. So the ring is an upper bound, and a design can fail earlier. The check blocks a
chain longer than the ring and gives an advisory for 15 or 16 on 7 series. Messages: `records/*/a7_chain1[5-7]/` and
`records/k26/k26_chain9/placer_messages.txt`.

Second pass (`records/analyse/analyse.tsv`, source clock delay of each input's same-clock path on the mux fanout):

| Design | BUFGCTRL sites | Delay spread across inputs |
|---|---|---|
| a7 bal4 [route] | first level X0Y0, X0Y2; last X0Y1 (UG949 Fig. 67) | 0 (all four 5.897 ns) |
| a7 chain7 [route] | X0Y0 to X0Y6, consecutive | 5.897 to 7.077 ns: 1.18 ns |
| k26 bal4 [place] | first level X0Y25, X0Y31; last X0Y24 (adjacent in the ring of eight) | 2.713 to 2.728 ns: 15 ps |
| k26 chain7 [place] | X0Y25, Y24, Y31, Y30, ..., Y27 (round the ring) | 2.731 to 3.760 ns: 1.03 ns |

### (e) Switching in simulation (unisim models, xsim 2026.1)

| Scenario | BUFGCTRL (S select, CE tied) | BUFGMUX (CE select) | BUFGMUX_CTRL (S select) |
|---|---|---|---|
| e1 switch I0 to I1, both running | switched, 0 runt pulses | switched, 0 | switched, 0 |
| e2a I0 stops **low**, then switch | **locked up** (0 edges in 140 ns) | switched | **locked up** |
| e2b I0 stops **high**, then switch | **locked up** | **locked up** | **locked up** |
| e2c/e2d IGNORE0 raised after the stop | switched (both cases) | no IGNORE pin | no IGNORE pin |
| e3 select changed 10 ps before a clock edge, 20 times | 0 runts | 0 runts | 0 runts |

The safe-switch protocol (`designs/clk_switch_safe.v`, bench `tb_safe_switch.v`) behaved as designed:

- p1, both clocks running: switched with IGNORE never raised and no runt pulse.
- p2, switch requested to a stopped clock: refused (`err` pulsed once, the selection stayed).
- p3, the selected clock stopped high: IGNORE was raised for that input, the switch completed (10 edges in 140 ns),
  and there were no runt pulses.

### (f) BUFGCE versus a fabric clock enable (report_power, vectorless, enable toggle rate 2 %)

| Enable static probability | a7 BUFGCE: dynamic W (clocks) | a7 fabric CE: dynamic W (clocks) | k26 BUFGCE | k26 fabric CE |
|---|---|---|---|---|
| 0.1 | 0.033 (0.007) | 0.011 (0.003) | 0.014 (0.002) | 0.007 (<0.001) |
| 0.5 | 0.033 (0.007) | 0.021 (0.004) | 0.014 (0.002) | 0.010 (0.001) |
| 0.9 | 0.033 (0.007) | 0.030 (0.005) | 0.014 (0.002) | 0.013 (0.002) |

The vectorless estimate does not carry the enable's probability through a BUFGCE. The gated registers and the gated
clock tree are estimated as if always enabled, so on both parts the BUFGCE design reports **more** power than the
fabric enable at every duty. The power saving of a BUFGCE is real in silicon (the tree stops), but report_power shows
it only with switching activity from simulation (SAIF). The second pass also set activity on the gated clock net
itself (static probability 0.1, toggle rate 20 %): the dynamic power stayed at 0.033 W (a7) and 0.014 W (k26). A SAIF
run was not made.

### (q) Altera: clock control block in Quartus Prime Lite 25.1std

| Arm | Cyclone V 5CEBA4F23C7 | MAX 10 10M50DAF484C7G |
|---|---|---|
| q1 `altclkctrl`, glitch-free OFF, no group | clkctrl logic 0 ALUT, 0 registers; worst setup slack -2.680 ns (timing not met) | 0, 0; -2.655 ns |
| groups on the source clocks (`set_clock_groups -logically_exclusive`) | clk0/clk1 transfers become "false path"; worst slack **+6.956** ns (met) | "false path"; **+6.827** ns |
| generated clocks on the block's output, grouped (UG949 form) | clk1mux to clk0 (path C) still timed: clk0 worst slack -2.244 ns | timed: -1.414 ns |
| q2 glitch-free ON | **1 ALUT and 1 register** added in the clkctrl entity; a Critical Warning that the ENA port "should not be connected" when ENA register mode is "always enabled" | **2 and 2** added |
| q3 RTL clock mux | **Warning 19016 "Clock multiplexers are found and protected"** and 19017 naming `clkm` (mux_lut.v line 9) | the same two warnings |

- The output node of the block differs by family: `...|sd<n>|outclk` on Cyclone V, `...|clkctrl1|outclk` on MAX 10.
  The first MAX 10 generated-clock attempt used the Cyclone V name and was ignored (Critical Warning 332049, "empty
  collection"); it was rerun with `gen_m10.sdc`.
- The mistake carries over to Altera unchanged: grouping the sources hid the crossing; generated clocks kept it.
- Unlike Vivado, Quartus names an RTL clock mux at synthesis.
- Design Assistant was not run.

## Pre-registered expectations against what happened

| Exp | Expected | Happened |
|---|---|---|
| E-a1 | multiple_clock lists the FDM clock pins | yes: 33 pins |
| E-a2 | clock interaction "Timed (unsafe)", no common primary clock | yes |
| E-a3 | no TIMING-56 (60 %) | yes, none; instead TIMING-6/7 (Critical Warning) fired, which the pre-registration did not foresee |
| E-a4 | report_cdc lists the crossings as unsafe | yes, 68 Critical rows |
| E-a5 | the existing gates fail arm a | yes (multiple_clock, and the TIMING-6/7 Critical Warnings) |
| E-b1 | source groups hide path A from report_cdc; every gate passes | yes, and they also hide it from timing (WNS -6.63 to +0.419) |
| E-b2, E-b4 | logically = physically exclusive | yes: identical reports (a7, synth) |
| E-b3 | generated clocks keep path A visible | yes |
| E-b5 | `-asynchronous` loses the same coverage | **partly wrong**: timing coverage lost, but report_cdc still lists the crossings |
| E-b6 | TIMING-56 fires | yes, x1, on both parts |
| E-b7 | case analysis leaves one mode untimed | yes |
| E-b8, E-b9 | b8 passes, b9 fails | yes: +0.295 against -6.609 (a7, routed) |
| E-b10 | source groups are correct with no interaction | yes, and the check does not flag them |
| E-c1 | LUT3 + BUFG, TIMING-14; Place 30-574 (50 %) | LUT3 + BUFG and TIMING-14 yes; **no** Place 30-574 on either part |
| E-c2 | constant select removes the LUT | yes |
| E-c3 | runt pulses | yes, 40 of 40 |
| E-d1, E-d2 | balanced trees place on adjacent sites | placed; sites and delays in the second pass |
| E-d3 | a chain one longer than the ring fails or degrades | **failed placement** on both parts; on 7 series it failed earlier than the ring (15 of 16) in this design |
| E-d4 | chain of 7 places | yes on both |
| E-e1 | glitch-free switch with both running | yes |
| E-e2 | a clock stopped low lets the switch complete; stopped high locks up | **wrong for the S select**: BUFGCTRL and BUFGMUX_CTRL lock up in both cases; only the CE-select BUFGMUX completed when the old clock stopped low. IGNORE releases it, as UG472 says |
| E-e3 | CE setup violation may glitch or warn (uncertain) | no runt and no message: the unisim functional model has no timing; the CE glitch is a silicon timing effect the model cannot show |
| E-f1 | BUFGCE power falls with the enable duty | **wrong as an estimate**: the vectorless report does not respond to the enable at all |
| E-f2 | the select is timed | yes: CE on the rising edge, S on the falling edge, against each input clock |
| E-q1 | no logic beyond the block; both clocks timed until grouped | yes |
| E-q2 | glitch-free ON adds a few registers | yes: 1 (Cyclone V), 2 (MAX 10) |
| E-q3 | Quartus warns on an RTL clock mux (uncertain) | yes: 19016/19017; Design Assistant not run |

## Reproduce

From the worktree root (each Vivado list is one heavy job: take a slot with `_handoff/take_heavy_slot.sh`, run it under
`systemd-run --user --scope -p MemoryMax=5G nice -n 15`; `build/208/run_heavy.sh` did both):

    vivado -mode batch -source results/208/tcl/run_jobs.tcl -tclargs results/208/tcl/jobs_a7.txt build/208/a7      # 24 jobs, about 35 min
    vivado -mode batch -source results/208/tcl/run_jobs.tcl -tclargs results/208/tcl/jobs_k26_rest.txt build/208/k26
    vivado -mode batch -source results/208/tcl/analyse.tcl -tclargs build/208 results/208/records/analyse/analyse.tsv
    results/208/quartus/run_quartus.sh build/208/quartus             # ARMS=gen, ARMS=gen_m10: the generated-clock arms
    vivado -mode batch -source results/208/tcl/run_jobs.tcl -tclargs results/208/tcl/jobs_review.txt build/208/a7   # and jobs_review2/3, jobs_review_k26
    vivado -mode batch -source results/208/tcl/redump.tcl -tclargs build/208      # the revised dump on every checkpoint
    results/208/collect_runs.sh build/208/a7 results/208/records/a7      # and k26
    python3 results/208/summarise.py

The job lists hold absolute paths of the worktree that ran them; edit the prefix to rerun elsewhere. The first a7 list
stopped at `a7_r_none` (a segfault, see Known gaps) and was rerun from there as `jobs_a7_rest.txt`; the first k26 list
ran to `k26_u_ctrl_genphys` with routing and the rest ran as `jobs_k26_rest.txt` with lighter stages. Simulations
(no slot needed):

    xvlog results/208/sim/tb_bufgctrl.v $XILINX_VIVADO/data/verilog/src/glbl.v && xelab -L unisims_ver tb_bufgctrl glbl -s s && xsim s -R
    (tb_safe_switch.v also needs designs/clk_switch_safe.v; tb_lutmux.v needs no library)

## Known gaps and limits

- **Routing on xck26 was cut short.** The routed k26 arms (u_none, u_srclog, u_genphys, u_ctrl_genphys) took 25 to 59
  min each in route_design (the router fights the deliberately failing cross-clock paths). The remaining k26 arms ran
  to synthesis (the `r_` arms) or placement (lut, cascades, power), so their timing is a pre-route estimate.
- **The simulation is functional.** The unisim BUFGCTRL model has no setup or hold checks, so the CE-select glitch that
  UG472 warns about (setup violated on CE) cannot be shown in xsim (e3). Showing it would need a timing simulation with
  SDF or the board.
- **Power is a vectorless estimate.** No SAIF was made; the BUFGCE row says what the estimator does, not what silicon draws.
- **One design per question, one run per arm** (the tool is deterministic for a fixed input). The cascade limit is
  measured with chains fed by one MMCM in a small design. A design with clock buffers already placed elsewhere may hit
  it sooner.
- **report_clock_networks segfaulted** (Vivado 2026.1) on the post-synthesis MMCM design `a7_r_none`, inside
  `HASTClockSniffer::isForwardedClock` (stack in `records/gotchas/`). The runner stopped calling it, and no arm uses it.
- Altera: Design Assistant was not run. The Quartus arms are one small design per family, compiled once.
- **The check was tuned on these arms.** Its verdicts on the recorded designs (`measured.json` `check`) are a record,
  not a validation on held-out designs. The correctness review found five false-pass or false-fail cases in the first
  version, and they were fixed:
  - source groups via `-include_generated_clocks`;
  - a mux behind a BUFGCE preset;
  - paths from unrelated clocks;
  - false paths;
  - unconnected pins.

  The fixes are covered by real arms (u_fp, u_inclgen) or hand-made dumps. They were not reviewed again (one review
  per brief).
