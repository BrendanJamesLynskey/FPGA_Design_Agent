# AGENT b119_tcp_fast (fda-handover/1)
source: designs/b119_tcp_fast/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b119_tcp_fast

## identity
kind=showcase produced_by=session part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM) top=tcp_fast (wrapped with input registers in ooc_wrap for the out-of-context build) tool=Vivado 2026.1
verified: verified except: 24 of 27 requirements without passing evidence; 27 of 27 requirements not agreed; required method mix not yet measured; mutation floor not yet measured; 21 stale or differing evidence items (record: designs/b119_tcp_fast/VERIFIED.md, designs/b119_tcp_fast/verified.json; definition: docs/verified.md)

## summary
A block that holds the TCP connection state which software hands it and sends each OUCH 5.0 order of brief 110 as one complete Ethernet, IPv4 and TCP frame, with sequence number, identification and both checksums finished incrementally from partial sums of a template. It supports the speculative start and abort of brief 110, where an aborted frame is poisoned and consumes no sequence space, refuses to send when it is not armed, its state is stale, the window is closed or the MSS is too small, and hands every sent segment back to software. A Python TCP owner and a software OUCH exchange test it end to end in simulation, seeded faults in the RTL are caught, and the block is built out of context for the KR260's part at the 10G core clock.
not: real market data, a real exchange or a real network; every order comes from our own generator and no frame is ever sent anywhere; a board run, power, or timing inside the 10G core; the numbers are simulation and an out-of-context Vivado 2026.1 build; receiving, parsing or acknowledging anything; software owns the receive side and writes the acknowledgement state into the block; TCP options, selective acknowledgement, window scaling, several connections or a hardware retransmission; the MAC, the frame check sequence and the transmit multiplexer; the block's words go to a MAC that does not exist here (docs/phase2_integration.md is a plan)

## state
stage=built vivado=2026.1 kb_pin=eaf6794 build_id=None
gates: rtl_equals_model=pass lint=pass seeded_faults=pass ooc_build_2026_1=pass board_run=not-run

## interface
clk clk 161.132MHz
rst rst active-high: synchronous; resets every register including the counters; the block is not armed after reset; one clock domain, no asynchronous input
if order side go, go_spec, f_sym, f_px, f_qty, f_ref, commit, abort, cfg_*, busy, late, refuse_v, refuse_code (the ports of ouch_enter of brief 110 and three more): a go while busy is dropped; a refused order is lost; abort in the go clock cancels the go; cfg_* must stay static while a segment is in flight doc=designs/b119_tcp_fast/docs/tcp_fast.md
if segment output o_v, o_d[63:0], o_sof, o_eof, o_keep[7:0], o_poison (to the MAC): 113 bytes without the frame check sequence in fifteen words, never paused; o_poison with the last word asks the MAC to corrupt the check sequence doc=designs/b119_tcp_fast/docs/tcp_fast.md
if sent-segment record rec_v, rec_seq, rec_len, rec_id, rec_pay[511:0]: one clock for each unpoisoned segment and not buffered; a poisoned segment produces none doc=designs/b119_tcp_fast/docs/tcp_fast.md
if software register bus sw_we, sw_waddr[4:0], sw_wdata[31:0], sw_raddr[4:0], sw_rdata[31:0]: static writes while busy are ignored and counted; live registers restart the staleness age; reads show the registers as they were before the next edge doc=designs/b119_tcp_fast/docs/tcp_fast.md
param PAYLEN=59 legal=fixed
param segment bytes=113 legal=fixed

