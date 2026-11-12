# Project mode, non-project mode, and what this flow keeps from both (brief 18)

The agent builds in **non-project mode**: [flow/build.tcl](../flow/build.tcl) reads sources and XDC, runs every stage and writes
every report itself. UG892 (v2026.1, "Project Mode Advantages") lists what project mode adds on top: automatic management of
sources, IP and block designs, stored synthesis and implementation results, "cross probing from implementation results to RTL
source files", run strategies with standard reports, and multiple runs. The Vivado wizards are a second group of project-mode
conveniences: several compute or check something that a scripted flow does not get unless it asks.

This page is the inventory, measured first on an earlier release and re-measured by brief 49 on **Vivado 2026.1** (Basic licence tier; the owner's personal install, `xc7a100tcsg324-1`, Zynq-7020 for the PS7
rows). Numbers come from the 2026.1 files under [results/project_parity_2026_1/](../results/project_parity_2026_1/); each section names its script. Every verdict below came out the same on 2026.1; where a number moved, the 2026.1 value is given.
Nothing here needs the GUI. Where a result could not be got in batch it is marked **not measured** with the reason.

Status words: **kept** (the flow already has it), **beaten** (the flow does it better for an agent), **added** (this brief),
**gap** (project mode has it, the flow does not, listed for the planner).

## 1. Project mode features

