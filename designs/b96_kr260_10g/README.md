# b96_kr260_10g: A 10GBASE-R link on the KR260 SFP+ cage: our own PCS and 64-bit MAC with a mock trading path

<!-- Generated from handover.yaml by flow/handover.py (brief 68). Edit handover.yaml, or the text between the prose markers, then run: python -m flow.handover write designs/b96_kr260_10g -->

A Kria KR260 design that carries our own 10GBASE-R PCS (64B/66B, scrambler, gearbox, block lock) and a 64-bit Ethernet MAC on one GTH lane at 10.3125 Gb/s, with the mock trading path of brief 58A behind it (a one-rule 64-bit decision in the same message format), because the AMD 10G Ethernet core is refused on the free Basic licence. Verified against an independent Python reference in simulation (the GT is a behavioural stand-in) and built to a bitstream on Vivado 2026.1 Basic with every flow gate passing in two variants. Brief 96C added a rate-matching elastic buffer as a build option (default off, the board-proven 97C receive path); the base and its rate-matched variants have run on a KR260 optical loopback, not yet against a network card or a second reference clock.

Not in scope:

- an interoperability proof: a PCS talking to itself accepts its own symmetric mistakes, only a network card proves it
- the full 58A trading core (book, rule table, interlocks, ARP) at 64 bits: trade64 is a small stand-in with one rule
- the reconciliation sublayer link-fault state machine, the BER monitor, an ARP or ICMP responder

Kind: example; written by hand. State: built. For an agent: [AGENT.md](AGENT.md).

