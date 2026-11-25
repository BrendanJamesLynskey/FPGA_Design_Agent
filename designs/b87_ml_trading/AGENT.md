# AGENT b87_ml_trading (fda-handover/1)
source: designs/b87_ml_trading/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b87_ml_trading

## identity
kind=showcase produced_by=session part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM) top=ooc_wrap (one arm with an input register), out of context; trigger_core with ML_ARM = 1 in simulation tool=Vivado 2026.1

## summary
Small decision models for the 58A trading path, trained on synthetic order flow and built in the fabric of the K26 (Kria KR260). Boosted trees, an MLP built by hand and through hls4ml with Vitis HLS, and a LUT network are each checked bit for bit against their integer models over the whole test split, built out of context and routed, and the boosted trees sit behind the 58A rule table in simulation, switched by a register.
not: real market data or a real exchange; the order flow comes from our own seeded generator with a planted signal; a board run; every number here is from simulation or an out-of-context Vivado 2026.1 build; a trading result; the back-test's fill model is an assumption and its differences are within noise

## state
stage=built vivado=2026.1 kb_pin=5e2eab8 build_id=None
gates: rtl_equals_model=pass ooc_build_2026_1=pass board_run=not-run

## interface
clk clk 125MHz
rst rst active-high: synchronous; resets only the valid pipeline of an arm and the feature unit's state, not the datapath
if arm ports clk, rst, in_v, in_f[37:0] (packed features), out_v, out_cls[1:0]: out_v follows in_v by exactly LATENCY clocks for every input; one input a clock; ties go to the lower class doc=designs/b87_ml_trading/docs/arms.md
if model control in trigger_core registers 0x02A ML_CTRL (enable, tracked instrument), 0x02B ML_LAST_CLASS, 0x02C ML_VETOES: with ML_ARM = 0 (the default) the 58A path is unchanged and the registers read 0, 1 and 0 doc=designs/b87_ml_trading/docs/arms.md
param ML_ARM=0 in 58A, 1 in the integration test legal=0 none, 1 gbt_comb, 2 lutnet; 3 (mlp_hand, 13 clocks) is refused because an arm's LATENCY must be at most 8 clocks
param label horizon=40 events legal=any positive integer (model/lobsim.py Params.horizon)
param training seed built=seed 0 of three legal=0, 1 or 2 (the evaluation trains all three)

## files
designs/b87_ml_trading/model/lobsim.py 6e6c8c3f87: order-flow generator, features, label, splits
designs/b87_ml_trading/model/arms.py 83acd888cb: the arms and their integer models
designs/b87_ml_trading/model/evaluate.py 5378839b18: training and scoring
designs/b87_ml_trading/model/gen_rtl.py 2b093862ec: RTL generator
designs/b87_ml_trading/rtl/ml_feat.sv 74e91004bc: feature unit for the 58A book
designs/b87_ml_trading/rtl/ml_gate.sv 69ffe79a20: model gate behind the rules
designs/b87_ml_trading/ooc/ooc.py 2660202d6c: out-of-context clock search
designs/b87_ml_trading/docs/preregistration.md ced929e6b6: pre-registration

## commands
train and score every arm (~17min): python3 -m designs.b87_ml_trading.model.evaluate --out results/b87
regenerate the RTL and check it against the models over the test split (~3min): python3 -m designs.b87_ml_trading.model.gen_rtl && B87_RECORD=results/b87 python3 -m pytest -q designs/b87_ml_trading/tests/test_b87_rtl.py
the 58A integration in simulation (~1min): B87_RECORD=$PWD/results/b87/integration python3 -m pytest -q designs/b87_ml_trading/tests/test_b87_integ_rtl.py
[heavy] hls4ml conversion, C simulation and Vitis HLS (~3min): python3 -m designs.b87_ml_trading.model.hls4ml_arm --synth --clock 2.0
[heavy] out-of-context builds and the clock search (~60min): python3 -m designs.b87_ml_trading.ooc.ooc

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b87_ml_trading/tests/test_b87_rtl.py 2ffcf72e10
R2 results/b87/hls4ml_csim.json d00b95f079
R3 designs/b87_ml_trading/tests/test_b87_integ_rtl.py 02050fb09d
R4 results/b87/summary.json 1625246873
R5 results/b87/accuracy.json dad79e6188
R6 results/b87/ooc/gbt_comb.json bd70057950
R7 results/b87/integration/integration_latency_sim.json 0b7136ae81
R8 results/b87/ooc/mlp_hand.json 182a6d2338
R9 results/b87/ooc/mlp_hls4ml.json eb7c3afa06

