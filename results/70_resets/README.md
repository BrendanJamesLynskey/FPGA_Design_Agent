# Results: reset conventions measured on the fabric and in AMD's own IP (brief 70)

Brief 70 measured what an active-low or active-high, synchronous or asynchronous reset costs on two parts (Artix-7 xc7a100t-1
and Zynq UltraScale+ xck26) with one small parameterised bench, surveyed how AMD's own IP and generated block designs use
resets (Vivado 2026.1 install, unencrypted HDL read in our own words, netlists, a black-box simulation of the Processor
System Reset), audited our own RTL against the house rule that resets are synchronous (owner, 2026-11-13), and fed the
results into the agent's `resets` check (brief 71), the knowledge bank and the Designer prompt. Every Vivado figure is one
run on Vivado 2026.1, out of context: single measurements, not averages, with no estimate of run-to-run noise.

## Records

- `records/xc7a100tcsg324-1.tsv`, `records/xck26-sfvc784-2LV-c.tsv`: the matrix, one line per arm and measurement (tab
  separated: part, arm, block set, key, value). `records/xck26-sfvc784-2LV-c_rerun.tsv`: a second run of one xck26 arm (see the gaps).
- `records/matrix_summary.json`: the numbers below, computed from those lines by `summary.py`; `flow/checks/reset_costs.json` is
  the part of it the reset check quotes (a test keeps both in step with the records).
