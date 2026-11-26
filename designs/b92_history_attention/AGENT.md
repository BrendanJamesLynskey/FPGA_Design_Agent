# AGENT b92_history_attention (fda-handover/1)
source: designs/b92_history_attention/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b92_history_attention

## identity
kind=showcase produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM); also xc7a100tcsg324-1 (Nexys A7) out of context top=b92_<arm> (a stateful front end and a head), out of context, behind an input register tool=Vivado 2026.1
verified: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement (record: designs/b92_history_attention/VERIFIED.md, designs/b92_history_attention/verified.json; definition: docs/verified.md)

## summary
A gated study of whether order-flow history helps small integer classifiers on synthetic limit-order-book data, and what it costs in the fabric. A self-exciting generator (Hawkes-type arrivals, sign persistence, informed bursts) makes history matter; lagged features help the 87 trees (gate passed). On one common head, exponentially decaying sums and a learned fixed window each add about 0.015 test accuracy over the history-free head, while two softmax-free tiny attentions end about 0.012 below the decaying sums, so no attention block was built in Vivado. The stateful arms are bit-exact against a twin and built out of context on the K26 and the Artix-7 100T.
not: real market data; both generators are seeded synthetic order flow with planted structure; a board run or a full-design build; every hardware number is an out-of-context, post-route Vivado 2026.1 build; an attention block in the fabric: it lost at the stage 2 test, so its RTL was simulated against its twin but never built; a model of a real market; the clustering is exponential and short-memory (docs/what_we_found.md section 2)

## state
stage=built vivado=2026.1 kb_pin=6185830 build_id=None
gates: rtl_equals_twin=pass ooc_build_2026_1=pass board_run=not-run

## interface
clk clk 80.6MHz
rst rst active-high: synchronous; clears the valid pipeline and the front end's state (sums, window); never the datapath or out_cls
if arm ports clk, rst, in_v, in_f[50:0] (87 features, then ts+1, sv+8, ofi+31), out_v, out_cls[1:0]: state advances only on in_v; out_v follows in_v by exactly LATENCY clocks; ties go to the lower class doc=designs/b92_history_attention/docs/generator.md
if generator and training API Python (hist.hawkes_sim, hist.frontends, hist.attn, hist.stage2, hist.rtl): options and the behaviours a user could guess wrong are listed in the datasheet doc=designs/b92_history_attention/docs/generator.md
param decay rate pair=shifts 2 and 4 (chosen on validation from 1/3, 2/4, 3/5, 4/6) legal=any shift pair
param window length=8 and 16 events legal=any N
param attention=N=16, key size 4, value size 4, forms top1 and relu legal=fixed in this brief

## files
designs/b92_history_attention/hist/hawkes_sim.py 34ad166fc0: the self-exciting generator
designs/b92_history_attention/hist/prims.py ede1e37f5d: both generators behind one interface, history columns
designs/b92_history_attention/hist/gen_stats.py f279cbee31: generator statistics
designs/b92_history_attention/hist/stage1.py 7badb80dd2: stage 1, the gate
designs/b92_history_attention/hist/tokens.py ede96dfab1: tokens and split data
designs/b92_history_attention/hist/frontends.py f8ea826c77: decaying sums and window codes
designs/b92_history_attention/hist/attn.py e931c38ce7: tiny attention: trainer and integer twin
designs/b92_history_attention/hist/stage2.py 87ebb7bce6: stage 2 arms, freeze, test scoring
designs/b92_history_attention/hist/rtl.py a2a78de058: SystemVerilog emitters of the stateful arms
designs/b92_history_attention/hist/stream.py 78450c83cb: port packing and the stream twin
designs/b92_history_attention/hist/sim.py 40f06c15c1: Icarus runner
designs/b92_history_attention/hist/cli.py d8dac770a3: RTL generation
designs/b92_history_attention/hist/importance.py fdd9d9bb8f: tree split importance
designs/b92_history_attention/tb/tb_stream.sv c9bbb03986: stream test bench
designs/b92_history_attention/ooc/ooc.py b1b085d9e1: out-of-context clock search
designs/b92_history_attention/docs/design.md 6fec52d0aa: design note
designs/b92_history_attention/docs/preregistration.md abd96614e0: pre-registration, stages 0-1
designs/b92_history_attention/docs/preregistration_stage2.md 83c49887e1: pre-registration, stage 2
designs/b92_history_attention/docs/what_we_found.md c3c5c1eeea: the write-up
designs/b92_history_attention/docs/generator.md e952618e0f: datasheet
results/b92/summary.py 1ecc6d416d: summary and figures
results/b92/tables.py 4a451e5ecb: tables