![Block diagram: the design's blocks and the links between them](docs/handover/architecture.svg)

<!-- prose:what -->
<!-- /prose:what -->

## Technical parameters

| Item | Value |
|---|---|
| Part | `xck26-sfvc784-2LV-c` |
| Board | Kria KR260 |
| Top | `kr260_10g_top` |
| Tool | Vivado 2026.1 |
| Note | GTHE4_CHANNEL_X0Y6 of quad 224; SFP+ cage J24; reference MGTREFCLK0 (Y6/Y5); variant (a) is selftest/build.yaml |

Clocks:

- `clk_25`: 25 MHz (from `designs/b96_kr260_10g/design.xdc`); input C3, an open-source example figure, unconfirmed against the schematic; an MMCM makes the 100 MHz free-running clock
- `sfp_mgt_refclk`: 156.25 MHz (from `designs/b96_kr260_10g/design.xdc`); MGTREFCLK0 of quad 224; frequency and source unconfirmed (two third-party sources agree, no AMD document or schematic)

Resets:

- `reset helper`, active high: the register block is reset while the MMCM is unlocked; each path is held in reset while the GT Wizard reports its transmit or receive side not done

Interfaces:

- `Host register block` (32-bit register bus over JTAG (BSCANE2 USER4, jtag_bus)) ([datasheet](docs/register_map.md)): generated from regmap.py; unmapped reads return 0; counters read from a snapshot; reads have no side effects
- `SFP+ lane and control pins` (one GTH lane at 10.3125 Gb/s; tx_disable, mod_abs, rx_los, tx_fault, I2C) ([datasheet](docs/board_run_plan.md)): the laser is disabled at reset (tx_disable = 1; polarity unconfirmed until the first board run)

| Parameter | Value | Legal range | Note |
|---|---|---|---|
| `NEAR_END` | 0 (variant b), 1 (variant a) | 0 or 1 | 1 selects the near-end PMA loopback at reset |
| `TRADE` | 1 (variant b), 0 (variant a) | 0 or 1 | 1 enables the mock trading path at reset; it still needs ARM |
| `RATE_MATCH` | 0 (default), 1 (the 96C elastic buffer) | 0 or 1 | 0 is the receive path of main 6909e43f (brief 97C, board-proven); 1 puts rate_match between the receive PCS and the MAC (11 clocks slower on the board); the register map is the same, with the rate-match and frequency words reading 0 at 0 |
| `EYESCAN` | 0 (default), 1 (the eyescan build) | 0 or 1 | 1 adds brief 96D's DRP access, eye-scan point sequencer (es_ctrl) and TX drive registers (FEATURES bit 4); with 0 they read 0 and the GT's DRP and drive ports are tied to the old constants; es.xdc also powers up the GT's eye-scan circuit in the eyescan build |
| `RM_OWN` | 0 (default), 1 (the 96E own gray-pointer buffer) | 0 or 1 | RATE_MATCH = 1 only (FEATURES bit 5); 1 uses rate_match_gp.sv (about 5 clocks, 1.2 clocks of tick-to-trade over the 97C path in simulation) instead of the xpm_fifo_async buffer (5.3 clocks) |
| `RM_DIRECT` | 0 (default), 1 (build rm_gp_direct) | 0 or 1 | RM_OWN = 1 only; 1 sets rate_match_gp's ENT_SYNC to 0 (direct read of the entry flops, 1.2 clocks of tick-to-trade in simulation) which fails the report_cdc gate (38 CDC-1 Critical); kept as evidence |
| `GO_REG` | 1 (default), 0 in lat_all3 | 0 or 1 | RATE_MATCH = 0 only, the register stage of the go-pulse crossing (brief 97's all3 variant removes it) |
| `line rate` | 10.3125 Gb/s | fixed by 10GBASE-R | QPLL0 from the 156.25 MHz reference; the user clocks (161.133 MHz) carry 64 bits a word and the PCS takes one clock pause in 33 |

| Quantity | Value | Source |
|---|---|---|
| Resources | LUTs, variant (b): 6167 LUT; registers, variant (b): 14,183 FF | M1, M2 |
| Timing | worst setup slack, variant (b): 0.221 ns; worst hold slack, variant (b): 0.011 ns; worst setup slack, latency variant all3 with the rate matcher (RATE_MATCH = 1): 0.004 ns; worst setup slack, build lat_all3_bypass (the 97C cuts with both GT buffers bypassed): 0.066 ns | M3, M4, M9, M12 |
| Power | total on-chip power estimate, variant (b): 1.087 W | M5 |
| Latency | transmit latency, worst gearbox phase: 3 clocks; digital tick-to-trade, worst simulated case with the rate matcher (RATE_MATCH = 1): 13 clocks; digital tick-to-trade, simulation of the default build (RATE_MATCH = 0, the 97C path): 11 clocks; GT-port tick-to-trade in simulation with AMD's real macros, own gray-pointer buffer (RM_OWN = 1), mean over four phases at phase 1550 ps: 13 clocks; GT-port tick-to-trade in simulation, build lat_all3_bypass, mean over four phases (the same as lat_all3 within 0.1 clock, because the stand-in has no GT buffers and the bypass's saving is not simulated): 7.6 clocks | M7, M8, M10, M11, M13 |
| Throughput | not measured | [Known gaps](#known-gaps-and-limits) |

![Resource use as a share of the part, and timing slack](docs/handover/resources.svg)

<!-- prose:parameters -->
<!-- /prose:parameters -->

## How to build, run and reproduce

| Step | Command | Heavy slot | Time |
|---|---|---|---|
| simulate the PCS, MAC and core against the Python reference; needs Icarus Verilog and cocotb 2.0.1 | `python -m pytest -q designs/b96_kr260_10g/tests` | no | about 2 min |
| build variant (b) and run all gates; needs local Vivado 2026.1 (Basic tier) and a heavy slot (take_heavy_slot.sh), MEM_MAX=6G reaches the cap | `flow/run_vivado.sh designs/b96_kr260_10g base` | yes | about 22 min |
| build variant (a), the near-end loopback self-test; needs as above | `flow/run_vivado.sh designs/b96_kr260_10g/selftest base` | yes | about 22 min |
| the UVM 1.2 regression of the PCS and MAC in xsim (every test over its seeds, coverage merge, seeded bugs); needs Vivado 2026.1 xsim (Basic tier is enough); a simulation-only run, no heavy slot while the load is under 6 and more than 12 GB is free | `designs/b96_kr260_10g/verif/uvm/scripts/run_regress.sh --mutants --record results/112_uvm_pcs_mac` | no | about 40 min |
| the pyuvm regression of the PCS and MAC in Icarus (every test over its seeds, coverage merge, seeded bugs); needs pyuvm 5.0.0 and cocotb-coverage in a venv that sees cocotb 2.0.1; needs Icarus Verilog 12, cocotb 2.0.1, pyuvm 5.0.0, cocotb-coverage; a simulation-only run, no heavy slot while the load is under 6 and more than 12 GB is free | `PYTHONPATH=. python designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --mutants --record results/123_pyuvm_pcs_mac` | no | about 15 min |

Tool: Vivado 2026.1. Build ID of the inputs at handover: `43708f17` (`python flow/manifest.py show designs/b96_kr260_10g`: what a rebuild of today's sources and flow would carry; it changes when any build input or the flow changes, so it can differ from the build ID in an older evidence record). Knowledge-bank pin: `93d158c`.

| File | What |
|---|---|
| [`designs/b96_kr260_10g/dbg_xvc/rtl/xvc_debug.sv`](dbg_xvc/rtl/xvc_debug.sv) | the debug path of build dbg_xvc: PS AXI master, AXI4 to AXI4-Lite converter, Debug Bridge (AXI to BSCAN) and one ILA on status taps (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/rtl/b96_core.sv`](dbg_xvc/rtl/b96_core.sv) | copy of rtl/b96_core.sv for build dbg_xvc with three read-only tap ports for the debug ILA (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/rtl/kr260_10g_top.sv`](dbg_xvc/rtl/kr260_10g_top.sv) | copy of rtl/kr260_10g_top.sv for build dbg_xvc with the debug path instantiated (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/build.yaml`](dbg_xvc/build.yaml) | how flow/run_vivado.sh builds dbg_xvc (the eyescan build plus the debug path, brief 131) |
| [`designs/b96_kr260_10g/ip/amd_ip_xvc.tcl`](ip/amd_ip_xvc.tcl) | the AMD IP of build dbg_xvc: Zynq UltraScale+ PS, AXI Protocol Converter, Debug Bridge, ILA (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/docs/dbg_xvc.md`](dbg_xvc/docs/dbg_xvc.md) | what build dbg_xvc is, what the ILA watches and why, what the debug logic changes, measured against the parent build (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/docs/xvc_board_side.md`](dbg_xvc/docs/xvc_board_side.md) | how XVC would run on the KR260's Ubuntu: which variant fits, the overlay, the Vivado connection; written, not run (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/docs/xvc_board_test.md`](dbg_xvc/docs/xvc_board_test.md) | the pre-registered board test for build dbg_xvc: criteria written before any board time (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/board/pl-dbg-xvc.dtsi`](dbg_xvc/board/pl-dbg-xvc.dtsi) | device-tree overlay fragment for the debug bridge on the KR260; not loaded on a board (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/board/xvc_board_session.sh`](dbg_xvc/board/xvc_board_session.sh) | the board-session script for the dbg_xvc test, given by the planner at the board; not run (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/board/xvc_capture.tcl`](dbg_xvc/board/xvc_capture.tcl) | Vivado hardware-manager side of the dbg_xvc board test: XVC connection and ILA captures; not run (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/model/xvc_verdict.py`](dbg_xvc/model/xvc_verdict.py) | the pre-registered verdict of the dbg_xvc board test (brief 131) |
| [`designs/b96_kr260_10g/dbg_xvc/scripts/dump_netlist_timing.tcl`](dbg_xvc/scripts/dump_netlist_timing.tcl) | dumps a routed build's core cells and slacks so the debug build can be compared with its parent (brief 131) |
| [`designs/b96_kr260_10g/verif/pyuvm/README.md`](verif/pyuvm/README.md) | how the pyuvm (Python UVM on cocotb and Icarus) bench for the PCS and MAC is built, run and limited; the same job as the SystemVerilog UVM bench (brief 123) |
| [`designs/b96_kr260_10g/verif/pyuvm/COMPARISON.md`](verif/pyuvm/COMPARISON.md) | the measured comparison of the pyuvm and the SystemVerilog UVM bench, where each fits the project, and a section for the verification course (brief 123) |
| [`designs/b96_kr260_10g/verif/uvm/README.md`](verif/uvm/README.md) | how the UVM 1.2 bench for the PCS and MAC is built, what each part checks, the coverage and the seeded bugs (brief 112) |
| [`designs/b96_kr260_10g/rm_gp_bypass/rtl/b96_core.sv`](rm_gp_bypass/rtl/b96_core.sv) | copy of rtl/b96_core.sv for build rm_gp_bypass with the GT buffer-bypass controllers connected, run gates and (brief 96F1b) the alignment timeout and retry status in GT_BUF |
| [`designs/b96_kr260_10g/rm_gp_bypass/rtl/gt_bp_ctl.sv`](rm_gp_bypass/rtl/gt_bp_ctl.sv) | per-direction reset synchroniser, 30 ms TX / 130 ms RX alignment timeout with bounded retry and gave-up flag for the bypass controller (brief 96F1b) |
| [`designs/b96_kr260_10g/rm_gp_bypass/rtl/gt_bp_gate.sv`](rm_gp_bypass/rtl/gt_bp_gate.sv) | per-direction gate that releases the paths only after the bypass controller has restarted and finished (brief 96F1) |
| [`designs/b96_kr260_10g/ip/amd_ip_bypass.tcl`](ip/amd_ip_bypass.tcl) | the GT Wizard configuration with both buffers bypassed (brief 96F1) |
| [`designs/b96_kr260_10g/host/b96f1_bypass.py`](host/b96f1_bypass.py) | board driver and pre-registered verdict for build rm_gp_bypass (brief 96F1) |
| [`designs/b96_kr260_10g/lat_all3_bypass/build.yaml`](lat_all3_bypass/build.yaml) | build lat_all3_bypass, the default receive path with the 97C latency cuts and both GT elastic buffers bypassed; points at the parent builds' files, no copy (brief 126) |
| [`designs/b96_kr260_10g/host/b126_all3_bypass.py`](host/b126_all3_bypass.py) | board driver and pre-registered verdict for build lat_all3_bypass (brief 126) |
| [`designs/b96_kr260_10g/rm_gp_ml/rtl/ml_stage.sv`](rm_gp_ml/rtl/ml_stage.sv) | the ML decision stage of build rm_gp_ml: one-instrument book, order-flow features, classifier pipeline and counters (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/rtl/ml_pkg.sv`](rm_gp_ml/rtl/ml_pkg.sv) | constants shared by the ML stage (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/rtl/trade64.sv`](rm_gp_ml/rtl/trade64.sv) | copy of rtl/trade64.sv for build rm_gp_ml with the model's veto on the rule's decision (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/rtl/rx_path.sv`](rm_gp_ml/rtl/rx_path.sv) | copy of rtl/rx_path.sv for build rm_gp_ml with the ML stage's ports through to trade64 (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/rtl/rx_path_legacy.sv`](rm_gp_ml/rtl/rx_path_legacy.sv) | copy of rtl/rx_path_legacy.sv for build rm_gp_ml with the ML ports tied off (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/rtl/b96_core.sv`](rm_gp_ml/rtl/b96_core.sv) | copy of rtl/b96_core.sv for build rm_gp_ml with the ML registers, crossings and status words (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/build.yaml`](rm_gp_ml/build.yaml) | how flow/run_vivado.sh builds rm_gp_ml (rm_gp with the ML stage, brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/docs/ml_stage.md`](rm_gp_ml/docs/ml_stage.md) | which model block was chosen and why, how the stage is arranged, the measured cost in context (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/docs/ml_registers.md`](rm_gp_ml/docs/ml_registers.md) | register map of the ML stage, generated from rm_gp_ml/regmap_ml.py (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/model/twin.py`](rm_gp_ml/model/twin.py) | Python twin of the ML stage over the brief 87 references (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/model/stream.py`](rm_gp_ml/model/stream.py) | synthetic Bench Feed v1 streams as 10GBASE-R words, with the twin's expectation per frame (brief 113) |
| [`designs/b96_kr260_10g/rm_gp_ml/sim/tb_ml_core.sv`](rm_gp_ml/sim/tb_ml_core.sv) | whole-core xsim bench with a synthetic feed injected on the receive words (brief 113) |
| [`designs/b96_kr260_10g/host/b113_ml.py`](host/b113_ml.py) | board driver and pre-registered verdict for build rm_gp_ml (brief 113) |
| [`designs/b96_kr260_10g/rtl/es_ctrl.sv`](rtl/es_ctrl.sv) | DRP master and eye-scan point sequencer for the GTHE4 channel (EYESCAN = 1), brief 96D |
| [`designs/b96_kr260_10g/es.xdc`](es.xdc) | powers up the GT's eye-scan circuit (ES_EYE_SCAN_EN, ES_ERRDET_EN) in the eyescan build |
| [`designs/b96_kr260_10g/model/eyescan.py`](model/eyescan.py) | Python twin of the eye-scan point sequencer's DRP traffic |
| [`designs/b96_kr260_10g/tests/eyescan_cocotb.py`](tests/eyescan_cocotb.py) | cocotb bench of the sequencer against the twin and a DRP stand-in |
| [`designs/b96_kr260_10g/rtl/b96_pkg.sv`](rtl/b96_pkg.sv) | block codes, scrambler, CRC-32 functions |
| [`designs/b96_kr260_10g/rtl/pcs_tx.sv`](rtl/pcs_tx.sv) | transmit PCS (encode, scramble, gearbox) |
| [`designs/b96_kr260_10g/rtl/pcs_rx.sv`](rtl/pcs_rx.sv) | receive PCS (gearbox with slip, block lock, descramble, decode) |
| [`designs/b96_kr260_10g/rtl/mac64_tx.sv`](rtl/mac64_tx.sv) | 64-bit MAC transmitter |
| [`designs/b96_kr260_10g/rtl/mac64_rx.sv`](rtl/mac64_rx.sv) | 64-bit MAC receiver |
| [`designs/b96_kr260_10g/rtl/frame_src.sv`](rtl/frame_src.sv) | frame builder for orders, feed, probe and test frames |
| [`designs/b96_kr260_10g/rtl/trade64.sv`](rtl/trade64.sv) | the 64-bit mock trading decision |
| [`designs/b96_kr260_10g/rtl/tx_path.sv`](rtl/tx_path.sv) | transmit domain: sources, generator, timestamps |
| [`designs/b96_kr260_10g/rtl/rx_path.sv`](rtl/rx_path.sv) | receive domain: PCS, MAC, decision, counters |
| [`designs/b96_kr260_10g/rtl/b96_core.sv`](rtl/b96_core.sv) | registers, GT wrapper and clock-domain crossings |
| [`designs/b96_kr260_10g/rtl/kr260_10g_top.sv`](rtl/kr260_10g_top.sv) | board top (MMCM, SYSMON, pins) |
| [`designs/b96_kr260_10g/rtl/rx_path_legacy.sv`](rtl/rx_path_legacy.sv) | the 97C receive path (main 6909e43f), used when RATE_MATCH = 0 |
| [`designs/b96_kr260_10g/rtl/rate_match.sv`](rtl/rate_match.sv) | rate-matching elastic buffer (idle insert and delete between frames, xpm_fifo_async), brief 96C |
| [`designs/b96_kr260_10g/rtl/rate_match_gp.sv`](rtl/rate_match_gp.sv) | low-latency elastic buffer with our own gray-pointer crossing (RM_OWN = 1), brief 96E |
| [`designs/b96_kr260_10g/rate_match_gp.xdc`](rate_match_gp.xdc) | set_max_delay -datapath_only for the direct-read variant of rate_match_gp (build rm_gp_direct only) |
| [`designs/b96_kr260_10g/model/ratematch.py`](model/ratematch.py) | Python twin of the rate matcher, compared output for output with the RTL |
| [`designs/b96_kr260_10g/host/b96c_ppm.py`](host/b96c_ppm.py) | board driver for the ppm sweep (TX phase-interpolator offset, measured ppm, SYSMON conditions) |
| [`designs/b96_kr260_10g/rtl/hs_vec.sv`](rtl/hs_vec.sv) | coherent vector crossing |
| [`designs/b96_kr260_10g/model/pcs.py`](model/pcs.py) | bit-serial Python reference of the PCS (the twin) |
| [`designs/b96_kr260_10g/design.xdc`](design.xdc) | pins, clocks, slow-pin constraints |
| [`designs/b96_kr260_10g/docs/design.md`](docs/design.md) | design note: decisions and alternatives |
| [`designs/b96_kr260_10g/docs/board_run_plan.md`](docs/board_run_plan.md) | stage 3 plan for the board |
| [`designs/b96_kr260_10g/docs/what_we_found.md`](docs/what_we_found.md) | results and gaps |
| [`designs/b96_kr260_10g/docs/loop_timing_feasibility.md`](docs/loop_timing_feasibility.md) | loop-timing and buffer-bypass feasibility study (96F) |
| [`designs/b96_kr260_10g/docs/loop_timing_board_test_plan.md`](docs/loop_timing_board_test_plan.md) | board test plan for loop timing (96F, for approval) |
| [`designs/b96_kr260_10g/docs/loop_timing_sources.md`](docs/loop_timing_sources.md) | AMD sources read for loop timing (XAPP1276, Wizard example, TXPI, QPLL outside the core; 96F2) |
| [`docs/latency_definitions.md`](../../docs/latency_definitions.md) | our latencies against STAC-T0 and wire-to-wire definitions (109) |
| [`designs/b96_kr260_10g/model/loop_timing.py`](model/loop_timing.py) | Python model of the loop-timing frequency tracker (96F) |
| [`designs/b96_kr260_10g/regmap.py`](regmap.py) | register map as data |
| [`designs/b96_kr260_10g/docs/register_map.md`](docs/register_map.md) | interface datasheet |

<!-- prose:build -->
<!-- /prose:build -->

## Verified

![Verification matrix: each activity and its result](docs/handover/verification.svg)

| ID | Activity | Result | What | Evidence | Conditions |
|---|---|---|---|---|---|
| E1 | simulation | pass | PCS and MAC against an independent bit-serial Python model clock for clock; frames in lane 0 and lane 4, every length residue, any bit offset; the whole core with a stand-in for the GT: probe echo, trading loop, decisions, poisoned orders | [`designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py`](tests/test_b96_pcs_rtl.py) (run in CI) | - |
| E2 | build | pass | variant (b), the default build (RATE_MATCH = 0, the 97C receive path; rebuilt for brief 96C addendum 2), synthesis, implementation and bitstream on the Basic tier; every flow gate and every GT gate passes (29 of 29) | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) | - |
| E5 | formal | pass | the RATE_MATCH = 0 core is equivalent to main 6909e43f's core (eqy, slang front end, OSS CAD Suite; XPM crossings as wires, GT a black box, the 96C-only registers cut from the proof copy: see results/b96c/eqy_default/README.md); a planted change in the MAC error counter fails it | [`results/b96c/eqy_default/result_default.txt`](../../results/b96c/eqy_default/result_default.txt) | - |
| E6 | board | pass | the rate-matched builds (RATE_MATCH = 1, from f47986f4) on a KR260 optical loopback: safety accepted on all four variants (100 of 100 restarts locked, 500 of 500 orders sent = fired = order_ok per variant, every fault counter 0, SYSMON inside the DS925 windows); the TX phase-interpolator route gave no relative offset (0.0 ppm at every code; non-zero targets recorded unreachable), so rate matching under a real offset is not shown on hardware; the buffer costs 11 clocks of loop latency | [`results/b96c/hw/20261119_080724/control/stage3.json`](../../results/b96c/hw/20261119_080724/control/stage3.json) | KR260, SFP+ optical loopback, Vivado 2026.1 bitstreams of 2026-11-19, 100 restarts a variant, 20 s dwell at 0 ppm |
| E4 | build | pass | variant (a), the near-end loopback self-test, built before brief 96C and not rebuilt with the rate matcher: synthesis, implementation and bitstream; every flow gate and every GT gate passes | [`results/b96/build_a/gates.json`](../../results/b96/build_a/gates.json) | - |
| E3 | review | pass | one independent correctness review (Sonnet) and one fix round | [`results/b96/README.md`](../../results/b96/README.md) | - |
| E7 | simulation | pass | whole core in xsim with AMD's real XPM macros, four clock phases: tick-to-trade of the 97C path, of the xpm_fifo_async buffer and of the own gray-pointer buffer (RM_OWN = 1); the numbers and the accounting of the board's loop-latency increase are in design.md section 11 | [`results/b96e/core_lat_sim.json`](../../results/b96e/core_lat_sim.json) | - |
| E8 | build | pass | build rm_gp (RATE_MATCH = 1, RM_OWN = 1), all 29 gates, WNS +0.105 ns, WHS +0.011 ns, stamp 1a2fa1a8 recomputed from the tree; not loaded on a board | [`results/b96e/builds/rm_gp/digest.json`](../../results/b96e/builds/rm_gp/digest.json) | - |
| E9 | build | pass | build rm_gp_bypass (both GT buffers bypassed, brief 96F1), all 29 gates, WNS +0.090 ns, WHS +0.010 ns, report_cdc no critical, stamp b2a7aeea; not loaded on a board | [`results/b96f1/builds/rm_gp_bypass/digest.json`](../../results/b96f1/builds/rm_gp_bypass/digest.json) | - |
| E10 | simulation | pass | the Wizard's own buffer-bypass controllers with our run gate against a stand-in transceiver in xsim, 28 checks (start on the reset-done edge, stale done held off, error holds the paths in reset) | [`results/b96f1/bypass_seq/result.txt`](../../results/b96f1/bypass_seq/result.txt) | - |
| E11 | build | pass | build rm_gp_bypass rebuilt with the reset synchroniser and the alignment timeout and retry (brief 96F1b), all 29 gates, WNS +0.118 ns, WHS +0.010 ns, report_cdc no critical and no waivers, stamp 86037ce1; not loaded on a board; supersedes E9 | [`results/b96f1b/builds/rm_gp_bypass/digest.json`](../../results/b96f1b/builds/rm_gp_bypass/digest.json) | - |
| E12 | simulation | pass | gt_bp_ctl with the Wizard's own controllers against a stand-in transceiver in xsim (reset assert and release, normal start, retries, give-up, error not retried, clock inactive), plus the 28 checks of E10 unchanged; the whole core in three scenarios; the real 30 ms and 130 ms values | [`results/b96f1b/bypass_ctl/result.txt`](../../results/b96f1b/bypass_ctl/result.txt) | - |
| E13 | build | pass | build lat_all3_bypass (default receive path, 97C's three latency cuts, both GT buffers bypassed; brief 126), all 29 gates, WNS +0.066 ns, WHS +0.010 ns, report_cdc no critical, methodology no critical, stamp 9641284d; not loaded on a board | [`results/b126/builds/lat_all3_bypass/digest.json`](../../results/b126/builds/lat_all3_bypass/digest.json) | - |
| E14 | simulation | pass | the whole core of lat_all3_bypass in xsim with AMD's real XPM macros at four clock phases, with a stand-in transceiver with the bypass controllers' ports and the safety counters read back; 8 of 8 orders, every safety counter 0, the same digital tick-to-trade as lat_all3 within 0.1 clock; one retry recovers a hung alignment, a never-aligned link sends nothing | [`results/b126/core_sim/all3_bypass.json`](../../results/b126/core_sim/all3_bypass.json) | - |

Gates at handover: `build_2026_1` pass.

<!-- prose:verified -->
**Specification to evidence.** Every requirement of this design against the checks that cover it, with each status computed from the evidence files, the gaps and the stale evidence: [verif/matrix.md](verif/matrix.md) ([html](verif/matrix.html)), generated from [verif/testplan.yaml](verif/testplan.yaml) by `python -m flow.trace_v1 write`; schema and rules in [docs/traceability_v1.md](../../docs/traceability_v1.md). Requirements here are drafts written from the design documents; the matrix shows which are closed by simulation, formal proof, post-route timing or the board, and which depend on an external element (a network card, a second clock) that only hardware verification can close.
<!-- /prose:verified -->

## Measured

Every value is read from the record by `python -m flow.handover fill`, not typed.

| ID | What | Value | Runs | Source | Conditions |
|---|---|---|---|---|---|
| M1 | LUTs, variant (b) | 6167 LUT | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `utilization.lut` | routed, Vivado 2026.1 |
| M2 | registers, variant (b) | 14,183 FF | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `utilization.ff` | as M1 |
| M3 | worst setup slack, variant (b) | 0.221 ns | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `timing.wns_ns` | routed, user clocks 161.133 MHz and 100 MHz |
| M4 | worst hold slack, variant (b) | 0.011 ns | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `timing.whs_ns` | as M3 |
| M5 | total on-chip power estimate, variant (b) | 1.087 W | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `power.total_w` | report_power after routing, vectorless, confidence Medium |
| M6 | Vivado peak resident memory of the variant (b) build | 4439 MiB | 1 | [`results/b96c/builds/control/run.json`](../../results/b96c/builds/control/run.json) `vivado_peak_rss_mib` | 1 thread, MemoryMax=6G scope, one run, no cap hits |
| M7 | transmit latency, worst gearbox phase | 3 clocks | 1 | [`results/b96/latency_sim.json`](../../results/b96/latency_sim.json) `tx_clocks_max` | simulation, 161.13 MHz clock, MAC output register to the GT word with the last bit of the start block |
| M8 | digital tick-to-trade, worst simulated case with the rate matcher (RATE_MATCH = 1) | 13 clocks | 1 | [`results/b96c/core_sim.json`](../../results/b96c/core_sim.json) `tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks.max` | simulation, same-phase clocks, the Icarus stand-in of the FIFO macro; GT, optics and clock-crossing phase not included; the board measured 11 clocks more than 97C, see E6 and design.md section 9 |
| M10 | digital tick-to-trade, simulation of the default build (RATE_MATCH = 0, the 97C path) | 11 clocks | 1 | [`results/b96c/core_sim_default.json`](../../results/b96c/core_sim_default.json) `tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks` | simulation, same-phase clocks; as M8 |
| M9 | worst setup slack, latency variant all3 with the rate matcher (RATE_MATCH = 1) | 0.004 ns | 1 | [`results/b96c/builds/rm_all3/digest.json`](../../results/b96c/builds/rm_all3/digest.json) `timing.wns_ns` | as M3; the margin is thin |
| M11 | GT-port tick-to-trade in simulation with AMD's real macros, own gray-pointer buffer (RM_OWN = 1), mean over four phases at phase 1550 ps | 13 clocks | 1 | [`results/b96e/core_lat_sim.json`](../../results/b96e/core_lat_sim.json) `results.rate_match_1_rm_own_1.1550.tick_to_trade.mean` | xsim 2026.1, whole core, GT stand-in, phase 1550 ps between the clocks; the 97C path is 10.75 and the xpm_fifo_async buffer 16.0 at the same phase; the board has not measured this build |
| M12 | worst setup slack, build lat_all3_bypass (the 97C cuts with both GT buffers bypassed) | 0.066 ns | 1 | [`results/b126/builds/lat_all3_bypass/digest.json`](../../results/b126/builds/lat_all3_bypass/digest.json) `timing.wns_ns` | as M3 |
| M13 | GT-port tick-to-trade in simulation, build lat_all3_bypass, mean over four phases (the same as lat_all3 within 0.1 clock, because the stand-in has no GT buffers and the bypass's saving is not simulated) | 7.6 clocks | 1 | [`results/b126/core_sim/all3_bypass.json`](../../results/b126/core_sim/all3_bypass.json) `means_over_phases_clocks.rate_match_0_rm_own_0.tick_to_trade` | xsim 2026.1, whole core, GT stand-in with the bypass controllers' ports, four phases between the clocks |

<!-- prose:measured -->
<!-- /prose:measured -->

## Known gaps and limits

- **hardware**: The design has run on a KR260 optical loopback only (briefs 97 and 96C), never against a network card or a second reference clock, so rate matching (RATE_MATCH = 1) has not been seen under a real frequency offset; the TX phase-interpolator route gave none. The reference clock source and frequency, the 25 MHz input and the SFP+ control pin functions are unconfirmed against the schematic (third-party example).
- **interoperability**: The PCS and MAC are checked against a model written by the same author and against zlib and a recurrence; the standard text was not available, so only a network card proves the block formats and scrambler order.
- **simulation**: The transceiver is a behavioural stand-in because the free simulator refuses the real model; the whole-core bench uses same-phase clocks, so the receive-to-transmit crossing phase is not simulated.
- **trading path**: trade64 is a one-rule 64-bit stand-in, not the 58A core; orders that overlap are dropped; no cancel after send; the order fields cross as a quasi-static bus (CDC-6 warning).
- **protocol**: No link-fault state machine, BER monitor, ARP or ICMP responder; ordered sets are counted and shown as idles; receive does not check preamble, runts or jumbo frames; the transmit MAC does not pad.
- **throughput**: The line rate and the 10 Gb/s payload rate are by configuration and by the gearbox arithmetic; no throughput or error-rate measurement exists because nothing ran on a board.
- **build**: The 96C builds of the latency variant with the buffer (rm_all3) and its ppm twin hit the 6 GiB scope cap about 1000 times and used about 700 MiB of swap (the base build did not); the Vivado resident peak of the base build is 4439 MiB. all3 closes timing with 0.004 ns of setup slack, which is thin.
- **constraints**: The per-entry data path to the first synchroniser flop (write-clock entry flop to the first `xpm_cdc_array_single` flop) has no max-delay bound: the one-clock margin of `ENT_SYNC = 1` covers normal routing, but it is not constrained.
- **ml stage**: Build rm_gp_ml (the ML decision stage behind the rule, brief 113) has not run on a board; its board test is pre-registered in results/b113/preregistration.md and the owner's script is written. The stage tracks one instrument with a top-of-book and sees the first message of a frame only; the model is brief 87's trees on one planted-signal data set.

<!-- prose:gaps -->
<!-- /prose:gaps -->

## Next steps

1. Run _handoff/fpga_agent/run_96f1_stage1.sh on the KR260 (pre-registered in results/b96f1/preregistration.md, amendment 2026-11-20), build rm_gp_bypass (stamp 86037ce1, brief 96F1b) against the 96E rm_gp board run; read the retry counts and gave-up flags.
2. Run docs/board_run_plan.md steps 1 to 4 on the KR260 (laser polarity first), then the NIC steps after the owner buys a card and cable.
3. Confirm the reference clock and the control pins against the carrier schematic.
4. Widen the 58A core to 64 bits, or add the missing 58A features to trade64.

Open questions:

- Does the PL load over JTAG with the PS idle on the KR260 (flow/program.py has no KR260 board entry yet)?

<!-- prose:next -->
<!-- /prose:next -->

## History

| Date | Brief | PR | What |
|---|---|---|---|
| 2026-11-21 | - | - | brief 126: build lat_all3_bypass (the default receive path, the 97C latency cuts and the GT buffer bypass together), all 29 gates, WNS +0.066 ns, report_cdc no critical; simulated in xsim; board test pre-registered from the two measured runs (E 16.0, L 38.0, D 6.0, tick-to-trade 22 clocks) and script written; nothing run on a board |
| 2026-11-20 | - | - | brief 96F1b: build rm_gp_bypass with AMD-style synchronised controller reset and a 30 ms TX / 130 ms RX alignment timeout with 3 retries then a gave-up flag (GT_BUF bits 29:16); all 29 gates, timing met, report_cdc no critical; gave-up added as a fail line before any board time; nothing run on a board |
| 2026-11-20 | - | - | brief 123: pyuvm bench for the PCS and MAC (designs/b96_kr260_10g/verif/pyuvm) with the same tests, bugs and coverage bins as brief 112, run in Icarus; same verification result, measured comparison and recommendation in COMPARISON.md; no RTL change |
| 2026-11-20 | - | - | brief 112: UVM 1.2 bench for the PCS and MAC (designs/b96_kr260_10g/verif/uvm): agents, reference models, scoreboard, coverage, SVAs, regression and seeded bugs, in xsim 2026.1; no RTL bug found; xcrg refused on the Basic tier |
| 2026-11-20 | - | - | brief 96F1: build rm_gp_bypass (both GT elastic buffers bypassed; Wizard probe in results/b96f1/wizard_probe), all 29 gates, timing met, report_cdc no critical; board test pre-registered and script written, nothing run on a board |
| 2026-11-19 | - | - | brief 96E: own gray-pointer elastic buffer (RM_OWN), +1.2 clocks of tick-to-trade over 97C in xsim against +5.3 for the macro buffer; the board's +11 accounted (1.25 left in D); build rm_gp with all 29 gates; board run and real-offset plan pending the owner |
| 2026-11-19 | - | - | brief 96D: on-chip RX eye scan (EYESCAN build option, es_ctrl, flow/eyescan); built with all 29 gates; simulated against a stand-in; not yet run on the board |
| 2026-11-19 | - | - | brief 96C addendum 2: RATE_MATCH build parameter, default 0 (the 97C path, shown equivalent by eqy and the 97C bench); the board measured the buffer at +11 clocks and no relative offset by the TX phase interpolator |
| 2026-11-19 | - | - | brief 96C: elastic-buffer rate matcher (xpm_fifo_async) in the base design and lat_all3, TX phase-interpolator ppm controls, four builds with all 29 gates, board session pending |
| 2026-11-17 | - | - | brief 96 stages 0 to 2: board facts, design note, PCS, MAC, trading path, host code, builds; one review round |

<!-- prose:history -->
<!-- /prose:history -->
