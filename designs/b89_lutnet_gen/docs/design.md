# b89 LUT-network generator: design note

Written before the generator's final form was chosen, and kept as the record of why each choice was made. Every
number here is from `results/b89/diagnosis.json` (train and validation splits only) or `results/b87/`. The test split
was not used for anything in this note.

## 1. The problem

Brief 87 built a LUT network from a quick generator of our own: 6.0 ns and 76 LUTs on the K26, but 0.4207 test
accuracy, below the trivial imbalance rule (0.4266). The boosted trees (0.4914) and the MLP (0.4988) beat the rule.
The goal here is a generator whose networks:

- **beat the trivial rule** on the 87 test split with a paired interval that excludes zero (the accuracy floor), and
  approach the 87 trees;
- stay inside a **latency budget of 10 ns** and a **resource budget of 2,000 LUTs** on the K26
  (`xck26-sfvc784-2LV-c`), out of context, quoted at no faster than the 87 2.0 ns floor;
- are bit-exact against a Python twin on every input, with a latency that does not depend on the data.

## 2. Diagnosis: why the 87 network lost

Short experiments, each recorded in `results/b89/diagnosis.json` (`python -m designs.b89_lutnet_gen.diag.diagnose`).
"val" is validation accuracy; the trivial rule's validation figure (0.4489) is in-sample, because the rule was tuned
on validation.

| Question | Experiment | Finding |
|---|---|---|
| D2: how much is there to learn? | large boosted-tree ensembles on the raw features | 100 rounds x depth 4: train 0.523, val **0.4801**; 300 x depth 6: train 0.564, val 0.4717. The features allow about 0.48; above that is label noise (the label is the sign of a mid move 40 events ahead, three classes). The whole useful range is 0.449 to 0.48. |
| D1: did the 2-bit input codes lose it? | the 87 tree configuration on raw features and on 1- to 4-bit quantile codes | raw 0.4746; 1-bit 0.4777; 2-bit 0.4673; 3-bit 0.4771; 4-bit 0.4747. The 2-bit codes cost about 0.007, a small part of the gap. Two features (spread, last mid direction) collapse to two codes under quantile cuts. |
| D3: is fan-in 3 too narrow? | the 87 tree configuration on each 3-feature subset | the best triples reach 0.465 alone (single features at most 0.434, the imbalance bucket). A fan-in of 3 sees enough. |
| D0: the 87 network itself | retrained with its own code, seeds 0-2 | seed 0 reproduces the recorded validation accuracy (0.4004) exactly; training accuracy is barely above validation (no over-fitting: it under-fits), and some first- and second-layer neurons are constant. |
| D4: the training method | the 87 structure in a vectorised trainer: quantised as 87; float hidden values; quantised with BatchNorm | quantised: val 0.4534, 0.4548, 0.4076 (one seed collapses); **float hidden values: 0.4801, 0.4701, 0.4742**; quantised with BatchNorm: 0.416-0.434. With 3-bit inputs and float hidden values: 0.480-0.482. |

**Finding.** The 87 network did not lose because of its features, its input codes or its fan-in: the same sparse
structure with unquantised hidden values reaches the ceiling (0.47-0.48). It lost in training with the quantisers in
the loop: it under-fits (training accuracy about 0.43-0.47), its validation accuracy swings by about 0.02 from epoch
to epoch, one seed in three collapses, and adding BatchNorm alone does not help. Round 3 (section 5) found the main
mechanism: the integer scores were used directly as the logits of the loss.

## 3. The literature, in our own words

Papers were read from arXiv (IDs checked at export.arxiv.org); no code was taken from any of them.

- **LogicNets** (Umuroglu et al., arXiv 2004.03021). A neuron with few, low-precision inputs and a quantised output
  is a truth table, so a network trained with that sparsity and quantisation can be turned directly into a netlist
  of tables, pipelined layer by layer. Sparsity is fixed and random before training; table cost grows exponentially
  with fan-in x bits, so both are kept small.
- **PolyLUT** (Andronic and Constantinides, arXiv 2309.02334). The function inside a table can be richer than a
  linear map and an activation: they train multivariate polynomials, which the table absorbs at no extra hardware
  cost, so fewer layers reach the same accuracy.