## commands
generator statistics, stage 1 (validation, then test after the selection is committed) (~50min): python3 -m designs.b92_history_attention.hist.gen_stats && python3 -m designs.b92_history_attention.hist.stage1 val && python3 -m designs.b92_history_attention.hist.stage1 test
stage 2: fit, freeze, then score the test split (~45min): python3 -m designs.b92_history_attention.hist.stage2 fit && python3 -m designs.b92_history_attention.hist.stage2 freeze && python3 -m designs.b92_history_attention.hist.stage2 test
generate RTL, check against the twins, lint (~10min): python3 -m designs.b92_history_attention.hist.cli rtl && B92_RECORD=results/b92 python3 -m pytest -q designs/b92_history_attention/tests
[heavy] out-of-context builds and clock search on both parts (~240min): python3 -m designs.b92_history_attention.ooc.ooc --part xck26-sfvc784-2LV-c --arms b92_ref_current b92_a1_decay b92_a4_lut b92_a2_win8 b92_a2_win16 && python3 -m designs.b92_history_attention.ooc.ooc --part xc7a100tcsg324-1 --arms ... --start 30.0
summary, figures and tables (~1min): python3 results/b92/summary.py && python3 results/b92/tables.py

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b92_history_attention/tests/test_b92_rtl.py 44817e5f08
R2 results/b92/summary.json d5bf9a75c6

## evidence
E1 simulation pass R1 ci: every stateful arm equals its stream twin on all 100,000 events of the ten test sessions, 20,000 random events and 9,000 extreme-input events, with one fixed latency; Verilator -Wall clean
E2 build pass R2: out-of-context, post-route builds of five arms on the K26 and the Artix-7 100T with a clock search; every recorded clock closed setup, hold and pulse width

