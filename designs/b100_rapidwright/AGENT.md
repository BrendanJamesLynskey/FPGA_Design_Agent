# AGENT b100_rapidwright (fda-handover/1)
source: designs/b100_rapidwright/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b100_rapidwright

## identity
kind=showcase produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=chain_top (the chain); reloc_top (the block runs); s0_top (stage 0, also xc7a100tcsg324-1) tool=Vivado 2026.1

## summary
Three RapidWright capabilities built as tested agent tools and compared with Vivado alone on the K26 (xck26-sfvc784-2LV-c). They are a pre-implemented block stamped at other sites with its internal timing kept, an annealing placer for the transmit latency chain of brief 96, and RWRoute routing of the whole design or of the worst-path nets. Vivado 2026.1 times every result; RapidWright's own estimates are never used. The block capability works and is the only one that beats Vivado alone (on repeatability); placement and routing lose to Vivado on timing; the agent given the tools did no better than the agent without them.
not: a board run; no bitstream of the chain was made or loaded, and the chain's GT is a bare primitive without a reference clock or reset sequence; a claim that RapidWright's placer or router is better or worse than Vivado's in general; this is one chain, one part, our first-cut placer and a handful of period perturbations; the full brief 96 design; the chain is brief 96's own MAC and PCS RTL with a bare GT, not the GT Wizard design

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=None
gates: rapidwright_roundtrip=pass comparison_vivado_2026_1=pass

