# AGENT b2_tmp_adt7420 (fda-handover/1)
source: designs/b2_tmp_adt7420/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b2_tmp_adt7420

## identity
kind=board-selfcheck produced_by=human part=xc7a100tcsg324-1 board=Nexys A7-100T top=b2_tmp_adt7420_top tool=Vivado 2026.1

## summary
Reads the Nexys A7's ADT7420 temperature sensor over I2C (address 0x4B, 100 kHz) from a small register block in the test shell. The host reads the ID register and the temperature, and the pass rule checks the ID, that no byte was not acknowledged and that the temperature is plausible. The design only sets the register pointer and reads, so it cannot change the sensor's configuration. `selfcheck.py` holds the on-board pass rule, written before any board run.
not: a temperature measurement: the pass range (10 to 40 C) only shows the sensor answers with a plausible value, not that it is accurate; an agent benchmark task; it was written by hand to prove the board inventory on hardware

## state
stage=board-verified vivado=2026.1 kb_pin=1fc7ed8 build_id=75af5be3
gates: build_2026_1=pass board_selfcheck=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the board's reset button, synchronised by the test shell's reset synchroniser (assert asynchronous, release synchronous)
if UART register window test shell, 8N1 UART at 115200 baud: four registers at shell addresses 0x80 to 0x83 (CTRL, STATUS, RDATA, INFO); the map is in the header of rtl/tmp_regs.sv; other window addresses read 0, and writes to any address but CTRL are ignored doc=shell/PROTOCOL.md
if ADT7420 I2C TMP_SCL and TMP_SDA, open drain with the board's pull-ups, LVCMOS33: START, address and write, pointer byte, repeated START, address and read, one or two bytes, STOP; the master waits while the device stretches SCL; a byte that is not acknowledged sets nack and the transfer ends with a STOP doc=boards/nexys_a7_100t/inventory.yaml
param QUARTER=250 legal=1 to 65535 (16-bit divider); the board value is 250
param DEV_ADDR=75 legal=7-bit address; the board value is 0x4B (75)
param CLKS_PER_BIT=868 legal=set by the shell's UART; the board value is 868

## files
designs/b2_tmp_adt7420/rtl/i2c_ptr_read.sv 59cc6685aa: I2C master that sets a register pointer then reads one or two bytes; it never writes a data byte
designs/b2_tmp_adt7420/rtl/tmp_regs.sv 6eb149b903: the registers in the shell window, with the register map in its header
designs/b2_tmp_adt7420/rtl/b2_tmp_adt7420_top.sv d517769e4f: board top (test shell, open-drain pins, line synchroniser and the register block)
designs/b2_tmp_adt7420/design.xdc 84ced0fed6: pins, the 100 MHz clock and the false paths on the asynchronous inputs and slow outputs
designs/b2_tmp_adt7420/build.yaml 629b82eb19: how flow/run_vivado.sh builds the design
designs/b2_tmp_adt7420/selfcheck.py 1cb403454f: the on-board check and its pass rule (docstring), pre-registered before any board run
designs/b2_tmp_adt7420/verif/fsm.yaml 7993de31e5: the state table of the I2C engine, read by the FSM coverage check
designs/b2_tmp_adt7420/tests/tmp_cocotb.py 421b81e94f: cocotb tests against an ADT7420 model that loses its pointer on a STOP, NACKs a wrong address and stretches SCL
designs/b2_tmp_adt7420/tests/test_tmp_rtl.py 9e86a9ff6b: pytest entry that runs the cocotb tests with Icarus Verilog

## commands
simulate against the ADT7420 model (~1min): python3 -m pytest -q designs/b2_tmp_adt7420/tests/test_tmp_rtl.py
[heavy] build and run the gates (~4min): flow/run_vivado.sh designs/b2_tmp_adt7420 base
power gate, program SRAM, self-check, three times (~2min): python3 flow/board_check.py designs/b2_tmp_adt7420 --runs 3

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b2_tmp_adt7420/tests/test_tmp_rtl.py 9e86a9ff6b
R2 results/vivado_2026_1_remeasure/b2_builds.json 2ab9aafe7a
R3 results/board_v2/b2_tmp_adt7420.json ddf2c0fb48