| Project-mode feature (UG892 / UG893) | In this flow | How it matches or beats it | Status |
|---|---|---|---|
| Automatic IP scoped constraints and their ordering (IP XDC read before the user XDC, `PROCESSING_ORDER`) | `read_verilog` only: no IP cores, so no IP XDC. The one family the designs use, `xpm_cdc_*`, gets its exceptions from [flow/xpm_cdc.tcl](../flow/xpm_cdc.tcl) by cell name (PR #83) | XPM exceptions are applied and proven (setup WNS -1.364 ns to +8.891 ns on the QR1 probe). IP XDC from the Clocking Wizard and FIFO Generator was read in section 3: the Clocking Wizard's is a `create_clock` and `set_input_jitter` on its input port; the FIFO Generator's native async-FIFO exceptions are written but commented out | kept for XPM, **gap** for IP (no `read_ip` in `build.yaml`) |
| IP management: customisation, OOC synthesis and caching, version upgrade | none; direct instantiation of primitives (MMCME2, PLLE2, XPM) is the rule | no IP cache to go stale, no `upgrade_ip`, every source is diffable text. The cost: nothing that a wizard computes is used unless the agent reproduces it (section 3) | beaten for reproducibility, **gap** for wizard computations |
| Run management, strategies, Intelligent Design Runs, incremental compile | one fixed sequence (`opt_design`, `place_design`, `phys_opt_design`, `route_design`, default directives). No strategies, no `read_checkpoint -incremental` | each run is a process with a recorded time and cgroup memory peak (`run.json`) and a gate result; nothing is hidden in a run directory. Intelligent Design Runs need project mode and UltraScale(+) (UG949, quoted in [methodology.md](methodology.md)), so they never applied to the Artix-7. Strategies would be a directive sweep: **gap**, not needed while every design closes | **gap** (strategies), beaten (record) |
| Per-step checkpoints and reports | two checkpoints (`post_synth.dcp`, `post_route.dcp`) and a report group per UltraFast stage ([methodology.md](methodology.md)) | project mode writes `<step>.dcp` after every step and a standard report set. The flow writes more reports than project mode's defaults (CDC, QoR assessment, high-fanout, clock interaction) and parses them into gates. No `post_opt.dcp` or `post_place.dcp`: **gap**, one line each in `build.tcl` if a repair loop ever needs to resume | kept, small gap |
| Run dashboards (Design Runs window, project summary, status bars) | `gates.json`, `run.json`, `flow/summarise.py`, the results pages | the same facts as data the agent and CI read. No GUI: nothing a person can look at without the pages | beaten for the agent |
| Simulation sets (xsim behavioural, post-synthesis, post-implementation timing) | Icarus, Verilator (CI) and cocotb with a blind golden model and mutation testing; no xsim | independent checking is the point of the project (house rules). **Gap:** no post-implementation timing simulation (`write_verilog -mode timesim` plus SDF) | beaten (verification), **gap** (timing sim) |
| Block designs (IP Integrator, block automation, connection automation, address editor) | none | **Measured:** every step runs in batch on a Zynq-7020: `create_bd_design`, `apply_bd_automation -rule xilinx.com:bd_rule:processing_system7`, the AXI connection rule, `assign_bd_address` (GPIO at 0x41200000), `validate_bd_design` all succeed (section 3). Using it needs `build.yaml` support for a Tcl block-design script: **gap** | **gap** |
| Wizard-only checks (MIG pin validation and others) | rule checker `mig_pin_rules.py` (13b); other wizards: section 3 | the MIG wizard's pin verification has no Tcl command; implementation did not reject a byte-group fault (section 2). Per-wizard results in section 3 | see sections 2 and 3 |
| Cross-probing: RTL, elaborated and synthesised netlist, timing reports, device view | **added:** [flow/xprobe.tcl](../flow/xprobe.tcl), [flow/xprobe.py](../flow/xprobe.py): JSON per build and an SVG device map | section 4 | **added** |
| ECO and debug-probe insertion (Set Up Debug, ECO Navigator) | debug cores by Tcl ([flow/debug.tcl](../flow/debug.tcl)): on Vivado 2026.1's free Basic tier `create_debug_core` is refused, so the flow adds one ILA IP to the netlist with the probes packed into at most 5 ports (brief 48); the `create_debug_core` route is kept for a tier that allows it | Set Up Debug runs `create_debug_core`, which the Basic tier refuses; the flow inserts the ILA from `probes.yaml` as IP instead. ECO (edit a routed checkpoint) is not used: **gap**, no use case yet | kept (debug), **gap** (ECO) |
| Source file management, out-of-date status, hierarchy view | `build.yaml` plus `sources_sha256` and `BUILD_STAMP` in every build | a build is reproducible from the sources by hash; project mode tracks time stamps | beaten |
| Timing Constraints Wizard (missing clocks, I/O delays, clock groups) | `check_timing -verbose` after synthesis and routing, the XDC checker and the CDC gate | see section 3 | kept |

### What non-project mode does better

- **Reproducible and diffable.** No project database, no generated IP trees in the source tree, no auto-upgrade of IP.
  The inputs of a build are a list of files and a hash.
- **Memory and process control.** One process, `general.maxThreads`, `synth.maxThreads`, `chipscope.maxJobs` pinned to 1,
  capped by a cgroup (6 GB). Project-mode runs launch child Vivado processes for synthesis and implementation (seen in the
  MIG runs of section 2: `launch_runs` starts a separate synthesis process), which is harder to cap on the shared PC.
- **Every check is a command with a file.** Nothing depends on a window an agent cannot open; the stages and gates are
  explicit and the same in CI.
- **Constraint order is exact.** The flow decides when each XDC is read and when `xpm_cdc.tcl` runs; project mode decides
  for it (and, for XPM, did not apply the exceptions in non-project mode, which is why the flow had to).

## 2. Wizard-only checks: the MIG pin validation

Question (owner): can a UI wizard be part of the scripted flow? For the MIG the wizard's pin validation was missing in the
scripted generation (13b: `generate_target` accepts a swapped byte group and a duplicate pin silently).

**Step 1: the Tcl behind the wizard.** Not run in the GUI: `xdotool` is not installed and there is no root to install it
(`which Xvfb xvfb-run xdotool`: Xvfb and xvfb-run only), so no wizard click-through and no journal. Static evidence instead:

- The Vivado Tcl interpreter has no MIG command: `info commands *mig*` returns only `implement_mig_cores` and
  `migrate_pblock` (not pin validation); `*verify*` returns `platform_verify pr_verify tandem_verify`
  ([results/project_parity_2026_1/wizards/wizards2.txt](../results/project_parity_2026_1/wizards/wizards2.txt)). New in 2026.1: a
  `validate_ip` command exists (`info commands validate_*`). Whether it checks a MIG pinout was **not tested**: the batch generation
  below still accepts both faulty pinouts without a message.
- The MIG IP's Tcl (`data/ip/xilinx/mig_7series_v4_2/xgui/xgui.tcl`) only checks that the `.prj` file exists and is readable
  (`validate_XML_INPUT_FILE`); `updateAllModelParams` calls the native generator (`generateMig`).
- The engine library `libxv_mig7.so` contains the classes behind the GUI's pin page (`PinVerification::verifyPinSet`,
  `ByteVerification`, `BankVerification`, `UCFGeneration`). They are reached through the wizard, not through a `CONFIG.*`
  property or a command. **Conclusion: no Tcl command for the wizard's pin verification was found.** The wizard's own
  journal could not be recorded (no GUI driving tool); that is the one thing this step did not do.

