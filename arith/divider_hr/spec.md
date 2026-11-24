# High-radix divider: radix-4 SRT, exact quotient and remainder

Specification of `arith/divider_hr` (brief 139c). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

Exact division of two normalised significands (MSB set), quotient with 2K fractional bits and the exact remainder, by the radix-4 SRT recurrence: signed digits {-2..2}, the digit chosen from the top bits of the partial remainder and three bits of the divisor, the quotient converted to binary on the fly. Three implementations: carry-save remainder, iterative (one digit per clock, no carry chain across the word inside the loop); carry-propagate remainder, iterative (one adder in the loop); carry-save, unrolled and pipelined (PIPE digit steps per register stage). The same pair as arith/divider (brief 139b) at width W + 2K, but two quotient bits per clock instead of one.

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid flags and the iterative variants' busy state)
* in: `in_valid`; `in_ready` (1 for the unrolled variant; low while an iterative variant is busy); `in_data`: {a, b}, 2*W bits, both unsigned and normalised (MSB set): a / b is in (1/2, 2)
* out: `out_valid`; `out_data`: {quo, rem}: quo 2*K + 1 bits, rem W bits, both unsigned; meaningful only while out_valid is high
* handshake: a transfer happens on a rising edge where in_valid and in_ready are both high; there is no back-pressure on the output (out_valid is one clock wide per result, results are never held)

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | operand width in bits (a and b are W-bit normalised significands) | 7 or more |
| `K` | fractional radix-4 digits of the quotient (2K fractional bits); the division takes K + 1 digit steps, the first being the integer digit | 1 or more |
| `PIPE` | unrolled variant only: digit steps per register stage | 1 to K + 1 (more behaves as K + 1) |

## The function

* precondition: a and b are W-bit with the MSB set (2**(W-1) <= a, b < 2**W). The behaviour for other inputs is not specified and no flag is raised.
* quotient: quo = floor(a * 4**K / b); quo < 2**(2K+1), so it has K integer-digit bits plus the integer digit: one integer bit (quo >= 4**K exactly when a >= b) and 2K fractional bits
* remainder: rem = a * 4**K - quo * b, so 0 <= rem < b (the exact remainder, an integer in the units of the divisor)
* relation to integer division: the same pair as arith/divider (brief 139b) at width W + 2K with n = a * 4**K and d = b

Error bound: exact (no approximation; the remainder is returned).

Latency: clock edges from the edge that accepts an input to the edge that samples out_valid high (1 = out_valid is high in the cycle immediately after the accepting edge).

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `srt4_iter` | `divider_hr_iter` | K + 3 | one division per K + 3 clocks (in_ready low while busy) | carry4 = 2 + ceil((W+3)/4) + ceil((W+1)/4), dsp48 = 0, bram = 0, ff = 2*(W+3) + 2*W + 3*(2*K+1) + ceil(log2(K+2)) + 5, lut = about 2*(W+3) for the compressor with the b and 2b select, plus the digit table (10 inputs) | carry-save remainder (no carry chain across W bits in the loop, two remainder registers) and one carry-propagate add at the end; two quotient bits per clock |
| `srt4_cpa` | `divider_hr_cpa` | K + 3 | one division per K + 3 clocks (in_ready low while busy) | carry4 = ceil((W+3)/4) + ceil((W+1)/4), dsp48 = 0, bram = 0, ff = (W+1) + 2*W + 3*(2*K+1) + ceil(log2(K+2)) + 5, lut = about W + 3 for the b and 2b select, plus the digit table | the same digits with an ordinary binary remainder: one adder in the loop (a carry chain on every step) and one register fewer; on a fabric with fast carry chains this may beat the carry-save form, which is what the Vivado runs are for |
| `srt4_pipe` | `divider_hr_pipe` | ceil((K + 1) / PIPE) + 1 | one division per clock | carry4 = 2*(K+1) + ceil((W+3)/4) + ceil((W+1)/4), dsp48 = 0, bram = 0, ff = ceil((K+1)/PIPE) * (2*(W+3) + W + 2*(2*K+1)) + (2*K+1) + W + ceil((K+1)/PIPE) + 1, lut = about (K+1) * 2*(W+3) for the compressors plus (K+1) digit tables | K + 1 compressor rows in one pipeline for one division per clock; PIPE sets the register spacing (one carry-save step is very short, so PIPE above 1 is the usual choice) |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `srt4_iter` | valid/ready on the input (a transfer is in_valid and in_ready on a rising edge; in_ready is low while a result is being computed and is high again in the cycle out_valid is high), out_valid one clock wide, no back-pressure on the output, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `srt4_cpa` | valid/ready on the input (a transfer is in_valid and in_ready on a rising edge; in_ready is low while a result is being computed and is high again in the cycle out_valid is high), out_valid one clock wide, no back-pressure on the output, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `srt4_pipe` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid in any variant except that the unrolled pipeline's first stage logic is between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow. in_ready of an iterative variant is a registered state and may drive a source's enable directly.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous: do not give it an asynchronous or set_false_path treatment. Do not retime across the valid pipeline of the unrolled variant without re-running the harness (latency is part of the contract). The operands must be normalised before this block (arith/lzc_norm from brief 139b is the matching leading-zero count and shifter). Out-of-context numbers (Fmax, area, power) are not yet measured: see build/<variant>/<fabric>/build.yaml, prepared and not run.
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins (the eight divisor intervals of the digit-selection table among them).

