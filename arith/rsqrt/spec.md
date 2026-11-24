# Reciprocal square root of a significand in [1, 4)

Specification of `arith/rsqrt` (brief 139c). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

The reciprocal square root 1 / sqrt(X) of a significand X in [1, 4) (a floating-point value whose exponent has been made even), with W fractional bits, from a seed table of 3 * 2**A entries and zero, one or two Newton-Raphson iterations. Three implementations: the table alone (one clock, about A + 2 correct bits), the table plus one Newton step (three multiplications in series, 6 clocks) and the table plus two (11 clocks). Fully pipelined, one result per clock; the error bound is stated per variant.

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid pipeline, not the data path)
* in: `in_valid`; `in_ready` (constant 1 (a free-running pipeline)); `in_data`: x, W bits, unsigned, in [2**(W-2), 2**W)
* out: `out_valid`; `out_data`: y, W + 1 bits, unsigned: 1 / sqrt(X) with W fractional bits; meaningful only while out_valid is high
* handshake: valid only: a new x may be applied on every clock; out_valid is in_valid delayed by the latency; there is no stall, enable or back-pressure

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | operand width in bits (x has 2 integer bits and W - 2 fractional bits: X = x / 2**(W-2) in [1, 4)) | 8 to 24 (the seed constant is computed in 64-bit integers at elaboration: 2 * (W + 2) + A + 1 must be at most 63) |
| `A` | seed-table resolution: the table has 3 * 2**A entries, one per interval of width 2**-A of X in [1, 4) | 2 to W - 3 |

## The function

* precondition: 2**(W-2) <= x < 2**W (X in [1, 4)): the significand of a floating-point value whose exponent has been made even (shift by one more place when it was odd). The behaviour for x below 2**(W-2) is not specified and no flag is raised.
* exact value: Y_exact = 2**W / sqrt(X) = sqrt(2**(3W-2) / x), in (2**(W-1), 2**W]
* result: y approximates Y_exact; y is an integer up to 2**W, and 2**W only for x within one table interval of 2**(W-2) (X = 1)
* error: e = Y_exact - y in units of the last place (2**-W). table: |e| <= 2**(W-A-2) + 1 (two-sided). nr1 (table + one Newton step): -1/4 < e < 2**(W-2A-3) + 3/2. nr2 (table + two): -1/4 < e < 2**(W-4A-7) + 3/2. The exact-arithmetic Newton map never exceeds the exact value; the small negative side comes from the truncation of the residual and of the shifts.

Error bound: per variant, in units of the last place of y: table |e| <= 2**(W-A-2) + 1; nr1 -1/4 < e < 2**(W-2A-3) + 3/2; nr2 -1/4 < e < 2**(W-4A-7) + 3/2. Checked over every input for W = 8 to 12 at every A (2 to W - 3), W = 14 at A = 6 and W = 16 at A = 7, and by sampling to W = 32 (tests/test_rsqrt_model.py); proved for all input sequences by SymbiYosys at W = 8, 10, 12 for the points in tests/test_rsqrt_formal_rtl.py. Not proved for other widths..

