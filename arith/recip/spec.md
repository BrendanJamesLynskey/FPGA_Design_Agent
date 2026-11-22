# Reciprocal of a normalised significand

Specification of `arith/recip` (brief 139c). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

The reciprocal 1 / B of a significand B in [1, 2), with W fractional bits, from a seed table and zero, one or two Newton-Raphson iterations. Three implementations: the table alone (no multiplier, one clock, about A + 1 correct bits), the table plus one Newton step (two DSP multipliers in series, 5 clocks, about 2A + 2 bits) and the table plus two (9 clocks, full precision). Fully pipelined, one result per clock; the error bound is stated per variant.

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid pipeline, not the data path)
* in: `in_valid`; `in_ready` (constant 1 (a free-running pipeline)); `in_data`: b, W bits, unsigned, normalised (MSB set)
* out: `out_valid`; `out_data`: y, W + 1 bits, unsigned: the reciprocal with W fractional bits; meaningful only while out_valid is high
* handshake: valid only: a new b may be applied on every clock; out_valid is in_valid delayed by the latency; there is no stall, enable or back-pressure

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | operand width in bits (b is a W-bit normalised significand, B = b / 2**(W-1) in [1, 2)) | 8 or more |
| `A` | seed-table address bits (2**A entries, the A bits below the leading one of b) | 2 to W - 2 |

## The function

* precondition: b has its MSB set (2**(W-1) <= b < 2**W). The behaviour for other inputs is not specified and no flag is raised.
* exact value: Y_exact = 2**(2W-1) / b, in (2**(W-1), 2**W] (the reciprocal of B = b / 2**(W-1), as a fraction of W bits: 1/B in (1/2, 1])
* result: y approximates Y_exact; y is an integer in [2**(W-1) - 2**(W-A), 2**W], and 2**W only for b = 2**(W-1) (B = 1)
* error: e = Y_exact - y in units of the last place (2**-W). table: |e| <= 2**(W-A-1) + 1/2 (two-sided). nr1 (table + one Newton step): 0 <= e < 2**(W-2A-2) + 3/2. nr2 (table + two): 0 <= e < 2**(W-4A-4) + 3/2. The Newton variants never exceed the exact value.

Error bound: per variant, in units of the last place of y: table |e| <= 2**(W-A-1) + 1/2; nr1 0 <= e < 2**(W-2A-2) + 3/2; nr2 0 <= e < 2**(W-4A-4) + 3/2. Checked over every input for W = 8 to 12 at every A (2 to W - 2), W = 16 at A = 7 and 8, and by sampling to W = 32 (tests/test_recip_model.py); proved for all input sequences by SymbiYosys at W = 8, 10, 12 for the points in tests/test_recip_formal_rtl.py. Not proved for other widths..