## evidence
E1 simulation pass R1 ci: register-level tests against an ADT7420 model; ID and temperature reads, a wrong address is not acknowledged and the bus is released, clock stretching, repeated one and two byte reads, and no data byte is ever written to the sensor
E2 build pass R2: whole-board build on Vivado 2026.1; every gate passes (built, not programmed)
E3 board pass x3 R3: three self-check runs on the board, from a clean committed tree; each passes the pre-registered rule (ID 0xCB with no NACK, temperature inside the range) | cond: wall power; the power gate (report_power total and junction temperature against the 2.0 W and 85 C limits) passed before programming; XADC rails and die temperature were not read during these runs; no reference thermometer was used

## measured
M1 resources lut=413 LUT R2#builds.b2_tmp_adt7420.lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1, xc7a100tcsg324-1, including the test shell
M2 resources ff=341 FF R2#builds.b2_tmp_adt7420.ff: flip-flops, whole board design | routed whole-board build, Vivado 2026.1, including the test shell
M3 timing wns_ns=4.08 ns R2#builds.b2_tmp_adt7420.wns_ns: worst setup slack | routed, at the 100 MHz board clock
M4 timing whs_ns=0.122 ns R2#builds.b2_tmp_adt7420.whs_ns: worst hold slack | ditto
M5 power power_w=0.116 W R2#builds.b2_tmp_adt7420.power_w: total on-chip power estimate | report_power after routing, vectorless (default toggle rates), the board's thermal environment
M6 board -=18.875 C R3#results[0].steps.selfcheck.temperature_c: temperature read from the sensor, first recorded run | 13-bit power-on mode, 0.0625 C a step; room temperature not recorded; pass range 10 to 40 C
M7 board -=0xCB R3#results[0].steps.selfcheck.id: ID register value, first recorded run | register 0x0B read with no NACK; the pass rule requires 0xCB

## gaps
[latency] Not measured. A read takes nine bit periods for each of the address, pointer and address-read bytes plus nine for each data byte at 100 kHz by construction; no record times it.
[throughput] Not applicable; the block moves one or two bytes per host request.
[E3] The board runs used bitstreams built on the earlier Vivado release; the 2026.1 build (E2) was not programmed. Re-run the board check on a 2026.1 bitstream to close this.
[operating conditions] The board runs predate the 2026-11-11 rule; die temperature and the VCCINT, VCCAUX and VCCBRAM rails were not read from the XADC, so the runs cannot be shown to be inside the recommended operating conditions.
[accuracy] The temperature was not compared with a reference, and the room temperature was not recorded; the range check shows the sensor answers plausibly, not that the reading is accurate. Only the 13-bit power-on mode is decoded.
[behaviour] GO written while a transfer runs is ignored (i2c_ptr_read.sv takes GO only when idle), but no test covers it. A CTRL write while a transfer runs still changes the pointer and byte-count registers; the engine loads the pointer byte after the address is acknowledged, so a write before that point changes the pointer sent, while the byte count is taken at GO. A byte count other than 2 reads one byte. After a NACK the transfer ends with a STOP, nack stays set until the next GO and RDATA is 0. A 2-byte read puts the first byte in bits 15 to 8. STATUS and RDATA reads of undefined addresses return 0 with no error.
[reset] Reset clears the registers, DONE, NACK and the pointer, and releases both I2C lines. A reset in the middle of a transfer releases the lines at once without a STOP, which can leave a device mid-byte.

## next_actions
1. Re-run the board check on a Vivado 2026.1 bitstream with the XADC read at the start and end of each run.
2. Add tests for GO written while busy and for a CTRL write during a transfer, and state the behaviour in the register map header.
3. Compare the temperature with a reference thermometer once, and record the room temperature.

## open_questions
- Should the 16-bit (high resolution) configuration be supported, which would need a configuration write that this design deliberately cannot do?

## history
2026-10-31 04c pr=-: written with the board inventory, power budget and power gate; 3 of 3 board runs pass
2026-11-11 49 pr=-: rebuilt on Vivado 2026.1; every gate passes (not programmed)
2026-11-13 68 pr=-: handover written to the documentation standard
