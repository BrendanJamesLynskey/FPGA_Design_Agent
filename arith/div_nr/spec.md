# Reciprocal-multiply divider (Newton-Raphson and Goldschmidt)

Specification of `arith/div_nr` (brief 139c). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

Approximate division of two normalised significands by a seed table and DSP multipliers: the quotient to about 1.5 units of the last place, no remainder. Two implementations with the same multiplier count and different structure: Newton-Raphson (the reciprocal of the divisor by IT Newton steps in series, then one multiply by the dividend) and Goldschmidt (the dividend and the divisor multiplied by the same correction factors, so the two multiplies of an iteration are independent and only IT + 1 multipliers are in series). Fully pipelined, one quotient per clock.

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid pipeline, not the data path)
* in: `in_valid`; `in_ready` (constant 1 (a free-running pipeline)); `in_data`: {a, b}, 2*W bits, both unsigned and normalised (MSB set): a / b is in (1/2, 2)
* out: `out_valid`; `out_data`: q, W bits, unsigned: approximately a * 2**(W-1) / b (W - 1 fractional bits); meaningful only while out_valid is high
* handshake: valid only: a new pair may be applied on every clock; out_valid is in_valid delayed by the latency; there is no stall, enable or back-pressure

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | operand width in bits (a and b are W-bit normalised significands) | 8 or more |
| `A` | seed-table address bits (2**A entries, the A bits below the leading one of b) | 2 to W - 2 |
| `IT` | iterations: Newton steps of the reciprocal, or Goldschmidt iterations | 1 or more |

## The function

* precondition: a and b have their MSB set (2**(W-1) <= a, b < 2**W). The behaviour for other inputs is not specified and no flag is raised.
* exact value: Q_exact = a * 2**(W-1) / b, a real number in (2**(W-2), 2**W)
* result: q approximates Q_exact; q < 2**W
* error: e = Q_exact - q in units of the last place of q (2**-(W-1)). newton: 0 <= e < 3/2 + 2**(W - 2**IT * (A+1) + 1) (one-sided). goldschmidt: -1/2 < e < 3/2 + 2**(W - 2**IT * (A+1) + 1).

Error bound: per variant, in units of the last place of q: newton 0 <= e < 3/2 + 2**(W - 2**IT * (A+1) + 1); goldschmidt -1/2 < e < 3/2 + 2**(W - 2**IT * (A+1) + 1). Checked over every normalised pair for W = 8 (A = 2 to 6, IT = 1 to 3), W = 9 (A = 3 to 5, IT = 1 to 3) and W = 10 (A = 4, IT = 2), and by sampling to W = 32 (tests/test_div_nr_model.py); proved for all input sequences by SymbiYosys at W = 8 for the points in tests/test_div_nr_formal_rtl.py. Not proved for other widths. When the second term is below 1/2 the Newton result is floor(Q_exact) or floor(Q_exact) - 1 (it never exceeds Q_exact and is less than 3/2 below it)..

