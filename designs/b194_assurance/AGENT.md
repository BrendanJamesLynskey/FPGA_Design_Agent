# AGENT b194_assurance (fda-handover/1)
source: designs/b194_assurance/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b194_assurance

## identity
kind=demonstration produced_by=session part=xc7a100tcsg324-1 board=none (out of context) top=a194_core tool=Vivado 2026.1
verified: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement (record: designs/b194_assurance/VERIFIED.md, designs/b194_assurance/verified.json; definition: docs/verified.md)

## summary
A burst sequencer in front of a 512 x 64 FIFO with an accumulating checksum, AXI4-Stream handshakes. Each reliability structure is a parameter (ECC 0/1/2, parity, safe-state FSM, TMR on the remaining-words counter, watchdog) so that its area, Fmax, latency and what it catches in a seeded single-event-upset simulation are measured against the plain design. It is the demonstration design of the verification profiles and is not a held-out benchmark task.
not: a held-out or benchmark task; it was written for the measurements of docs/assurance.md; a board design; it has no pins, no constraints and was only built out of context; a failure-rate figure; the fault injection is seeded single bit flips in simulation

## state
stage=simulated vivado=2026.1 kb_pin=6185830 build_id=none

## interface
clk aclk 200MHz
rst aresetn active-low: AXI reset polarity at the stream ports; inverted once inside and used synchronously everywhere
if slave stream AXI4-Stream, 64-bit tdata, tvalid, tready: tready is low unless the sequencer is running a burst and the FIFO is not full; valid never waits for ready doc=designs/b194_assurance/rtl/a194_core.sv
if master stream AXI4-Stream, 64-bit tdata, tvalid, tready: one word at most every second clock (the FIFO read takes two clocks); the payload is stable while valid is high and ready low doc=designs/b194_assurance/rtl/a194_core.sv
if control and status start, len[15:0] in; busy, done (one clock), checksum[63:0], err_corr, err_det, fsm_fault, wd_fault, tmr_fault out: len is sampled with start while idle; a start while busy is ignored; len 0 completes without words; the error flags are sticky until reset doc=designs/b194_assurance/rtl/a194_core.sv
param ECC=0 legal=0 none, 1 fabric SECDED code over 64 data bits, 2 RAMB36E1 built-in ECC (simulation needs xsim and UNISIM)
param PAR=0 legal=0 or 1
param SAFE=0 legal=0 or 1
param TMR=0 legal=0 or 1
param WD=0 legal=0 or 1

## files
designs/b194_assurance/rtl/a194_ctrl.sv e1d5114034: the sequencer, the counter (optionally TMR), the watchdog, the safe-state attribute
designs/b194_assurance/rtl/a194_fifo.sv 3496072888: the FIFO with the three ECC variants
designs/b194_assurance/rtl/a194_core.sv 9c1a73f8c3: the top: output register, parity, checksum, error flags
designs/b194_assurance/rtl/a194_secded.sv 55648e8a97: the SECDED functions (64 data bits, 8 check bits) of the fabric ECC variant
designs/b194_assurance/tb/tb_func.sv a45ff29b26: ports-only functional bench (runs on RTL and on Vivado netlists)
designs/b194_assurance/tb/tb_fault.sv 965b4b5f08: the seeded single-event-upset campaign (RTL, fault hooks compiled in with A194_FI)
designs/b194_assurance/tests/mutants.py 5fd5058750: seven RTL bugs used to measure what each verification method catches
designs/b194_assurance/tests/test_b194_rtl.py addb99b782: Icarus tests of the variants, a mutant and a small fault campaign

## commands
functional bench, fault campaign and mutant checks under Icarus (~1min): python3 -m pytest -q designs/b194_assurance/tests/test_b194_rtl.py
the full seeded fault campaign (xsim for the ECC primitive variants) (~12min): python3 designs/b194_assurance/tests/run_faults.py --trials 300 --seed 1
[heavy] out-of-context cost runs and netlist checks (~30min): python3 -m flow.assurance cost --ctrl; python3 -m flow.assurance costs; python3 -m flow.assurance_profiles netlist

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b194_assurance/tests/test_b194_rtl.py addb99b782
R2 results/b194/faults.json 80d72b120f
R3 results/b194/costs.json 99c229db9a

## evidence
E1 simulation pass R1: the functional bench passes on every variant that needs no block RAM primitive; a planted bug is caught; the fault campaign classes follow from what each structure does
E2 simulation pass R2: seeded fault-injection campaign, 300 trials per cell, eight variants, six fault targets
E3 build pass R3: out-of-context synthesis and routing of the eight variants on Vivado 2026.1, area and slack at a 5.0 ns constraint

## measured
M1 resources lut=120 LUT R3#variants.u.lut: LUTs of the plain design | routed, out of context, Vivado 2026.1, xc7a100tcsg324-1
M2 timing wns_ns=0.423 ns R3#variants.u.wns_route_ns: worst setup slack of the plain design at 5.0 ns | routed, out of context, a 5.0 ns constraint on aclk
M3 latency latency_clocks=3 clocks R3#variants.u.latency_clocks: latency, slave accept to first master valid | tb/tb_lat.sv, output always ready, one one-word burst; the same for every variant
M4 other -=300 trials R2#variants.u.targets.ram.silent: silent corruptions of a stored word in the plain design (of 300 trials) | one bit flipped in the word stored by one write, seed 1
M5 other -=300 trials R2#variants.ecc_prim.targets.ram.corrected: the same fault with the built-in block RAM ECC, corrected and flagged (of 300 trials) | INJECTSBITERR on one write, xsim with UNISIM, seed 1

## gaps
[power] Not measured; no power report was taken for any variant.
[throughput] Not measured; one master word at most every second clock by construction.
[board] Never programmed; no hardware measurement.
[UltraScale+] Every cost and effect was measured on the 7-series part only.
[fsm_safe_state] The safe-state effect is a netlist property; the RTL fault injection cannot show it and no netlist-level injection was run.
[latency] Measured in simulation only, one burst; throughput was not measured.
[structure] The cost figures come from one small design and one run per variant; the spread between runs is unknown.
[behaviour] A start while busy is ignored; len is taken at start; the watchdog does not watch an idle sequencer; after a flagged ECC error the stored word stays wrong until rewritten.

## next_actions
1. Run the safe-state and TMR variants through netlist-level fault injection.
2. Repeat the cost runs on UltraScale+ and on a larger design.

## open_questions
- Which of the structures should the interview propose by default for a block the spec does not mention?

## history
2026-11-23 194 pr=-: written with the assurance switch measurements