Latency: clock edges from the edge that accepts an input to the edge that samples out_valid high (1 = out_valid is high in the cycle immediately after the accepting edge).

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `table` | `rsqrt_table` | 1 | one result per clock | carry4 = ceil((A+2)/4), dsp48 = 0, bram = 0, ff = W + 2, lut = the 3 * 2**A x W ROM as LUT6s: about W * 3 * 2**(A-6) for A = 6 or 7 (a RAMB18 instead if the tool maps it) | no multiplier and the smallest latency, but only about A + 2 correct bits (error 2**(W-A-2) ulp) |
| `nr1` | `rsqrt_nr` | 6 | one result per clock | carry4 = ceil((A+2)/4) + ceil((2*W+4)/4) + ceil((W+3)/4), dsp48 = 4, bram = 0, ff = 2*W + 3 + (16*W + 33 - 2*A) + 5 + 1, lut = the 3 * 2**A x (W+2) ROM as LUT6s | about 2A + 3 correct bits for three multiplications in series (y*y, x*(y*y), y*residual; y*y needs two DSPs at 19 bits) and 6 clocks |
| `nr2` | `rsqrt_nr` | 11 | one result per clock | carry4 = ceil((A+2)/4) + 2 * (ceil((2*W+4)/4) + ceil((W+3)/4)), dsp48 = 8, bram = 0, ff = 2*W + 3 + 2*(16*W + 33 - 2*A) + 10 + 1, lut = the 3 * 2**A x (W+2) ROM as LUT6s | full precision (about one ulp) from a small table, for eight DSPs and 11 clocks |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `table` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `nr1` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `nr2` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid except the seed table's address decode (a short subtract) between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous. Do not retime across the valid pipeline without re-running the harness (latency is part of the contract). The multipliers are written as * on registered operands so that Vivado can map each to a DSP48 with its input and output registers; whether it does is not yet measured (build/<variant>/<fabric>/build.yaml, prepared and not run).
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/rsqrt_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* The input is x with TWO integer bits: X = x / 2**(W-2) in [1, 4), not a mantissa in [1, 2). Inputs below 2**(W-2) are outside the contract. Make the exponent even before the call (an odd exponent shifts the significand by one place), and halve the result's exponent afterwards.
* The result is an approximation, not correctly rounded. The error is up to about 1.5 ulp for the Newton variants, slightly two-sided (down to -1/4 ulp), and 2**(W-A-2) ulp for the table-only variant.
* y has W + 1 bits and W fractional bits: y = 2**W only for X = 1 (to within a table interval); otherwise y < 2**W.
* The table has 3 * 2**A entries (X in [1, 4) divided into intervals of width 2**-A), so A = 7 is 384 entries, not 128.
* The Newton variants carry two guard bits (F = W + 2) and floor at every shift; they are not unbiased. The error bound includes that.
* Latency differs by variant (1, 6, 11) and is part of the contract; throughput is one per clock for all.
* Reset drops results in flight; the data registers are not cleared (never read without a valid).

## Verification (everything before Vivado)

* Model: `model.py` is the specification, in exact integer arithmetic with floor shifts and two guard bits, and the error against the exact value (an integer square root to 2**-64) is measured: within the stated bound over every input at W = 8 to 12 for every A from 2 to W - 3, at W = 14 (A = 6) and W = 16 (A = 7), and over sampled inputs to W = 32; the residual word never overflows its width.
* Simulation: all three variants against the model, every input at W = 8 to 14 (every A at W = 8 and 9), 3000 random and seed-table-boundary inputs at W = 16 to 24 (the seed constant limits W to 24), back to back at the stated latency.
* Mutants: 15 seeded faults, all killed; one more (E01) is equivalent by an argument given in `verif/mutants.yaml`.
* Formal: SymbiYosys by k-induction proves each variant meets the stated error bound (a comparison of squares) for all input sequences at W = 8, 10 and 12 (8 jobs); six seeded faults and a deliberately too-tight bound are refuted. Not proved for other widths.
* Lean: the exact Newton step 4*S**3 - T*(3S - T)**2 = (S - T)**2 * (4S - T), and so its one-sidedness when T <= 4S (`formal/lean/Arith/Newton.lean`, two theorems), proved with the `grind` ring solver, statements not approved. The truncations and the seed table's accuracy are not in Lean.

Finding while building it: Unlike the reciprocal's, the reciprocal-square-root variants can end slightly ABOVE the exact value (down to about -0.23 ulp at the tested points). The exact Newton map never overshoots (Lean, `rsqrt_step_one_sided`), so the overshoot comes only from the floors: the square, the product with x and the residual are each floored, and the sign of the combined effect on the residual is not fixed. The error bound states the small negative side.

## Prepared for Vivado (not run)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_rsqrt_build_rtl.py`. **No Vivado run has been made**: there are no Fmax, area or power figures for this function.

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (RSQRT-F-MODEL, RSQRT-F-RTL-EXH, RSQRT-F-RTL-RAND, RSQRT-F-LAT, RSQRT-F-LINT, RSQRT-F-MUTANT, RSQRT-F-FORMAL-BOUND, RSQRT-F-LEAN-NEWTON, RSQRT-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
