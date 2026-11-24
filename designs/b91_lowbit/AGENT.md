# AGENT b91_lowbit (fda-handover/1)
source: designs/b91_lowbit/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b91_lowbit

## identity
kind=showcase produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM); also xc7a100tcsg324-1 (Nexys A7) out of context top=ooc_wrap (one generated network with an input register), out of context tool=Vivado 2026.1

## summary
A generator and a measurement of eight weight formats for tiny integer networks: binary, ternary, INT4, an MXFP4-style E2M1 format with a power-of-two scale, our power-of-two format log4 (with and without a zero) and a two-term log4+1. Each is trained with its quantiser in the loop, exported to integers, checked against a bit-exact Python twin and generated RTL, and built out of context on the K26 and the Artix-7 100T. On the brief 87 synthetic order flow the 4-bit-weight formats match the 89 LUT network and the 87 trees on accuracy but need about four times the LUTs, so no format is on the accuracy-against-area or accuracy-against-latency front.
not: real market data; the data are brief 87's seeded synthetic order flow with a planted signal; a board run or a full-design build; every hardware number is an out-of-context, post-route Vivado 2026.1 build; weights held in block RAM (the phase-2 student): phase 1 weights are constants; docs/stage2_plan.md is a plan only; a general-purpose tool; the argmax is written for three classes and the networks have at most two hidden layers

## state
stage=built vivado=2026.1 kb_pin=5e2eab8 build_id=None
gates: rtl_equals_twin=pass ooc_build_2026_1=pass board_run=not-run

## interface
clk clk 98MHz
rst rst active-high: synchronous; clears only the valid pipeline, never the datapath (out_cls is undefined until the first out_v)
if network ports clk, rst, in_v, in_f[37:0] (packed 87 features, feature 0 in the low bits), out_v, out_cls[1:0]: out_v follows in_v by exactly LATENCY clocks for every input; one input a clock; ties go to the lower class doc=designs/b91_lowbit/docs/generator.md
if generator API and options Python (lowbit.model.Config, train, twin_predict; lowbit.rtl.emit) and flow/lowbit.py: every option with its default and the behaviours a user could guess wrong (rounding, zero, scale as a shift, floor, tie to lowest class) doc=designs/b91_lowbit/docs/generator.md
param format=binary_t3, binary_t7, ternary, int4, mxfp4, log4, log4_nz, log4p1 legal=the same
param pipe=comb and layer (A = 4 networks); comb only for the A = 2 and 8 sweep legal=comb, layer
param act_bits=4 (binary: 1); 2 and 8 for log4 and mxfp4 legal=any positive width up to the 8-bit feature width

## files
designs/b91_lowbit/lowbit/formats.py bad7171fd9: the formats: element grids, rounding, CSD
designs/b91_lowbit/lowbit/model.py f93660b3c4: trainer, exporter, integer twin, accumulator bounds
designs/b91_lowbit/lowbit/rtl.py ce48e1f084: SystemVerilog emitter
designs/b91_lowbit/lowbit/cli.py 29c3a4f74f: stage 1, selection, stage 2, freeze, RTL
designs/b91_lowbit/lowbit/evaluate.py a22df91a93: test-split scoring (pre-registered)
designs/b91_lowbit/lowbit/seedmean.py e58da4229f: post-hoc seed-mean comparison
designs/b91_lowbit/ooc/ooc.py f2024cd5cd: out-of-context clock search
designs/b91_lowbit/docs/design.md 388ef95201: design note
designs/b91_lowbit/docs/preregistration.md 0fd6397eca: pre-registration
designs/b91_lowbit/docs/what_we_found.md dea94c4fb2: the write-up
designs/b91_lowbit/docs/stage2_plan.md 71bfdf7f35: plan: FP4 hardware for the phase-2 student
flow/lowbit.py 8c56739acc: flow tool: train, emit, predict

## commands
train all stage 1 networks, select, sweep, freeze, emit RTL (~75min): python3 -m designs.b91_lowbit.lowbit.cli stage1 && python3 -m designs.b91_lowbit.lowbit.cli select && python3 -m designs.b91_lowbit.lowbit.cli stage2 && python3 -m designs.b91_lowbit.lowbit.cli freeze && python3 -m designs.b91_lowbit.lowbit.cli rtl
score the test split (after frozen.json is committed) (~2min): python3 -m designs.b91_lowbit.lowbit.evaluate && python3 -m designs.b91_lowbit.lowbit.seedmean
RTL against the twins, lint (~6min): B91_RECORD=results/b91 python3 -m pytest -q designs/b91_lowbit/tests flow/tests/test_91_lowbit_rtl.py
[heavy] out-of-context builds and clock search on both parts (~480min): python3 -m designs.b91_lowbit.ooc.ooc --part xck26-sfvc784-2LV-c --arms <modules> --start 3.0
summary, figures and tables (~1min): python3 results/b91/summary.py && python3 results/b91/tables.py

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b91_lowbit/tests/test_b91_rtl.py ecaaa4a511
R2 results/b91/summary.json 3dfc25ab7e
R3 results/b91/accuracy.json f2b0902973
R4 results/b91/accuracy_seedmean.json f0841f2ed7

