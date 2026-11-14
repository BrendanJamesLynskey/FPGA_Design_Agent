# AGENT b59a_axi_tx (fda-handover/1)
source: designs/b59a_axi_tx/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b59a_axi_tx

## identity
kind=showcase produced_by=human part=xc7a100tcsg324-1 board=Nexys A7-100T top=b59a_axi_tx_top tool=Vivado 2026.1

## summary
Board demonstration of an on-chip AXI4-Lite and AXI4-Stream traffic generator, protocol checker and scoreboard. A program loaded over the UART shell drives a vendor block-RAM controller or our own peripheral and stream FIFO, which carry run-time seeded bugs. Ten AXI4-Lite and five AXI4-Stream rules are watched and counted, a capture records the bus around the first violation, and AMD's AXI Protocol Checker watches the same AXI4-Lite bus as a cross-check.
not: full AXI4 (bursts, IDs, several transactions in flight), a slave side, a DMA target or a soak mode; a hunt for bugs in a third-party core; the peripheral, the FIFO and their bugs are ours and deliberately simple

## state
stage=board-verified vivado=2026.1 kb_pin=20d73e8 build_id=55b4d5dd
gates: build_2026_1=pass board_plan=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the reset button, synchronised; the host can hold the targets' ARESETn low through SYS_CTRL bit 12
if UART register window test shell, 8N1 UART at 115200 baud: shell addresses 0x80-0xFF; offsets 0x00-0x3F transactor (axi_tx/host/regs.py), 0x40-0x4C XADC, 0x50-0x55 AMD checker status; other offsets read 0 doc=shell/PROTOCOL.md
if Transactor, checker and scoreboard AXI4-Lite master with monitors; AXI4-Stream source and sink: program format, rules, counters, capture; one AXI4-Lite transaction outstanding, 32-bit stream data doc=docs/axi_tx.md
if Target 0 (board) AMD AXI BRAM Controller 4.1 with Block Memory Generator 8.4, AXI4-Lite: 8 KB; only address bits 12:0 reach it, so a higher address wraps rather than errors doc=docs/axi_tx.md
if Target 1 (board) axil_demo_periph, AXI4-Lite: ID, R0-R3, COUNT, WCOUNT, BUG; write to a read-only register answers SLVERR; address 0x20 up answers DECERR (reads 0); AxPROT ignored doc=docs/axi_tx.md
param CLKS_PER_BIT=868 legal=positive integer; 868 gives 115200 baud
param SDATA_W=32 legal=32 only
param program RAM=256 instructions of four 32-bit words legal=loops nest 4 deep

## files
designs/b59a_axi_tx/rtl/b59a_axi_tx_top.sv 4d042b962a: board top
designs/b59a_axi_tx/design.xdc 62d07a8525: pins and clock
designs/b59a_axi_tx/ip/amd_ip.tcl 13744aab59: creates the AMD IP (hash-listed in flow/ip_tcl_allow.yaml)
docs/axi_tx.md 6cd2f9dcfc: interface datasheet
axi_tx/tests/test_59a_rtl.py 0ad2ec372f: cocotb tests
axi_tx/programs/board_plan.yaml e56a3dcaeb: pre-registered board plan

## commands
simulate every program, seeded bug and memory fault (~1min): python -m pytest -q axi_tx/tests/test_59a_rtl.py
formal proofs and checker mutants to depth 20 (~19min): python axi_tx/formal/run_formal.py --depth 20
[heavy] build the board design (~12min): flow/run_vivado.sh designs/b59a_axi_tx base
run the board plan (~8min): python3 axi_tx/host/run_board.py --plan axi_tx/programs/board_plan.yaml --json results/59a_axi_tx/board_run.json

## records (path sha256-prefix; claims below cite R<n>)
R1 axi_tx/tests/test_59a_rtl.py 0ad2ec372f
R2 results/59a_axi_tx/formal.json 1e66e6a1b0
R3 results/59a_axi_tx/false_fire.json 5202b17824
R4 results/59a_axi_tx/board_build.json 0a91499e62
R5 results/59a_axi_tx/board_run.json ab761ea3ea
R6 results/59a_axi_tx/summary.json 25f8f05aa0

## evidence
E1 simulation pass R1 ci: cocotb on Icarus: clean runs fire no rule, each seeded bug fires its rule, a WSTRB-ignoring memory is caught by the scoreboard
E2 formal pass R2: SymbiYosys to depth 20: rules quiet on legal traffic, fire alone on their violation; every checker mutant fails a proof
E3 faults pass R3: 11 legal but unusual scenarios; no rule fired
E4 build pass R4: whole-board build, Basic tier; every gate passes
E5 board pass x17 R5: pre-registered plan on the final bitstream, clean commit; each verdict as planned | cond: wall power; power gate before programming; JTAG XADC before and after, fabric XADC after every run, inside the operating conditions; JTAG build ID matched; fast supply droop not seen

