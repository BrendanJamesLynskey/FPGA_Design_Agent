# AGENT b191_ps_axi_lat (fda-handover/1)
source: designs/b191_ps_axi_lat/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b191_ps_axi_lat

## identity
kind=demonstration produced_by=session part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM) top=ps_axi_lat_top (the PL image); axi_lat_probe (simulated alone) tool=Vivado 2026.1

## summary
A register block with a free-running counter that timestamps every AXI read request and every write it accepts, one on each of the Zynq UltraScale+ processor system's two AXI masters towards the fabric (M_AXI_HPM0_FPD and M_AXI_HPM0_LPD), and a host program that times 32-bit reads and writes of it from the Arm Cortex-A53 with the processor's own timer and with the fabric's counter. The probe is simulated against an edge-counting AXI master and seeded faults are caught; the host program and its judging script are tested without a board against a software stand-in. The board row (B-R8) is pre-registered; the programmable-logic image's build recipe is written and was not built, and nothing has run on a board.
not: a measured result; no latency figure for the processor-to-fabric path exists yet, only the means of measuring it; a built bitstream; the image's recipe (build.yaml, the processor-system IP script) is untested, so its clock constraint, address assignment and the flow's gates are unchecked; the latency of the ACP or HP ports, DMA, cached accesses, wider accesses or a faster fabric clock than 100 MHz; a design that does anything else; the image has no I/O pins and no function besides the two probes

## state
stage=simulated vivado=2026.1 kb_pin=5e2eab8 build_id=fbc74516
gates: rtl_equals_model=pass lint=pass seeded_faults=pass build=not-run board_run=not-run