Latency: clock edges from the edge that accepts an input to the edge that samples out_valid high (1 = out_valid is high in the cycle immediately after the accepting edge).

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `table` | `recip_table` | 1 | one reciprocal per clock | carry4 = 0, dsp48 = 0, bram = 0, ff = W + 2, lut = the 2**A x W ROM as LUT6s: about W * 2**(A-5) for A = 6 to 8 (a RAMB18 instead if the tool maps it, from about A = 9) | no multiplier and the smallest latency, but only about A + 1 correct bits (error 2**(W-A-1) ulp) |
| `nr1` | `recip_nr` | 5 | one reciprocal per clock | carry4 = ceil((2*W+4)/4) + ceil((W+3)/4), dsp48 = 2 * ceil((W+3)/24), bram = 0, ff = 2*W + 3 + (13*W + 25 - 2*A) + 4 + 1, lut = the 2**A x (W+2) ROM as LUT6s | about 2A + 2 correct bits for two multipliers in series (b*y, then y*residual) and 5 clocks; the usual choice when W is at most about 2A + 2 |
| `nr2` | `recip_nr` | 9 | one reciprocal per clock | carry4 = 2 * (ceil((2*W+4)/4) + ceil((W+3)/4)), dsp48 = 4 * ceil((W+3)/24), bram = 0, ff = 2*W + 3 + 2*(13*W + 25 - 2*A) + 8 + 1, lut = the 2**A x (W+2) ROM as LUT6s | full precision (about one ulp, set by the truncations) from a small table, for four multipliers and 9 clocks |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `table` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `nr1` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `nr2` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid except the seed table's address decode between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous. Do not retime across the valid pipeline without re-running the harness (latency is part of the contract). The multipliers are written as * on registered operands so that Vivado can map each to a DSP48 with its input and output registers; whether it does is not yet measured (build/<variant>/<fabric>/build.yaml, prepared and not run).
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/recip_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* b must be normalised (MSB set). An unnormalised b indexes the seed table with the wrong bits and gives a wrong result without any flag; normalise first (arith/lzc_norm, brief 139b) and take the exponent separately.
* The result is an approximation, not a correctly rounded reciprocal. The Newton variants are one-sided (never above the exact value) by up to about 1.5 ulp; the table-only variant is two-sided and its error is 2**(W-A-1) ulp, which is large unless A is close to W.
* y has W + 1 bits and W fractional bits: y = 2**W exactly when b = 2**(W-1) (the reciprocal of 1.0 is 1.0), otherwise y < 2**W. A W-bit output register would drop that case.
* A is the seed-table address width: the table has 2**A entries of W (table) or W + 2 (Newton) bits. A larger A gives a better seed (the error falls by about 2**A) and a bigger table; A above 7 or 8 is probably a block RAM, which the latency formulas here do not include (the table is a combinational ROM in front of a register).
* The Newton variants carry two guard bits (F = W + 2) and truncate (floor) at every shift; they are not unbiased. The error bound includes that.
* Latency differs by variant (1, 5, 9) and is part of the contract; throughput is one per clock for all.
* Reset drops results in flight; the data registers are not cleared (never read without a valid).

## Verification (everything before Vivado)

* Model: `model.py` is the specification, in exact integer arithmetic with floor shifts and two guard bits, and the error against the exact rational value is measured: within the stated bound over every normalised input at W = 8 to 12 for every table width A from 2 to W - 2, at W = 16 for A = 7 and 8, and over sampled inputs to W = 32; the Newton variants never exceed the exact value; the residual word never overflows its width.
* Simulation: all three variants against the model, every input at W = 8 to 14 (every A at W = 8 and 9), 3000 random and seed-table-boundary inputs at W = 16 to 32, back to back at the stated latency.
* Mutants: 13 seeded faults, all killed; two more (E01, E02) are equivalent by arguments given in `verif/mutants.yaml`.
* Formal: SymbiYosys by k-induction (the datapath is a feed-forward pipeline, so an induction depth above the latency is an unbounded proof) proves each variant meets the stated error bound for all input sequences at W = 8, 10 and 12 (8 jobs); six seeded faults and a deliberately too-tight bound are refuted. Not proved for other widths.
* Lean: the exact Newton reciprocal step squares the residual, S*S - b*y1 = (S - b*y)**2, so it never overshoots (`formal/lean/Arith/Newton.lean`, two theorems), proved, statements not approved. The truncations and the seed table's accuracy are not in Lean.

Finding while building it: Two mutants of the residual (a reference value off by 2**W, a logical instead of arithmetic shift) are equivalent: the residual is kept in a word of F - A + 1 bits, so everything above that word, including exactly the bits those mutations change, is discarded. The word width is therefore a checked claim (the model asserts it at every step) and not an optimisation: a wider table error would silently wrap it.

## Prepared for Vivado (not run)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_recip_build_rtl.py`. **No Vivado run has been made**: there are no Fmax, area or power figures for this function.

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (RECIP-F-MODEL, RECIP-F-RTL-EXH, RECIP-F-RTL-RAND, RECIP-F-LAT, RECIP-F-LINT, RECIP-F-MUTANT, RECIP-F-FORMAL-BOUND, RECIP-F-LEAN-NEWTON, RECIP-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