- `records/ip_reset_survey.json` (the survey of the install's IP source), `records/ip_netlists.tsv` and `records/xpm_netlists.tsv`
  (default-configuration netlists of the IP and of the XPM reset macros), `records/psr_sequence.json` (the Processor System
  Reset simulation), `records/bd_wiring.tsv` (three generated block designs: how the tools wire resets).
- `audit/async_resets.tsv`: every asynchronous-reset block in our own RTL and generators (47 blocks; see the audit below).
- `rtl/`, `tcl/`, `psr_sim/`, `survey/`: the bench RTL, the Vivado scripts, the simulation and the survey script.

## Reproduce

`run_matrix.sh <scratch>` runs both parts under one heavy slot (Vivado, `MemoryMax=6G`, one thread);
`tcl/ipreset.tcl`, `tcl/xpmreset.tcl` and `tcl/bd.tcl` are batch Vivado scripts (several minutes each; the block designs need
the 2026.1 install); `psr_sim/run_psr.py` runs the simulation (Vivado simulator, Basic tier);
`survey/survey.py` reads the install; `summary.py` rebuilds the summary (`--check` is the test). A different Vivado release can
give different counts.

## Measured

Bench: a 16 x 32 register bank, a counter with a two-stage pipeline, an 18 x 18 + 32 DSP multiply-add pipeline and a
1024 x 32 block-RAM read path with an output register (692 flip-flops and 216 LUTs in the base case), reset port arriving 3 ns
into a 5 ns clock. Tables after routing, except the four "reset registered" rows per part, which are synthesis counts only (no route data, no slack); "control only" resets valid bits, counters and state only; "reset registered" is one
plain register after the reset port.

### xc7a100tcsg324-1

| variant | LUTs | flip-flops (FDRE / FDSE / FDCE / FDPE) | control sets | inverter LUTs on the reset | WNS to a reset pin (ns) | WNS overall (ns) |
|---|---|---|---|---|---|---|
| synchronous, active high, reset all | 216 | 692 (692 / 0 / 0 / 0) | 18 | 0 | 1.373 | 0.11 |
| synchronous, active low, reset all | 217 | 692 (692 / 0 / 0 / 0) | 18 | 1 | 0.1 | 0.1 |
| synchronous, active high, reset control only | 201 | 692 (692 / 0 / 0 / 0) | 20 | 0 | 0.575 | 0.137 |
| synchronous, active low, reset control only | 202 | 692 (692 / 0 / 0 / 0) | 20 | 1 | 0.546 | 0.132 |
| asynchronous, active high, reset all | 287 | 830 (0 / 0 / 830 / 0) | 18 | 0 | 1.511 | 0.016 |
| asynchronous, active low, reset all | 288 | 830 (0 / 0 / 830 / 0) | 18 | 1 | 0.204 | -0.033 |
| asynchronous, active high, reset control only | 201 | 692 (640 / 0 / 52 / 0) | 20 | 0 | 0.486 | 0.226 |
| asynchronous, active low, reset control only | 202 | 692 (640 / 0 / 52 / 0) | 20 | 1 | 0.388 | 0.167 |
| synchronous, one reset condition written in both polarities, reset all | 217 | 692 (692 / 0 / 0 / 0) | 18 | 1 | 0.07 | 0.07 |
| asynchronous, one reset condition written in both polarities, reset all | 288 | 830 (0 / 0 / 830 / 0) | 18 | 1 | 0.16 | -0.059 |
| synchronous, one signal tested at both levels (two polarities of one reset), reset all | 217 | 692 (692 / 0 / 0 / 0) | 19 | 1 | 0.194 | 0.158 |
| asynchronous, one signal tested at both levels (two polarities of one reset), reset all | 288 | 830 (0 / 0 / 830 / 0) | 19 | 1 | 0.171 | -0.057 |
| synchronous, active high, reset registered, no fan-out limit | 216 | 693 (693 / 0 / 0 / 0) | 19 | 0 | - | - |
| synchronous, active high, reset registered, MAX_FANOUT = 50 on the register | 216 | 709 (709 / 0 / 0 / 0) | 241 | 0 | - | - |
| synchronous, active low, reset registered, no fan-out limit | 217 | 693 (693 / 0 / 0 / 0) | 19 | 0 | - | - |
| synchronous, active low, reset registered, MAX_FANOUT = 50 on the register | 217 | 693 (693 / 0 / 0 / 0) | 19 | 0 | - | - |

### xck26-sfvc784-2LV-c

| variant | LUTs | flip-flops (FDRE / FDSE / FDCE / FDPE) | control sets | inverter LUTs on the reset | WNS to a reset pin (ns) | WNS overall (ns) |
|---|---|---|---|---|---|---|
| synchronous, active high, reset all | 216 | 692 (692 / 0 / 0 / 0) | 18 | 0 | 1.449 | 1.449 |
| synchronous, active low, reset all | 216 | 692 (692 / 0 / 0 / 0) | 18 | 0 | 1.449 | 1.449 |
| synchronous, active high, reset control only | 201 | 692 (692 / 0 / 0 / 0) | 20 | 0 | 1.839 | 1.839 |
| synchronous, active low, reset control only | 201 | 692 (692 / 0 / 0 / 0) | 20 | 0 | 1.839 | 1.839 |
| asynchronous, active high, reset all | 287 | 830 (0 / 0 / 830 / 0) | 18 | 0 | 1.864 | 1.864 |
| asynchronous, active low, reset all | 287 | 830 (0 / 0 / 830 / 0) | 18 | 0 | 1.864 | 1.864 |
| asynchronous, active high, reset control only | 201 | 692 (640 / 0 / 52 / 0) | 20 | 0 | 1.864 | 1.864 |
| asynchronous, active low, reset control only | 201 | 692 (640 / 0 / 52 / 0) | 20 | 0 | 1.864 | 1.864 |
| synchronous, one reset condition written in both polarities, reset all | 216 | 692 (692 / 0 / 0 / 0) | 18 | 0 | 1.449 | 1.449 |
| asynchronous, one reset condition written in both polarities, reset all | 287 | 830 (0 / 0 / 830 / 0) | 18 | 0 | 1.864 | 1.864 |
| synchronous, one signal tested at both levels (two polarities of one reset), reset all | 216 | 692 (692 / 0 / 0 / 0) | 18 | 0 | 1.449 | 1.449 |
| asynchronous, one signal tested at both levels (two polarities of one reset), reset all | 287 | 830 (0 / 0 / 830 / 0) | 18 | 0 | 1.864 | 1.864 |
| synchronous, active high, reset registered, no fan-out limit | 216 | 693 (693 / 0 / 0 / 0) | 19 | 0 | - | - |
| synchronous, active high, reset registered, MAX_FANOUT = 50 on the register | 216 | 709 (709 / 0 / 0 / 0) | 241 | 0 | - | - |
| synchronous, active low, reset registered, no fan-out limit | 217 | 693 (693 / 0 / 0 / 0) | 19 | 0 | - | - |
| synchronous, active low, reset registered, MAX_FANOUT = 50 on the register | 233 | 709 (709 / 0 / 0 / 0) | 225 | 0 | - | - |

In the matrix the "inverter LUTs" column counts the LUT1 inverters on the reset net; for the "registered" arms the inverter
sits after the register, so it reads 0 there.

What the tables show, each against "synchronous, active high, reset all":

- **Active-low reset:** one LUT1 inverter on the reset net, not one per flip-flop. On the 7-series part it is still there after
  routing and the reset-pin slack falls from 1.373 to 0.1 ns on a 692-load net. On xck26 it is gone after place and route and the
  reset-pin slack is 1.449 ns for both polarities.
- **Asynchronous reset on everything:** +71 LUTs and +138 flip-flops on both parts. The DSP A, B and M registers (142
  flip-flops in the DSP block's neighbourhood against 36; PREG and CREG stay absorbed) and the block RAM's output register (34 against 2) stay in fabric. The
  extra LUTs are not explained by a record (the DSP's output stage and the carry chains differ); a mechanism was not isolated.
- **Asynchronous reset on control registers only, against synchronous control only:** no change in LUTs, flip-flops or control sets
  (52 FDCE); with control-only reset the DSP registers all stayed absorbed, so this bench shows no blocking there; the blocking seen above needs the asynchronous reset on the DSP and RAM registers.
- **Reset control registers only, against everything:** 15 fewer LUTs and 2 more control sets. The saving looks like merging of
  the reset into the read multiplexers of registers with enables; the mechanism was not isolated.
- **One reset tested at both levels:** one more control set on 7-series (19 against 18); on xck26 the extra set is removed by place
  and route. The same condition spelled two ways costs nothing extra.
- **MAX_FANOUT = 50 on a registered reset** replicates the register: control sets 19 to 241 and 693 to 709 flip-flops (active
  high, both parts); active low on xck26 gives 225 control sets and 16 more LUTs; active low on 7-series gave no change (a likely reason is that the register's only load is the inverter; not
  isolated). The `synth_design -fanout_limit` arms are void (see the gaps).
- **Processor System Reset (simulation, default settings):** a request shorter than 4 clocks is ignored; the outputs assert 12 clocks
  after it begins and release 40 (bus structure, interconnect), 56 (peripheral) and 72 (core) clocks after it ends; with no
  request at power-up they release at 47, 63 and 79. The generated IP defaults to an active-high external reset (the entity default being low is from reading the source, not a record).
- **Default netlists of AMD's IP (xc7a100t only)** (AXI GPIO, UART Lite, Timer, INTC, IIC, Quad SPI, DMA, Register Slice, PSR, FIFO Generator,
  XPM FIFO and macros): flip-flops with synchronous reset only, except `xpm_cdc_async_rst` (4 FDPE, as intended).
  Generated designs: Zynq PS with SmartConnect has none; with the AXI Interconnect in that design the interconnect core holds 69 FDCE and
  33 FDPE (xck26; in the MicroBlaze design on xc7a100t it holds none); the MicroBlaze design's debug module holds 31 FDCE and 6 FDPE and MicroBlaze 7 FDCE.
- **How the tools wire resets:** the PSR's `peripheral_aresetn` reaches the peripherals' `s_axi_aresetn` and the interconnect's
  master and slave `ARESETN` pins; `interconnect_aresetn` the interconnect's own; `bus_struct_reset` the LMB memory; `mb_reset`
  MicroBlaze; the debug module feeds the PSR's `mb_debug_sys_rst`. MicroBlaze automation left `ext_reset_in` open; the 2026.1
  automation offers SmartConnect only, so the AXI Interconnect was placed and wired by hand.
- **Fixes made because of the survey:** the `dds_awg` block RAM no longer has a reset-driven pin (AMD's block-RAM DRC on a pin driven from an asynchronous register; the reset masks the
  output through one plain register, bit-identical); the GT Wizard's reset inputs of `b56a` come from registers (the five
  remaining LUTAR-1 rows are inside the Wizard and not ours); the `hwsw/cfu.py` generator uses synchronous resets.

## The owner's three claims (2026-11-13)

1. **Polarity is not a big issue for FPGAs (long routes have both polarities; async set/reset exist; a sync reset folds into the LUT):
   partly.** On UltraScale+ confirmed: the inverter is absorbed (0 LUTs after place and route, equal slack). On 7-series refuted
   at high fan-out: the slice SR pin is active high only, one LUT1 stays, and it cost 1.27 ns of reset-pin slack on a 692-load
   net (one run; an inverter in front of a large fan-out is a stage to time); whether registering the reset after one inversion removes the stage was not measured (the registered-reset arms have no timing). That both polarities exist as global routes was not tested; two polarities of one reset cost one control set on 7-series.
2. **A flip-flop has one SR pin, set as set or reset, synchronous or asynchronous, shared by the slice: confirmed for
   the cells, not measured for the slice.** Every netlist uses FDRE, FDSE, FDCE or FDPE and none has both a set and a reset; the
   slice-level sharing was taken from UG474 and UG574, not measured separately.
3. **A synchronous reset can fold into the D-input LUT; an asynchronous one cannot and blocks DSP and RAM register absorption:
   confirmed, folding on thin evidence.** Absorption: 142 against 36 and 34 against 2 flip-flops (both parts). Folding: seen for the two valid bits of the RAM path (a 2-flip-flop block, on 7-series and on xck26); the same
   registers with an asynchronous reset used FDCE CLR pins. With control-only reset the same block cost 2 LUTs, so this is one observation, not a rule.

## AMD IP reset table

The knowledge-bank skill `amd-ip-reset-map` and `flow/amd_ip_resets.py` carry the table (port, polarity, inside, what you
provide, measured sequence) for the Processor System Reset, AXI GPIO, UART Lite, Timer, INTC, IIC, Quad SPI, DMA and CDMA,
Register Slice, AXI Interconnect, SmartConnect, FIFO Generator and the XPM macros. Against AMD's own guidance (UG949 ch. 3,
held edition v2025.2, not re-read at 2026.1): the peripherals' netlists follow it (synchronous, reset registered or inverted
once); AMD's AXI Interconnect core (in the Zynq design), the MicroBlaze debug module and, slightly, MicroBlaze use asynchronous flip-flops, and the Register
Slice's readable source has an asynchronous clear that its default netlist does not show; the DMA mixes polarities inside.