## evidence
E1 simulation pass R1 ci: every generated network equals its twin on all 99,100 test samples and 20,000 random packed inputs with one fixed latency; accumulators stay inside their computed bounds; binary XNOR form equals the integer form; Verilator -Wall clean
E2 build pass R2: out-of-context, post-route builds on the K26 and the Artix-7 100T with a clock search; every recorded clock closed setup, hold and pulse width

## measured
M1 other log4_acc=0.4884 fraction R3#networks.log4_h16x8_a4.runs[0].test.mean: log4 test accuracy | 99,100 test samples in 10 sessions; synthetic order flow; built seed
M2 other log4_nz_acc=0.4919 fraction R3#networks.log4_nz_h16x8_a4.runs[0].test.mean: log4_nz test accuracy | ditto
M3 other int4_acc=0.489 fraction R3#networks.int4_h16x8_a4.runs[1].test.mean: int4 test accuracy | ditto
M4 other mxfp4_acc=0.4878 fraction R3#networks.mxfp4_h16x8_a4.runs[0].test.mean: mxfp4 test accuracy | ditto
M5 other binary_t3_acc=0.4733 fraction R3#networks.binary_t3_h8_a4.runs[0].test.mean: binary_t3 test accuracy | ditto
M6 other log4_vs_rule=0.0618 fraction R3#networks.log4_h16x8_a4.paired_vs.trivial_rule_87.difference_mean: log4 minus the 87 trivial rule, paired | 99,100 test samples in 10 sessions; synthetic order flow; built seed; 95% interval in the record
M7 other log4_vs_lgsmall_seedmean=-0.0015 fraction R4#networks.log4_h16x8_a4.paired_vs.lg_small.difference_mean: log4 seed-mean minus lg_small, paired (post hoc) | mean of 3 seeds per session; 95% interval in the record
M8 resources log4_h16x8_a4_comb_k26_lut=1591 LUT R2#rows[13].k26.lut: log4 comb, K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M9 latency log4_h16x8_a4_comb_k26_lat=10.2 ns R2#rows[13].k26.latency_ns: log4 comb, K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M10 resources int4_h16x8_a4_comb_k26_lut=2068 LUT R2#rows[6].k26.lut: int4 comb, K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M11 latency int4_h16x8_a4_comb_k26_lat=10.05 ns R2#rows[6].k26.latency_ns: int4 comb, K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M12 resources mxfp4_h16x8_a4_comb_k26_lut=2056 LUT R2#rows[9].k26.lut: mxfp4 comb, K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M13 latency mxfp4_h16x8_a4_comb_k26_lat=11.25 ns R2#rows[9].k26.latency_ns: mxfp4 comb, K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M14 resources log4_nz_h16x8_a4_comb_k26_lut=1406 LUT R2#rows[16].k26.lut: log4_nz comb, K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M15 latency log4_nz_h16x8_a4_comb_k26_lat=11 ns R2#rows[16].k26.latency_ns: log4_nz comb, K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M16 resources binary_t3_h8_a4_comb_k26_lut=209 LUT R2#rows[0].k26.lut: binary_t3 comb, K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M17 latency binary_t3_h8_a4_comb_k26_lat=3.3 ns R2#rows[0].k26.latency_ns: binary_t3 comb, K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M18 latency log4_nz_a7_lat=29.5 ns R2#rows[16].a7.latency_ns: log4_nz comb, Artix-7 100T latency | xc7a100tcsg324-1, as the K26 rows

## gaps
[board_run] Not run on a board and not built inside the 58A top; out of context only.
[timing] Out of context the clock has no buffer or jitter, so every latency is quoted at no faster than 2.0 ns.
[power] Not measured; the out-of-context builds have no power report.
[data] One synthetic data set and one planted signal; the ranking of formats may not hold elsewhere.
[scale] Scales are powers of two; a real-valued per-neuron scale was not tried, so the accuracy price of the restriction is unknown.
[comparison] The formats use two shapes and the rule chose different shapes per format, so cross-format area compares format and size together; the networks are not tuned per format.
[phase2] Weights here are constants. Where weights live in block RAM the cost of each format changes; docs/stage2_plan.md is a plan, not a measurement.
[throughput] Every network accepts one input a clock (the RTL test streams half the inputs back to back); no separate throughput figure is recorded.
[behaviour] Guessable wrongly: rounding is linear nearest with ties to the even code index; the scale is a right shift that floors; class-score ties go to the lowest class; binary and log4_nz have no zero weight.

## next_actions
1. A LUT-network hybrid: enumerate quantised neurons into tables.
2. Trained sparsity and narrower accumulators for ternary and log4.
3. A real-valued per-neuron scale as an ablation.
4. The stage 2 plan for weights in block RAM.

## open_questions
- Is the gap to the 89 LUT networks the adder trees alone, or also the missing table-level nonlinearity?

## history
2026-11-16 91 pr=-: design, generator, pre-registered scoring, out-of-context builds on both parts, write-up
