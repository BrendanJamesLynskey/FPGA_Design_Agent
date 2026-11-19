# AGENT b89_lutnet_gen (fda-handover/1)
source: designs/b89_lutnet_gen/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b89_lutnet_gen

## identity
kind=showcase produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM); also xc7a100tcsg324-1 (Nexys A7) out of context top=ooc_wrap (one generated network with an input register), out of context tool=Vivado 2026.1

## summary
Our own generator of LUT networks for nanosecond inference. It trains a sparse network with its quantisers in the loop, enumerates every neuron into a truth table, and emits SystemVerilog plus a bit-exact Python twin, with a choice of pipelining. On the brief 87 synthetic order-flow data its best network beats the trivial rule and equals the 87 boosted trees on the test split; it is built out of context on the K26 and the Artix-7 100T beside TreeLUT, the published tree-to-LUT tool, as the reference.
not: real market data; the data are brief 87's seeded synthetic order flow with a planted signal; a board run or a full-design build; every hardware number is an out-of-context, post-route Vivado 2026.1 build; a general-purpose tool; the argmax is written for three classes, and the generator has been measured on one data set

## state
stage=built vivado=2026.1 kb_pin=2338b83 build_id=None
gates: rtl_equals_twin=pass ooc_build_2026_1=pass board_run=not-run

## interface
clk clk 202MHz
rst rst active-high: synchronous; clears only the valid pipeline, never the datapath (out_cls is undefined until the first out_v)
if network ports clk, rst, in_v, in_f[37:0] (packed 87 features, feature 0 in the low bits), out_v, out_cls[1:0]: out_v follows in_v by exactly LATENCY clocks for every input; one input a clock; ties go to the lower class doc=designs/b89_lutnet_gen/docs/generator.md
if generator API and options Python (lutgen.model.Config, train, twin_predict; lutgen.rtl.emit): every option with its default and the behaviours a user could guess wrong (table address order, pass-through codes, best-validation epoch, pipelining definition) doc=designs/b89_lutnet_gen/docs/generator.md
param pipe=comb and layer (both built) legal=comb, layer, or a positive integer N (a register after every N-th LUT layer)
param arm=lg_add, lg_small, lg_b87 (results/b89/frozen.json) legal=any configuration of lutgen.model.Config; tables of at most 2^12 entries

## files
designs/b89_lutnet_gen/lutgen/model.py 7cec5eabcd: training, encoder, wiring, enumeration, twin
designs/b89_lutnet_gen/lutgen/rtl.py 7edb6e722b: SystemVerilog emitter
designs/b89_lutnet_gen/lutgen/cli.py 65570849ed: trains the frozen arms, emits rtl/gen
designs/b89_lutnet_gen/lutgen/evaluate.py 85f75e581c: test-split scoring
designs/b89_lutnet_gen/diag/diagnose.py b8b335f50b: the diagnosis of the 87 network
designs/b89_lutnet_gen/treelut_ref/run_treelut.py 7aaa76f5e3: TreeLUT reference (pinned)
designs/b89_lutnet_gen/ooc/ooc.py 441d9a2b5d: out-of-context clock search on both parts
designs/b89_lutnet_gen/docs/preregistration.md 19c3a745fb: pre-registration

## commands
diagnosis of the 87 network (train and validation only) (~45min): python3 -m designs.b89_lutnet_gen.diag.diagnose
a design round on validation (r1, r2, r3, fanin) (~15min): python3 -m designs.b89_lutnet_gen.lutgen.explore r3
train the frozen arms, emit the RTL, score the test split (~10min): python3 -m designs.b89_lutnet_gen.lutgen.cli train && python3 -m designs.b89_lutnet_gen.lutgen.cli rtl && python3 -m designs.b89_lutnet_gen.lutgen.evaluate
TreeLUT reference (its own venv) (~5min): ~/Claude_sandbox/_worktrees/89-treelut/venv/bin/python -m designs.b89_lutnet_gen.treelut_ref.run_treelut tune
RTL against the twins, lint (~2min): B89_RECORD=results/b89 python3 -m pytest -q designs/b89_lutnet_gen/tests/test_b89_rtl.py
[heavy] out-of-context builds and clock search on both parts (~90min): python3 -m designs.b89_lutnet_gen.ooc.ooc --part xck26-sfvc784-2LV-c --arms lg_add_comb lg_add_layer lg_small_comb lg_small_layer lg_b87_comb lg_b87_layer treelut_arm

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b89_lutnet_gen/tests/test_b89_rtl.py 3d9eb57504
R2 results/b89/summary.json 48b73dd7e4
R3 results/b89/accuracy.json b2f23ad7c2