## interface
clk pl_clk0 100MHz
rst aresetn active-low: the processor system's pl_resetn0 through a 4-flop reset synchroniser (asynchronous assert, synchronous release); clears the counter, the registers and the counts, not the log memory
if AXI4 slave (one per processor master) awid, awaddr, awlen, awsize, awvalid/awready, wdata, wstrb, wlast, wvalid/wready, bid, bresp, bvalid/bready, arid, araddr, arlen, arsize, arvalid/arready, rid, rdata, rresp, rlast, rvalid/rready (32-bit data, 16-bit ids): single-beat 32-bit accesses only; anything else is answered SLVERR and counted; unmapped reads return 0 with SLVERR; partial write strobes are refused doc=designs/b191_ps_axi_lat/docs/ps_axi_lat.md
if register window 4 KiB at the PS addresses 0xA0000000 (FPD) and 0x80000000 (LPD); ID, BUILD, CLK_HZ, SCRATCH, CNT, WR_TS, WR_N, LOG_N, TRIG, CTRL, BAD and the write-clock log: the counter is 32 bits and wraps in 42.9 s at 100 MHz; software uses differences modulo 2^32 doc=designs/b191_ps_axi_lat/docs/ps_axi_lat.md
param LOG_DEPTH=256 legal=a power of two, at most 256
param CLK_HZ=100,000,000 legal=the fabric clock in Hz
param BUILD_STAMP=0xB1910F01 legal=any 32-bit stamp (the flow sets it from the sources' hash)

## files
designs/b191_ps_axi_lat/rtl/axi_lat_probe.sv dbe358452d: the AXI4 slave register block with the counter, the timestamps and the log
designs/b191_ps_axi_lat/rtl/ps_axi_lat_top.sv c0dd014072: the PL image's top, the processor system with both masters and one probe each
designs/b191_ps_axi_lat/ip/amd_ip_lat.tcl d11b2c8067: the Zynq UltraScale+ processor system IP of the image
designs/b191_ps_axi_lat/host/ps_axi_lat.c 6314d9e390: the host program (aarch64, static) that measures, with a software stand-in for the registers under -DMOCK
designs/b191_ps_axi_lat/scripts/ps_axi_lat_verdict.py 2ccf918349: judges a board session's files against the pre-registration
designs/b191_ps_axi_lat/board/ps_axi_lat_session.sh 503a52a626: the board session script (written, not run)
designs/b191_ps_axi_lat/board/pl-ps-axi-lat.dtsi 90a8819a25: the device-tree overlay source for the generic-uio route
designs/b191_ps_axi_lat/tests/b191_cocotb.py 8be45da32e: cocotb bench of the probe with an edge-counting AXI master
designs/b191_ps_axi_lat/tests/test_b191_host.py 4f426b3360: the host program and verdict script without a board
designs/b191_ps_axi_lat/tests/run_mutants.py 70274ea6e0: seeded-fault runner for the probe
designs/b191_ps_axi_lat/docs/ps_axi_lat.md 3416762880: datasheet, register map and the pre-registration of board row B-R8

## commands
the probe bench and the host tests (no board) (~1min): python3 -m pytest -q designs/b191_ps_axi_lat/tests
the seeded faults in the probe (~1min): python3 designs/b191_ps_axi_lat/tests/run_mutants.py --json results/191_trading_variants/mutation_probe.json
the board session (planner gives it at the board; not run) (~60min): designs/b191_ps_axi_lat/board/ps_axi_lat_session.sh <board ssh target> <results dir> <built .bit> <build stamp>

## records (path sha256-prefix; claims below cite R<n>)
R1 results/191_trading_variants/pytest_junit.xml be267a11ab
R2 results/191_trading_variants/mutation_probe.json 0f01fea1ee
R3 designs/b191_ps_axi_lat/build.yaml 96b26afc0d
R4 results/191_trading_variants/sim/probe_sim.json d68ea794c7

## evidence
E1 simulation pass R1: the probe against an AXI master that counts clock edges, so every timestamp is checked against the edge in which the access was accepted - identity, scratch, read and write timestamps with AW and W in either order, the log and its saturation, bad accesses, back pressure and a random mix against a model
E2 faults pass R2: twelve seeded faults in the probe (stamps one clock late, the log, strobes, ids, the clear, unmapped writes) all fail the bench
E3 model pass R1: the host program built with a software stand-in for the registers, its JSON judged by the verdict script (valid and invalid sets), and the aarch64 static build
E4 build not-run R3: the PL image was not built; the board row waits for it

## measured
M1 latency read_to_read_clocks_min=2 clocks R4#min_read_to_read_clocks: the smallest interval between two read requests at the probe's port from a master that takes each response in one clock | simulation, one clock; a property of the probe (request, response, next request), not of the processor

## gaps
[E4] The PL image was not built, so there is no build record; the board row waits for it.
[resources] Not measured; the image was not built, so there is no utilisation. The probe is a few hundred LUTs and one block of memory by construction, not by measurement.
[timing] Not measured; no implementation was run. The probe is one clock domain of 10 ns with a counter, so closure is expected, not shown.
[power] Not measured; nothing was built or run on a board.
[throughput] Not applicable to a probe; the figures it measures are latencies, and the board has not run.
[build] The PL image was not built. The recipe is written, and the properties it sets exist in the IP definition of Vivado 2026.1, but the PS clock constraint, the address assignment and the flow's gates are unchecked.
[board_run] Not run on a board. Whether /dev/mem accepts the mapping on the board's Ubuntu kernel, the PS base addresses and the timer frequency are unconfirmed (docs/ps_axi_lat.md lists them).
[values] No latency value is measured; the pre-registration judges the validity of the measurement and records three hypotheses.
[clock] Only a 100 MHz fabric clock is prepared; the processor-to-fabric crossing's cost depends on that clock.

## next_actions
1. Build the image (about 15 minutes, small), fix whatever the flow's gates report, and record the build ID.
2. Run board row B-R8 in the next board visit and use the figures to fix what a fast and slow loop split may ask of software.
3. A 250 MHz row (a one-line change in the IP script) to see how much of the latency is the fabric clock.

## open_questions
- Does the board's Ubuntu kernel allow /dev/mem for the PS-PL windows, or does the generic-uio overlay have to be used?

## history
2026-11-23 191 pr=-: Probe, host program, verdict script and pre-registration written and tested without a board; the image's recipe written, not built.
