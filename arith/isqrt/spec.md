# Integer square root (floor root and remainder)

Specification of `arith/isqrt` (brief 139b). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

Floor square root of an unsigned W-bit integer, with the remainder x - root**2, by the digit-by-digit recurrence: restoring iterative, restoring unrolled and pipelined, and non-restoring unrolled and pipelined (PIPE result bits per register stage).

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid flags and the iterative variant's busy state)
* in: `in_valid`; `in_ready` (1 for the unrolled variants; low while the iterative variant is busy); `in_data`: x, W bits, unsigned
* out: `out_valid`; `out_data`: {root, rem}: root RW bits, rem RW + 1 bits, both unsigned; meaningful only while out_valid is high

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | radicand width in bits | 3 or more |
| `PIPE` | unrolled variants only: result bits per register stage | 1 to RW |

## The function

root = floor(sqrt(x)), rem = x - root**2, so 0 <= rem <= 2 * root; x = 0 gives (0, 0)

Error bound: exact.

Latency: clock edges from the accepting edge to the edge that samples out_valid high.

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `restoring_iter` | `isqrt_restoring_iter` | RW + 1 | one root per RW + 1 clocks | carry4 = ceil((RW+3)/4), dsp48 = 0, bram = 0, ff = 3*RW + 1 + ceil(log2(RW+1)) + 2 | smallest; one subtractor of half the radicand's width reused RW times |
| `restoring_pipe` | `isqrt_restoring_pipe` | ceil(RW / PIPE) | one root per clock | carry4 = RW * ceil((RW+3)/4), dsp48 = 0, bram = 0, ff = ceil(RW/PIPE) * (RW + 1 + RW) + (ceil(RW/PIPE) - 1) * 2*RW + ceil(RW/PIPE) | PIPE sets the register spacing; restore multiplexer per step |
| `nonrestoring_pipe` | `isqrt_nonrestoring_pipe` | ceil(RW / PIPE) | one root per clock | carry4 = RW * ceil((RW+3)/4) + ceil((RW+2)/4), dsp48 = 0, bram = 0, ff = ceil(RW/PIPE) * (RW + 2 + RW) + (ceil(RW/PIPE) - 1) * 2*RW + ceil(RW/PIPE) | no restore mux; add or subtract by the previous sign; the correction adder is in the last stage's path |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `restoring_iter` | valid/ready on the input (a transfer is in_valid and in_ready on a rising edge; in_ready is low while a result is being computed and and is high again in the cycle out_valid is high), out_valid one clock wide, no back-pressure on the output, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `restoring_pipe` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `nonrestoring_pipe` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid in any variant except that the unrolled pipelines' first stage logic is between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow. in_ready of an iterative variant is a registered state and may drive a source's enable directly.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous: do not give it an asynchronous or set_false_path treatment. Do not retime across the valid pipeline of a multi-stage variant without re-running the harness (latency is part of the contract). Out-of-context numbers (Fmax, area, power) for the variants are not yet measured: see build/<variant>/<fabric>/build.yaml, prepared and not run.
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/isqrt_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* The result is the floor: sqrt(15) gives 3 with remainder 6, not 4 and not a fraction. The remainder is returned because the digit recurrence produces it free; it is at most 2 * root.
* An odd W is allowed: the radicand is zero-extended to 2 * RW bits, so a 9-bit radicand has a 5-bit root.
* The root is RW bits and the remainder RW + 1 bits; out_data packs them as {root, rem}, root in the high bits.
* W = 2 is not supported (RW = 1 leaves no bits for the shifted terms in this coding); use 3 or more.
* The iterative variant accepts an input only while in_ready is high; out_valid is one clock wide and out_data is overwritten by the next accepted input on the edge that samples it.
* Reset drops results in flight; the data registers are not cleared (never read without a valid).

## Verification (everything before Vivado)

* Model: `model.py` is the specification (`math.isqrt`) plus the two recurrences step by step; exhaustive for W = 3 to 14 and by random values at W up to 200; the non-restoring remainder is shown to stay in [-(2q+1), 2q], which sets its register width.
* Simulation: every variant against the model, exhaustive for W = 3 to 16 (odd and even), 3000 random and near-square values at W = 24, 31, 32, 48, 64, every pipeline depth at W = 11.
* Mutants: 16 seeded faults, all killed.
* Formal: SymbiYosys with `abc pdr` proves each variant against the characterisation root**2 + rem = x and rem <= 2 * root for all input sequences at W = 6 to 10 (unbounded), and the two pipelines against each other; six seeded faults are caught (bounded).
* Lean: the restoring recurrence is a floor square root for every width (`formal/lean/Arith/Isqrt.lean`), proved, statement not approved. The non-restoring recurrence's correctness for all widths is NOT proved; its statement (invariant: -(2q+1) <= rem <= 2q, and rem + 2q + 1 is the corrected remainder when negative) is the next Lean target.

Finding while building it: W = 2 (a one-bit root) does not fit the coding (the trial term {root[RW-2:0], 01} has no bits); the spec says W >= 3.

## Vivado builds (prepared in brief 139b, run in brief 160)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_isqrt_build_rtl.py`. The runs were made in brief 160: see the Measured section below; the expected primitive use above was written before them.

## Measured (Vivado out-of-context, brief 160)

