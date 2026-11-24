# Radix-4 integer square root (floor root and remainder)

Specification of `arith/sqrt_r4` (brief 139c). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

The same function as arith/isqrt (floor square root of an unsigned W-bit integer, with the remainder) computed two root bits per step: the radix-4 digit recurrence with the non-redundant digit set {0,1,2,3}, the digit chosen by three trial subtractions in parallel. Two implementations: iterative (one digit per clock) and unrolled and pipelined (PIPE digit steps per register stage). It is the radix-4 counterpart of isqrt's radix-2 restoring recurrence; the redundant-digit (SRT) square root is not in this entry.

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid flags and the iterative variant's busy state)
* in: `in_valid`; `in_ready` (1 for the unrolled variant; low while the iterative variant is busy); `in_data`: x, W bits, unsigned
* out: `out_valid`; `out_data`: {root, rem}: root RW bits, rem RW + 1 bits, both unsigned; meaningful only while out_valid is high

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | radicand width in bits | 5 or more |
| `PIPE` | unrolled variant only: radix-4 steps per register stage | 1 to RP |

## The function

root = floor(sqrt(x)), rem = x - root**2, so 0 <= rem <= 2 * root; x = 0 gives (0, 0). Identical to arith/isqrt: the two functions can be swapped for each other at the same W.

Error bound: exact.

Latency: clock edges from the accepting edge to the edge that samples out_valid high.

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `iter` | `sqrt_r4_iter` | RP + 1 | one root per RP + 1 clocks (about half of isqrt_restoring_iter's RW + 1) | carry4 = 3*ceil((QW+4)/4) + 2*ceil((QW+3)/4), dsp48 = 0, bram = 0, ff = 4*RP + 2*QW + 1 + ceil(log2(RP+1)) + 2 | half the clocks of the radix-2 iterative root for three parallel trial subtractors and a 24q+9 adder |
| `pipe` | `sqrt_r4_pipe` | ceil(RP / PIPE) | one root per clock | carry4 = RP * (3*ceil((QW+4)/4) + 2*ceil((QW+3)/4)), dsp48 = 0, bram = 0, ff = ceil(RP/PIPE) * (2*QW + 1) + (ceil(RP/PIPE) - 1) * 4*RP + ceil(RP/PIPE) | PIPE sets the register spacing; the unrolled radix-4 root has half the stages of isqrt_restoring_pipe at PIPE = 1 and about three times the subtractors per stage |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `iter` | valid/ready on the input (a transfer is in_valid and in_ready on a rising edge; in_ready is low while a result is being computed and is high again in the cycle out_valid is high), out_valid one clock wide, no back-pressure on the output, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `pipe` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid in any variant except that the unrolled pipeline's first stage logic is between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow. in_ready of the iterative variant is a registered state and may drive a source's enable directly.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous: do not give it an asynchronous or set_false_path treatment. Do not retime across the valid pipeline of the unrolled variant without re-running the harness (latency is part of the contract). Out-of-context numbers (Fmax, area, power) are not yet measured: see build/<variant>/<fabric>/build.yaml, prepared and not run.
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/sqrt_r4_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* The result is the floor, as for isqrt: sqrt(15) gives 3 with remainder 6. The remainder is returned because the recurrence produces it free; it is at most 2 * root.
* The digit set is {0,1,2,3} and non-redundant: the remainder is an ordinary binary number, not carry-save, and there is no final correction. 'Radix-4' here means two result bits per step, not the redundant SRT digit set {-2..2} that a radix-4 divider uses; that redundant square root is not in this entry.
* W below 5 is not supported (the first step needs RP >= 2 in this coding); use isqrt for W = 3 or 4.
* An odd W is allowed: the radicand is zero-extended to 4 * RP bits, so a 9-bit radicand has a 5-bit root. When RW is odd the internal root has one more bit than the output; the top bit is always zero and is not output.
* The root is RW bits and the remainder RW + 1 bits; out_data packs them as {root, rem}, root in the high bits.
* The iterative variant accepts an input only while in_ready is high; out_valid is one clock wide and out_data is overwritten by the next accepted input on the edge that samples it.
* Reset drops results in flight; the data registers are not cleared (never read without a valid).

## Verification (everything before Vivado)

* Model: `model.py` is the specification (`math.isqrt`) plus the radix-4 recurrence step by step with the RTL's register widths asserted; exhaustive for W = 5 to 14 and by random values to W = 200; the pairs and the packing are the same as arith/isqrt's (tested).
* Simulation: both variants against the model, exhaustive for W = 5 to 16 (odd and even, so RW odd and even), 3000 random and near-square values at W = 24, 31, 32, 48, 64, every pipeline depth at W = 13 (RP = 4).
* Mutants: 18 seeded faults, all killed.
* Formal: SymbiYosys with `abc pdr` proves each variant against the characterisation root**2 + rem = x and rem <= 2 * root for all input sequences at W = 6 to 14 (unbounded, 11 jobs); proves the radix-4 pipeline equal, cycle for cycle after delaying the shorter one, to arith/isqrt's restoring pipeline at W = 8, 10 and 12 (a different recurrence written for the same specification); six seeded faults are caught (bounded).
* Lean: the radix-4 recurrence is a floor square root for every number of steps (`formal/lean/Arith/SqrtR4.lean`), proved, statement not approved; the Lean recurrence is a transcription of the RTL's step, cross-checked against the Python model on every 8-bit and every 17th 12-bit radicand; register widths are not modelled.

Finding while building it: The coding needs the root to have at least two radix-4 digits (W >= 5): with one digit the trial values are formed from a zero-width slice of the root, so W = 3 and 4 are left to arith/isqrt. The third trial value, 24q + 9, needs its own adder in front of its comparator (8q + 1 and 16q + 4 are bit concatenations), so the three-subtractor step has one carry chain more than its name suggests; whether that costs Fmax against isqrt's single chain is the question the prepared Vivado runs are for.

## Prepared for Vivado (not run)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_sqrt_r4_build_rtl.py`. **No Vivado run has been made**: there are no Fmax, area or power figures for this function.

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (SQRT4-F-MODEL, SQRT4-F-RTL-EXH, SQRT4-F-RTL-RAND, SQRT4-F-LAT, SQRT4-F-LINT, SQRT4-F-MUTANT, SQRT4-F-FORMAL-REF, SQRT4-F-FORMAL-ISQRT, SQRT4-F-LEAN-RECURRENCE, SQRT4-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
