# Leading-zero count and normaliser

Specification of `arith/lzc_norm` (brief 139b). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

Count the leading zeros of an unsigned W-bit word and shift the word left by that count so the first one sits in the MSB. Four implementations: a tree count then a barrel shifter, the same with a priority-loop count, a log-shifter whose stage decisions are the count (optionally pipelined, PIPE stages per register group), and the tree version with the count and the shift in separate clocks.

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid flags)
* in: `in_valid`; `in_ready` (always 1); `in_data`: x, W bits, unsigned
* out: `out_valid`; `out_data`: {lz, y}: lz LW bits, y W bits; meaningful only while out_valid is high

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | word width in bits | 2 or more (any value, not only powers of two) |
| `PIPE` | stagewise variant only: shifter stages per register group | 1 to K (more than K behaves as K) |

## The function

* x nonzero: lz = number of zero bits above the highest one bit (0 to W - 1); y = x << lz truncated to W bits, so y[W-1] = 1
* x zero: lz = W; y = 0

Error bound: exact.

Latency: clock edges from the accepting edge to the edge that samples out_valid high.

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `tree_barrel` | `lznorm_tree_barrel` | 1 | one per clock | carry4 = 0, dsp48 = 0, bram = 0, ff = W + LW + 1, lut = about W * ceil(K/2) for the shifter plus about W/2 for the tree | logarithmic-depth count, then a barrel shifter; both in one clock |
| `loop_barrel` | `lznorm_loop_barrel` | 1 | one per clock | carry4 = 0, dsp48 = 0, bram = 0, ff = W + LW + 1, lut = as tree_barrel if the tool restructures the loop; more if it keeps the priority chain | the same function written as a priority loop; the Vivado runs decide whether it costs more than the tree |
| `stagewise_pipe` | `lznorm_stagewise_pipe` | ceil(K / PIPE) | one per clock | carry4 = 0, dsp48 = 0, bram = 0, ff = ceil(K/PIPE) * (P + K) + ceil(K/PIPE), lut = about K * P (one 2:1 mux per bit per stage) plus K NOR trees | log shifter whose decisions are the count (no separate count); PIPE sets the register spacing; P = 2**K flip-flops per group |
| `tree_barrel_2st` | `lznorm_tree_barrel_2st` | 2 | one per clock | carry4 = 0, dsp48 = 0, bram = 0, ff = 2*W + 2*LW + 2 | the tree and the shifter in separate clocks (more flip-flops, one more clock, about half the depth per stage) |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `tree_barrel` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `loop_barrel` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `stagewise_pipe` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `tree_barrel_2st` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid in any variant except that the unrolled pipelines' first stage logic is between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow. in_ready of an iterative variant is a registered state and may drive a source's enable directly.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous: do not give it an asynchronous or set_false_path treatment. Do not retime across the valid pipeline of a multi-stage variant without re-running the harness (latency is part of the contract). Out-of-context numbers (Fmax, area, power) for the variants are not yet measured: see build/<variant>/<fabric>/build.yaml, prepared and not run.
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/lznorm_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* A zero input gives lz = W (not W - 1 and not 0) and y = 0: lz needs ceil(log2(W+1)) bits, one more than the largest non-zero count when W is a power of two.
* The shift is left, by lz, within W bits: y has its MSB set for every non-zero x, and the bits shifted in at the bottom are zeros.
* Widths that are not powers of two are handled by padding the word with zeros at the bottom to the next power of two inside the block (the count is unaffected); the padding costs nothing in the count but may cost flip-flops in the stagewise variant.
* out_data packs {lz, y} with lz in the high bits.
* The count of consecutive words is not carried between words: each word is independent.
* The tree and the loop variants have the same function and latency; whether they synthesise to the same logic is for the Vivado runs, and the simulation cannot tell them apart.

## Verification (everything before Vivado)

* Model: `model.py` is the specification (`bit_length`) plus the stagewise log-shifter recurrence; exhaustive for W = 2 to 14 and random for W up to 256.
* Simulation: every variant against the model, exhaustive for W = 2 to 16 (powers of two and not), 3000 values at W = 24, 32, 33, 48, 64, 100, every pipeline depth of the stagewise variant.
* Mutants: 16 seeded faults, all killed; one mutant (E01, the loop variant wired to the tree) is equivalent by construction: the two variants differ only in how the count is written, which simulation cannot see.
* Formal: SymbiYosys with `abc pdr` proves each variant against the characterisation of the count and the word for all input sequences at W = 5 to 12 (unbounded), and proves the tree and the loop variants equal (the question simulation cannot answer); six seeded faults are caught (bounded).
* Lean: the recursive-halving tree is correct for every width 2**k: the count brackets the word, 2**(P-1-c) <= x < 2**(P-c) (`formal/lean/Arith/Lzc.lean`), proved, statement not approved. Non-power-of-two widths (zero padding), the stagewise variants and the barrel shift are not in the Lean model.

Finding while building it: The loop variant and the tree variant are the same function with the same latency: simulation cannot distinguish them, only the formal equivalence check shows they agree. Whether Vivado builds them as the same logic is the open question the prepared runs are for.

## Vivado builds (prepared in brief 139b, run in brief 160)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_lzc_norm_build_rtl.py`. The runs were made in brief 160: see the Measured section below; the expected primitive use above was written before them.

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (LZN-F-MODEL, LZN-F-RTL-EXH, LZN-F-RTL-RAND, LZN-F-LAT, LZN-F-LINT, LZN-F-MUTANT, LZN-F-FORMAL-REF, LZN-F-FORMAL-PAIR, LZN-F-LEAN-TREE, LZN-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