## evidence
E1 simulation pass R1 ci: every hand-RTL arm equals its integer model on all test-split samples, with one fixed latency
E2 simulation pass R2: the hls4ml arm's C simulation equals the integer model's logits bit for bit, and its Verilog equals it in Icarus with a fixed latency
E3 simulation pass R3 ci: trigger_core with the boosted trees (and again with the LUT network); the fabric's features and classes equal the Python twin on a generator stream and on 300 edge-case messages, and a disagreeing order is vetoed and counted
E4 build pass R4: out-of-context, post-route builds of every arm on the K26 with a clock search; each recorded clock closed (setup, hold and pulse width)

## measured
M1 other gbt_acc=0.4914 fraction R5#arms.gbt.runs[0].test_quantised.mean: boosted trees (combinational), test accuracy, seed 0 | 99,100 test samples in 10 sessions; synthetic order flow
M2 other mlp_acc=0.4988 fraction R5#arms.mlp.runs[0].test_quantised.mean: MLP, test accuracy, seed 0 | as M1
M3 other rule_acc=0.4266 fraction R5#arms.imbalance_rule.test.mean: trivial rule (imbalance threshold), test accuracy | ditto
M4 timing gbt_comb_ns=4.4 ns R6#closed_at_ns: boosted trees (combinational), clock period closed post-route | out of context, Vivado 2026.1, one thread
M5 resources gbt_comb_lut=640 LUT R6#at_closed_clock.lut: boosted trees (combinational), LUTs | as M4
M6 latency gate_clocks=1 clocks R7#modes.speculative_model_on.stages_cycles.model gate (rule fire -> decision): added clocks from the rule's decision to the gated decision in the 58A path, model on | simulation, 8 ns clock, speculative mode
M7 latency t2t_on=9 clocks R7#modes.speculative_model_on.decision_to_first_byte: last price byte in to first preamble byte out, model on | as M6
M8 resources mlp_hand_lut=6018 LUT R8#at_closed_clock.lut: MLP (hand RTL), LUTs | as M4
M9 timing mlp_hls4ml_ns=2.3 ns R9#closed_at_ns: MLP (hls4ml + Vitis HLS), clock period closed post-route | ditto
M10 latency mlp_hls4ml_lat=75.9 ns R4#rows[4].latency_ns: MLP (hls4ml), latency at the quoted clock | 33 clocks x 2.3 ns, out of context
M11 latency mlp_hand_lat=37.7 ns R4#rows[3].latency_ns: MLP (hand RTL), latency at the quoted clock | 13 clocks x 2.9 ns, out of context

## gaps
[board_run] Not run on a board; the KR260 build with the model in the 58A top is a next step.
[timing] The feature unit and the gate (ml_feat, ml_gate) have no Vivado run; only the arms were built. Out of context the clock has no buffer or jitter, so every latency is quoted at no faster than 2.0 ns.
[power] Not measured; the out-of-context builds have no power report and nothing ran on a board.
[throughput] Every arm accepts one input a clock (the RTL test streams the first half of the test split back to back), but no throughput figure beyond that is recorded.
[data] Synthetic order flow from one generator with a planted signal; the accuracies say how well each arm recovers it, nothing about a market.
[E4] Out-of-context builds; inside a full design the clock and placement can differ. Only seed 0 is built.
[lutnet] The LUT network (seed 0) does not beat the trivial rule on the test split; it is reported as not useful.
[behaviour] Guessable wrongly: the feature history follows one tracked instrument only; a decision for another instrument passes unchanged; a vetoed decision still performs the rule's pin and log actions; ML_LAST_CLASS updates even with the model off; the hls4ml core must run every clock (its ap_vld input stalls the pipeline).

## next_actions
1. Phase 2 (docs/jepa_student_plan.md) - a JEPA-pretrained teacher distilled into a student within the MLP's cost.
2. Build the 58A board top with ML_ARM = 1 and take the board run with stage timestamps.
3. A richer generator (several instruments, regimes) so that the arms are separated by more than one feature set.

## open_questions
- Should the model veto, or skew the price and size of the order instead?

## history
2026-11-15 87 pr=-: generator, arms, RTL, hls4ml, out-of-context builds and the 58A integration in simulation