**Step 2: implementation as the check.** [flow/mig_impl_check.tcl](../flow/mig_impl_check.tcl): `create_ip mig_7series` from the
`.prj`, `open_example_project`, synthesis, `opt_design`, `place_design`, then `report_drc` (default and `bitstream_checks`).
The three `.prj` files are the private KB's (good; `mig_mut_bytegroup`: DQ0 and DQ8 swapped; `mig_mut_dup`: DQ0 on the A0
pin). Vivado 2026.1, one thread, `MemoryMax=6G`, results in [results/project_parity_2026_1/mig_impl/](../results/project_parity_2026_1/mig_impl/).

| .prj | synth | place | `report_drc` after place | `bitstream_checks` |
|---|---|---|---|---|
| good | ok (253 s) | ok (26 s) | NSTD-1, UCIO-1 (the same 5 of 51 ports have no LOC or I/O standard; the DRC text does not name them), CFGBVS-1, REQP-1709 | NSTD-1, UCIO-1, RTSTAT-12 (not routed), CFGBVS-1, REQP-1709 |
| bytegroup | ok (242 s) | ok (27 s) | **the same rules and counts as good** | **the same as good** |
| dup | ok (247 s) | ok (26 s) | the same rules, with 6 of 51 ports (not 5) without LOC and I/O standard, plus **PLIO-3** ("Partially locked IO Bus ddr2_dq[15:0]: ddr2_dq[0] not locked") and BUFC-1 (the DQ0 input buffer has no loads) | as good, plus BUFC-1; UCIO-1 and NSTD-1 are Errors here |

**Result:** the duplicate-pin fault shows up, but only as warnings and a count: no placer error, and the Critical Warnings (NSTD-1, UCIO-1) are already present in the baseline because the example design's own system ports have no LOC, so the signal is **PLIO-3 naming `ddr2_dq[0]`**, BUFC-1 on the DQ0 buffer, and 6 against 5 unplaced ports. A wrapper that constrains every system port would turn UCIO-1 into a clean pass/fail; that was not built. The byte-group fault is **not** rejected by synthesis, placement or either DRC deck. The
generator re-derives the PHY's byte-lane parameters from the pins it is given, so the design is consistent with the wrong
pins; the DQ/DQS association is only visible to a rule checker (or, on hardware, as a calibration failure).
Route was not run for the faults (see "not done" in the report). **Recommendation:** keep `mig_pin_rules.py` as the gate for
byte groups and bank rules, and treat the implementation check as a second opinion for a duplicate or missing pin (read PLIO-3 for the DDR bus and
the count of ports without LOC after `place_design`; it costs 7 to 10 minutes of synthesis plus about a minute of
placement on this PC, so it belongs in a pre-board check, not in the default flow). `mig_pin_rules.py` already flags
both faults without Vivado (13b). Not added to the default flow.

**Step 3: GUI driving** is only for when steps 1 and 2 both fail. Step 2 does catch a missing pin, and step 1 found no command,
so by the brief's rule step 3 applies to the byte-group case. It was **not run**: no `xdotool` or accessibility tool is
installed and the brief forbids system installs. Alternatives not tried: the JRE bundled with Vivado has `java.awt.Robot`,
which works under Xvfb; that would be a small experiment for a session with the planner's OK.

## 3. Every wizard: benefit, batch equivalent, agent flow, gap