## measured
M1 resources lut=7043 LUT R4#utilization.lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1
M2 resources ff=7308 FF R4#utilization.ff: flip-flops, whole board design | as M1
M3 timing wns_ns=0.169 ns R4#timing.wns_ns: worst setup slack | routed, 100 MHz clock
M4 timing whs_ns=0.035 ns R4#timing.whs_ns: worst hold slack | ditto
M5 power power_w=0.185 W R4#power.total_w: total on-chip power estimate | report_power after routing, vectorless, confidence Medium
M6 latency write_min=2 clocks R6#bram_write_latency_min: minimum AXI4-Lite write latency to the block-RAM target | one run (bram_random_rw) on the board; clocks as counted by axil_mon
M7 latency write_max=12 clocks R6#bram_write_latency_max: maximum AXI4-Lite write latency to the block-RAM target | as M6; includes injected back-pressure
M8 latency read_min=1 clocks R6#bram_read_latency_min: minimum AXI4-Lite read latency to the block-RAM target | as M6
M9 latency read_max=8 clocks R6#bram_read_latency_max: maximum AXI4-Lite read latency to the block-RAM target | as M7
M10 board -=17 runs R6#runs_pass: board runs that passed | of 17 planned runs, one bitstream (44b780c9)
M11 board -=13 runs R6#parity_digest_equal: runs against our own peripheral and FIFO whose digest and cycle count equal the simulation's | of 13 such runs; 0 differences in logged transactions
M12 board -=5 runs R6#amd_asserted: runs on which AMD's checker asserted, all of them runs on which ours flagged an AXI4-Lite rule | AXI4-Lite only; its status bits not decoded to rule names
M13 verification -=32 proofs R6#formal_proofs_pass: formal proofs passed | of 32, depth 20, Yosys 0.33
M14 verification -=53 mutants R6#formal_mutants_killed: checker mutants killed by at least one proof | of 53 (17 semantic), depth 12
M15 verification -=0 scenarios R3#re: false-alarm scenarios that fired a rule | of 11 scenarios, simulation

## gaps
[throughput] Not measured as a data rate; the records give transaction counts and latencies, not bytes per second on either bus.
[latency] Latency is from one run (bram_random_rw) with random back-pressure; none for the peripheral target or without back-pressure.
[E3] The 11 scenarios were chosen by the checker's author; they show those legal cases are quiet, not that no legal traffic can fire a rule.
[amd_ip] The AMD IP build test (amd_ip_probe.json) shows the five cores build on Vivado 2026.1 without a licence; the AMD traffic generator and stream checker were not used on the board.
[verification] Proofs are bounded to 20 cycles and the properties were written by the checker's author; AMD's checker agreeing on hardware is the independent evidence. The clean Verilator lint run has no record in results/.
[board] BRAM-target runs are compared with a transaction-level model, not with simulation cycle for cycle (Icarus cannot run the AMD core); block RAM keeps contents across runs, so unwritten words are unknown to the model.
[build identity] Board evidence is tied to commit e562dd3 (build ID 44b780c9); later commits changed build inputs, not logic, so the current tree has another build ID and no rebuild or board re-run was made.
[operating conditions] The XADC samples about 1 MSPS with alarms latched between reads, so a shorter supply droop is not seen.
[behaviour] Guessable wrongly (RTL and docs/axi_tx.md): the target select is a static mux, change it only while no program runs; rules 0-8 are not evaluated while ARESETn is low; a READY-to-VALID path shows only as a VALID that drops or changes; outstanding counts saturate at 255; a read of an unwritten word counts as unchecked, not matched; whether a write to an unlisted window offset is ignored was not checked.
[scope] One AXI4-Lite transaction in flight, no IDs, bursts, slave side or soak mode; stream data 32-bit only; AMD's checker does not watch the stream.
[readout speed] A board run reads every counter and the log over 115200-baud UART, taking 7 to 33 seconds; no faster readout is built.

## next_actions
1. Decode the AMD checker's pc_status bits to rule names using the AMD protocol-checker guide's table, and add them to the run record.
2. Add the full AXI4 transactor, the slave side and a soak mode that steers random traffic toward untested combinations.
3. Root-cause the 64-bit stream synthesis trim, or keep the core 32-bit only and say so at every interface.
4. Run the board plan again on a bitstream built from the current tree, so the evidence and the build ID agree.

## open_questions
- Is a faster readout (JTAG-AXI or a higher baud rate) worth building before the next board plan?

## history
2026-11-12 59A pr=-: transactor, checker, scoreboard, formal proofs, board demonstration and showcase page (site/showcase/axi_transactor.yaml); review rounds added rule 9 and re-ran the whole plan; 17 of 17 board runs pass
2026-11-13 68 pr=-: handover written to the documentation standard
