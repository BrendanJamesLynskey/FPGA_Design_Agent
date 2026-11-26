# Constraints complete before synthesis (brief 230)

Owner, 2026-11-26: "when written by hand, constraints are written before synthesis ... every i/o could be somehow constrained ... Surely clocks and
resets are known before synthesis? It's important that synthesis is aware of timing constraints, for it to meet timing closure later on."

Before this brief the XDC was read before `synth_design` (flow/build.tcl), so synthesis did see the constraints, but whether they were **complete**
was known only after synthesis (`post_synth_no_unconstrained_endpoints`, Vivado `check_timing`). The pre-synthesis checker (`check_constraints`) read the XDC text for wrong
values, order and names, never for a port or a clock that nothing covers. In the 224 arm's 8 recorded runs, 10 stage visits failed on that gate after a full
synthesis each (`results/230_constraints_complete/records_scan.json`).

The code is `flow/known_constraints.py`. It reads files only (the top module's ports and the RTL's primitive instances, `spec.yaml`, `boards/<board>/board.yaml`, the XDC text): no model, no Vivado.

## Port classes

Every top port gets exactly one class. A port that nothing covers is a finding, rule `FDA-CON-14`, reported by `check_constraints`, and **`build` does not start Vivado** while one is open.

| Class | How a port gets it | Covered when the XDC has | Who writes it |
|---|---|---|---|
| clock | a `create_clock` names it | the `create_clock` | the board's clock by `board_constraints`; others the model |
| gt_refclk | the port feeds an `IBUFDS_GTE*` | a `create_clock` on the P port (the N port takes none) | **the flow** when the board file lists exactly one lane with a reference clock: its pins (`PACKAGE_PIN`) and frequency; otherwise the model |
| fwd_clock | a `create_generated_clock` names the output (a forwarded clock, brief 20) | the generated clock | the model |
| gt_serial | the port is wired to a `GT*_CHANNEL` serial pad (or is named like one: rx/tx, p/n) | nothing: the pads go to the GT pads, no fabric timing | nobody |
| reset | the name is a reset (`rst`, `reset`, `aresetn`, ...) | an input delay (a timed synchronous reset) or a commented false path plus the placeholder delay | the model (judgement: asynchronous into a synchroniser, or timed) |
| slow | the port matches `slow_ports` in the board file | a 0 ns placeholder delay and a commented false path | **the flow** (`known_post.xdc`) |
| async | `spec.yaml` marks the port `async: true` | the same | **the flow**, with the spec's `reason` in the comment |
| input / output | everything else | `set_input_delay` / `set_output_delay` from the interface's data sheet formula (brief 20 rules) | the model |

A **false path alone does not cover a port**: Vivado's `check_timing` lists a port that has a false path and no delay under `no_output_delay` ("2 ports with no output delay but user has a false path constraint"),
and the gate counts it (measured: 224 arm p5 run 1, `led[0]`, `led[1]`). So a slow port gets the 0 ns placeholder delay as well, as `designs/b96_kr260_10g/design.xdc` does by hand.

## Who writes which constraint

- **The flow writes** (`flow/prepare.py` -> `<build>/known_pre.xdc`, read before the design's XDC, and `<build>/known_post.xdc`, read after it):
  - the clock of each `BSCANE2` in the RTL (the JTAG TCK, `create_clock -name jtag_tck -period 33.333` on `<instance path>/INTERNAL_TCK`): this covers the supplied `jtag_bus` wherever the module came from (`data/` or `designs/`);
  - the clock of each `USR_ACCESSE2` (`create_clock -name usr_cclk -period 10.000 [get_pins <inst>/CCLK]`) and a commented false path from it (the USR_ACCESS word is constant after configuration);
  - for each slow or `async: true` port the design's XDC does not already constrain: the placeholder delay against the board clock's port and the false path, each with its reason; one command per kind, listing the ports together (a false path on a constant output alone is reported `EXC-IGNORED`, measured);
  - for the one transceiver reference clock pair of a one-lane board: `PACKAGE_PIN` on both pins and the `create_clock` at the board's frequency, unless the design's XDC already has them.
  A clock the design's own XDC already defines on the same pin is left alone (nothing is written twice). `FDA_KNOWN_XDC=0` turns the files off.
- **The model writes** the timed-interface delays and the design's own exceptions (CDC groups, multicycle paths) and every clock the flow cannot know (a reference clock's frequency comes from the board file, `gt.<lane>.refclk.mhz`).
- **The repair note** (`gates` tool, after a failed post-synthesis gate): each unconstrained endpoint with its class and the line to add, or the question when the class is unknown ("which port, primitive or generated clock should clock u_div?"), not only the raw report.

