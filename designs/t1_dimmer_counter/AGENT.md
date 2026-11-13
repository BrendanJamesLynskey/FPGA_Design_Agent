# AGENT t1_dimmer_counter (fda-handover/1)
source: designs/t1_dimmer_counter/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/t1_dimmer_counter

## identity
kind=example produced_by=human part=xc7a100tcsg324-1 board=Nexys A7-100T top=t1_dimmer_counter_top tool=Vivado 2026.1

## summary
A 16-bit up/down/clear counter on the Nexys A7-100T. Debounced buttons step it, the LEDs show it under PWM brightness (register or switches), the 7-segment display shows count and brightness in hex, and every register is reachable over the USB-UART through the test shell. The hand-written reference design for task T1.
not: an agent run; the RTL, model and tests were written by hand; a gamma-corrected or auto-repeating dimmer; brightness is linear in the duty and one press is one step; a claim of compliance with any standard; the traceability record is DO-254-style evidence only

## state
stage=board-verified vivado=2026.1 kb_pin=1fc7ed8 build_id=595c2767
gates: build_2026_1=pass board_bringup=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the board's reset button, through the shell's reset synchroniser
if UART register window test shell, 8N1 UART at 115200 baud: COUNT 0x00 RW, DUTY 0x01 RW (reset 0x40), CTRL 0x02 RW (reset 0x2; bit 0 DUTY_SRC, bit 1 DISPLAY_EN), INPUTS 0x03 RO, PRESSES 0x04 RO; offsets 0x05 to 0x7F read 0; design ID T1DC doc=shell/PROTOCOL.md
if buttons and switches BTNU, BTND, BTNC, SW[15:0] in; asynchronous, LVCMOS33 (SW[8] and SW[9] are LVCMOS18, bank 34): synchronised and debounced; a press is a 0 to 1 change; clear beats up beats down; a shell write to COUNT beats a press doc=designs/t1_dimmer_counter/spec.yaml
if LEDs and display LED[15:0], 7-segment CA to CG with AN[7:0], active low segments and anodes: LEDs show COUNT gated by the PWM; digits 0 to 3 show COUNT, 6 and 7 the effective duty, 4 and 5 blank doc=designs/t1_dimmer_counter/spec.yaml
param DEBOUNCE_CYCLES=1,000,000 legal=tests shrink it; the board value is 10 ms at 100 MHz
param PWM_PRESCALE=4 legal=positive integer
param REFRESH_BITS=17 legal=tests shrink it
param CLKS_PER_BIT=868 legal=shell parameter

## files
designs/t1_dimmer_counter/spec.md 27829433c2: the natural-language spec
designs/t1_dimmer_counter/spec.yaml 89f4fcc7db: structured spec with assumptions, register map and REQ-01 to REQ-11
designs/t1_dimmer_counter/architecture.yaml 7ba0324624: blocks, crossings, predicted resources
designs/t1_dimmer_counter/BRINGUP.md e55b2a9427: bring-up guide for a tester
designs/t1_dimmer_counter/rtl/t1_dimmer_counter_top.sv 4ee0684c27: board top (shell plus design)
designs/t1_dimmer_counter/rtl/dimmer_counter.sv 2b37e3497c: counter, PWM, display scan, registers
designs/t1_dimmer_counter/rtl/debounce.sv e7dd140726: synchroniser and debounce per button
designs/t1_dimmer_counter/rtl/sevenseg_scan.sv 406b05c7a2: display scanner
designs/t1_dimmer_counter/design.xdc 1efd57b95f: pins, clock, async-input false paths
designs/t1_dimmer_counter/build.yaml d40ffa6a47: build recipe for flow/run_vivado.sh
designs/t1_dimmer_counter/probes.yaml 3f3110901c: ILA probes
designs/t1_dimmer_counter/lint/waivers.yaml e4690d029b: the one FDA-HDL waiver (XDCH-2) with its reason
designs/t1_dimmer_counter/model.py 9557dc4698: golden model written from spec.yaml alone
designs/t1_dimmer_counter/hw_checks.py 0a3b051d8c: ILA captures against the model
designs/t1_dimmer_counter/tests/test_t1_rtl.py f65d4511ad: cocotb tests of the RTL against the model
designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py 867a982673: verification bench with bound checkers and coverage
designs/t1_dimmer_counter/tests/test_t1_hw.py 45ade63537: on-board UART tests
designs/t1_dimmer_counter/tests/run_mutants.sh 578c194e3d: sed mutants the tests must fail
designs/t1_dimmer_counter/verif/testplan.yaml 5f32751ff1: requirements traced to checks
designs/t1_dimmer_counter/verif/checkers/t1_bind.sv 817eaeab2b: bound assertion checkers
designs/t1_dimmer_counter/verif/formal/debounce.sby f866b08ab4: SymbiYosys proof of the debouncer (scan.sby does the display scanner)

