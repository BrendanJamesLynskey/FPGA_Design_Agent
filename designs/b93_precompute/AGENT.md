# AGENT b93_precompute (fda-handover/1)
source: designs/b93_precompute/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b93_precompute

## identity
kind=showcase produced_by=session part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM); also xc7a100tcsg324-1 (Nexys A7) out of context top=ooc_wrap (one block with input registers), out of context; the integration is trigger_core in simulation tool=Vivado 2026.1
verified: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement (record: designs/b93_precompute/VERIFIED.md, designs/b93_precompute/verified.json; definition: docs/verified.md)

## summary
Measures how much of the brief 87 decision model can be done while a message is still arriving. The model's inputs turn out to be known three clocks before the price field, so computing the features early removes the one or three clocks the model added to the 58A path, at no LUT cost. A table of the model's class per interval of its deepest feature (partial evaluation) is built for the 87 trees and the 89 lg_small network and measured, and it saves nothing in clocks in this design.
not: real market data or a real exchange feed; the data are brief 87's seeded synthetic order flow and our own Bench Feed v1 format; a board run or a full-design build of ML_PRE 1 to 3; every hardware number is an out-of-context, post-route Vivado 2026.1 block build; a model that uses the message's own price; none exists in this programme, and every arm must equal the 87 integer model

## state
stage=built vivado=2026.1 kb_pin=eaf6794 build_id=None
gates: rtl_equals_twin=pass ooc_build_2026_1=pass board_run=not-run

## interface
clk clk 166.7MHz
rst rst active-high: synchronous; clears the valid pipeline and, in the feature unit and gate, the state; never the table or datapath of a table block
if table block ports clk, rst, e_v, e_f[37:0], l_v, l_x[7:0], out_v, out_cls[1:0]: l_v must come FILL clocks after e_v and no later than FILL - 1 clocks after the next e_v; out_v is l_v delayed by exactly one clock doc=designs/b93_precompute/docs/blocks.md
if trigger_core parameters ML_ARM and ML_PRE ML_ARM and ML_PRE, integer parameters: ML_PRE 0 is the 87 behaviour and the default; registers 0x02A-0x02C are unchanged doc=designs/b93_precompute/docs/blocks.md
param ML_PRE=0 (default), 1, 2 and 3 all built in simulation legal=0 to 3; 2 and 3 need ML_ARM 1 or 4

## files
designs/b93_precompute/model/gen_rtl.py 47e61982fe: generator of the table blocks
designs/b93_precompute/rtl/ml_feat_pre.sv 8745a2f49b: early feature unit
designs/b93_precompute/rtl/ml_gate_pre.sv b69f63825b: gate for an early class
designs/b58a_trigger/rtl/trigger_core.sv 802883690b: ML_PRE and ML_ARM 4 added (defaults unchanged)
designs/b93_precompute/ooc/ooc.py 950817e484: out-of-context clock search on both parts

## commands
table blocks against the 87 and 89 models, feature unit in lockstep, gate timing (~3min): B93_RECORD=results/b93 python3 -m pytest -q designs/b93_precompute/tests/test_b93_pe_rtl.py designs/b93_precompute/tests/test_b93_feat_pre_rtl.py
the model behind trigger_core for one ML_ARM and ML_PRE (~1min): B93_ML_ARM=1 B93_ML_PRE=1 B93_RECORD=results/b93 python3 -m pytest -q designs/b93_precompute/tests/test_b93_integ_rtl.py
[heavy] out-of-context builds and clock search on both parts (~180min): python3 -m designs.b93_precompute.ooc.ooc --part xck26-sfvc784-2LV-c --arms gbt_comb lg_small_comb gbt_pe gbt_pe2 lgs_pe lgs_pe2 ml_feat ml_feat_pre

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b93_precompute/tests/test_b93_pe_rtl.py 06d5a9a3a1
R2 results/b93/summary.json f6e69c7195