## evidence
E1 simulation pass R1 ci: every generated network equals its twin on all 99,100 test samples and 20,000 random packed inputs with one fixed latency; every table cell in the RTL equals the model; Verilator -Wall clean; TreeLUT's Verilog equals TreeLUT
E2 build pass R2: out-of-context, post-route builds on the K26 and the Artix-7 100T with a clock search; every recorded clock closed setup, hold and pulse width

## measured
M1 other lg_add_acc=0.4913 fraction R3#arms.lg_add.runs[0].test.mean: lg_add (built seed), test accuracy | 99,100 test samples in 10 sessions; synthetic order flow
M2 other lg_add_vs_rule=0.0646 fraction R3#arms.lg_add.paired_vs.trivial_rule_87.difference_mean: lg_add minus the 87 trivial rule, paired test difference | as M1; 95% interval in the record
M3 other lg_add_vs_trees=-0.0002 fraction R3#arms.lg_add.paired_vs.trees_87.difference_mean: lg_add minus the 87 boosted trees, paired test difference | as M1
M4 other treelut_acc=0.4983 fraction R3#treelut.seed0.mean: TreeLUT seed 0, test accuracy | ditto
M5 latency lg_add_k26_lat=4.95 ns R2#rows[0].k26.latency_ns: lg_add_comb, K26 latency | 1 clock at the closed period, out of context, Vivado 2026.1, one thread
M6 resources lg_add_k26_lut=882 LUT R2#rows[0].k26.lut: lg_add_comb, K26 LUTs | as M5
M7 latency lg_small_k26_lat=4.5 ns R2#rows[2].k26.latency_ns: lg_small_comb, K26 latency | ditto
M8 resources lg_small_k26_lut=325 LUT R2#rows[2].k26.lut: lg_small_comb, K26 LUTs | ditto
M9 latency treelut_k26_lat=7.5 ns R2#rows[6].k26.latency_ns: TreeLUT (pipeline [0,1,1] + output register), K26 latency | 3 clocks at the closed period, as M5
M10 resources treelut_k26_lut=869 LUT R2#rows[6].k26.lut: TreeLUT, K26 LUTs | as M5
M11 latency lg_add_a7_lat=13.85 ns R2#rows[0].a7.latency_ns: lg_add_comb, Artix-7 100T latency | xc7a100tcsg324-1, as M5

## gaps
[board_run] Not run on a board and not built inside the 58A top; out of context only.
[timing] Out of context the clock has no buffer or jitter, so every latency is quoted at no faster than 2.0 ns.
[power] Not measured; the out-of-context builds have no power report.
[throughput] Every network accepts one input a clock (the RTL test streams half the inputs back to back); no separate throughput figure is recorded.
[data] One synthetic data set; the generator's ranking against trees and MLPs may not hold elsewhere.
[treelut] TreeLUT is tuned for accuracy on a small grid with 8-bit inputs; a cost-tuned point could be smaller, and only its seed 0 is built while our built seed is chosen on validation.
[behaviour] Guessable wrongly: the model returned by training is the best validation epoch, not the last; narrow features pass through exactly and use fewer code bits than asked; class-score ties go to the lower class (their share of test rows is tie_share_test_built_seed in results/b89/accuracy.json).

## next_actions
1. Learned wiring (pruning and regrowth) in place of random triples.
2. Put lg_small behind the 58A rule table in place of the 87 LUT network and build the KR260 top.
3. A cost-tuned TreeLUT point for an area comparison at equal accuracy.

## open_questions
- Is the remaining 0.007 to the MLP and TreeLUT worth more tables, or is the label noise the limit?

## history
2026-11-16 89 pr=-: diagnosis, generator, three design rounds, pre-registered test scoring, TreeLUT reference, out-of-context builds