Vivado 2026.1 (build 6511674), out-of-context synthesis, placement and routing on one thread, one run per point, at the clock shown. LUT, FF and carry cells are as reported after routing for the wrapper (which registers every port, so the FF column includes the wrapper's register bits); WNS at the target clock gives Fmax = 1000 / (clock - WNS), a lower bound (marked `>=`) when WNS is positive; latency is the spec's, in clocks, without the wrapper's two. `F` marks a point on the area-against-Fmax front of its group, `L` on the area-against-latency front (see [../../results/160_arith_vivado/README.md](../../results/160_arith_vivado/README.md)). Records: [verif/results/](verif/results/), the pre-stated expectation and its verdict per point: [verif/results/vivado_surface.json](verif/results/vivado_surface.json).

| Variant | Part | Point | Clock ns | LUT | FF | SRL | Carry | DSP | BRAM | WNS ns | Fmax MHz | Logic levels | Latency | Fronts | Expectation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nonrestoring_pipe | a7 | PIPE=1, W=16 | 2.0 | 89 | 159 | 10 | 22 | 0 | 0 | -1.922 | 255.0 | 7 | 8 |  | missed |
| nonrestoring_pipe | a7 | PIPE=4, W=16 | 2.0 | 82 | 76 | 0 | 22 | 0 | 0 | -8.44 | 95.8 | 19 | 2 |  | missed |
| nonrestoring_pipe | a7 | PIPE=1, W=32 | 2.0 | 278 | 481 | 26 | 68 | 0 | 0 | -2.33 | 230.9 | 12 | 16 |  | missed |
| nonrestoring_pipe | a7 | PIPE=4, W=32 | 2.0 | 270 | 214 | 4 | 71 | 0 | 0 | -9.911 | 84.0 | 29 | 4 |  | missed |
| nonrestoring_pipe | a7 | PIPE=16, W=32 | 2.0 | 261 | 102 | 0 | 71 | 0 | 0 | -32.03 | 29.4 | 83 | 1 | L | met |
| nonrestoring_pipe | k26 | PIPE=1, W=16 | 1.4 | 87 | 161 | 10 | 14 | 0 | 0 | -0.173 | 606.8 | 6 | 8 |  | missed |
| nonrestoring_pipe | k26 | PIPE=4, W=16 | 1.4 | 78 | 76 | 0 | 13 | 0 | 0 | -2.616 | 249.0 | 15 | 2 |  | missed |
| nonrestoring_pipe | k26 | PIPE=1, W=32 | 1.4 | 279 | 483 | 26 | 40 | 0 | 0 | -0.377 | 562.7 | 6 | 16 |  | missed |
| nonrestoring_pipe | k26 | PIPE=4, W=32 | 1.4 | 266 | 210 | 8 | 41 | 0 | 0 | -3.393 | 208.6 | 20 | 4 |  | missed |
| nonrestoring_pipe | k26 | PIPE=16, W=32 | 1.4 | 260 | 102 | 0 | 41 | 0 | 0 | -12.07 | 74.2 | 58 | 1 | L | met |
| restoring_iter | a7 | PIPE=1, W=16 | 2.0 | 44 | 76 | 0 | 3 | 0 | 0 | -0.975 | 336.1 | 5 | 9 | FL | met |
| restoring_iter | a7 | PIPE=1, W=32 | 2.0 | 79 | 141 | 0 | 5 | 0 | 0 | -1.422 | 292.2 | 7 | 17 | FL | met |
| restoring_iter | k26 | PIPE=1, W=16 | 1.4 | 44 | 76 | 0 | 2 | 0 | 0 | 0.241 | >=862.8 | 4 | 9 | FL | met |
| restoring_iter | k26 | PIPE=1, W=32 | 1.4 | 74 | 141 | 0 | 3 | 0 | 0 | 0.008 | >=718.4 | 5 | 17 | FL | met |
| restoring_pipe | a7 | PIPE=1, W=16 | 2.0 | 113 | 149 | 10 | 16 | 0 | 0 | -1.12 | 320.5 | 5 | 8 |  | missed |
| restoring_pipe | a7 | PIPE=4, W=16 | 2.0 | 77 | 74 | 0 | 16 | 0 | 0 | -6.734 | 114.5 | 15 | 2 | L | missed |
| restoring_pipe | a7 | PIPE=1, W=32 | 2.0 | 427 | 453 | 26 | 59 | 0 | 0 | -1.49 | 286.5 | 7 | 16 |  | missed |
| restoring_pipe | a7 | PIPE=4, W=32 | 2.0 | 302 | 209 | 4 | 59 | 0 | 0 | -9.173 | 89.5 | 21 | 4 |  | missed |
| restoring_pipe | a7 | PIPE=16, W=32 | 2.0 | 321 | 102 | 0 | 59 | 0 | 0 | -33.911 | 27.8 | 69 | 1 |  | met |
| restoring_pipe | k26 | PIPE=1, W=16 | 1.4 | 108 | 149 | 10 | 9 | 0 | 0 | 0.097 | >=606.8 | 4 | 8 |  | missed |
| restoring_pipe | k26 | PIPE=4, W=16 | 1.4 | 67 | 72 | 0 | 2 | 0 | 0 | -1.154 | 391.5 | 12 | 2 | L | missed |
| restoring_pipe | k26 | PIPE=1, W=32 | 1.4 | 425 | 473 | 26 | 35 | 0 | 0 | 0.002 | >=606.8 | 4 | 16 |  | missed |
| restoring_pipe | k26 | PIPE=4, W=32 | 1.4 | 304 | 204 | 8 | 35 | 0 | 0 | -2.611 | 249.3 | 16 | 4 |  | missed |
| restoring_pipe | k26 | PIPE=16, W=32 | 1.4 | 319 | 102 | 0 | 35 | 0 | 0 | -12.209 | 73.5 | 61 | 1 |  | met |

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (SQRT-F-MODEL, SQRT-F-RTL-EXH, SQRT-F-RTL-RAND, SQRT-F-LAT, SQRT-F-LINT, SQRT-F-MUTANT, SQRT-F-FORMAL-REF, SQRT-F-FORMAL-PAIR, SQRT-F-LEAN-RESTORING, SQRT-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