## files
designs/b119_tcp_fast/rtl/tcp_fast.sv 0a9b9e0de8: the TCP fast path
designs/b119_tcp_fast/rtl/itch_ouch_tcp_top.sv dce6ad68f3: brief 110's trading path with tcp_fast in place of its stub port (simulation)
designs/b119_tcp_fast/model/tcpref.py f6ca3aecbc: segment, checksum and decision reference
designs/b119_tcp_fast/model/softtcp.py 1f6b650e44: TCP endpoint, owner and software exchange
designs/b119_tcp_fast/model/soup.py fb5ab8e196: SoupBinTCP and OUCH response packers and parsers
designs/b119_tcp_fast/model/hwmodel.py 5bdd61efa5: untimed stand-in for the block's register file
designs/b119_tcp_fast/model/orders.py f2009e9338: order payload builder from brief 110's packers
designs/b119_tcp_fast/tests/b119_cocotb.py 6e94d3d68c: cocotb bench of the block
designs/b119_tcp_fast/tests/b119_top_cocotb.py cb47428981: cocotb bench behind brief 110's risk logic
designs/b119_tcp_fast/tests/netsim.py 3632074a28: the pure-Python network of owner, exchange and stand-in
designs/b119_tcp_fast/tests/run_mutants.py c4a57bf19d: seeded-fault runner
designs/b119_tcp_fast/ooc/ooc.py 48962fa558: out-of-context build driver
designs/b119_tcp_fast/docs/tcp_fast.md d93c76bd30: datasheet
designs/b119_tcp_fast/docs/software_side.md 340d510d39: the Python TCP owner and exchange
designs/b119_tcp_fast/docs/phase2_integration.md e58721f2a6: integration notes for the 10G MAC and open points

## commands
the whole bench (cocotb on Icarus), the Python-side tests and the lint (~1min): python3 -m pytest -q designs/b119_tcp_fast/tests/test_b119_model.py designs/b119_tcp_fast/tests/test_b119_rtl.py designs/b119_tcp_fast/tests/test_b119_lint.py
the same with the measurement records written (latency in clocks, outcomes, end-to-end figures) (~1min): B119_RECORD=$PWD/results/b119 python3 -m pytest -q designs/b119_tcp_fast/tests/test_b119_rtl.py
the seeded faults (every mutant of verif/mutants.yaml against the bench) (~20min): python3 designs/b119_tcp_fast/tests/run_mutants.py --jobs 2 --json results/b119/mutation.json
[heavy] the out-of-context builds (two clocks) (~30min): python3 -m designs.b119_tcp_fast.ooc.ooc --clocks 6.2061 5.0

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b119_tcp_fast/tests/test_b119_rtl.py 76d186b184
R2 designs/b119_tcp_fast/tests/test_b119_model.py 7515e2264b
R3 designs/b119_tcp_fast/tests/test_b119_lint.py 7e15fe26fa
R4 results/b119/mutation.json 060d260994
R5 results/b119/top_sim.json 71c94f32fe
R6 results/b119/ooc/tcp_fast.json 284f533ef5
R7 results/b119/bench_sim.json 8dcf52c49d

## evidence
E1 simulation pass R1 ci: the block against the reference in cocotb - random connections and orders byte exact, checksum corner cases, an abort at every offset, speculative verdicts, every refusal path, register semantics, continuity of the sequence space with software, a long random mix, and the software owner and exchange end to end
E2 model pass R2 ci: the checksum reference against outside vectors, the TCP endpoint, the owner and the exchange against the untimed stand-in, including a dropped segment and heartbeats
E3 lint pass R3 ci: Verilator -Wall lint of the block and the frame builder inside it, no warnings
E4 faults pass R4: every one of the seeded faults in the block (constants, operators and conditions across the checksum, the segment, the verdict, the refusals and the registers) fails the bench
E5 simulation pass R5: brief 110's path with the block in place of its stub port against brief 110's reference model - the same orders leave, with the same payload bytes, valid checksums and gapless sequence numbers, speculative orders that are refused are poisoned
E6 build pass R6: out-of-context, post-route builds on the K26 at the required 10G core clock and a faster one; the required clock closed (setup, hold and pulse width)