## interface
clk clk 312.5MHz
rst rst active-high: synchronous, from a register in the source shift register; the RTL is brief 96's and is not changed here
if agent tools (rw_status, rw_relocate_block, rw_place_chain, rw_route, rw_referee) agent/core/rapidwright_tools.py; offered to a role only with FDA_RAPIDWRIGHT=1 and RapidWright installed: every argument is validated, inputs are checkpoint file names inside build/<variant>/, outputs go to build/<variant>/rw/, and only rw_referee returns timing, from Vivado doc=designs/b100_rapidwright/docs/tools.md
if RapidWright scripts flow/rw/*.py run with the pinned venv python (flow/rapidwright_pin.py): relocate.py, place_chain.py, route.py, roundtrip.py print one JSON line; they need RapidWright and Vivado 2026.1 on PATH doc=designs/b100_rapidwright/docs/design.md
param clock period=set per run by the scripts, 3.40 ns for the first chain run, plus 0.01 ns per perturbation (3.2 ns in the agent runs) legal=any period the scripts are given
param RapidWright=2026.1.2 legal=the release whose year and minor match the Vivado release (2026.1.x)
param block relocation targets=SLICE_X35Y57, SLICE_X41Y117, SLICE_X41Y177 (original block at SLICE_X35Y87) legal=only the anchor sites RapidWright lists as valid for the block's footprint
param chain placer=simulated annealing on whole slices, 200000 moves, window of 60 columns by 40 rows around GTHE4_CHANNEL_X0Y6 legal=any slice site of the same type inside the window that is free; slices with carry chains or LUT RAM stay

## files
designs/b100_rapidwright/docs/design.md 4afa1e7335: the design note written before the code, and what changed after it (section 6)
designs/b100_rapidwright/docs/what_we_found.md 6ee5acb0d8: the results with their tables, rendered from the summary record
designs/b100_rapidwright/docs/licences.md 4b545ec475: licences of RapidWright, its device files and the Java runtime, and what is committed
designs/b100_rapidwright/docs/tools.md 3de7472dc2: datasheet for the five agent tools and the scripts behind them
designs/b100_rapidwright/rtl/pcs_unit.sv c825d999f4: the relocatable block (brief 96's pcs_tx with its own source and sink, three input pins)
designs/b100_rapidwright/rtl/chain_top.sv 0204d59663: the transmit chain with a bare GT
designs/b100_rapidwright/scripts/run_c1.sh 501cd38a76: capability 1 end to end
designs/b100_rapidwright/scripts/run_c23.sh ea789b7cfd: capabilities 2 and 3 end to end
designs/b100_rapidwright/agent_run/run_arm.py e2b2564bca: the stage 2 agent runs, with and without the tools
flow/rw/place_chain.py d6e884f392: the annealing placer
flow/rw/route.py 2ddfda190f: RWRoute full and net-list routing
flow/rw/relocate.py d1fd27257f: block relocation
flow/rapidwright_pin.py 00b1af66eb: versions, hashes and paths of the RapidWright install

## commands
install RapidWright into a git-ignored venv (no root; downloads the jar from AMD's GitHub release) (~5min): tools/rapidwright_env/setup.sh
[heavy] capability 1 (block, relocation, stamp, Vivado alone), three site targets, two period perturbations (the stamp arm ran at 3.40 ns in both because of a clock override, see what_we_found.md) (~90min): PERIODS="3.40 3.41" designs/b100_rapidwright/scripts/run_c1.sh
[heavy] capabilities 2 and 3 on the chain, per period perturbation (~120min): BASE=3.40 STEPS="0 1" designs/b100_rapidwright/scripts/run_c23.sh
[heavy] the stage 2 agent runs (access key in .env; Claude Code token file) (~75min): python3 designs/b100_rapidwright/agent_run/run_arm.py a --max-turns 30 --minutes 75
tests that need neither tool (~1min): python3 -m pytest -q designs/b100_rapidwright/tests agent/tests/test_100_rapidwright.py

## records (path sha256-prefix; claims below cite R<n>)
R1 results/b100/summary.json e19da36328
R2 agent/tests/test_100_rapidwright.py ce04bcd03f

## evidence
E1 review pass R1: RapidWright reads and writes Vivado 2026.1 checkpoints for both parts and Vivado accepts them (route, DRC, bitstream)
E2 build pass R1: every comparison number is Vivado 2026.1 timing on a routed checkpoint (relocation, placement, routing runs)
E3 lint pass R2 ci: argument validation, fixed argv, refusals and the skip-without-RapidWright behaviour of the agent tools; the block-path analysis

## measured
M1 timing s0_k26_wns_after=0.218 ns R1#stage0.xck26.after_rapidwright_wns_ns: K26 checkpoint WNS after RapidWright read and write, Vivado route_design | s0_top at a 4 ns target, Vivado 2026.1, one thread; the value before the round trip is in the same record
M2 timing s0_a7_wns_after=-5.36 ns R1#stage0.xc7a100t.after_rapidwright_wns_ns: Artix-7 100T checkpoint WNS after RapidWright read and write, Vivado route_design | as M1; the 4 ns target is missed on this part before and after
M3 resources jvm_peak_gib=2.6 GiB R1#stage0.jvm_peak_gib_first_read: JVM scope peak memory on a first checkpoint read for the K26 | cgroup peak of the whole scope including the Vivado RapidWright starts; under 1 GiB when the EDIF is cached
M4 timing base_s0_period=3.776 ns R1#capabilities23.rows[0].achieved_period_ns: baseline chain, achieved period at a 3.40 ns target, Vivado alone, perturbation s0 | target minus whole-design WNS; chain_top on the K26, one thread, Vivado 2026.1
M5 latency base_s0_latency=7.552 ns R1#capabilities23.rows[0].chain_latency_ns_2clk: baseline chain, two-clock chain latency at that period | two registers on the wire-to-wire path (MAC output, PCS output) times the achieved period; the GT's own latency is not included
M6 resources base_lut=1768 LUT R1#capabilities23.rows[0].lut: baseline chain LUTs | as M4; the same count in every arm (RapidWright moves, it does not resynthesise)
M7 resources base_ff=414 FF R1#capabilities23.rows[0].ff: baseline chain flip-flops | as M4
M8 timing base_mean_period=3.95 ns R1#capabilities23.by_arm.base.achieved_period_ns_mean: mean achieved period, Vivado alone, over the perturbations | N runs in the record; perturbation is the target period (+0.01 ns each)
M9 timing place_mean_period=4.429 ns R1#capabilities23.by_arm.place.achieved_period_ns_mean: mean achieved period, our annealing placement then Vivado routing | as M8, the same placed checkpoints as M8 are the starting point
M10 timing rwr_mean_period=5.877 ns R1#capabilities23.by_arm.rwr.achieved_period_ns_mean: mean achieved period, RWRoute routing of Vivado's placement | as M8; Vivado checks and times, does not route
M11 timing fixed_mean_period=4.611 ns R1#capabilities23.by_arm.fixed.achieved_period_ns_mean: mean achieved period, RWRoute on the worst-path nets inside Vivado's routing | as M8
M12 other stamp_c3_identical=351 endpoints R1#capability1.blocks.stamp_p3_40.copies.3.endpoints_identical: stamped blocks, copy 3 endpoints with the same delay as copy 0 | of the endpoints common to both copies, period perturbation 3.40 ns, Vivado data-path delay
M13 other alone_c3_identical=6 endpoints R1#capability1.blocks.alone_p3_40.copies.3.endpoints_identical: Vivado alone, the same four-copy design, copy 3 endpoints with the same delay as copy 0 | as M12
M14 other agent_a_calls=12 calls R1#stage2.a.tool_calls: stage 2, tool calls of the arm with the RapidWright tools | Claude Sonnet 5.5, 30 turn cap, 75 minute cap, one run
M15 other agent_b_calls=15 calls R1#stage2.b.tool_calls: stage 2, tool calls of the arm without the RapidWright tools | as M14

## gaps
[power] Not measured; no power report was made for any run, and no bitstream of the chain exists.
[throughput] Not applicable to this work; the chain moves one 64-bit word a clock by construction and no throughput figure is claimed.
[board_run] No board was touched, so no claim is made that a faster chain survives the transceiver's own latency; that is a question for an owner session.
[seeds] Vivado's placer has no seed parameter, so a seed is a 0.01 ns step of the target period; two or three of them per capability, which shows scatter but is not a distribution.
[placer] The annealer is a first cut that minimises wire length with fixed weights; the comparison says nothing about what a timing-driven RapidWright placer would do.
[single_chain] One chain, one part (the K26 for all three capabilities; the Artix-7 only in stage 0), and the chain's GT is a bare primitive without the real clocking.
[block_interface] A pre-implemented block with a wide input bus could not be stamped in Vivado 2026.1 (input pins unreachable past locked routes); the block used has three input pins.
[stage2] Stage 2 is one run per arm; the arms differ in tools only, but the without arm's pblock build outlasted the tool call timeout, so its second attempt was never seen by the agent.
[review] One Sonnet review and one fix round per the check-once rule; the fixes are not re-reviewed.

## next_actions
1. Merge brief 97's latency path tool when it lands and give the placer its chain instead of the fixed cell patterns.
2. A timing-driven placer that takes criticality from Vivado's report each round, and RWRoute with Vivado's delay model, then repeat the comparison on the full brief 96 design.
3. Hand the stamped-block flow a wider interface by routing the block's input pins in context before locking its routes, or by reserving pin access in the out-of-context run.

## open_questions
- Does the relocatable block keep its delays on the Artix-7, where the column structure differs?

## history
2026-11-17 100 pr=-: stage 0, three capabilities, tools and the with-and-without agent runs
