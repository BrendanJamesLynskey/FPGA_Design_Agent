# b91 generator datasheet: the low-bit network generator

Code: `lowbit/` (model, formats, RTL emitter, simulator wrapper, driver) and the flow tool `flow/lowbit.py`. This page
states every behaviour a user could reasonably guess wrong.

## Training options (`lowbit.model.Config`)

| Field | Default | Meaning and traps |
|---|---|---|
| `fmt` | `int4` | `binary_t3`, `binary_t7` (the number after `_t` is the thermometer levels per feature), `ternary`, `int4`, `mxfp4`, `log4`, `log4_nz`, `log4p1`. Element tables: design.md section 3. |
| `hidden` | `[16, 8]` | Neurons per hidden layer. The score layer (3 neurons) is added. |
| `act_bits` | 4 | Width of the input code and of every hidden activation. Ignored by the binary formats (1-bit activations, thermometer inputs). A feature with at most 2^A distinct training values is passed through exactly. |
| `epochs`, `lr`, `lr_scale`, `batch`, `seed` | 25, 3e-3, 2e-2, 1024, 0 | `lr_scale` is the learning rate of the scale exponents, biases and logit scale. The frozen runs use 30 epochs. |

## Behaviours

- **The scale is a shift.** Each neuron's weights are `c x e` with `c = 2^-sh`, `sh` in 0..14. `sh` is part of the
  model (`layers[i]["sh"]`), not a hidden float. There is no real-valued scale anywhere in the exported network.
- **The activation floors.** `a = clip((z + B) >> sh, 0, 2^A - 1)` with an arithmetic shift (rounds toward minus
  infinity). The rounding offset is inside `B`.
- **Score layer.** `s = (z << k) + B`, with `k = shmax - sh >= 0`. Scores of the three classes are in common units;
  the loss scale is not exported (the argmax ignores a positive scale). **Ties go to the lowest class index** in the
  twin and the RTL.
- **A zero element.** `binary` and `log4_nz` have no zero: a latent weight of exactly 0 becomes +1 (binary) or +-1.
  `log4`, `log4p1`, `ternary`, `int4`, `mxfp4` round small values to zero (below half the smallest element), and a
  tie at exactly half goes to zero.
- **Rounding** is nearest in the linear domain, ties to the even code index, saturating. It is **not** rounding in the
  log domain, even for the log formats.
- **Bias.** The exported bias `B` is an integer in the accumulator's units; the trained bias is rounded to a multiple
  of the neuron's `c`.
- **Binary.** Weights +-1 on activations in {0, 1}; the neuron is the FINN neuron up to a constant that the threshold
  absorbs (design.md section 4). Hidden units have one output bit.
- **Epoch kept** = best validation accuracy of the exported integers. Validation is used for that only.

## RTL

Ports as the brief 87 arms: `clk, rst, in_v, in_f[37:0]` (the 87 feature packing), `out_v, out_cls[1:0]`. `rst` is
synchronous and clears only the valid pipeline; `out_cls` is undefined until the first `out_v`. `pipe = comb`: LATENCY
1. `pipe = layer`: LATENCY = layers + 1 (a register after every layer, with the 3 scores registered, then the output
register). The encoder is a ROM per feature (or compares, for binary) in front of layer 1. Input features are not
registered inside the module. One input a clock; no data-dependent path. No multiplier is written. Verilator
`UNUSEDSIGNAL` is waived by a pragma in the generated file (sum wires carry bits that the shift and clip ignore);
everything else of `-Wall` is clean.

## Flow tool

`python3 -m flow.lowbit train|emit|predict` (flow/lowbit.py docstring). `emit` refuses a `--fbits` list whose length
differs from the model's feature count. The argmax is written for three classes.

## Limits

Three classes; features up to 8 bits (a ROM of 256 entries per code bit); one data set. Weights per neuron are not
limited, but the accumulator width grows with fan-in and element size (it is computed, not assumed).