All variants are selected through `rtl/divider_hr_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* Both operands must be normalised (MSB set). An unnormalised divisor can break the digit selection (it indexes a table by the three bits below the leading one) and the result is then wrong without any flag. Normalise first (arith/lzc_norm), divide, and take the exponent difference separately.
* The quotient is exact, not rounded: quo = floor(a * 4**K / b) and the remainder rem = a * 4**K - quo * b is returned. For a floating-point divide the remainder gives the sticky bit (rem != 0) and the rounding position is yours to choose; K = ceil((W - 1) / 2) gives W - 1 or W fractional quotient bits.
* quo has 2K + 1 bits: the top bit is the integer part (1 when a >= b), the other 2K bits are fractional. With W even and K = W / 2 there is one more fractional bit than W - 1.
* rem is in the units of the divisor (an integer below b), not a fraction of the quotient's last place.
* 'Radix 4' here means two quotient bits per step with the redundant digit set {-2,-1,0,1,2} (SRT): the partial remainder stays in a carry-save form in srt4_iter and srt4_pipe, and the quotient is converted to binary on the fly, so the final quotient may be one more than the last digit string's value and is corrected by the sign of the final remainder.
* The first of the K + 1 digit steps is the integer digit; the latency is therefore K + 3 for the iterative variants, not K + 1.
* A division is not accepted while an iterative variant is busy: in_ready is low for K + 2 clocks. out_valid is one clock wide and out_data is overwritten by the next accepted division on the edge that samples it.
* W below 7 is not supported (the digit estimate takes bits W-1 down to W-7).
* Reset drops results in flight; the data registers are not cleared (never read without a valid).

## Verification (everything before Vivado)

* Model: `model.py` is the specification (Python `//` and `%`, equal to the 139b divider at the widened width) plus the carry-save and carry-propagate SRT recurrences step by step; the selection table is checked equal to an exhaustive exact-fraction search; the recurrences assert the convergence bound |u| <= 2b/3 after every step, the 0-or-1-unit estimate error and the exactness of every step for every pair at W = 7 and 8 (K = 1 to 4) and by random pairs to W = 64.
* Simulation: all variants against the model, exhaustive over every pair of normalised operands at W = 7 (K = 1, 3, 4), W = 8 (K = 2, 4, 5), W = 9 (K = 4, 5) with random input gaps, 3000 random and boundary-ratio pairs at W = 12 to 48, every pipeline depth at W = 8, K = 5.
* Mutants: 32 seeded faults, all killed; two more (E01, E02) are equivalent by arguments given in `verif/mutants.yaml`.
* Formal: the five step lemmas (first digit, carry-save step for any split of the remainder into two words, carry-propagate step, on-the-fly conversion, final correction) are proved by SymbiYosys for ALL inputs at W = 7, 8, 9, 10, 12 and 16 (combinational; no K appears); each variant equals the characterisation a * 4**K = quo * b + rem, 0 <= rem < b, for all input sequences at W = 7, K = 1 (unbounded, abc pdr) and without a counterexample to the bounded depth at W = 7, K = 3; the carry-save and carry-propagate iterative variants are proved equal; eight seeded faults are caught.
* Lean: for every number of digit steps K and every selection rule that keeps the remainder bounded, the recurrence with the final correction is exactly floor(4**K * a / b) and the remainder (`formal/lean/Arith/DividerHr.lean`, three theorems), proved, statements not approved. The selection table's containment is not in Lean: it is the exact-fraction search in the model and the step lemmas above.

Finding while building it: abc pdr proves the whole divider only at K = 1 (about a minute); at K = 2 the unrolled pipeline did not finish in 400 s, because the invariant relating the quotient and remainder registers is nonlinear. The step lemmas make the proof independent of K instead: every fact the induction needs is a combinational statement about one step, which SymbiYosys proves for all inputs at W = 16 in under a minute. One mutant looked like a bug and is not: the initial value of the Q-1 register is read only while Q is still zero, and a first digit of zero is always followed by a digit of at least one (tested for every pair), so it can be anything.

## Prepared for Vivado (not run)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_divider_hr_build_rtl.py`. **No Vivado run has been made**: there are no Fmax, area or power figures for this function.

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (DIVHR-F-MODEL, DIVHR-F-RTL-EXH, DIVHR-F-RTL-RAND, DIVHR-F-LAT, DIVHR-F-LINT, DIVHR-F-MUTANT, DIVHR-F-FORMAL-LEMMA, DIVHR-F-FORMAL-REF, DIVHR-F-FORMAL-PAIR, DIVHR-F-LEAN-RECURRENCE, DIVHR-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
