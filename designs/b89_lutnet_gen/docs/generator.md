# lutgen: options and behaviour (datasheet)

`lutgen` trains a LUT network and emits it as SystemVerilog plus a bit-exact Python twin. This page lists every
option with its default and every behaviour a user could reasonably guess wrong. The method and the reasons for each
choice are in [design.md](design.md).

## Python API

```python
from designs.b89_lutnet_gen.lutgen import model as M, rtl as R
m = M.train(M.Config(...), X_train, y_train, X_val, y_val)     # dict: thresholds, wiring, tables, accuracies
cls = M.twin_predict(m, X)                                      # the bit-exact reference for the RTL
sv = R.emit(m, "my_net", fbits=[8, 8, 4, 3, 5, 8, 2], pipe="layer")
```

As a flow tool for any data: `python3 -m flow.lutgen train|emit|predict` (`flow/lutgen.py`; `emit` takes
`--pipe comb|layer|N` and `--reg-encoder`, both tested in `flow/tests/test_89_lutgen_rtl.py`).

Command line for the brief 89 models: `python -m designs.b89_lutnet_gen.lutgen.cli train|rtl` (see the README).

## Config fields

| Field | Default | Meaning | Could be guessed wrong |
|---|---|---|---|
| `in_bits` | `[2]*7` | code bits per input feature; the encoder makes up to `2^b - 1` thresholds | a feature with no more distinct training values than codes is passed through exactly (thresholds `min .. max-1`), so it may use fewer bits than asked; a value above the training maximum gets the top code, below the minimum code 0 |
| `thresholds` | `"quantile"` | `"quantile"`: equal-population cuts on the training split; `"tree"`: the cuts a 30-round, depth-3 boosted-tree ensemble (scikit-learn `HistGradientBoostingClassifier`, training split only) uses most often for that feature | duplicate quantiles are merged, so a skewed feature can get fewer codes than `2^b`; `"tree"` with a feature the ensemble never splits on falls back to quantiles |
| `layers` | `[[16,3,2],[8,3,2]]` | hidden LUT layers, each `[neurons, fan_in, out_bits]`; `[]` means the score layer reads the input codes directly | `fan_in` is in codes (each code is `in_bits` or the previous layer's `out_bits` wide), not in bits |
| `out_fan_in` | `4` | fan-in of each score neuron | |
| `out_bits` | `4` | bits of each score neuron's signed output (two's complement, `-2^(b-1) .. 2^(b-1)-1`) | |
| `output` | `"direct"` | `"direct"`: one score neuron per class; `"additive"`: `per_class` score neurons per class, summed | in `"additive"` the score neurons are grouped by class in order: neurons `c*per_class .. (c+1)*per_class-1` belong to class `c` |
| `per_class` | `1` | score neurons per class in `"additive"` | ignored in `"direct"` |
| `wiring` | `"random"` | `"random"`: every input of a layer is wired at least once, then uniform without repeats inside a neuron; `"greedy"`: layer 1 subsets ranked by a depth-3 tree's training accuracy | wiring is fixed before training and never learned; it depends on `seed` |
| `hidden`, `depth` | `16`, `2` | width and number of hidden layers of each neuron's inner float network | these cost nothing in hardware: only the truth table is built |
| `batchnorm` | `True` | BatchNorm before each quantiser (its running statistics are folded into the tables) | |
| `epochs`, `lr`, `batch` | `20`, `3e-3`, `1024` | Adam, cosine decay over all steps | the model returned is the epoch with the best **validation** accuracy, not the last |
| `seed` | `0` | wiring, initial weights and batch order | training uses two CPU threads; results are repeatable on one machine and library version, not guaranteed across versions |
| `n_classes` | `3` | | the RTL argmax is written for 3 classes only |

A neuron whose table would exceed 2^12 entries (`MAX_ADDR_BITS`) is refused with an error.

## Encoder

Feature `j` becomes `code_j = number of thresholds t in T_j with x_j > t` (strictly greater). In the RTL this is a
sum of 1-bit compares on the unsigned feature field. A feature field is read as unsigned; the 87 features are all
unsigned by construction (the OFI feature carries an offset of 128).

## Tables

Entry `addr` of a neuron's table is its output when its wired inputs, concatenated with the **first wired input in
the most significant bits**, equal `addr`. Every entry is defined: inputs that never occur in training still have an
entry (the trained network's output there), so the twin and the RTL agree on any input, not only on the data.

## RTL (`rtl.emit`)

- Ports: `clk`, `rst`, `in_v`, `in_f[sum(fbits)-1:0]`, `out_v`, `out_cls[1:0]`; feature 0 in the least significant
  bits. The brief 87 arm interface, so `designs/b87_ml_trading/tb/tb_arm.sv` and its `ooc_wrap` take it unchanged.
- `rst` is synchronous, active high, and clears only the valid pipeline; the datapath registers are never reset, so
  `out_cls` is undefined until the first `out_v`.
- `LATENCY` (a localparam) = clocks from `in_v` to `out_v`, the same for every input; one new input every clock.
  - `pipe="comb"`: 1 (encoder, all layers, the adders and the argmax before one output register);
  - `pipe="layer"`: LUT layers + 1 (a register after every LUT layer, hidden and score, plus the output register
    after the score adder and argmax); a network with no hidden layer has LATENCY 2;
  - `pipe=N`: a register after every N-th LUT layer, plus the output register;
  - `reg_encoder=True` adds one register after the encoder compares (+1).
- The features are not registered inside the module: the producer's register is assumed (the out-of-context
  wrapper adds one, outside `LATENCY`).
- Ties between class scores go to the lower class index (`>` compares), as in the twin (`numpy.argmax`).
- The output is `` `default_nettype none `` clean and uses only constant vectors indexed by a wire (no memories), so
  synthesis maps the tables to LUTs, never to BRAM.
