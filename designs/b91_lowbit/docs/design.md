# b91 design note: low-bit number formats for nanosecond inference (written before the code, brief 91)

## 1. The question

The trading-path models of briefs 87 and 89 are tiny: seven integer features, a few small layers, fully unrolled, with
every weight a constant in the fabric. Which weight format gives the best accuracy for its latency and LUTs: binary,
ternary, INT4, MXFP4-style, or a 4-bit format of our own that suits LUTs and carry chains? Brief 89 found that training
with the quantisers in the loop mattered more than the network shape, so every format is trained that way.

Reference points, all from committed results: the trivial imbalance rule 0.4266; the 87 boosted trees 0.4914 (K26:
4.4 ns, 640 LUTs); the 87 MLP 0.4988 (37.7 ns, 6,018 LUTs); the 89 LUT networks `lg_add` 0.4913 (4.95 ns, 882 LUTs),
`lg_small` 0.4892 (4.5 ns, 325 LUTs), `lg_b87` 0.4811 (3.2 ns, 129 LUTs); TreeLUT seed 0 (2.5 ns x 3 clocks, 869 LUTs).
The validation ceiling found in brief 89 is about 0.48: the label is mostly noise.

## 2. Literature, in our own words (every arXiv ID checked at export.arxiv.org on 2026-11-16)

- **FINN** (Umuroglu et al., 2017, arXiv 1612.07119) builds binarised networks for FPGAs. With weights and activations
  in {-1, +1} a neuron is XNOR then popcount, then a compare with a threshold, and batch normalisation and the
  activation fold into that one integer threshold. This is the origin of "real-valued thresholds folded into integer
  compares" in our binary format. Training is BinaryNet (Courbariaux et al., 2016, arXiv 1602.02830): a sign in the
  forward pass, a clipped straight-through gradient in the backward pass. XNOR-Net (Rastegari et al., 2016, arXiv
  1603.05279) adds real scale factors, which we do not need because the threshold absorbs them.
- **Ternary** (Li and Liu, 2016, arXiv 1605.04711): weights in {-1, 0, +1} with a real per-layer or per-neuron scale.
  The zero makes the network sparse; a zero weight costs no hardware at all.
- **Logarithmic quantisation** (Miyashita, Lee and Murmann, 2016, arXiv 1603.01025): values are rounded to a power of
  two, so a multiplication is a shift. Incremental network quantisation (Zhou et al., 2017, arXiv 1702.03044) trains
  weights restricted to powers of two or zero. Additive powers of two (Li et al., 2019, arXiv 1909.13144) show that a
  weight written as a sum of two powers of two recovers most of the accuracy lost by a single power of two, with a
  shift-and-add cost. Our "log4" and "log4+1" formats are the single-term and two-term forms; the code layouts below
  are our own definitions.
- **OCP Microscaling Formats (MX) Specification v1.0** (Sep 2023; companion paper arXiv 2310.10537). Read from the
  specification text. MXFP4 is a block of k = 32 elements, each FP4 E2M1 (1 sign, 2 exponent, 1 mantissa bit, exponent
  bias 1, no Inf or NaN), with one shared scale in E8M0 (a power of two, 8 bits) per block. E2M1 magnitudes are 0, 0.5
  (the subnormal), 1, 1.5, 2, 3, 4, 6; the maximum normal value is 6. Conversion (section 6.3): the scale X is the
  largest power of two not above the block's maximum magnitude, divided by the largest power of two representable in
  the element format (4 = 2^2 for E2M1, whose maximum 6 is 1.5 x 2^2); elements are the values divided by X, rounded
  to the element format with roundTiesToEven, with values above the maximum normal clamped to it, and values below
  the minimum subnormal after rounding converted to zero. Dot products are computed on the elements and the scales
  are applied once per block. Its cost is 8 bits of scale per 32 elements, 4.25 bits per element.