## measured
M1 other ref_current_acc=0.4844 fraction R2#arms.ref_current.test_accuracy: history-free head test accuracy | retained test rows of the 10 test sessions; synthetic self-exciting order flow; built seed
M2 other a1_decay_acc=0.4997 fraction R2#arms.a1_decay.test_accuracy: decaying sums test accuracy | ditto
M3 other a2_win8_acc=0.5008 fraction R2#arms.a2_win8.test_accuracy: window N=8 test accuracy | ditto
M4 other a2_win16_acc=0.5009 fraction R2#arms.a2_win16.test_accuracy: window N=16 test accuracy | ditto
M5 other a3_top1_acc=0.4873 fraction R2#arms.a3_top1.test_accuracy: attention top-1 test accuracy | ditto
M6 other a3_relu_acc=0.4878 fraction R2#arms.a3_relu.test_accuracy: attention ReLU-linear test accuracy | ditto
M7 other a4_lut_acc=0.4885 fraction R2#arms.a4_lut.test_accuracy: LUT net on the sums test accuracy | ditto
M8 other decay_vs_head=0.0153 fraction R2#arms.a1_decay.paired_vs.ref_current.difference_mean: decaying sums minus the history-free head, paired | built seeds; 95% interval in the record
M9 other attn_top1_vs_decay=-0.0124 fraction R2#attention_vs_decay.a3_top1.difference_mean: attention top-1 minus decaying sums, paired | ditto
M10 other gate_difference=0.0067 fraction R2#gate.gate_difference.hawkes.mean: gate: lagged-feature trees minus current-feature trees, self-exciting generator | 3-seed mean per session; 95% interval in the record
M11 resources ref_current_k26_lut=1619 LUT R2#arms.ref_current.hardware.k26.lut: ref_current K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M12 latency ref_current_k26_lat=10.2 ns R2#arms.ref_current.hardware.k26.latency_ns: ref_current K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M13 resources ref_current_a7_lut=1214 LUT R2#arms.ref_current.hardware.a7.lut: ref_current Artix-7 LUTs | out of context, post-route, Vivado 2026.1, one thread
M14 latency ref_current_a7_lat=30.55 ns R2#arms.ref_current.hardware.a7.latency_ns: ref_current Artix-7 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M15 resources a1_decay_k26_lut=2313 LUT R2#arms.a1_decay.hardware.k26.lut: a1_decay K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M16 latency a1_decay_k26_lat=24.8 ns R2#arms.a1_decay.hardware.k26.latency_ns: a1_decay K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M17 resources a1_decay_a7_lut=2127 LUT R2#arms.a1_decay.hardware.a7.lut: a1_decay Artix-7 LUTs | out of context, post-route, Vivado 2026.1, one thread
M18 latency a1_decay_a7_lat=64.1 ns R2#arms.a1_decay.hardware.a7.latency_ns: a1_decay Artix-7 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M19 resources a4_lut_k26_lut=554 LUT R2#arms.a4_lut.hardware.k26.lut: a4_lut K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M20 latency a4_lut_k26_lat=9 ns R2#arms.a4_lut.hardware.k26.latency_ns: a4_lut K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M21 resources a4_lut_a7_lut=441 LUT R2#arms.a4_lut.hardware.a7.lut: a4_lut Artix-7 LUTs | out of context, post-route, Vivado 2026.1, one thread
M22 latency a4_lut_a7_lat=27.9 ns R2#arms.a4_lut.hardware.a7.latency_ns: a4_lut Artix-7 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M23 resources a2_win8_k26_lut=3250 LUT R2#arms.a2_win8.hardware.k26.lut: a2_win8 K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M24 latency a2_win8_k26_lat=26.5 ns R2#arms.a2_win8.hardware.k26.latency_ns: a2_win8 K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M25 resources a2_win8_a7_lut=2882 LUT R2#arms.a2_win8.hardware.a7.lut: a2_win8 Artix-7 LUTs | out of context, post-route, Vivado 2026.1, one thread
M26 latency a2_win8_a7_lat=70.3 ns R2#arms.a2_win8.hardware.a7.latency_ns: a2_win8 Artix-7 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M27 resources a2_win16_k26_lut=5372 LUT R2#arms.a2_win16.hardware.k26.lut: a2_win16 K26 LUTs | out of context, post-route, Vivado 2026.1, one thread
M28 latency a2_win16_k26_lat=26.8 ns R2#arms.a2_win16.hardware.k26.latency_ns: a2_win16 K26 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1
M29 resources a2_win16_a7_lut=4482 LUT R2#arms.a2_win16.hardware.a7.lut: a2_win16 Artix-7 LUTs | out of context, post-route, Vivado 2026.1, one thread
M30 latency a2_win16_a7_lat=72.7 ns R2#arms.a2_win16.hardware.a7.latency_ns: a2_win16 Artix-7 latency | clocks x max(closed period, 2.0 ns); out of context, Vivado 2026.1

## gaps
[board_run] Not run on a board and not built inside the 58A top; out of context only.
[timing] Out of context the clock has no buffer or jitter, so every latency is quoted at no faster than 2.0 ns; the arms have two registered stages before the output (three for attention).
[power] Not measured; the out-of-context builds have no power report.
[data] Two synthetic generators with planted structure; the ranking of history mechanisms may not hold on real order flow.
[attention] Attention was trained with a throwaway head, frozen, then given the common head; its negative result holds for that recipe only. It was not built in Vivado.
[comparison] Many paired intervals over 10 sessions, uncorrected; the gain of the sums over the history-free head has a lower bound of +0.004.
[throughput] Every arm accepts one event a clock (the RTL test streams half the events back to back).
[behaviour] Guessable wrongly: state is cleared by rst and advances only on in_v; the first N outputs after a reset use an empty history; shifts floor; ties go to the lower class and, in attention, to the most recent event.

## next_actions
1. End-to-end training of attention and head, with learned shifts, on a generator whose relevant events depend on context.
2. Merge the front end and the head into one clock and measure the period it costs.
3. Weights written by the slow loop through a descriptor with a model id and schema check (87 phase 2).

## open_questions
- Would a power-of-two softmax approximation close the gap, or is the data simply too simple for content-dependent weights?

## history
2026-11-16 92 pr=-: generator, gated stages, pre-registered scoring, stateful RTL, out-of-context builds on both parts, write-up