## Hard blocks

| Block | What it needs | Who supplies it | How we know |
|---|---|---|---|
| BSCANE2 (clock source) | a create_clock on the TCK output (INTERNAL_TCK pin), at most 30 MHz on the JTAG cable; its crossings go through xpm_cdc macros, which carry their own constraints | flow (known_pre.xdc) for jtag_bus; the design for its own BSCANE2 | measured (Vivado 2026.1, xck26): results/230_constraints_complete/elab_probe: the fixture's TCK registers are unclocked in report_clocks at elaboration and in check_timing no_clock after synthesis; 224 p5 run 1 listed 193 u_jtag registers; designs/b96_kr260_10g/design.xdc uses this line and closes |
| USR_ACCESSE2 (clock source (configuration clock)) | a clock on the CCLK pin (the primitive is a clocked cell with an internal clock); the DATA word is constant after configuration, so paths from it are cut with a reason | flow (known_pre.xdc) | measured (Vivado 2026.1, xck26): after synthesis check_timing no_clock lists u_usr/CCLK (fixture and 224 p5 run 1); at elaboration the CCLK pin is NOT among the registers' clock pins, so only the static primitive check sees it; 209 and 224 designs that closed define a clock on CCLK |
| STARTUPE3, STARTUPE2 (dedicated pins) | nothing for the USRCCLKO/USRDONE pins in fabric timing unless the design drives the flash clock (then a create_generated_clock on USRCCLKO is the design's, brief 20 handling) | document only | document: UG570 (configuration), UG949; not measured |
| ICAPE3, ICAPE2 (clocked by the design) | its CLK is an ordinary fabric clock (no extra constraint); the configuration port is not a package pin | document only | document: UG570; not measured |
| SYSMONE1, SYSMONE4, XADC (analog inputs and a DCLK) | DCLK is an ordinary fabric clock (1 to 5.2 MHz ADC clock after the internal divider); VP/VN and VAUXP/N are dedicated analog pins: no XDC delay, no I/O standard | document only | document: UG580, DS925 table 127; not measured |
| BUFGCE_DIV (derived clock) | Vivado derives the divided clock from the input clock automatically when the input has a clock; a divider fed by an unclocked pin leaves the output unclocked | Vivado (automatic derivation) | measured (Vivado 2026.1, xck26): the fixture's BUFGCE_DIV output is an auto-derived generated clock (P,G,A, divide by 2) in report_clocks at elaboration and after synthesis, with no constraint of ours |
| MMCME2_ADV, MMCME3_ADV, MMCME4_ADV, PLLE2_ADV, ... (derived clock) | outputs are derived automatically from the input clock (create_clock on the input only); feedback needs nothing | Vivado (automatic derivation) | measured (Vivado 2026.1, xck26): the fixture's MMCME4_ADV CLKOUT0 and CLKFBOUT are auto-derived (P,G,A) at elaboration and after synthesis; so are clk_u and fb in designs/b96_kr260_10g |
| GTHE4_CHANNEL, GTHE3_CHANNEL, GTYE4_CHANNEL, GTYE3_CHANNEL, ... (transceiver (serial pads, reference clock, user clocks)) | TXP/TXN/RXP/RXN go to the GT pads: no fabric timing and no XDC delay (placement is the GT site, LOC on the channel); the reference clock port needs a create_clock at its frequency; TXOUTCLK/RXOUTCLK are derived by Vivado through the PLL and the BUFG_GT dividers from that reference clock | the design (create_clock on the reference clock port); the board file lists the lane pins and the frequency | measured (Vivado 2026.1, xck26, designs/b96_kr260_10g): after synthesis check_timing is zero in every check, with the four serial pad ports in the top and only the reference clock constrained; the channel and QPLL clocks (TXOUTCLK, RXOUTCLK, QPLL0OUTCLK) are auto-derived (P,G,A) in report_clocks, at elaboration as well |
| IBUFDS_GTE4, IBUFDS_GTE3, IBUFDS_GTE2, IBUFDS_GTE5, ... (transceiver reference clock input) | PACKAGE_PIN on both pins of the pair (the board lane's MGTREFCLK pins) and a create_clock on the P pin at the reference frequency (the N pin takes none) | flow (known_pre.xdc) when the board file lists exactly one lane with a reference clock and the design names neither; otherwise the design | measured (Vivado 2026.1, xck26): 224 p5 run 1 replay: a reference clock with a create_clock but no PACKAGE_PIN on its ports left AVAL-324 (hard block needs LOC), AVAL-326, NSTD-1 and UCIO-1 open; designs/b96_kr260_10g/design.xdc places Y6/Y5 and clocks the P port. The flow now writes the board's pins and frequency |
| zynq_ultra_ps_e, PS8, zynq_ultra_ps_e_0 (processor system (Zynq UltraScale+ PS)) | MIO and PS DDR pins are fixed by the PS and take no XDC; PL clocks pl_clk0..3 take their period from the PS IP's own constraints; EMIO routed to PL pins is ordinary fabric I/O and gets an ordinary class; PS-PL AXI crossings follow the IP's clocks | the AMD IP (its own XDC, generated with the IP) | measured (Vivado 2026.1, xck26, designs/b191_ps_axi_lat elaborated): report_clocks lists the PS IP's own pl_clk0 clocks with no XDC of ours for them, and the PS has no top ports (MIO and DDR are fixed by the PS); EMIO through PL pins is not in that design (not measured) |
| ddr4, mig, pcie, cmac, ... (AMD IP that ships its own XDC (memory controller, PCIe, CMAC, other GT-based IP)) | the IP's pins, clocks and exceptions come from the XDC it generates; our XDC must not duplicate or override them, and the build must read it | the AMD IP (ip_tcl generates it with its constraints) | document: PG150, PG213, PG203; not measured (no such design in this repository) |

## What a user could get wrong

- **A port the spec calls slow that is actually timed.** `slow_ports` (board file) and `async: true` (spec) cut the port from timing with a false path, which hides a real failure if the port is in fact synchronous to a clock. The board file's list is a fact about the board (LEDs, an SFP+ cage's status pins);
  for a spec's `async: true` give a `reason:` on the port. The false path's comment carries it; with no reason the comment says "no reason given: add one to the spec" and the constraint is still written, so the missing reason is visible in the XDC and in `known_post.xdc` in the build directory.
- **The model's own clock on the same pin replaces the flow's.** Vivado keeps one clock per source without `-add`; the flow skips a pin the design's XDC already clocks, so the design's clock (name, period) wins and the flow's false path from `usr_cclk` is not written either.
- **An XDC that builds port lists in Tcl** (`set`, `foreach`, `$var`) cannot be read as text: no `FDA-CON-14` is raised for it, and the post-synthesis gate is the only check.
- **`inout` ports** are covered by either delay in the pre-synthesis check; `check_timing` wants both an input and an output delay, so the post-synthesis gate can still list one.
- **The period 10.000 ns of `usr_cclk`** is a choice for a clock that carries no timed path (its paths are cut); it is not a measured configuration clock rate.
- **A constant output** (such as a tied-off laser disable) may be dropped from `check_timing`'s list by Vivado; the pre-synthesis rule still asks for a class, because the constant is not known from the files.

## Measured

All on Vivado 2026.1, xck26-sfvc784-2LV-c; files in [results/230_constraints_complete](../results/230_constraints_complete/README.md).

- **Records first (no new runs).** In the 8 recorded runs of 224's arm that have a trace, 17 stage visits ran a gates call and 10 of them failed `post_synth_no_unconstrained_endpoints`; in the 16 recorded 209 pilot runs that have build results (no trace, so counted per gates call) 6 gates calls in 4 runs failed it.
  Every endpoint in those reports is one the new code writes (the `u_jtag` TCK registers, `u_usr/CCLK`, the LED outputs) or flags before synthesis (`records_scan.json`; by instance and port name against each run's final design, not by re-running).
- **Replay of 224 p5 run 1** (the state where it stopped, and the state a constraints visit starts from: board pins, board clock, reference clock only): with the flow's files `check_timing` is zero in every check and `post_synth_no_unconstrained_endpoints` passes with no model repair
  (the original: `u_usr/CCLK` no clock, `led[0]`, `led[1]` no output delay). The other post-synthesis gates also pass except `post_synth_methodology_no_critical`: TIMING-6 and TIMING-7, two clocks (`sys_clk_pin`, `gt_refclk0`) timed together with no clock group, a judgement the spec states (asynchronous) and the model writes. Before the board's reference clock pins were written (first replay), DRC also failed AVAL-324, AVAL-326, NSTD-1 and UCIO-1.
- **A false path alone is not enough.** `check_timing` listed `led[0]`, `led[1]` (false path, no delay) under `no_output_delay`; and a separate false path on a constant output (`sfp_tx_disable`) is `EXC-IGNORED` ("Non-existent path"), so the flow writes one command per kind.
- **Elaborated design (`synth_design -rtl`).** `check_timing`, `report_clock_networks` and `report_timing_summary` are refused ("not supported pre-synthesis", Elaboration 18-496). `report_clocks`, `get_clocks`, `get_ports` and `all_registers -clock_pins` work: on a fixture with one of each source,
  MMCM and BUFGCE_DIV outputs are listed as auto-derived and 25 of 44 register clock pins are unclocked (the `USR_ACCESSE2` clock, the `BSCANE2` TCK registers, a fabric-register clock) in 133 ms, against 17.6 s for `check_timing` after synthesis; on `designs/b96_kr260_10g` (15913 clock pins) none are unclocked, in 2.9 s. The `USR_ACCESSE2` CCLK pin is
  not in the elaborated list (after synthesis it is). The same `all_registers -clock_pins` step **crashed Vivado (exit 139)** on the elaborated PS design `designs/b191_ps_axi_lat`; so it is a recipe in `elab_probe/probe.tcl`, not part of `flow/build.tcl`.
- **Transceiver pins.** `designs/b96_kr260_10g` (GTH, one reference clock constrained) has every `check_timing` count at zero with the four serial pad ports in the top; the channel and QPLL clocks appear in `report_clocks` as auto-derived (P,G,A) at elaboration already. The serial pads take no fabric constraint.
- **Processor system.** On the elaborated `designs/b191_ps_axi_lat`, `report_clocks` lists the PS IP's own `pl_clk0` clocks with no line of ours, and the top has one port (a placeholder output). EMIO routed through PL pins is not in any design here: not measured.
- **False-positive scan.** The completeness check on the 33 committed designs that have a build.yaml and an XDC: 3 findings (two are an input `din` with no delay in `designs/b100_rapidwright/agent_run`, one is `unused_o` of `designs/b191_ps_axi_lat`, which has a false path and no delay and was never built), none on a design that closes (`false_positive_scan.json`).


## Known gaps

- Supplied modules do **not** ship a scoped `.xdc` fragment beside them (`SCOPED_TO_REF`): the flow derives the same lines from the primitives the RTL contains, which also covers a copy of `jtag_bus.sv` supplied as `data/` with no fragment. A module that needs a constraint not derivable from a primitive would need the fragment mechanism.
- `FDA-CON-15` (a clock-source primitive nothing clocks) has no rule of its own: the flow writes the two clocks it can know, and any other unclocked source shows as an unclocked register pin in the elaborated-design check below, not as a text finding.
- Clocks generated in fabric (a register used as a clock) and IP that ships its own XDC are not read by this module.
