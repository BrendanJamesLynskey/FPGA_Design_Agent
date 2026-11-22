# AGENT m141_ddr2_sched (fda-handover/1)
source: designs/m141_ddr2_sched/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/m141_ddr2_sched

## identity
kind=showcase produced_by=human part=xc7a100tcsg324-1 board=Digilent Nexys A7-100T (one Micron MT47H64M16HR-25 DDR2 part, x16, single rank) top=ddr2_sched tool=Vivado 2026.1

## summary
A request queue in front of a DDR2 command bus for the Micron MT47H64M16 on the Nexys A7, with two policies chosen by a parameter, latency-first for few random reads and bandwidth-first for streams, an abstract command interface that maps to AMD's PHY-only interface or to the MIG native interface, and the JEDEC timing rules enforced by per-bank counters. The rules are proved on the command stream by SymbiYosys against an independent monitor, and the scheduler is measured against a behavioural DDR2 model written from the data sheet.
not: a data path, a PHY, a MIG core, DDR2 initialisation or calibration, ZQ, on-die termination, power-down or self-refresh; the scheduler issues commands and the data bursts follow them at fixed latencies; any Vivado build or board run; both heavy slots were taken by other sessions during the work, and the build plan and the pre-registered board test are written but not run; the four-wide command packing a controller clock slower than the memory clock needs; the scheduler decides one command per memory clock

## state
stage=simulated vivado=2026.1 kb_pin=93d158c build_id=None
gates: sim_vs_model=pass formal_rules=pass board_run=not-run

## interface
clk clk 325MHz
rst rst active-high: synchronous; clears the queue, every timer and the refresh state; applied once before en rises and never while the part is in use, because a reset in the middle would forget the open banks of a real part
if request req_v, req_rdy, req_wr, req_addr, req_tag: a valid and ready handshake for one BL8 burst by burst address; req_rdy does not depend on req_v; tags must be unique among queued requests doc=designs/m141_ddr2_sched/docs/blocks.md
if command cmd_v, cmd_op, cmd_bank, cmd_row, cmd_col, cmd_tag: one registered DDR2 command a clock (ACTIVATE, READ, WRITE, PRECHARGE, PRECHARGE ALL, REFRESH); the data burst follows a READ by the read latency and a WRITE by the write latency; there is no completion signal doc=designs/m141_ddr2_sched/docs/blocks.md
if control en, ref_defer: en rises once when the PHY says the part is initialised and precharged; ref_defer postpones refresh within the allowance and never past it doc=designs/m141_ddr2_sched/docs/blocks.md
param POLICY=0 latency-first (default), 1 bandwidth-first legal=0 or 1
param QD=8 (default) legal=2 and up, verified in simulation to 33
param MAP=0 (default), 1, 2 legal=0 to 2
param AGE_LIM=1024 (default) legal=above the wait of a request in a full queue
param REF_POST=4 (default) legal=0 to 6
param timing parameters T_RCD to T_REFI, RL, WL, BL2=MT47H64M16-25 at a clock period of 2500 ps by default; tests/m141_timing.py derives them for a period legal=whole clocks below 256 (counters are 8 bits), RL = WL + 1, tREFI at least four times the longest refresh sequence

## files
designs/m141_ddr2_sched/rtl/ddr2_sched.sv 8bf988b3a0: the scheduler
designs/m141_ddr2_sched/rtl/ddr2_addrmap.sv e833a65470: burst address to row, bank and column
designs/m141_ddr2_sched/tb/tb_ddr2.sv 3a3dee9c61: bench with the behavioural DDR2 timing model
designs/m141_ddr2_sched/verif/formal/ddr2_props.sv 3ebbc30bca: timing rules, helper invariants, ordering, refresh and bounded-response properties
designs/m141_ddr2_sched/verif/formal/run_formal.py 2017e11ff7: runner of the proofs, covers and mutants
designs/m141_ddr2_sched/tests/m141_measure.py 70562c2700: runs the bench for a policy, map, pattern and timing profile and reduces the output to numbers
designs/m141_ddr2_sched/tests/m141_timing.py 268fa31dbb: data sheet values and the conversion to clocks for each timing profile

## commands
bench against the model, seeded faults, lint (~12min): python3 -m pytest -q designs/m141_ddr2_sched/tests/test_m141_clean_rtl.py designs/m141_ddr2_sched/tests/test_m141_faults_rtl.py designs/m141_ddr2_sched/tests/test_m141_lint_rtl.py
the proofs, covers and mutants of the CI set (~20min): python3 -m pytest -q designs/m141_ddr2_sched/tests/test_m141_formal.py
the measured simulation runs of results/b141 (~60min): python3 designs/m141_ddr2_sched/tests/m141_measure.py --json results/b141/sim_summary.json

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/m141_ddr2_sched/tests/test_m141_clean_rtl.py 2099ffaf57
R2 designs/m141_ddr2_sched/tests/test_m141_faults_rtl.py be03ea22a8
R3 designs/m141_ddr2_sched/tests/test_m141_formal.py ac0787b084
R4 results/b141/formal_full.json ac86f9315c
R5 results/b141/sim_summary.json af8f1a7bfe
R6 designs/m141_ddr2_sched/tests/test_m141_lint_rtl.py 3ef61f54ec