## measured
M1 latency first_byte_clocks_after_go=1 clocks R7#timing.first_byte_clocks_after_go: clocks from the clock go is presented to the first byte of the frame | simulation, one clock; the same clock in which brief 110's stub port shows its first word
M2 latency tcp_checksum_field_clocks_after_go=7 clocks R7#timing.tcp_checksum_field_clocks_after_go: clocks from go to the last byte of the TCP checksum field | simulation, one clock
M3 latency last_byte_clocks_after_go=15 clocks R7#timing.last_byte_clocks_after_go: clocks from go to the last byte of the segment | ditto
M4 latency itch_to_first_ethernet_byte_spec_clocks=3 clocks R5#behind_risk_logic.speculative.first_ethernet_byte_clocks_after_last_itch_byte: clocks from the last byte of a triggering ITCH message to the first byte of the Ethernet frame, speculative start | simulation of brief 110's path with the block behind it, one clock; only when the frame is idle and no earlier candidate is in flight
M5 latency itch_to_first_ethernet_byte_clocks=8 clocks R5#behind_risk_logic.non_speculative.first_ethernet_byte_clocks_after_last_itch_byte: the same with the frame started at the risk verdict | as M4
M6 throughput clocks_per_segment=15 clocks R7#timing.back_to_back_clocks_between_segment_starts: clocks between the starts of two segments sent back to back | simulation; the block is busy for the whole segment and drops a go meanwhile
M7 resources lut=1546 LUT R6#at_required.core_lut: LUTs of tcp_fast at the required clock, including the frame builder inside it | out of context, Vivado 2026.1, one thread; the wrapper's input registers are not counted
M8 resources ff=2907 FF R6#at_required.core_ff: registers of tcp_fast at the required clock | as M7
M9 timing wns_ns=1.77 ns R6#at_required.wns_ns: worst setup slack at the required clock | out of context, post-route, period 6.2061 ns, no clock buffer or jitter
M10 timing whs_ns=0.055 ns R6#at_required.whs_ns: worst hold slack at the required clock | as M9
M11 timing closed_at_ns=5 ns R6#closed_at_ns: fastest clock period tried that closed | a closed point out of the two tried, not a bound; as M9
M12 resources bram_tiles=0 tiles R6#at_required.bram_tiles: block RAM tiles used | as M7
M13 other mutants_killed=73 faults R4#killed: seeded faults killed by the bench | simulation, the whole bench per fault
M14 other mutants_valid=73 faults R4#valid: seeded faults that build and were tried | as M13
M15 other random_segments=450 segments R7#random_segments: random segments compared byte for byte with the reference | simulation, random connections, orders and states including sequence numbers at the wrap

## gaps
[board_run] Not run on a board; phase 2 would put the block behind the 10G MAC of the KR260 design (docs/phase2_integration.md).
[power] Not measured; an out-of-context build has no realistic activity and nothing ran on a board.
[E6] Out of context the clock has no buffer or jitter and the inputs are registered in the wrapper; inside the 10G core the clock and placement can differ.
[mac] The pair of this block and the 10G MAC's transmit path was not simulated; whether a MAC accepts a word every clock, pads a short poisoned frame and corrupts the frame check sequence on request is the 96 design's behaviour, not shown here.
[refusals] A refused order is lost and the risk logic of brief 110 is not told, so its order number and position count have already moved; the feedback is not built.
[tcp] No TCP options (timestamps must be off on the connection), no selective acknowledgement, no window scaling inside the block (software scales the values it writes), one connection, no hardware retransmission and no parsing of received segments.
[software] The TCP endpoint is a minimal user-space model with no congestion control, delayed acknowledgements, orderly close or zero-window probes; the exchange follows the Nasdaq documents for the fields it fills but is our own model and no real port was involved.
[spec] SoupBinTCP 3.00 and OUCH 5.0 layouts of the exchange's replies were read from the public documents; the padding of the Login Request's sequence number field is assumed, and brief 110's UNCONFIRMED items about the Enter Order stay open.
[busy] The block is busy for fifteen clocks per segment, so brief 110's order queue sees a longer busy time than with the stub port; the effect on rejected candidates at a real feed rate was not measured.
[data] Synthetic orders from our own generators; the figures say how the block behaves on them and nothing about a market.

## next_actions
1. Build the transmit multiplexer and the register bridge of docs/phase2_integration.md, and simulate the block with the 96 design's MAC.
2. Add the refusal feedback from the block to the risk logic (release the order number and the position).
3. Run the owner against a real TCP peer on the host (a second machine or a namespace) and compare captures with the bench's frames.

## open_questions
- Is the fifteen-clock busy time acceptable at the feed rates of interest, or should a second segment buffer let the next order start while the last words go out?
- Should the owner's pure acknowledgements go through the block so that its sequence number is always current?

## history
2026-11-20 119 pr=-: RTL, software TCP owner and exchange, bench, seeded faults, out-of-context builds, datasheet and integration notes