- **PolyLUT-Add** (arXiv 2406.04910). Several small tables whose outputs are added give a neuron a wider effective
  fan-in than one table could afford, because an adder grows linearly while a table grows exponentially.
- **NeuraLUT** (Andronic and Constantinides, arXiv 2403.00849). Whole small float sub-networks (with skip
  connections) are hidden inside each table; only the table boundary is quantised, so the training sees a much
  smoother function inside.
- **TreeLUT** (Khataei and Bazargan, arXiv 2501.01511). Gradient-boosted trees on quantised features, with the leaf
  values quantised to a few bits; each tree is a small logic function of the features' threshold bits, and class
  scores are integer sums through a pipelined adder tree. No DSPs or BRAM.
- **SparseLUT** (arXiv 2503.12829). Instead of random sparse wiring, connections are pruned and regrown during
  training to choose which inputs each table sees.
- **DWN** (Differentiable Weightless Neural Networks, arXiv 2410.11112) and **LUTNet** (arXiv 1904.00938): lookup
  tables as the learned element itself, trained with relaxed gradients; noted, not followed.

## 4. Method and decisions

| Decision | Chosen | Alternatives considered | Why |
|---|---|---|---|
| Neuron function | small float network inside each table (NeuraLUT-style): k inputs -> 16 -> 16 -> 1 | linear + activation (LogicNets); polynomial (PolyLUT) | the table hides any function at the same cost; the 87 generator already used it; D4 shows the structure is not the limit |
| Quantisation in the loop | straight-through rounding at every table boundary; BatchNorm before each quantiser | post-training quantisation; learned step sizes | the tables must be exactly what was trained; BatchNorm keeps each neuron's pre-quantiser value in range |
| Train/inference match | the twin and the RTL are the enumerated tables; the epoch kept is chosen by the **tables'** validation accuracy; BatchNorm statistics can be frozen for the last epochs | choose by the float forward pass | D4/round 1: the float forward and the tables disagree enough to swing accuracy by 0.02 |
| Score scale | a learned positive scale between integer scores and the loss's logits (`learn_temperature`) | integer scores as logits (87) | the class is an argmax, unchanged by a positive scale; without it the loss cannot express the small logit differences a noisy three-class label needs (round 3) |
| Output | `direct` (one score table per class) or `additive` (several score tables per class, summed) | direct only (87) | PolyLUT-Add and TreeLUT: an adder widens the effective fan-in cheaply |
| Input codes | quantile cuts or the cuts a small tree ensemble uses (`thresholds="tree"`); exact pass-through for narrow features | uniform cuts; learned thresholds | D1: quantile codes lose little; tree cuts are a cheap TreeLUT-style alternative, compared on validation |
| Wiring | random, covering every input once before repeating | greedy by a small tree's accuracy (implemented, `wiring="greedy"`); learned (SparseLUT) | random is the LogicNets baseline; greedy left as an option; learned wiring is a next step |
| Pipelining | a parameter: `comb`, `layer`, or every N layers; encoder optionally registered | fixed per-layer registers (87) | the 87 numbers show the right point depends on depth: a one-clock-per-level tree was slower than the combinational one |
| Model selection | three seeds; the built seed is the one with the best validation accuracy; all three are scored on test | seed 0 only (87) | 87's seed 0 was its worst seed; choosing on validation is fair and reported with all seeds |
| RTL | constant vectors indexed by the packed codes, one per output bit; the 87 arm ports | `case` statements; memories | maps to LUTs in every tool; `default_nettype none`; Verilator `-Wall` clean |

## 5. Design rounds (validation only)

At most three, each recorded in `results/b89/rounds/r<N>.json`; what changed and why is in
[how_we_built_it.md](how_we_built_it.md) with the numbers.

1. **r1**: the 87 shape with BatchNorm, cosine decay and the best-epoch rule.
2. **r2**: additive score layers and tree cuts, without a hidden layer and with one.
3. **r3**: the learned score scale and frozen BatchNorm statistics, on the shapes of r1 and r2.

The frozen configuration and the comparisons are pre-registered in [preregistration.md](preregistration.md) before
the test split is scored.