Scripts: [flow/clkwiz_probe.tcl](../flow/clkwiz_probe.tcl), [flow/wizard_probe.tcl](../flow/wizard_probe.tcl),
[flow/wizard_probe2.tcl](../flow/wizard_probe2.tcl), [flow/mmcm_timing_probe.tcl](../flow/mmcm_timing_probe.tcl),
[flow/cmt_check_probe.tcl](../flow/cmt_check_probe.tcl). "Measured yes" means the property or command worked in
`vivado -mode batch` with `create_ip` and `set_property CONFIG.*`, no GUI.

| Wizard | Benefit (what it computes or checks) | Batch equivalent (measured) | Agent flow now | Gap and fix |
|---|---|---|---|---|
| **Clocking Wizard** (`clk_wiz` 6.0) | M/D/O search; VCO and PFD legality; per-output jitter and phase error; generated XDC (`create_clock`, `set_input_jitter`); LOCKED and reset ports; MMCM or PLL | **Measured yes:** `CONFIG.MMCM_CLKFBOUT_MULT_F`, `MMCM_DIVCLK_DIVIDE`, `MMCM_CLKOUTn_DIVIDE(_F)`, `CLKOUTn_JITTER`, `CLKOUTn_PHASE_ERROR` read back after `set_property`; the XDC and `*_clk_wiz.v` header come from `generate_target`; out-of-range requests (900 MHz, 4 MHz) are refused with `IP_Flow 19-3460` ("valid freq in range (4.687 - 800.000)") | direct MMCME2/PLLE2 with hand M/D/O from the KB skill; no wizard | see below: values match, jitter is not needed from the wizard; **recommendation: keep direct instantiation, the wizard as the checker** |
| **Memory: Block Memory Generator** | primitive choice, latency, port widths; resource estimate | **Measured partly:** `CONFIG.Primitive` (8kx2 for the 4096 x 32 test), `READ_LATENCY_A`, register options readable; **no block-RAM count property** (`report_utilization` after synthesis gives it) | inference from RTL and `report_utilization` | none: nothing the wizard computes is needed beyond what synthesis reports |
| **FIFO Generator** | native or XPM FIFO, flags, thresholds, depth rules | **Measured yes** for `Output_Depth`, `Full_Threshold_*`, `Data_Count_Width`, `synchronization_stages`. The generated `fg.xdc` for an independent-clock FIFO has the CDC exceptions (`set_max_delay -datapath_only`, `set_bus_skew`, `set_false_path`) **all commented out**, the clock file has two `create_clock` lines | XPM FIFOs only (`xpm_fifo_*`), exceptions from `flow/xpm_cdc.tcl` | gap if the native generator were used: its exceptions would not apply. Not used |
| **XADC / System Management Wizard** | channel sequencer, alarm thresholds, DCLK limits | **Measured yes:** `CONFIG.CHANNEL_ENABLE_*`, `TEMPERATURE_ALARM_*`, `VCC*_ALARM_*`, `ADC_CONVERSION_RATE`, `DCLK_FREQUENCY` (100) readable and settable; `generate_target` ok | designs read XADC through DRP primitives only if a task needs it (none does) | none now |
| **Transceivers Wizard** | line-rate and reference-clock legality, PLL dividers, protocol presets | **Measured yes** on `xc7a200tfbg484-1` (GTP): `create_ip gtwizard`; a 12.5 Gb/s request on a GTP is **refused**; the PLL dividers (`gt0_pll0_fbdiv`, `refclk_div`, `rxout_div`, `txout_div`) and `gt_val_*` read back (2026.1 also lists a `gt0_val_*` set of CPLL and QPLL properties). A legal 3.125 Gb/s set did not apply in the probe (property names guessed wrongly), so the legal-case numbers are **not measured** | no transceiver design (the Nexys A7 and KV260 targets have none in use) | none now; the batch route exists |
| **Zynq PS7 configuration** | clock tree (actual PLL-derived frequencies), DDR parameters, MIO | **Measured yes:** `PCW_FPGA0_PERIPHERAL_FREQMHZ 100` gave `PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ = 100.000000`, `PCW_ACT_APU_PERIPHERAL_FREQMHZ = 666.666687`, `PCW_UIPARAM_DDR_FREQ_MHZ = 533.333333`, DDR bus width and capacity from the part number | ZedBoard work is not started; no PS design in the flow | none now |
| **Block / connection automation, address editor** | wiring, address map, validation | **Measured yes** (table above) | none | **gap:** no block-design input in `build.yaml` |
| **Timing Constraints Wizard** | finds missing clocks, I/O delays, clock groups, CDC constraints on a synthesised design and recommends XDC | **No Tcl command** (`info commands *wizard* *recommend* create_timing*` return nothing). Its detection is `check_timing -verbose`, `report_clock_interaction`, `report_cdc` and `report_exceptions` (Tcl, parseable) | `check_timing -verbose` (gate `no_unconstrained_endpoints` with the missing-port list), `report_clock_interaction`, `report_cdc`, the XDC checker | kept: the detections are the same reports. What the wizard adds, a suggested XDC, is the agent's job (and the repair loop's) |
| **Set Up Debug** | ILA insertion and probe connection | `create_debug_core` and `connect_debug_port` exist in batch but are refused on 2026.1 Basic; the `ila` IP customises with `CONFIG.C_NUM_OF_PROBES` and is what the flow uses there (one ILA, at most 5 ports, one clock) | **kept:** `flow/debug.tcl` from `probes.yaml` (the ILA variant, IP route) | none |
| **I/O Planning** | pin assignment checks (bank voltage, SSN, clock-capable pins) | `place_ports`, `report_drc`, `report_ssn`, `report_io` exist; 13b ran them netlist-free (BIVC-1 caught a 3.3 V port in a 1.8 V bank; SSN works on xc7a100t; clock-capable-pin rules **need a netlist**) | `check_constraints` (master XDC) plus the report set; 13b checks in the KB | the netlist-free clock check is a known hole (13b, F2) |
| **MIG** | pin verification (byte groups, banks), controller parameters, example design | section 2: generation yes, **pin validation no Tcl command**; implementation does not reject a byte-group fault | `mig_pin_rules.py` (KB) | rule checker stays the gate |
| **Open Example Project** | an IP's example design with constraints | `open_example_project -in_process` **measured yes** (used in section 2) | not used | none |
| **Create Runs / strategies wizard** | strategy and directive presets | not applicable (project runs) | fixed sequence | see section 1 |

