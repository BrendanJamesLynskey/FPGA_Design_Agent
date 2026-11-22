# Build dbg_xvc: an ILA reached over Ethernet (brief 131)

Status: built and routed on Vivado 2026.1 (numbers below, measured; some flow gates fail for debug-IP reasons, listed); **not loaded on a board** (the board test is pre-registered in `xvc_board_test.md`, the Linux side is in `xvc_board_side.md`).
Terms: ILA = integrated logic analyser (a capture memory in the PL that records chosen signals around a trigger); XVC = Xilinx Virtual Cable (JTAG shifts carried over TCP); PS = the Zynq UltraScale+ processing system (the ARM cores and Linux);
BSCAN = the FPGA's boundary-scan (JTAG) user chains; hardware manager = the Vivado tool that talks to ILAs.

## Why

Our board runs read FPGA counters over JTAG while the KR260's Linux is up, and the run plan already notes that the Linux check may need an override after the first JTAG load. Adam Taylor argues
(Hackster, "Debugging HW ILAs with PetaLinux over Ethernet", https://www.hackster.io/adam-taylor/debugging-hw-ilas-with-petalinux-over-ethernet-be6218) that JTAG access to an ILA while Linux runs can disturb the operating system,
and that a Debug Bridge on the PS's AXI plus XVC lets the hardware manager reach the ILA over the network instead. This build tests the second half of that on our design. **The first half (that JTAG disturbs Linux on this board) is not tested here.**

## What the build is

Build `dbg_xvc` = build `eyescan` (RATE_MATCH = 0, EYESCAN = 1; a non-latency build) plus a debug path. Differences from `eyescan`, and only these (checked by `tests/test_b131_xvc.py`):

| File | Change |
|---|---|
| `dbg_xvc/rtl/xvc_debug.sv` (new) | PS (default configuration, only M_AXI_HPM0_LPD and pl_clk0 at 100 MHz used) -> AXI4-to-AXI4-Lite converter -> Debug Bridge "From AXI to BSCAN" -> one ILA; three RXUSRCLK2 strobes cross to clk by `xpm_cdc_pulse` |
| `dbg_xvc/rtl/b96_core.sv` | copy of `rtl/b96_core.sv`: three output ports (`dbg_s`, `dbg_rxclk`, `dbg_rxp`) assigned from existing signals; the only line of the base that changes is the last port declaration (a comma added); nothing in the core reads the new ports |
| `dbg_xvc/rtl/kr260_10g_top.sv` | copy of `rtl/kr260_10g_top.sv`: three wires and the instance of `xvc_debug` |
| `ip/amd_ip_xvc.tcl` | the four AMD IP (PS, protocol converter, Debug Bridge, ILA); on the reviewed-Tcl allow-list `flow/ip_tcl_allow.yaml` |

The default build and every latency build (`rm_gp`, `rm_gp_bypass`, `lat_all3`, `lat_all3_bypass`, `rm_gp_ml`) are untouched: their `build.yaml` files do not name any of these files (checked by a test).
Deviation from the brief's wording: the brief said "one System ILA"; the System ILA IP is for IP Integrator (Vivado warns that it is intended for IPI only) and exists to watch AXI interfaces, so the build uses the plain `ila` IP, which is what a System ILA wraps for plain signals. One ILA, one probe of 38 bits, 1024 samples, storage qualification on, one input pipeline stage.

## What the ILA sees, and why

All 38 bits are in the 100 MHz `clk` domain. The 35 bits of `dbg_s` are levels that `b96_core` already brought into `clk` through its own synchronisers (so the ILA adds no new crossing for them); the 3 strobes cross through new `xpm_cdc_pulse` instances.

| Probe bit | Signal | Why it is worth watching |
|---|---|---|
| 0 | `tx_done` (GT TX reset sequence finished) | the transmit side came out of reset; with bit 1 this is the "GT reset done" pair |
| 1 | `rx_done` | receive side reset done; a drop with no command written is a GT restart |
| 2 | `pcs_lock` (64B/66B block lock) | link state: the signal whose rising edge a link-up capture would trigger on |
| 3 | `pgood` (GT power good) | transceiver powered |
| 4 | `cdrlock` | the receive clock-data recovery has locked |
| 5 | `cdr_stable` | what the Wizard waits for before releasing the receive datapath |
| 6, 7 | `txpmadone`, `rxpmadone` | PMA reset done, the inputs of the user-clock resets |
| 8-9 | `txbuf[1:0]` | GT TX buffer status (the buffer is bypassed only in builds not derived from this one) |
| 10-12 | `rxbuf[2:0]` | GT RX buffer status |
| 13, 14, 15 | `mod_abs`, `rx_los`, `tx_fault` | the SFP+ module's status pins as the design sees them |
| 16 | `p_seq` | restart pulse: any side's done level changing, or a GT reset command |
| 17-21 | `wz_all`, `wz_txpll`, `wz_rxpll`, `wz_txdp`, `wz_rxdp` | the five reset requests into the GT Wizard: which reset ran |
| 22-33 | `h_addr[11:0]` | the register address on the host bus |
| 34 | `h_we` | a register write: with 22-33 it shows which write caused a reset |
| 35 | decision fired (`r_fire`, RXUSRCLK2, crossed) | the order-fired strobe |
| 36 | start of packet (`r_sop`, crossed) | a frame began at the MAC |
| 37 | order frame seen (`r_order`, crossed) | the classifier saw an order frame |

The "GT bypass done" bits the brief mentioned exist only in builds with the buffer-bypass controllers (`rm_gp_bypass`, a latency build); this build is not derived from it, so it cannot show them: the `tx_done`/`rx_done` pair is the reset-done evidence available here.
A strobe that comes again within the pulse crossing's dead time (a few clock periods) is dropped from the ILA's view; the design's own counters are unaffected. The captured strobes show that a decision fired and when (to about 10 ns), not how many.

## What the path can and cannot reach

The Debug Bridge talks to the ILA's debug hub only. It does not reach the design's register bus (`jtag_bus` uses the physical TAP's USER4 chain; the bridge's soft TAP is a different one), configuration memory, flash or eFUSE. Writes over XVC can only change the ILA's own trigger and capture settings.
**Optional item 5, registers over the same path:** in principle `jtag_bus` could take its TCK/TDI/shift/capture/update from a second BSCAN master port of the bridge instead of the BSCANE2 primitive (the Debug Bridge IP has a BSCAN master interface count parameter, `C_NUM_BS_MASTER`),
which would let the existing register scripts run over XVC. **Not built and not checked**: it would need the register bus's DR protocol to survive the bridge's AXI latency, and the TAP selection of the host tools; it changes `jtag_bus`, which belongs to every build. Recorded as an idea only.

## Measured: what the debug logic changes (Vivado 2026.1, same flow and commit for both builds)

Both builds: Vivado 2026.1 (Basic licence), 2 threads, the same commit, `flow/run_vivado.sh ... base`, MemoryMax 12G (owner's decision of 2026-11-21: the 6G cap OOM-killed dbg_xvc three times; the parent had also only just fitted its earlier 6G run). Records: `results/b131/builds/{eyescan,dbg_xvc}/` (run.json, trimmed gates.json, digest.json), `results/b131/compare/summary.json`, netlist and timing dumps in `results/b131/dump/` (made by `dbg_xvc/scripts/dump_netlist_timing.tcl`, compared by `compare_builds.py`).

| | eyescan (parent) | dbg_xvc | difference |
|---|---|---|---|
| WNS, routed (ns) | 0.314 | 0.323 | +0.009 |
| WHS, routed (ns) | 0.011 | 0.011 | 0 |
| LUT | 6395 | 8216 | +1821 |
| FF | 14545 | 17410 | +2865 |
| BRAM tiles | 0 | 1.5 | +1.5 (the ILA) |
| DSP | 0 | 0 | 0 |
| Peak memory (scope, anonymous) | 8111 MiB | 9647 MiB | +1536 MiB |
| Wall time | 1048 s | 1745 s | +697 s |

**Where the added logic is.** About 1.8k LUTs and 2.9k FFs is mostly the PS8 wrapper's fabric glue, the AXI converter, the Debug Bridge with its soft TAP and the ILA with its debug hub; the split between them was not measured.

**The trading path and the core are untouched at cell level (measured).** `compare_builds.py` compares every cell under `u_core` of the two routed checkpoints. The 14311 cells with names from the RTL (flops, RAM, GT, clock buffers) are identical in name and library cell in both builds: 0 removed, 0 added, 0 changed. LUTs, carry chains and muxes have tool-made names that change from run to run, so they are compared by count per `u_core` child: `g_old.u_rx` (the receive path with MAC and trading decision) 0 change, every crossing and the transmit-side vectors 0, `g_old.u_tx` 11 fewer, `g_es.u_es` 7 fewer, `u_cfg_tx` 38 more, the register-block level 5 more; the net total is 25 more LUT-type cells under `u_core`. Those changes are the synthesis tool re-mapping logic that did not change in the source; they are reported as observed and not explained.
Each of the three tapped nets (decision fired, start of packet, order frame seen, RXUSRCLK2 domain) has two load pins in dbg_xvc, the design's own load and the first flop of the tap's crossing: one extra load per net.

**Timing through the trading path.** Worst slack of paths that start or end in the receive path (`u_rx`): setup 0.444 ns parent, 0.333 ns dbg_xvc; hold 0.017 / 0.015. In the transmit path (`u_tx`): setup 0.314 / 0.323; hold 0.011 / 0.011. The receive-path setup slack is 0.111 ns lower in the debug build although none of its cells changed; the placement and routing of a different netlist differ, and the cells and constraints do not. Whether the 0.111 ns is run-to-run variation was not measured (one run of each build). Both builds meet timing with positive slack on every clock.

**One naming effect found and fixed.** In the first dbg_xvc build the receive user clock took the name `dbg_rxclk` (Vivado names a clock after the net at the highest level of the hierarchy), which the flow's gates do not expect; the top now names that net `rxusr2`. The gate failures below did not change with the rename.

**Flow gates (`flow/gates.py`): the parent passes all of them; dbg_xvc does not.** All post-route timing gates pass for dbg_xvc: setup, hold, pulse width, no unconstrained endpoints, DRC, methodology (no critical warnings), `report_cdc` (no critical), power, I/O timing, bitstream. These fail:

| Gate | What the record shows | Cause |
|---|---|---|
| `post_synth_no_unconstrained_endpoints`, `post_synth_methodology_no_critical` | 1008 register pins with no clock, in the ILA's capture memory and debug hub, root `dbg_hub/sl_iport0_o[1]`; 1000 TIMING-17 critical warnings | at synthesis the debug hub's clock (a divided TCK made by the Debug Bridge's soft TAP) is not yet defined; the bridge's constraint file creates it (it is in `ip/dbb_xvc/.../axi_jtag.xdc`). The same pins pass after routing (`no_unconstrained_endpoints` ok). The reason it is missing at synthesis is not confirmed. |
| `post_synth_cdc_structure_clean` | 2203 crossings classed unsafe, rule U5 ("xpm_handshake bus without its Max Delay Datapath Only exception"), all between the core's clock domains (hs_vec crossings) | the exceptions do exist in the routed design (`exceptions_route.rpt` lists them with max_dpo 6.206 and 10 ns); the flow's checker does not match them in this build. Cause not found. The routed `report_cdc` has no critical item. |
| `post_synth_exceptions_clean`, `exceptions_clean` | exceptions "ignored" or "non-existent" in the Debug Bridge's and ILA's own constraint files, plus XPM exceptions "totally overridden" by others | debug IP constraints; the flow classifies some as `EXC-IGNORED-DEBUG-IP` and still fails on others |
| `post_place_hold` | worst hold slack at placement -2.3 ns (limit -0.5) | the routed design closes hold (0.011 ns); the worst place-stage path is not in the trading path |

`post_synth_resources_in_range` failed on the first run because the parent's architecture predicts 0 BRAM; `dbg_xvc/architecture.yaml` now predicts 1 to 2 and it passes.
These are the open items for the planner: either the debug IP needs its clocks constrained for the flow's synthesis-stage gates (a flow change, not made here), or the gates need a debug-build mode.

**Bitstream.** The flow's base build wrote `kr260_10g_top.bit` and the probe file `kr260_10g_top.ltx` was written from the routed checkpoint (it names the debug hub and `u_dbg/u_ila`); both are in the gitignored build directory and are not loaded on any board. Build ID `4a9ae66a`.