## Audit of our own RTL

`audit/async_resets.tsv` lists 47 asynchronous-reset blocks. Fixed in this brief: `hwsw/cfu.py` (2 generated blocks).
Remaining and why:

- `shell/rtl/reset_sync.sv` (1): the reset synchroniser itself (asynchronous assert, synchronous release): allowed.
- `ip_lib/eth_mac_rgmii/rtl/rgmii_tx.sv` (2): double-data-rate clock edges (`posedge clk or negedge clk`), not resets.
- `hil/cdc_soak/rtl` (7): the clock-crossing soak's asynchronous resets are the measurement rig; they stay.
- `hwsw/cfu_core/brv32p` (37): a pinned copy of the owner's other project; a synchronous-reset patch in the style of
  `brv32p_cfu.patch` is proposed to the planner, not made here.
- Generic knowledge-bank files (22, including `reset-strategy`) still teach asynchronous-reset defaults; they are pinned to the
  private RTL pack, so the fix belongs there and needs a re-pin.

## Recommendation

Keep the convention: `aresetn` (synchronous, active low) at AXI ports, synchronous active high inside, inverted once where the
reset enters and then registered. The measured cost of the inversion is one LUT (none on UltraScale+) plus, on 7-series with a
late-arriving reset and a large fan-out, a timing stage that the registration removes. No default was changed. Reset control
registers only; never give the registers around a DSP or RAM an asynchronous reset; never drive a block-RAM control pin from a
reset synchroniser's output; do not put MAX_FANOUT on a reset register without checking control sets.