### The Clocking Wizard against the KB's hand-chosen values

[flow/mmcm_search.py](../flow/mmcm_search.py) is the KB skill `artix7-mmcm-pll-configuration`'s search rule (smallest frequency
error, then highest legal VCO, then smallest D; -1 limits), with a unit test on the skill's worked values. Three target sets
from a 100 MHz input, plus two more; the wizard's own answer is from `generate_target` of the same request
([results/project_parity_2026_1/clkwiz/clkwiz.jsonl](../results/project_parity_2026_1/clkwiz/clkwiz.jsonl)):

| Target set (MHz) | Wizard: D / M / O | Hand search: D / M / O | Same? | Wizard output (MHz), jitter pk-pk ps, phase error ps |
|---|---|---|---|---|
| 74.25 (720p pixel clock) | 4 / 37.125 / 12.5 (VCO 928.1) | 4 / 37.125 / 12.5 | **yes** | 74.25, 245.5, 245.3 |
| 12.288 + 49.152 + 98.304 (audio) | 2 / 21.625 / 88, 22, 11 (VCO 1081.3) | the same | **yes** | 12.28693, 49.14773, 98.29545 (all 0.01 % low); jitter 238.5, 172.9, 148.8; phase error 159.4 |
| 25.175 (VGA) | 4 / 36.375 / 36.125 (VCO 909.4) | 6 / 62.875 / 41.625 (VCO 1047.9) | **no** | wizard 25.17301 (error 2.0 kHz), hand 25.17518 (error 0.18 kHz); jitter 319.8, phase error 246.7 |
| 200 + 50, **PLL** | 1 / 10 / 5, 20 (VCO 1000; generates `PLLE2_ADV`) | 1 / 16 / 8, 32 (VCO 1600, the -1 PLL limit) | no (both exact) | 200, 50; jitter 114.8, 151.6; phase error 98.6 |
| 900 and 4 | refused (valid range 4.687 to 800 MHz) | no legal setting | yes | none |