## evidence
E1 simulation pass R1 ci: both policies, six traffic patterns, two timing profiles and three address maps against the behavioural DDR2 model with no violation, every request served once, order kept, refresh gap within the JEDEC limit and the longest wait within the bound
E2 faults pass R2 ci: sixteen seeded faults in a copy of the RTL are each caught by the bench
E3 formal pass R3 ci: the timing rules and request order proved by k-induction with helper invariants at the real data sheet constants and at small ones, the refresh debt bound proved, the covers reached and fourteen mutants caught by named assertions
E4 formal pass R4: the full formal set including the bounded-response check at the proved bound plus six clocks, run to completion with the verdict of every job recorded
E5 simulation pass R5: every measured run of the results folder finished with zero violations of the DDR2 model
E6 lint pass R6 ci: Verilator -Wall clean on both modules

## measured
M1 latency lat_rand_read_p0_median=12 clocks R5#runs.lat_rand_read_p0.lat_clk.p50: median read latency, latency-first, light random reads | POLICY 0, random reads, mean gap between requests 40 clocks, nexys_650 profile (clock period 3077 ps, CL 5), Icarus simulation of the command bus, no PHY
M2 latency lat_rand_read_p0_p999=53 clocks R5#runs.lat_rand_read_p0.lat_clk.p999: 99.9th percentile read latency, latency-first, light random reads | as M1
M3 latency lat_rand_read_p1_median=17 clocks R5#runs.lat_rand_read_p1.lat_clk.p50: median read latency, bandwidth-first, light random reads | as M1 with POLICY 1
M4 throughput bw_seq_read_map0_p1_util=0.9798 fraction R5#runs.bw_seq_read_map0_p1.util: data-bus utilisation, bandwidth-first, sequential reads, page-interleaved map | POLICY 1, sequential reads, MAP 0, queue of 8 entries, nexys_650 profile, Icarus simulation of the command bus
M5 throughput bw_copy_map2_p1_util=0.8614 fraction R5#runs.bw_copy_map2_p1.util: data-bus utilisation, bandwidth-first, copy stream (read stream plus write stream), every burst to the next bank | POLICY 1, alternating read and write streams, MAP 2, queue of 8 entries, nexys_650 profile, Icarus simulation
M6 latency sat_mix_p0_wait_max=264 clocks R5#runs.bw_rand_mix_sat_p0.wait_max: longest wait of any request in a saturated mixed run, latency-first | POLICY 0, random reads and writes as fast as accepted, queue of 8 entries, nexys_650 profile
M7 latency window_post4_max_in_window=28 clocks R5#runs.refresh_window_p0_post4.lat_clk_win.max: maximum read latency of reads accepted inside a refresh-deferral window, latency-first, postponement 4 | POLICY 0, REF_POST 4, ref_defer high for 5000 of every 12000 clocks, random reads at light load, nexys_650 profile, Icarus simulation of the command bus
M8 latency window_post0_max_in_window=73 clocks R5#runs.refresh_window_p0_post0.lat_clk_win.max: maximum read latency of reads accepted inside the same window with no postponement allowance | as M7 with REF_POST 0
M9 latency window_post4_max_outside=91 clocks R5#runs.refresh_window_p0_post4.lat_clk_out.max: maximum read latency of reads accepted outside the window with postponement 4 (the cost moved out of the window) | as M7

## gaps
[resources] Not measured; no Vivado run was made because both heavy slots were taken by other sessions, so there is no LUT, flip-flop or block RAM figure for the scheduler.
[timing] Not measured; no out-of-context or full build exists, so the closed clock of the decision logic is unknown. The scheduler decides one command a clock and its combinational scan of the queue and the timer file is expected to close well below the memory clock.
[power] Not measured; no build and no board.
[board_run] Not run on a board and not built with MIG; the pre-registered board test and the build plan are in docs/memory_controller_plan.md sections 11 and 12.
[model] The DDR2 model and the formal monitor encode one reading of the Micron data sheet by the author of the scheduler; no vendor model was used, and JEDEC's refresh postponement allowance was not checked against the standard's text.
[bounded_response] The bounded-response property is a bounded model check from reset at small parameters, not a proof for all time; at real parameters the bound is measured in simulation only.
[phy_interface] The AMD PHY-only interface needs periodic reads, the temperature sample enable, FIFO flow control and up to four commands per controller clock; none is built, and the scheduler's one-command-a-clock decision is not what a controller clock four times slower needs.
[behaviour] Guessable wrongly: no data path and no completion signal; spacings are those of the registered output; a read waits for an older write to its address and is never forwarded the write's data; tags must be unique among queued requests and nothing checks it; a reset in the middle of operation is unsupported; an AGE_LIM below the wait of a request in a full queue makes the queue first-come first-served; tRC is implied by tRAS plus tRP at the data sheet values.

## next_actions
1. Run an out-of-context Vivado build of ddr2_sched on the Artix-7 100T and the K26 for several queue depths, to put resources and a closed clock on the block, in a heavy slot.
2. Find out whether the generated MIG sources can drop the controller and keep the PHY, then build the first design with the PHY interface, periodic reads and the temperature enable.
3. Make the decision four-wide so one controller clock carries up to four commands, and re-run the proofs and the measurements on it.
4. Run the pre-registered board test once the build exists.

## open_questions
- Does the MIG controller leave a row open after a read? The first hypothesis of the board test (the eager-precharge gain) depends on it.
- Is a four-wide decision better built as four scheduler copies on interleaved banks or as one wider arbiter?

## history
2026-11-21 141 pr=-: phase 0, the study and plan, scheduler RTL with two policies, behavioural DDR2 model and bench, formal proofs of the timing rules with helper invariants, request order, refresh debt and bounded response, measured policies, library entry form, build plan and pre-registered board test
