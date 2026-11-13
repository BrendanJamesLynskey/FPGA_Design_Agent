# AGENT b2_acl_adxl362 (fda-handover/1)
source: designs/b2_acl_adxl362/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b2_acl_adxl362

## identity
kind=board-selfcheck produced_by=human part=xc7a100tcsg324-1 board=Nexys A7-100T top=b2_acl_adxl362_top tool=Vivado 2026.1

## summary
Drives the Nexys A7's ADXL362 accelerometer over SPI mode 0 at 1 MHz from a small register block in the test shell. The host reads the three ID registers, switches the part to measurement mode, reads one X/Y/Z sample at rest, returns it to standby and reads POWER_CTL back. `selfcheck.py` holds the on-board pass rule, written before any board run.
not: an accelerometer application: it takes one sample per check, so it says nothing about noise, offsets, other ranges or interrupts; an agent benchmark task; it was written by hand to prove the board inventory on hardware

## state
stage=board-verified vivado=2026.1 kb_pin=1fc7ed8 build_id=97949768
gates: build_2026_1=pass board_selfcheck=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the board's reset button, synchronised by the test shell's reset synchroniser (assert asynchronous, release synchronous)
if UART register window test shell, 8N1 UART at 115200 baud: seven registers at shell addresses 0x80 to 0x86 (CTRL, STATUS, TX0, TX1, RX0, RX1, INFO); the map is in the header of rtl/acl_regs.sv; other window addresses read 0, and writes to STATUS, RX0, RX1, INFO or undefined addresses are ignored doc=shell/PROTOCOL.md
if ADXL362 SPI ACL_SCLK, ACL_MOSI, ACL_CSN out and ACL_MISO in, mode 0 (CPOL 0, CPHA 0), MSB first, LVCMOS33: one transfer is chip select low, 1 to 8 bytes out from TX0 and TX1 (byte 0 first) with the same number of bytes captured into RX0 and RX1, then chip select high; MISO is sampled at the end of each SCLK high half; INT1 and INT2 are not connected doc=boards/nexys_a7_100t/inventory.yaml
param HALF=50 legal=1 to 65535 (16-bit divider); the board value is 50
param CLKS_PER_BIT=868 legal=set by the shell's UART; the board value is 868

## files
designs/b2_acl_adxl362/rtl/spi_burst.sv 37b7defb72: SPI mode-0 master, 1 to 8 bytes per transfer
designs/b2_acl_adxl362/rtl/acl_regs.sv 6496778f1f: the registers in the shell window, with the register map in its header
designs/b2_acl_adxl362/rtl/b2_acl_adxl362_top.sv b8ae5fc066: board top (test shell, MISO synchroniser and the register block)
designs/b2_acl_adxl362/design.xdc 4cff2d7d30: pins, the 100 MHz clock and the false paths on the asynchronous inputs and slow outputs
designs/b2_acl_adxl362/build.yaml 0798052fac: how flow/run_vivado.sh builds the design
designs/b2_acl_adxl362/selfcheck.py 21453cdc1f: the on-board check and its pass rule (docstring), pre-registered before any board run
designs/b2_acl_adxl362/tests/acl_cocotb.py 108c8f737c: cocotb tests against an ADXL362 model (commands 0x0A and 0x0B, address auto-increment, transfer lengths 1 to 8, a mode-0 check)
designs/b2_acl_adxl362/tests/test_acl_rtl.py 7231f6afad: pytest entry that runs the cocotb tests with Icarus Verilog at HALF 4

## commands
simulate against the ADXL362 model (~1min): python3 -m pytest -q designs/b2_acl_adxl362/tests/test_acl_rtl.py
[heavy] build and run the gates (~4min): flow/run_vivado.sh designs/b2_acl_adxl362 base
power gate, program SRAM, self-check, three times (~2min): python3 flow/board_check.py designs/b2_acl_adxl362 --runs 3

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b2_acl_adxl362/tests/test_acl_rtl.py 7231f6afad
R2 results/vivado_2026_1_remeasure/b2_builds.json 2ab9aafe7a
R3 results/board_v2/b2_acl_adxl362.json a9dff9119f

