# Debug playbook: what a failed gate means and what to try

> **For humans only.** This page is for a person reading a failed gate (`flow/gates.py`) or a failed bring-up
> (`flow/bringup.py`). It is **not given to the agent in scored runs**: the gates report raw tool messages and
> rule IDs only, with no fix hints, so the arms without a knowledge pack do not receive this knowledge through the
> harness. The agent's knowledge comes only from the frozen packs listed in [knowledge/PACKS.md](../knowledge/PACKS.md).

Sources: AMD's Ross skills (github.com/Xilinx/ross-ai-assistant at commit `dce0fb9`, release 2026.10.1, MIT,
Copyright (C) 2026 Advanced Micro Devices, Inc.), mined and rewritten for this project's batch, non-project flow on
Vivado 2025.2; and AMD UG903, UG906, UG835, UG949 (all v2025.2), cited by chapter. Ross was tested by AMD on Vivado
2026.1; differences that matter here are noted.

## How to use it

1. Run `python3 flow/gates.py <build dir> --json gates.json` and find the first `FAIL` gate.
2. Open the report that gate reads (table below), find the rule ID, and look it up here.
3. Fix the cause, rebuild, and re-run the gates. Never waive a rule to make a gate pass without a written reason
   (Ross's own rule: never guess the design intent; report the conflict instead).

| Gate | Report in the build directory | IDs that appear there |
|---|---|---|
| `setup`, `hold`, `pulse_width` | `timing_summary.rpt` | WNS/TNS, WHS/THS, WPWS/TPWS |
| `no_unconstrained_endpoints` | `check_timing.rpt` | `no_clock`, `no_input_delay`, ... |
| `drc_clean` | `drc.rpt` | NSTD-1, UCIO-1, ... |
| `methodology_no_critical` | `methodology.rpt` | TIMING-n, XDC*, SYNTH-n, ... |
| `cdc_no_critical` | `cdc.rpt` | CDC-n |
| `bitstream_present` | Vivado log | the first ERROR before `write_bitstream` |

Fix order: clock definitions (TIMING-1/2/3/4/17), then clock relationships (TIMING-6/7/8), then I/O delays, then
logic. Ross resolves its "group 1" checks first for the same reason: clock fixes change every later result.

## Timing: setup, hold, pulse width

| Symptom | What it usually means | What to try |
|---|---|---|
| WNS < 0, path inside one clock, many logic levels | too much logic between registers for the period | pipeline; use carry chains, DSP or BRAM internal registers; check DONT_TOUCH/MARK_DEBUG is not blocking optimisation (UG906 ch. 5, Report Design Analysis) |
| WNS < 0, high net delay share | high fanout or far-apart cells | let `phys_opt_design` replicate, or register and replicate the driver |
| WNS < 0, requirement far below the period (e.g. 0.1 ns) | two clocks with an awkward ratio timed as related | decide whether the pair is asynchronous; add the CDC exception and synchronisers (TIMING-6/7/8) |
| WNS < 0 on a RAMB or DSP path | internal pipeline register unused | enable DO_REG / MREG / PREG and update the latency in the model and tests |
| WHS < 0, large | clock skew from logic on the clock path, or an inter-clock path without an exception | TIMING-14, TIMING-15 |
| WPWS < 0 | a clock above a resource limit (BUFG, BRAM, DSP; see DS181) | lower the clock or change the resource |

## check_timing (gate `no_unconstrained_endpoints`)

| Check | Meaning | What to try |
|---|---|---|
| `no_clock` | register clock pins reached by no clock | add the primary `create_clock`; avoid clocks made in logic (TIMING-17) |
| `unconstrained_internal_endpoints` | endpoints with no requirement | same causes as `no_clock` |
| `no_input_delay` / `no_output_delay` | ports with no I/O delay | add `set_input_delay`/`set_output_delay`; for asynchronous pins add a zero delay **and** a false path: in this flow a false path alone still counts (see `designs/t1_dimmer_counter/design.xdc`) |
| `partial_input_delay` / `partial_output_delay` | min or max (or one edge) missing | give both |
| `multiple_clock` | more than one clock reaches a register | usually a clock mux; constrain with `set_clock_groups -physically_exclusive` or case analysis |
| `loops`, `latch_loops` | combinational loops | remove in RTL (TIMING-23) |

## Methodology checks (`methodology.rpt`)

Rule meanings from UG906 (v2025.2) Appendix A; resolution steps mined from Ross
`skills/vivado-timing-methodology-checks/references/TIMING-<n>.md` where Ross has a file (marked R).

| ID | Meaning | What to try |
|---|---|---|
| TIMING-1 (R) | waveform of a clock on an MMCM/PLL output does not match its settings | compute F_in x M / (D x O); if it matches, rename the derived clock with `create_generated_clock`; if not, the constraint or the MMCM is wrong |
| TIMING-2 (R) | primary clock on an invalid pin (e.g. a register Q) | move `create_clock` to the port or primitive output; use a generated clock if the name is referenced |
| TIMING-3 (R) | primary clock on an MMCM/PLL output | delete it: Vivado derives it; rename if a name is needed (UG903 ch. 3, Renaming Auto-Derived Clocks) |
| TIMING-4 (R), TIMING-5 | clock redefined downstream on the same tree | keep the upstream primary; remove or convert the downstream definition |
| TIMING-6 (R), TIMING-7 (R), TIMING-8 (R) | clocks timed together with no common primary clock / node / period | asynchronous pair: `set_clock_groups -asynchronous` or `set_max_delay -datapath_only` + synchronisers; related pair: fix the clock definitions |
| TIMING-9 | CDC exception but no 2-flop synchroniser on the capture side | add a synchroniser, FIFO or handshake |
| TIMING-10 | synchroniser without ASYNC_REG | `(* ASYNC_REG = "TRUE" *)` on every stage |
| TIMING-11 | `-datapath_only` on a synchronous path | narrow the constraint to the asynchronous paths |
| TIMING-13 | path segmentation from max/min delay on invalid points | use register clock/data pins and ports as start/end points |
| TIMING-14 | LUT on the clock tree | clock enable instead of gating; BUFGCE if a gated clock is really needed |
| TIMING-15 | large hold from inter-clock skew (> 1 ns) | check for a missing CDC exception or logic on the clock path |
| TIMING-16 (R) | large setup violation (> 1 ns) early in the flow | constraint problem if the requirement is tiny or skew is high; architecture if logic levels are high |
| TIMING-17 (R) | sequential cell not clocked | add the missing clock |
| TIMING-18 (R) | missing input/output delay | add delays; asynchronous pins: zero delay + false path |
| TIMING-20 | latch with an unclocked gate | usually an unintended latch: fix the RTL (lint INFER-1) |
| TIMING-21 | MMCM COMPENSATION inconsistent | leave at AUTO |
| TIMING-23 | combinational loop | remove in RTL, or `set_disable_timing` at a chosen point |
| TIMING-24 | clock group / clock false path overrides a `-datapath_only` | use point-to-point false paths |
| TIMING-29 | multicycle setup without the matching hold | add `set_multicycle_path N-1 -hold` |
| XDCH-2 | same min and max delay on an I/O port | expected with this flow's zero-delay pattern for asynchronous pins (seen on T1, warning only) |
| XDCB-5 | runtime-inefficient way of finding pin objects in an XDC | prefer `get_ports`/`get_cells` over broad `get_pins` patterns (seen as a warning on the ILA build) |
| LUTAR-1 | a LUT drives an asynchronous reset | register the reset (reset synchroniser) so no logic sits on the reset path |
| SYNTH-6, -11, -12, -13 | RAMB or DSP primitive without its optional pipeline registers | enable the registers if the path is critical (not reported when slack is ample, UG906 ch. 5) |

Version note: Ross's TIMING skill declares "Requires Vivado 2026.1+", but the TIMING-n IDs and meanings above are
the same in the 2025.2 UG906 appendix.

## DRC (`drc.rpt`)

| ID | Meaning | What to try |
|---|---|---|
| NSTD-1 | a port has no I/O standard | give every top-level port a PACKAGE_PIN and IOSTANDARD from the master XDC. A critical warning in `report_drc`, **an error at `write_bitstream`** (F0A finding) |
| UCIO-1 | a port has no pin location | as NSTD-1; never waive: an unplaced pin can drive a net the board already drives. Waivers for NSTD-1/UCIO-1 turn object names into wildcards (UG906 ch. 3) |
| CFGBVS-1 (and the CONFIG_VOLTAGE warning) | configuration bank voltage not set | `set_property CFGBVS VCCO` and `CONFIG_VOLTAGE 3.3` on the Nexys A7 |
| RTSTAT-1 | unrouted nets | read-only check, cannot be waived (UG906 ch. 3): find why routing failed (congestion, unplaced cells) |
| RTSTAT-10 | nets with no routable loads | usually logic left without loads (seen on the ILA build); harmless if expected, otherwise a disconnected output |
| PDCN-1569 | "LUT equation term check" (the tool's description) | seen as a warning on the ILA build; not investigated further |

## CDC (`cdc.rpt`, from `report_cdc -details`)

From UG906 ch. 5, "CDC Rules and Descriptions". Only one rule per endpoint is shown (highest precedence first).

| ID | Severity | Meaning | What to try |
|---|---|---|---|
| CDC-1 | Critical | single-bit crossing not synchronised | 2-flop synchroniser with ASYNC_REG |
| CDC-2 / CDC-3 | Warning / Info | synchronised; ASYNC_REG missing / present | add ASYNC_REG / nothing |
| CDC-4 | Critical | multi-bit bus not synchronised | async FIFO, handshake, or Gray code |
| CDC-5 / CDC-6 | Warning | bus through per-bit synchronisers | safe only for Gray-coded or quasi-static values |
| CDC-7 | Critical | asynchronous reset not synchronised | reset synchroniser: asynchronous assert, synchronous release |
| CDC-8 / CDC-9 | Warning / Info | reset synchronised; ASYNC_REG missing / present | add ASYNC_REG / nothing (T1 shows CDC-3 and CDC-9) |
| CDC-10 | Critical | combinational logic before the synchroniser | register the signal in its source domain |
| CDC-11 | Critical | launch flop fans out into the destination domain | one path through one synchroniser |
| CDC-12 | Critical | several source clocks feed one synchroniser | separate the sources |
| CDC-13 / CDC-14 | Critical | crossing into a non-flip-flop primitive | synchronise before the primitive |
| CDC-15 / -16 / -17 | Warning | enable- or mux-controlled crossing | safe only if the control is synchronised and the data held stable |
| CDC-18 | Info | HARD_SYNC primitive | nothing |
| CDC-26 | Warning | LUTRAM read/write collision risk | separate read and write timing |

## Synthesis and lint messages (Vivado log)

Meanings from Ross `skills/vivado-rtl-lint/resolution/` and `skills/vivado-rtl-elaboration-analysis/resolution/`
at `dce0fb9`. Fix the first error first: later ones often cascade.

| ID | Meaning | What to try |
|---|---|---|
| `[Synth 8-36]` | identifier not declared | declaration, typo, missing file |
| `[Synth 8-439]` | module not found | the source is not in `build.yaml` |
| `[Synth 8-327]` / lint INFER-1 | latch inferred | assign every output on every path of the `always_comb`, or default it first |
| `[Synth 8-6859]` / lint ASSIGN-7 | multi-driven net | one driver per bit |
| `[Synth 8-689]` | port connection width mismatch | port order (positional connections) or declarations |
| `[Synth 8-3848]` / lint ASSIGN-5 | net or bits with no driver | add the assignment, or remove the signal |
| `[Synth 8-6014]`, `[Synth 8-3332]` | register removed (unused or constant) | expected for dead logic; otherwise an output is not connected (or an ILA probe was optimised away) |
| `[Synth 8-4767]` | RAM built from registers | rewrite to a block-RAM template (registered read) |
| lint ASSIGN-1 | result truncated | widen to the size the message gives |
| lint ASSIGN-2 | signed and unsigned mixed | cast both operands |
| lint CLOCK-1 | both edges of one clock in a module | use one edge |
| lint RESET-1 / RESET-2 | several async resets / some registers not reset | one reset; reset all registers of the block or none |

Version note: `synth_design -lint -file` writes a text table on 2025.2 (Ross reads a CSV from 2026.1), and UG835
v2025.2 lists only ASSIGN-1 to -7, QOR-1, INFER-1 to -3, CLOCK-1 and RESET-1/-2.

Verilator (`flow/lint.sh`, `-Wall`) reports its own names for the same problems: `WIDTH*` (widths), `UNUSED*` and
`UNDRIVEN` (unused or undriven signals), `LATCH` and `CASEINCOMPLETE` (latches and incomplete case),
`MULTIDRIVEN`, `BLKSEQ` (blocking assignment in a sequential block). Fix the RTL; suppress a warning only with a
comment saying why.

## Bring-up failures (`flow/bringup.py`)

| Symptom | What to try |
|---|---|
| power gate refuses | `report_power` total above 0.5 W: the board runs from USB; reduce the design or ask the owner about external power |
| no target / several targets | check the cable and `~/.config/fpga_design_agent/boards.yaml`; never program "the first target" |
| next run cannot open the cable | a previous `hw_server` still holds it: stop the whole process group |
| UART: no reply | C4 is the FPGA's receive (`UART_TXD_IN`), D4 its transmit (`UART_RXD_OUT`); check the build stamp |
| ILA: no core / probes missing | the ILA bitstream is not programmed, or the `.ltx` does not match it |
| ILA: compare value rejected | the `.ltx` split a probe over several hardware probes: set values per hardware probe from its `MAP` |
| ILA: `wait_on_hw_ila` hangs | the trigger never fired; capture with `-trigger_now` first; `-timeout` is in minutes (Ross `hw-ila-debug`) |
| board resets or drops off USB | stop at once and report (house rule) |
