# Build dbg_xvc: an ILA reached over Ethernet (brief 131)

Status: built on Vivado 2026.1 with the flow's gates (numbers below, measured); **not loaded on a board** (the board test is pre-registered in `xvc_board_test.md`, the Linux side is in `xvc_board_side.md`).
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

RESULTS_PLACEHOLDER