Latency: clock edges from the edge that accepts an input to the edge that samples out_valid high (1 = out_valid is high in the cycle immediately after the accepting edge).

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `newton` | `div_nr_newton` | 2 + 4 * IT | one quotient per clock | carry4 = IT * (ceil((2*W+4)/4) + ceil((W+3)/4)), dsp48 = (2 * IT + 1) * ceil((W+3)/24), bram = 0, ff = (W+3) + W + W*(4*IT+1) + IT*(13*W + 25 - 2*A) + 4*IT + 2 + W, lut = the 2**A x (W+2) ROM as LUT6s | the reciprocal by Newton steps in series (each step corrects itself, so truncations do not accumulate), then one multiply by a; a is carried through a shift register; 2*IT + 1 multipliers, all in series |
| `goldschmidt` | `div_nr_gs` | 2 + 2 * IT | one quotient per clock | carry4 = IT * ceil((W+4)/4), dsp48 = (2 * IT + 1) * ceil((W+3)/24), bram = 0, ff = (W+2) + 2*W + (W+4) + (W+3) + IT * (W+4 + W+3 + W+3 + W+4) + 2*IT + 2, lut = the 2**A x (W+2) ROM as LUT6s | a and b multiplied by the same correction factors, the two multiplies of an iteration independent, so only IT + 1 multipliers in series and about half the latency of newton at the same DSP count; errors are not self-correcting and the result may exceed the exact quotient by a fraction of an ulp |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `newton` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `goldschmidt` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable; out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid except the seed table's address decode between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous. Do not retime across the valid pipeline without re-running the harness (latency is part of the contract). The multipliers are written as * on registered operands so that Vivado can map each to a DSP48 with its input and output registers; whether it does is not yet measured (build/<variant>/<fabric>/build.yaml, prepared and not run).
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/div_nr_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* The result is an approximation with no remainder: q is within about 1.5 ulp of a * 2**(W-1) / b, not floor(a * 2**(W-1) / b). For an exact quotient and remainder use arith/divider_hr (or arith/divider) instead; an exact quotient from this block needs a correction step (multiply back and compare) that is not in this entry.
* Both operands must be normalised (MSB set); the seed table is indexed by the bits of b below the leading one. An unnormalised b gives a wrong result without any flag.
* q has W bits and W - 1 fractional bits: the integer part (0 or 1) is the top bit. a / b = 2 is not reachable (a < 2**W <= 2 * b), so q never overflows.
* Goldschmidt can return a value slightly ABOVE the exact quotient (down to -1/2 ulp in the error); Newton never does. If a one-sided result matters (a conservative estimate), use newton.
* The block is not a faster divider in latency terms at small W: newton's latency is 2 + 4 * IT clocks and goldschmidt's 2 + 2 * IT, against W + 1 for arith/divider's restoring iterative divider at one bit per clock; the gain is throughput (one result per clock) and DSP use instead of fabric.
* IT is a parameter, not a precision setting you can ignore: with a small table (A small) one iteration leaves an error of 2**(W - 2A - 1) ulp, and more iterations stop helping once the truncation floor (about 1.5 ulp) is reached.
* Reset drops results in flight; the data registers are not cleared (never read without a valid).

## Verification (everything before Vivado)

* Model: `model.py` is the specification, in exact integer arithmetic with floor shifts and two guard bits, and the error against the exact rational quotient is measured: over every normalised pair at W = 8 (A = 2 to 6, IT = 1 to 3), W = 9 (A = 3 to 5, IT = 1 to 3) and W = 10 (A = 4, IT = 2), and over 15000 sampled pairs at ten (W, A, IT) points to W = 32; Newton is one-sided (never above the exact quotient), Goldschmidt is within -1/2 ulp.
* Simulation: both variants against the model, exhaustive over every pair at W = 8 (A = 2 to 6, IT = 1 to 3) and W = 9, 4000 random and extreme pairs at W = 12 to 32, every iteration count 1 to 4.
* Mutants: 16 seeded faults, all killed.
* Formal: SymbiYosys by k-induction (the datapath is a feed-forward pipeline, so an induction depth above the latency is an unbounded proof) proves each variant meets the stated error bound for all input sequences at W = 8 for three (A, IT) points each (6 jobs); six seeded faults and a deliberately too-tight bound are refuted. Not proved for other widths.
* Lean: the exact iteration identities (`formal/lean/Arith/Newton.lean`): multiplying numerator and denominator by the same factor keeps n * b = d * a, and the denominator update squares its distance from 1; proved, statements not approved. The truncations are not in Lean.

Finding while building it: Both variants stop improving at about 1.2 ulp once the iteration error is below the truncation floor: three floors (the residual, the correction, the final shift) lose up to about 1.25 ulp however many iterations follow, so IT above 2 buys nothing at A = 7 and W = 16. Goldschmidt's errors are not self-correcting: its result can exceed the exact quotient by up to about 0.5 ulp, which Newton's never does.

## Prepared for Vivado (not run)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_div_nr_build_rtl.py`. **No Vivado run has been made**: there are no Fmax, area or power figures for this function.

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (DIVNR-F-MODEL, DIVNR-F-RTL-EXH, DIVNR-F-RTL-RAND, DIVNR-F-LAT, DIVNR-F-LINT, DIVNR-F-MUTANT, DIVNR-F-FORMAL-BOUND, DIVNR-F-LEAN-GS, DIVNR-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
