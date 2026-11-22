# Fixed-point rounding and saturation

Specification of `arith/fxp_round` (brief 139b). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

Drop S fractional bits from a signed W_IN-bit value with one of three rounding modes (truncate, round half up, convergent), then wrap or saturate to W_OUT bits. Three implementations: the rounding folded into one adder with a carry-in (`fold_add`), a shift followed by an increment (`inc_after`), and the fold adder with the saturation in its own clock (`two_stage`).

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid flags)
* in: `in_valid`; `in_ready` (always 1); `in_data`: x, W_IN bits, signed
* out: `out_valid`; `out_data`: y, W_OUT bits, signed; meaningful only while out_valid is high

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W_IN` | input width | 2 or more |
| `S` | fractional bits dropped | 0 to W_IN - 1 |
| `W_OUT` | output width | 2 or more (any relation to W_IN - S + 1) |
| `MODE` | 0 truncate (toward minus infinity), 1 round half up (ties toward plus infinity), 2 convergent (ties to the even result) |  |
| `SAT` | 0 wrap (keep the low W_OUT bits of the rounded value), 1 saturate (clamp to the W_OUT range) |  |

## The function

* rounded: r = trunc: floor(x / 2**S); half up: floor(x / 2**S + 1/2); convergent: nearest, a tie to the even integer. r needs W_IN - S + 1 bits (the largest x rounds up one past its truncated range)
* fit: SAT = 1: y = min(max(r, -2**(W_OUT-1)), 2**(W_OUT-1) - 1); SAT = 0: y = r modulo 2**W_OUT as a signed value

Error bound: before saturation: truncate 0 <= x/2**S - r < 1; half up and convergent |r - x/2**S| <= 1/2 (output LSBs); proved in Lean for all S (Arith.Rounding).

Latency: clock edges from the accepting edge to the edge that samples out_valid high.

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `fold_add` | `fxp_round_fold` | 1 | one per clock | carry4 = ceil((W_IN+1)/4), dsp48 = 0, bram = 0, ff = W_OUT + 1 | one carry chain of full width (constant and carry-in folded into the adder); saturation after the chain in the same clock |
| `inc_after` | `fxp_round_inc` | 1 | one per clock | carry4 = ceil((W_IN-S+1)/4), dsp48 = 0, bram = 0, ff = W_OUT + 1 | shorter carry chain (only the kept bits) plus an increment-decision LUT tree over the dropped bits |
| `two_stage` | `fxp_round_2st` | 2 | one per clock | carry4 = ceil((W_IN+1)/4), dsp48 = 0, bram = 0, ff = W_OUT + (W_IN-S+1) + 2 | the fold adder and the saturation in separate clocks (more flip-flops, one more clock, shorter path) |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `fold_add` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `inc_after` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `two_stage` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid in any variant except that the unrolled pipelines' first stage logic is between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow. in_ready of an iterative variant is a registered state and may drive a source's enable directly.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous: do not give it an asynchronous or set_false_path treatment. Do not retime across the valid pipeline of a multi-stage variant without re-running the harness (latency is part of the contract). Out-of-context numbers (Fmax, area, power) for the variants are not yet measured: see build/<variant>/<fabric>/build.yaml, prepared and not run.
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/fxp_round_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* Truncate is a floor (toward minus infinity), not toward zero: -1 >> 1 is -1, not 0. Round half up sends -2.5 to -2 and 2.5 to 3. Convergent sends 0.5 to 0, 1.5 to 2, 2.5 to 2, -0.5 to 0, -1.5 to -2.
* Rounding happens before saturation and can itself overflow: the largest input rounds up to 2**(W_IN-S-1), one past the truncated range, so SAT matters even when W_OUT = W_IN - S.
* Wrap (SAT = 0) takes the low W_OUT bits of the rounded value, not of the input: a rounding carry can change the wrapped result.
* W_OUT may be wider than W_IN - S + 1: the value is sign-extended and neither wrap nor saturate has an effect.
* S = 0 is the identity for every mode (only the fit to W_OUT acts).
* A convergent tie is judged on the value after dropping S bits: the 'even' test is on the floor's least significant bit, which is bit S of x.
* W_OUT = 1 is not supported (a signed 1-bit value cannot saturate to two distinct non-zero values in this coding); use 2 or more.

## Verification (everything before Vivado)

* Model: `model.py` is the specification (exact integer rounding by the definitions) plus the single-adder carry-in form; tested exhaustively for W_IN = 2 to 9 over every S and mode, with the error bounds and 15000 random large-width cases.
* Simulation: every variant against the model, exhaustive over x at W_IN = 5 and 8 for every S, four W_OUT around the rounded width, three modes, wrap and saturate (954 configurations over the three variants), and 6 tie-heavy random configurations per variant at each of W_IN = 16, 24, 32 and 48.
* Mutants: 14 seeded faults, all killed.
* Formal: SymbiYosys with `abc pdr` proves each variant against a reference written from the definitions with wide signed arithmetic for 8 configurations (unbounded), the fold form against the increment form, and catches six seeded faults (bounded).
* Lean: convergent rounding computed by the carry-in form equals its definition for every x and every h = 2**(S-1) > 0; half-up and convergent errors are at most half a unit, truncation's error is below one unit, a tie rounds to even (`formal/lean/Arith/Rounding.lean`); all proved, statements not approved. Saturation and wrap are not in the Lean model (checked by simulation and the formal reference).

Finding while building it: The rounded value needs W_IN - S + 1 bits, not W_IN - S: the largest input rounds up to 2**(W_IN-S-1). A saturating output exactly W_IN - S bits wide therefore saturates for that one input; the model, the tests and the harness cover it.

## Prepared for Vivado (not run)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_fxp_round_build_rtl.py`. **No Vivado run has been made**: there are no Fmax, area or power figures for this function.

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (FXR-F-MODEL, FXR-F-RTL-EXH, FXR-F-RTL-RAND, FXR-F-LAT, FXR-F-LINT, FXR-F-MUTANT, FXR-F-FORMAL-REF, FXR-F-FORMAL-PAIR, FXR-F-LEAN-HALFUP, FXR-F-LEAN-CONV, FXR-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