## commands
simulate the RTL against the model (~2min): python3 -m pytest -q shell/tests/test_shell_rtl.py designs/t1_dimmer_counter/tests/test_t1_rtl.py
verification bench with bound checkers, three seeds (~5min): SIM=verilator T1_SEEDS=1,2,3 python3 -m pytest -q designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py
formal proofs of the debouncer and the display scanner (~2min): flow/formal.sh designs/t1_dimmer_counter
hand-written mutants must each fail the tests (~5min): PYTHON=python3 designs/t1_dimmer_counter/tests/run_mutants.sh
[heavy] build the base and the ILA bitstreams (~10min): flow/run_vivado.sh designs/t1_dimmer_counter both
board bring-up, UART tests and ILA captures against the model (~3min): python3 flow/bringup.py designs/t1_dimmer_counter

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/t1_dimmer_counter/tests/test_t1_rtl.py f65d4511ad
R2 designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py 867a982673
R3 results/04f/README.md d7cc186f73
R4 results/04f/mutation_t1.json 34ba919972
R5 results/53_traceability/t1_dimmer_counter_trace.json 9050d0b59e
R6 results/f0a_2026_1/t1_dimmer_counter_base.json 71c1c9218c
R7 results/f0b_2026_1/t1_dimmer_counter_bringup.json 8e7ad647b8
R8 results/f0a_2026_1/t1_dimmer_counter_ila.json 902a57cf65

## evidence
E1 simulation pass R1 ci: cocotb tests of the RTL against the golden model (registers, debounce, PWM on-time, display)
E2 simulation pass R2 ci: verification bench with 23 bound assertions on seeds 1, 2 and 3 under Verilator 5.048 and under Icarus 12
E3 formal pass R3: SymbiYosys bounded proof and cover of the debouncer and display scanner, rerun in CI by flow/formal.sh
E4 faults pass R4: 21 mutants; the bench kills all 21 in the final run, 19 of 21 in the first (see gap E4)
E5 review pass R5: traceability matrix, all 11 requirements evidenced and every coverage hole justified; FDA-HDL lint passes with one waiver
E6 build pass R6: base build on Vivado 2026.1; every gate passes through bitstream
E7 board pass x1 R7: board bring-up on the 2026.1 builds; power gate, 8 of 8 UART tests and 4 of 4 ILA captures agree with the model | cond: wall power; power gate passed before programming (2.0 W and 85 C limits); XADC rails and die temperature were not read

## measured
M1 resources lut=487 LUT R6#gates.utilization.lut: LUTs, base build | routed base build, Vivado 2026.1, xc7a100tcsg324-1, including the test shell; the predicted range is 350 to 700
M2 resources ff=488 FF R6#gates.utilization.ff: flip-flops, base build | as M1
M3 resources bram_tile=0 tile R6#gates.utilization.bram_tile: BRAM tiles, base build | as M1; DSP48E1 is 0 too
M4 resources lut_ila=1668 LUT R8#gates.utilization.lut: LUTs, ILA build | routed ILA build, Vivado 2026.1; the debug core costs the difference from M1
M5 timing wns_ns=3.609 ns R6#gates.timing.wns_ns: worst setup slack, base build | routed, at the 100 MHz board clock; one build, not a trend
M6 timing whs_ns=0.064 ns R6#gates.timing.whs_ns: worst hold slack, base build | routed, at the 100 MHz board clock
M7 power power_w=0.15 W R6#gates.power.total_w: total on-chip power estimate, base build | report_power after routing, vectorless (default toggle rates), confidence Low; not a board measurement
M8 board led_on_clocks_pwm_40=256 clocks R7#steps.ila_captures.captures.pwm_40.led_on_clocks_measured[0]: LED on-time per 1,024-sample capture at DUTY 0x40, measured on the board by the ILA | ILA build; the model predicts the same value, and DUTY 0x08 and 0xA0 also match
M9 verification uart_tests=8 tests R7#steps.uart_tests.tests: UART tests passed on the board | tests/test_t1_hw.py on the base bitstream, 0 failures

## gaps
[latency] Button to count is 2 + DEBOUNCE_CYCLES + 1 clocks by design (10.00 ms at the board parameters); no record times it on the board.
[throughput] Not applicable; a control design with no data path.
[E4] The 100 percent is after fixing the bench for two survivors. The unbiased first-run score was 19 of 21.
[E7] One passing bring-up run on 2026.1; the earlier release had three in a row.
[manual checks] Buttons, display glyphs and three brightness levels were checked by a person on the earlier release's bitstream (results/f0b/manual_checks.md), not on 2026.1.
[operating conditions] XADC rails and die temperature were not read, so the runs cannot be shown inside the recommended operating conditions.
[behaviour] No auto-repeat or gamma curve exists. Reads of undefined window addresses return 0 with no error.

## next_actions
1. Repeat the manual button, display and brightness checks on the 2026.1 bitstream and record them.
2. Add a button-press ILA capture so a record times the button-to-count latency on the board.
3. Read the XADC rails and die temperature during bring-up.

## open_questions
- Should brightness follow a gamma curve so equal steps look equal (the spec default is linear)?
- Should holding a button auto-repeat (the spec default is no)?

## history
2026-10-30 02 pr=-: first bring-up on the board with the earlier release's builds
2026-11-01 04f pr=-: verification backbone applied; V3 reached, 21 mutants, formal proofs
2026-11-11 48 pr=-: rebuilt and brought up on Vivado 2026.1; the first bring-up run failed at the ILA step and was fixed
2026-11-12 53 pr=-: traceability matrix and HDL coding standard lint
2026-11-13 68 pr=-: handover written to the documentation standard