## evidence
E1 simulation pass R1 ci: every table block equals its 87 or 89 model on the test split, 20,000 random vectors and every late value, with out_v exactly one clock after l_v; Verilator -Wall clean
E2 build pass R2: out-of-context, post-route builds of eight blocks on the K26 and the Artix-7 100T with a clock search; every recorded clock closed setup, hold and pulse width

## measured
M1 latency gbt_gate_clocks_baseline=1 clocks R2#integration.gbt_pre0.gate_added_clocks: trees baseline, clocks the gate adds, simulation | 58A trigger_core at the 8 ns core clock, Icarus simulation, speculative mode
M2 latency gbt_gate_clocks_early=0 clocks R2#integration.gbt_pre1.gate_added_clocks: trees with early features, clocks the gate adds | as M1
M3 latency tick_to_decision_baseline=4 clocks R2#integration.gbt_pre0.tick_to_decision_clocks: last price byte to decision, baseline trees | ditto
M4 latency tick_to_decision_early=3 clocks R2#integration.gbt_pre1.tick_to_decision_clocks: last price byte to decision, early features | ditto
M5 latency gbt_comb_k26_ns=4.3 ns R2#ooc.k26.gbt_comb.quoted_ns: gbt_comb, K26 closed period | 1 clock, out of context, post-route, Vivado 2026.1, one thread
M6 resources gbt_comb_k26_lut=641 LUT R2#ooc.k26.gbt_comb.lut: gbt_comb, K26 LUTs | as M5
M7 latency gbt_pe2_k26_ns=4.15 ns R2#ooc.k26.gbt_pe2.quoted_ns: gbt_pe2 (table, fill 2), K26 closed period | ditto
M8 resources gbt_pe2_k26_lut=1692 LUT R2#ooc.k26.gbt_pe2.lut: gbt_pe2, K26 LUTs | ditto
M9 latency lg_small_comb_k26_ns=4.45 ns R2#ooc.k26.lg_small_comb.quoted_ns: lg_small_comb, K26 closed period | ditto
M10 latency lgs_pe2_k26_ns=2.95 ns R2#ooc.k26.lgs_pe2.quoted_ns: lgs_pe2 (table, fill 2), K26 closed period | ditto
M11 resources lgs_pe2_k26_lut=867 LUT R2#ooc.k26.lgs_pe2.lut: lgs_pe2, K26 LUTs | ditto
M12 latency ml_feat_pre_k26_ns=6 ns R2#ooc.k26.ml_feat_pre.quoted_ns: ml_feat_pre (early feature unit), K26 closed period | ditto
M13 resources ml_feat_pre_k26_ff=596 FF R2#ooc.k26.ml_feat_pre.ff: ml_feat_pre, K26 flip-flops (wrapper included) | ditto

## gaps
[board_run] Not run on a board and not built inside the 58A top; ML_PRE 1 to 3 are simulation only.
[timing] Out of context the clock has no buffer or jitter, so every latency is quoted at no faster than 2.0 ns; the bypass path of the gate is not in the block builds.
[power] Not measured; the out-of-context builds have no power report.
[throughput] Every block accepts one input a clock (the test streams half the vectors back to back); no separate throughput figure is recorded.
[data] One synthetic data set and one set of 87 features; none of them uses the message's own price, which is why the table arm gains nothing in clocks.
[behaviour] Guessable wrongly: state is committed at the price field, not at the early clock; a table block answers with another message's table if l_v breaks the timing contract and nothing detects it; the late feature is delayed by the fill in trigger_core, it is not really late.

## next_actions
1. Build the KR260 top with ML_PRE 1 and ML_ARM 4, then a board run.
2. Train a model with the message's own price as an input (for example inside or outside the touch) and measure the table arm on it.
3. Pipeline the table fill inside the model, not only at the scores, to see whether the table block can beat its baseline clock for trees.

## open_questions
- Is one core clock worth the extra flip-flops of the early feature unit on the board, or is the rule table the longer path to shorten next?

## history
2026-11-17 93 pr=-: stage 0, early feature unit, table blocks, integration for both models, out-of-context builds on both parts
