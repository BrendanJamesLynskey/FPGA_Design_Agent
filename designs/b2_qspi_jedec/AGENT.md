# AGENT b2_qspi_jedec (fda-handover/1)
source: designs/b2_qspi_jedec/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b2_qspi_jedec

## identity
kind=board-selfcheck produced_by=human part=xc7a100tcsg324-1 board=Nexys A7-100T top=b2_qspi_jedec_top tool=Vivado 2026.1

## summary
Reads the JEDEC ID of the Nexys A7's configuration flash (S25FL128S or S25FL127S) with the RDID command (9Fh) over single-bit SPI at 1 MHz, with SCK leaving through STARTUPE2. The 8-byte ID is read twice and compared with the data sheets' values. The opcode is a constant in the RTL, so the design cannot send a write, erase or register-write command. `selfcheck.py` holds the on-board pass rule, written before any board run.
not: a flash memory test: it reads only the ID, so it says nothing about the flash contents, erase, program or quad-mode operation; an agent benchmark task; it was written by hand to prove the board inventory on hardware

## state
stage=board-verified vivado=2026.1 kb_pin=1fc7ed8 build_id=ac857e6b
gates: build_2026_1=pass board_selfcheck=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the board's reset button, synchronised by the test shell's reset synchroniser (assert asynchronous, release synchronous)
if UART register window test shell, 8N1 UART at 115200 baud: five registers at shell addresses 0x80 to 0x84 (CTRL, STATUS, ID0, ID1, INFO); the map is in the header of rtl/qspi_regs.sv; other window addresses read 0, and a write to any address but CTRL, or to CTRL without bit 0, starts nothing doc=shell/PROTOCOL.md
if Configuration flash (single-bit SPI) QSPI_CSN, QSPI_DQ0 (to the flash) out, QSPI_DQ1 (from the flash) in, SCK through STARTUPE2, LVCMOS33: one transfer is chip select low, opcode 9Fh, eight ID bytes read, chip select high; QSPI_DQ2 (WP#) is held low and QSPI_DQ3 (HOLD#) high; the first transfer after reset is preceded by PREAMBLE clock pulses with chip select high because STARTUPE2 swallows the first edges after configuration doc=boards/nexys_a7_100t/inventory.yaml
param HALF=50 legal=1 to 65535 (16-bit divider); the board value is 50
param PREAMBLE=8 legal=0 to 255 clock pulses; the board value is 8
param CLKS_PER_BIT=868 legal=set by the shell's UART; the board value is 868

## files
designs/b2_qspi_jedec/rtl/qspi_rdid.sv 0a99319701: the RDID-only reader with a constant opcode 9Fh, eight ID bytes, the clock preamble for STARTUPE2
designs/b2_qspi_jedec/rtl/qspi_regs.sv 54e88e7824: the registers in the shell window, with the register map in its header
designs/b2_qspi_jedec/rtl/b2_qspi_jedec_top.sv 0b04adcaaa: board top (test shell, STARTUPE2, WP# and HOLD# levels, input synchroniser and the register block)
designs/b2_qspi_jedec/lint/STARTUPE2.sv cb4b1333b4: lint-only stand-in for the primitive; synthesis never reads it
designs/b2_qspi_jedec/design.xdc dbf0baeb0e: pins, the 100 MHz clock and the false paths on the asynchronous inputs and slow outputs
designs/b2_qspi_jedec/build.yaml b1de6d913a: how flow/run_vivado.sh builds the design
designs/b2_qspi_jedec/selfcheck.py cae1cf5de3: the on-board check and its pass rule (docstring), pre-registered before any board run
designs/b2_qspi_jedec/verif/fsm.yaml fcedfa2c6a: the state table of the reader, read by the FSM coverage check
designs/b2_qspi_jedec/tests/test_qspi_rtl.py 8e33f960db: source checks (9Fh is the only opcode; no write, erase or register-write opcode literal; no multi-bit input to the reader) and the pytest entry for the simulation
designs/b2_qspi_jedec/tests/qspi_cocotb.py 3c857fcb4d: cocotb tests against a flash model that decodes every command it receives

## commands
source checks and simulation against the flash model (~1min): python3 -m pytest -q designs/b2_qspi_jedec/tests/test_qspi_rtl.py
[heavy] build and run the gates (~4min): flow/run_vivado.sh designs/b2_qspi_jedec base
power gate, program SRAM, self-check, three times (~2min): python3 flow/board_check.py designs/b2_qspi_jedec --runs 3

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b2_qspi_jedec/tests/test_qspi_rtl.py 8e33f960db
R2 results/vivado_2026_1_remeasure/b2_builds.json 2ab9aafe7a
R3 results/board_v2/b2_qspi_jedec.json 57e6c720d3

## evidence
E1 simulation pass R1 ci: source checks that 9Fh is the only opcode and that no write, erase or register-write opcode literal exists, and a flash model that records every command, which must be only RDID, even after writes of every bit pattern to every window offset
E2 build pass R2: whole-board build on Vivado 2026.1; every gate passes (built, not programmed)
E3 board pass x3 R3: three self-check runs on the board, from a clean committed tree; each reads the same 8 ID bytes twice and passes the pre-registered rule (bytes 0 to 2 and byte 5 as expected) | cond: wall power; the power gate (report_power total and junction temperature against the 2.0 W and 85 C limits) passed before programming; XADC rails and die temperature were not read during these runs

## measured
M1 resources lut=447 LUT R2#builds.b2_qspi_jedec.lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1, xc7a100tcsg324-1, including the test shell
M2 resources ff=458 FF R2#builds.b2_qspi_jedec.ff: flip-flops, whole board design | routed whole-board build, Vivado 2026.1, including the test shell
M3 timing wns_ns=4.278 ns R2#builds.b2_qspi_jedec.wns_ns: worst setup slack | routed, at the 100 MHz board clock
M4 timing whs_ns=0.075 ns R2#builds.b2_qspi_jedec.whs_ns: worst hold slack | ditto
M5 power power_w=0.117 W R2#builds.b2_qspi_jedec.power_w: total on-chip power estimate | report_power after routing, vectorless (default toggle rates), the board's thermal environment
M6 board -=01 20 18 4d 01 80 30 30 R3#results[0].steps.selfcheck.id: the 8 ID bytes read from the flash, first recorded run | RDID at 1 MHz SCK; bytes 3, 4, 6 and 7 are recorded, not judged; the pass rule judges bytes 0 to 2 and byte 5

## gaps
[latency] Not measured. A transfer is 72 SCK periods at 1 MHz by construction, plus the one-time preamble after reset; no record times it.
[throughput] Not applicable; the block reads one 8-byte ID per host request.
[E3] The board runs used bitstreams built on the earlier Vivado release; the 2026.1 build (E2) was not programmed. Re-run the board check on a 2026.1 bitstream to close this.
[operating conditions] The board runs predate the 2026-11-11 rule; die temperature and the VCCINT, VCCAUX and VCCBRAM rails were not read from the XADC, so the runs cannot be shown to be inside the recommended operating conditions.
[part identity] The pass rule accepts both flash parts the board may carry. The record shows the bytes read but not which of the two parts is fitted, because the model-number bytes are recorded, not judged.
[behaviour] GO written while a transfer runs is ignored (qspi_rdid.sv takes GO only when idle), but no test covers it. The ID registers keep the previous transfer's bytes until a new transfer ends, and are cleared only by reset. CTRL reads 0. Only bit 0 of CTRL means anything. The first transfer after reset takes longer because of the preamble, and a reset repeats it. Reads of undefined addresses return 0 with no error.
[flash safety] Nothing was run that tries to make the flash accept a write; the claim that it cannot rests on the source checks and the flash model in E1, not on a board test, and WP# is held low as a second guard.

## next_actions
1. Re-run the board check on a Vivado 2026.1 bitstream with the XADC read at the start and end of each run.
2. Add a test for GO written while busy and state in the register map header that it is ignored.
3. Judge the model-number bytes once the part fitted to the board is known, to tell the two parts apart.

## open_questions
- Should the self-check read the JEDEC ID again at a faster SCK, to find the fastest clock the board's layout supports?

## history
2026-10-31 04c pr=-: written with the board inventory, power budget and power gate; 3 of 3 board runs pass
2026-11-11 49 pr=-: rebuilt on Vivado 2026.1; every gate passes (not programmed)
2026-11-13 68 pr=-: handover written to the documentation standard