- **Do the hand values match?** On 2 of 3 target sets they are identical; on VGA the hand rule is closer (0.18 kHz against
  2.0 kHz error) and on the PLL set the rule picks the highest legal VCO where the wizard picks a lower one. All are legal.
  Whether the 1600 MHz VCO gives less jitter than the wizard's 1000 MHz was **not measured**.
- **Are the wizard's jitter numbers available to timing?** Not needed. `report_timing` computes its own clock uncertainty
  from the MMCM primitive: on a hand-instantiated MMCM (`flow/mmcm_timing_probe.tcl`, synthesis only) the path report carries
  `Discrete Jitter (DJ)` and `Phase Error (PE)`, and DJ differs with the setting: 0.239 ns at VCO 928 MHz and 0.408 ns at VCO
  600 MHz (D5 M30 O12); VGA 0.287 ns (wizard values) against 0.305 ns (hand values); audio 0.210 ns. PE reads 0.000 before routing
  (it needs the clock tree). So timing sees jitter and phase error without the wizard
  ([results/project_parity_2026_1/mmcm_timing/](../results/project_parity_2026_1/mmcm_timing/)). The wizard's `CLKOUTn_JITTER` is a different,
  peak-to-peak figure for the user's information; the generated XDC adds only `set_input_jitter 0.100` on the input (a UI figure
  from the wizard's default) and `create_clock`.
- **VCO legality of a hand-instantiated MMCM.** The KB skill says neither `report_drc` nor `report_methodology` rejects an
  out-of-range VCO (checked 2026-11-03 with M13, D1 at 100 MHz). **This run found otherwise:** after `synth_design` with the input
  clock constrained, `report_drc` raises `AVAL-46` (Critical Warning, `v7v8_mmcm_fvco_rule1`: "The computed FVCO is 1300.000 MHz.
  The valid FVCO range for speed grade -1 is 600MHz to 1200MHz") for VCO 1300 MHz, 500 MHz and 454 MHz (PFD 9.1 MHz), and
  nothing for the legal setting 1000 MHz ([results/project_parity_2026_1/cmt_check/](../results/project_parity_2026_1/cmt_check/)). The flow's
  `post_synth_drc_clean` and `drc_clean` gates already count Critical Warnings, so an illegal MMCM VCO **is already a gate failure**.
  The KB note needs correcting by the planner (the KB is private and was not edited here). A separate VCO checker
  (`flow/cmt_check.tcl`, written for this probe) was therefore **not** wired into the flow: it duplicates AVAL-46.
- **LOCKED and reset wiring.** `CONFIG.USE_LOCKED`, `USE_RESET`, `RESET_TYPE`, `LOCKED_PORT` and `RESET_PORT` read back; the
  wizard always offers `locked` and `reset` ports. A hand instance gets that wiring only from the design standards and the
  reset-sequencing rules (the KB), not from a tool.
- **Readback gotcha.** With `CONFIG.PRIMITIVE PLL` the solution is stored in the `CONFIG.MMCM_*` properties; the `CONFIG.PLL_*`
  properties stay at their defaults. The generated Verilog (`PLLE2_ADV`, `CLKFBOUT_MULT 10`) is the truth.
- **Recommendation: keep direct instantiation and use the wizard as the checker.** The wizard adds no constraint or jitter
  figure the timer lacks, its XDC would need `read_ip` support, and the hand search is at least as accurate. Use
  `flow/mmcm_search.py` to choose, and (planner decision) cross-check each chosen set against the wizard's batch answer in
  the KB's pre-board checks: `flow/clkwiz_probe.tcl` does that in about a minute and needs no board or GUI. The VCO and
  PFD range gate already exists (AVAL-46).

## 4. Cross-probing as data

`flow/xprobe.tcl` (`xprobe_dump`) turns a routed design into `build/<variant>/xprobe.json`; `flow/xprobe.py` summarises it and
draws the device map. Set `FDA_XPROBE=1` for `flow/run_vivado.sh` (or run `flow/xprobe_run.tcl` on a `post_route.dcp`): the
step is off by default and changes no report or gate.

What Vivado gives, from a routed checkpoint (written on the earlier release; the two examples below were re-run on 2026.1):

| Wanted | Where it came from | Got it? |
|---|---|---|
| RTL file and line of a cell | cell properties `FILE_NAME`, `LINE_NUMBER` (set by `synth_design` for every primitive that came from RTL); `PARENT`, `HIERARCHICALNAME` | yes, for every start/end cell and net driver on the 10 paths and the 8 to 10 high-fanout nets of each example |
| RTL module | first hierarchy level of the cell name (`u_shell`, `u_rst`); `PARENT` for the full instance | yes |
| Placement | `LOC`; clock region from the **site** (`get_sites <LOC>`, property `CLOCK_REGION`); `PBLOCK` | yes; the cell's own `CLOCK_REGION` property is empty (**not available** on the cell) |
| Worst setup and hold paths per clock group | `get_timing_paths -setup/-hold -nworst 1 -unique_pins`; properties `SLACK`, `DATAPATH_DELAY`, `DATAPATH_LOGIC_DELAY`, `DATAPATH_NET_DELAY`, `STARTPOINT_PIN`, `ENDPOINT_PIN`, `STARTPOINT_CLOCK`, `ENDPOINT_CLOCK` | yes. `LOGIC_LEVELS` is present (0 on the reset path of `b2_acl_adxl362`, 3 on the worst `b2_qspi_jedec` paths) |
| Routed tiles of a path's nets | `get_nodes -of_objects <net>`, tile = prefix of the node name | only for nets with fanout up to 50 (whole net, not only the branch to one sink); a walk uphill from one sink node took minutes per path and was dropped; `ROUTE` is a list of node names without tile coordinates |
| High-fanout nets | `FLAT_PIN_COUNT > 50`, one row per driver pin (`get_nets -hier` lists a net under every hierarchical alias); driver cell with file and line; loads counted by clock region | yes |
| Congested cells | not collected. `report_design_analysis -congestion` is not parsed | **not available** in the release this was written on, and not re-checked on 2026.1; listed as follow-up |
| Device map | clock-region slice extent from `get_sites -of_objects <region>`; each placed slice-level primitive as (module, X, Y) | yes (SVG) |

Two examples on Vivado 2026.1, committed with the JSON and SVG ([results/project_parity_2026_1/xprobe/](../results/project_parity_2026_1/xprobe/)): from the
repo's local builds `b2_qspi_jedec` (WNS 4.278 ns, WHS 0.075 ns) and `b2_acl_adxl362` (WNS 3.335 ns, WHS 0.122 ns: the tighter of
the two). The only design with a negative or near-zero slack among them would have been the better
"real critical path"; none exists locally, so `b2_acl_adxl362` stands in. Its worst setup path (from the summary):