## evidence
E1 simulation pass R1 ci: register-level tests against an ADXL362 model, including the ID, measurement and standby sequence and transfer lengths 1 to 8
E2 build pass R2: whole-board build on Vivado 2026.1; every gate passes (built, not programmed)
E3 board pass x3 R3: three self-check runs on the board, from a clean committed tree; each passes the pre-registered rule (IDs AD 1D F2, magnitude inside the range, POWER_CTL back to 0) | cond: wall power; the power gate (report_power total and junction temperature against the 2.0 W and 85 C limits) passed before programming; XADC rails and die temperature were not read during these runs; the board's orientation was not recorded

## measured
M1 resources lut=729 LUT R2#builds.b2_acl_adxl362.lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1, xc7a100tcsg324-1, including the test shell
M2 resources ff=577 FF R2#builds.b2_acl_adxl362.ff: flip-flops, whole board design | routed whole-board build, Vivado 2026.1, including the test shell
M3 timing wns_ns=3.335 ns R2#builds.b2_acl_adxl362.wns_ns: worst setup slack | routed, at the 100 MHz board clock
M4 timing whs_ns=0.122 ns R2#builds.b2_acl_adxl362.whs_ns: worst hold slack | ditto
M5 power power_w=0.116 W R2#builds.b2_acl_adxl362.power_w: total on-chip power estimate | report_power after routing, vectorless (default toggle rates), the board's thermal environment
M6 board -=1.018 g R3#results[0].steps.selfcheck.magnitude_g: acceleration magnitude at rest, first recorded run | default range and 100 Hz output rate, 100 ms after the mode write; board orientation not recorded; pass range 0.57 to 1.43 g
M7 board -=0x02 R3#results[0].steps.selfcheck.revid: REVID register, first recorded run | recorded, not judged by the pass rule

## gaps
[latency] Not measured. A transfer takes eight SCLK periods per byte plus set-up and hold half periods at 1 MHz by construction; no record times it.
[throughput] Not applicable; the block moves at most 8 bytes per host request and the check takes one sample per run.
[E3] The board runs used bitstreams built on the earlier Vivado release; the 2026.1 build (E2) was not programmed. Re-run the board check on a 2026.1 bitstream to close this.
[operating conditions] The board runs predate the 2026-11-11 rule; die temperature and the VCCINT, VCCAUX and VCCBRAM rails were not read from the XADC, so the runs cannot be shown to be inside the recommended operating conditions.
[accuracy] The pass range for the magnitude is wide (0.57 to 1.43 g) because it must hold at any board tilt with worst-case offsets; the check does not calibrate or test offsets, noise, other ranges, the FIFO or the interrupt pins.
[REVID] The data sheet value quoted in selfcheck.py is 0x01 but the board returned a different value in all three runs (M7); the rule does not judge it, and no record explains the difference.
[behaviour] GO written while a transfer runs is ignored (spi_burst.sv takes GO only when idle), but no test covers it; a CTRL write changes the byte count register at once, though the running transfer keeps the count it started with; TX0 and TX1 writes during a transfer do not change that transfer; RX0 and RX1 hold the previous transfer's bytes until the transfer ends and are not cleared by a new one until then; a byte count of 0 is sent as 1 and above 8 as 8; bytes beyond the count read as 0; reads of undefined addresses return 0 with no error.
[reset] Reset clears the transmit data, sets the byte count to 1, and clears busy and done; the received bytes are cleared too. This design drives no reset signal to the sensor, so a reset between the measurement-mode write and the standby write leaves the part in measurement mode.

## next_actions
1. Re-run the board check on a Vivado 2026.1 bitstream with the XADC read at the start and end of each run.
2. Add a test for GO written while busy and state in the register map header that it is ignored.
3. Record the board orientation with each run so the magnitude can be compared with the expected 1 g more tightly.

## open_questions
- Should REVID be judged once the revision on the board is confirmed against the data sheet?

## history
2026-10-31 04c pr=-: written with the board inventory, power budget and power gate; 3 of 3 board runs pass
2026-11-11 49 pr=-: rebuilt on Vivado 2026.1; every gate passes (not programmed)
2026-11-13 68 pr=-: handover written to the documentation standard