- **INT4 in DSP48E2** (AMD/Xilinx white paper WP521, "Convolutional Neural Network with INT4 Optimization on Xilinx
  Devices", 24 June 2020, rev 1.0.1, which reports up to 77% more performance than INT8 on real hardware). The abstract
  page was read; the PDF body was not retrievable in this session, so we state only that. The DSP packing itself is
  described, for the same device, in DSP-Packing (arXiv 2203.11028); see docs/stage2_plan.md.
- **LogicNets** (arXiv 2004.03021) and our brief 89 generator: networks whose neurons are enumerated into LUTs. That is
  the comparison class in section 7.

No code from FINN, Brevitas, hls4ml or any paper is used; everything below is our own.

## 3. What a format is here

A weight is c_n x e, where e is an element from the format's integer grid and c_n = 2^-sh_n is a power of two shared by
the whole neuron. The neuron's weight row has at most 16 weights, below the MX block size of 32, so "one shared scale
per block" and "one scale per neuron" coincide, and the scale (E8M0 in MX) is a power of two in every format. That has
a consequence we exploit: the scale is the neuron's requantisation shift, so it costs wiring.

| Format | Elements (integer units) | Bits/weight | Zero | Hardware per weight |
|---|---|---|---|---|
| `binary` | -1, +1 | 1 | no (0 takes +) | an add or a subtract of the input bit |
| `ternary` | -1, 0, +1 | 2 | yes | an add, a subtract, or nothing |
| `int4` | -7 .. +7 (-8 unused) | 4 | yes | 0 to 2 shifted terms (7 = 8 - 1) |
| `mxfp4` | 0, +-1, 2, 3, 4, 6, 8, 12 (E2M1 values x 2) | 4 | yes | 0 to 2 shifted terms |
| `log4` | 0, +-1, 2, 4, 8, 16, 32, 64 | 4 | yes (code 0) | one shifted term |
| `log4_nz` | +-1, 2, 4 ... 128 | 4 | no | one shifted term |
| `log4p1` | 0, 2, 3, 4, 6, 8, 12 ... 192, 256 | 5 | yes | one or two shifted terms |

Details that a reader could guess wrong:

- **MXFP4 elements are the E2M1 values times two**, so that they are integers; the factor of two joins the scale.
  The grid is exactly E2M1: 0, 0.5, 1, 1.5, 2, 3, 4, 6.
- **log4** is sign plus a 3-bit exponent code; code 0 is zero (so both signs of zero exist and mean the same) and codes
  1..7 are 2^0 .. 2^6. We chose a zero because a noisy-label network wants many small or absent weights, and we test the
  alternative without a zero (**log4_nz**: eight levels 2^0 .. 2^7) as a named variant, so the choice is measured.
- **log4p1** is sign, a 3-bit exponent e and a 1-bit mantissa m: magnitude 2^e (1 + m/2), i.e. 2^e or 2^e + 2^(e-1),
  a sum of two powers of two. There are 16 magnitude
  codes: zero, then (e, m) in order for e = 0..7, with the last one, 1.5 x 2^7, dropped. That is 15 non-zero levels
  and 5 bits per weight ("4 + 1"). In integer element units (x2): 2, 3, 4, 6, 8, 12, ... 192, 256.
- **Rounding** is to the nearest element in the linear domain, ties to the element with the even code index (the MX
  rule is roundTiesToEven; for E2M1 an even code index is an even mantissa bit). Saturating at the largest element.
  Alternative considered: rounding in the log domain (Miyashita). We chose linear because the dot product's error is
  linear in the weight error; the geometric midpoint is a documented alternative, not measured.
- **Scale**: per neuron, a power of two with sh in 0..14 (a right shift of the exact sum). It is trained (section 5),
  not set by the MX conversion rule; the MX rule (largest power of two <= max|v| over the largest element power of
  two) is the starting point of our initialisation. Alternative considered: a real-valued per-neuron scale (what
  ternary and INT4 papers use). It would turn the requantisation into a constant multiplier or a set of threshold
  compares. We chose the power of two to keep the neuron an adder tree plus a shift; the accuracy cost of that
  restriction is not measured here and is listed as a gap.

## 4. Network, activations and the fabric mapping

Inputs (the 87 features, unchanged): each feature becomes a quantile code of A bits (the brief 89 encoder,
thresholds from the training split only; a feature with at most 2^A distinct values passes through exactly), realised
as a small ROM per feature. For the binary format the input is a **thermometer** (one bit per threshold; 3 or 7
thresholds per feature, formats `binary_t3` and `binary_t7`), because XNOR-popcount needs one-bit inputs.

Layers: hidden shapes `h16x8` (16-8, the 87 MLP shape) and `h8` (one hidden layer of 8), then 3 class-score neurons.
Hidden neuron: z = sum e_i x_i (exact integer), a = clip((z + B) >> sh, 0, 2^A - 1). Activation A = 4 by default
(binary: 1). The score neuron has no shift or clip: s = z 2^k + B, with k = shmax - sh >= 0, a left shift that is wiring,
so that classes with different scales compare in common units. Class = argmax, ties to the lowest class.

Accumulators are exact: the width of every wire comes from interval arithmetic over the true input ranges (the code
maxima, hidden clip ranges and weight elements), so nothing truncates silently. Each element is written as its
non-adjacent signed-digit terms (at most two for any element of our formats) and each neuron is a balanced tree of adds
and subtracts, because brief 87 measured a linear adder chain as 3.7 times slower than a balanced tree (10.9 against
2.9 ns closed period). No multiplier is written, so no DSP is used (checked in the reports).

**Binary is FINN's neuron.** With activations in {0, 1} and weights in {-1, +1} the neuron computes sum w x, and with
bipolar inputs xb = 2x - 1 the XNOR-popcount form gives sum w xb = 2 popcount - n; the two differ by the constant
sum w, which folds into the threshold B. `twin_predict_xnor` computes the binary networks the FINN way and a test
shows the classes are identical.

## 5. Training (our own)

Float latent weights; per-neuron exponent parameter p (sh = clamp(round(-p), 0, 14)) and bias b. The forward pass is
the integer pipeline exactly: the weight is c x Q(v / c) with Q the format's element quantiser, the bias is rounded
to a multiple of c, the activation is floor then clip. The backward pass is straight-through: identity through Q (inside
the grid) and through rounding and floor, zero through the clip; the binary hidden activation uses the derivative of a
sigmoid of width sqrt(fan-in)/2 (its clip would otherwise pass no gradient); the scale p also gets gradient through
c. The loss is cross-entropy on the real-valued scores times a learned positive scale (the brief 89 lesson: integer
scores used directly as logits cannot express small logit differences, and the argmax ignores a positive scale).
Initialisation is data-dependent, layer by layer: the pre-activation spread is a quarter of the range, centred, and p
from the largest latent weight (the MX rule). Adam, cosine decay, 30 epochs, batch 1024; the epoch kept is the one
whose integer twin scores best on validation (the brief 89 lesson: choose by the exported integers). Alternatives
considered: batch normalisation (it breaks the power-of-two scale after folding), a fixed MX scale (worse start).
All training is CPU, in a memory-capped scope.

## 6. Verification design

A bit-exact Python twin per format (`model.twin_*`), read only from the exported integers. RTL generated from the same
integers. Tests: twin = RTL on every test sample and 20,000 random packed inputs, back to back and with gaps; fixed
latency; Verilator -Wall clean (CI); one test per format of the code table, the rounding (hand-worked values, ties,
saturation, zero) and the CSD terms; an exhaustive per-neuron check of the accumulator bounds; the XNOR identity.

## 7. Measurement design

Out of context, post-route, Vivado 2026.1, `xck26-sfvc784-2LV-c` and `xc7a100tcsg324-1`, one thread, the brief 87
wrapper and the brief 89 clock search (setup, hold and pulse width must pass); latency = clocks x max(closed period,
2.0 ns). Each frozen network is built as `comb` (1 clock); the A = 4 networks also as `layer`. Fronts: accuracy per LUT
and accuracy against latency. The brief 89 LUT networks and the 87 trees are the comparison points; the comparison to
make plainly is whether a fixed number format can beat a network of arbitrary small learned functions.
Pre-registration: `preregistration.md`.