```
setup slack 3.335 ns: u_rst reset_sync.sv:14 (X0Y2, SLICE_X2Y132) -> u_regs spi_burst.sv:30 (X0Y2, SLICE_X0Y106)
rst: fanout 552, driven in u_rst reset_sync.sv:14; all 551 loads in clock region X0Y2
```

so "the critical path is the synchronised reset leaving `reset_sync.sv` line 14 and fanning out to 552 registers", which is what
the timing report's 5.4 ns of route delay (of a 6.2 ns data path) says in other words. The same data reaches the agent as evidence:
`flow/gates.py` adds an `xprobe` key to `gates.json` when `xprobe.json` exists, and `agent/graph/stages.py` appends
`cross-probe: ...` lines to the failing `post_route:setup` / `post_route:hold` gate in the repair visit's list. No tool was
added (the registered-tool golden test is untouched); the existing `report` tool can read `xprobe.json`.

## Reproduce

```
python3 flow/mmcm_search.py --compare results/project_parity_2026_1/clkwiz/clkwiz.jsonl      # the table in section 3
vivado -mode batch -source flow/clkwiz_probe.tcl -tclargs xc7a100tcsg324-1 <out> s1:100:MMCM:74.25 ...
vivado -mode batch -source flow/wizard_probe.tcl -tclargs <out>                       # one block per wizard
vivado -mode batch -source flow/mig_impl_check.tcl -tclargs xc7a100tcsg324-1 <.prj> <out>
FDA_XPROBE=1 flow/run_vivado.sh designs/<name> base                                    # writes build/base/xprobe.json
python3 flow/xprobe.py designs/<name>/build/base/xprobe.json --svg xprobe.svg --summary
```