## Known gaps and limits

- One run per arm, no noise estimate; out of context (the bench is not placed with real I/O).
- The `synth_design -fanout_limit 50` arms are void: the option is deprecated and changed nothing. `MAX_FANOUT` arms replace them.
  The first xck26 record of that arm (53 LUTs, 149 flip-flops) did not reproduce: the rerun matches the arm with no limit
  (217 LUTs, 693 flip-flops, 19 control sets); both records are kept and neither is used.
- The sink walker overwrites an entry when the reset register is replicated, so the per-sink counts of the MAX_FANOUT arms are not quoted.
- The `IS_*_INVERTED` property values of the DSP and RAM primitives read empty in the records; the evidence for "no absorption on
  7-series" is the inverter LUT and the pin's driver, not the properties. The flip-flop `IS_R_INVERTED` column is unreliable
  and is not quoted.
- The matrix covers xc7a100t and xck26; UltraRAM, UltraScale+ block-RAM control pins and REQP-1840 on xck26 were not tested.
- Folding of a synchronous reset into the LUT was seen once, on 7-series, in an isolated 2-flip-flop block.
- One configuration of each IP; FIFO Generator, SmartConnect and AXI Interconnect source is encrypted, so only netlists and
  the guides are known. The three block designs were synthesised once (no implementation).
- The Processor System Reset sequence is a simulation of one configuration with default settings.
