# Divider (unsigned, quotient and remainder)

Specification of `arith/divider` (brief 139b). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: draft`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.

Unsigned W-bit division n / d with quotient and remainder. Four implementations of the digit-recurrence family: restoring and non-restoring, each iterative (one quotient bit per clock, one shared subtractor) or unrolled and pipelined (PIPE quotient bits per register stage).

## Interface

* clock `clk` (rising edge); reset rst (synchronous, active high; clears only the valid flags and the iterative divider's busy state, not the data path)
* in: `in_valid`; `in_ready` (1 for the unrolled variants; low while an iterative divider is busy); `in_data`: {n, d}, 2*W bits, both unsigned
* out: `out_valid`; `out_data`: {q, r}, 2*W bits, both unsigned; meaningful only while out_valid is high
* handshake: a transfer happens on a rising edge where in_valid and in_ready are both high; there is no back-pressure on the output (out_valid is one clock wide per result, results are never held)

## Parameters

| Name | Meaning | Range |
|---|---|---|
| `W` | operand width in bits | 2 or more |
| `PIPE` | unrolled variants only: quotient bits per register stage | 1 to W (more than W behaves as W) |

## The function

* d nonzero: q = floor(n / d), r = n - q * d, so r < d
* d zero: q = 2**W - 1 (all ones), r = n (the RISC-V convention); no flag is raised

Error bound: exact (no approximation).

Latency: clock edges from the edge that accepts an input to the edge that samples out_valid high (1 = out_valid is high in the cycle immediately after the accepting edge).

## Variants

| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |
|---|---|---|---|---|---|
| `restoring_iter` | `div_restoring_iter` | W + 1 | one division per W + 1 clocks (in_ready low while busy) | carry4 = ceil((W+1)/4), dsp48 = 0, bram = 0, ff = 3*W + ceil(log2(W+1)) + 2 | smallest; one subtractor reused W times; slowest per division |
| `nonrestoring_iter` | `div_nonrestoring_iter` | W + 2 | one division per W + 2 clocks | carry4 = ceil((W+2)/4) + ceil((W+1)/4), dsp48 = 0, bram = 0, ff = 3*W + 1 + ceil(log2(W+2)) + 2 | no restore multiplexer, one extra clock and a second (correction) adder |
| `restoring_pipe` | `div_restoring_pipe` | ceil(W / PIPE) | one division per clock | carry4 = W * ceil((W+1)/4), dsp48 = 0, bram = 0, ff = ceil(W/PIPE) * 2*W + (ceil(W/PIPE) - 1) * W + ceil(W/PIPE) | PIPE sets the register spacing; many carry chains in series inside a stage when PIPE is large |
| `nonrestoring_pipe` | `div_nonrestoring_pipe` | ceil(W / PIPE) | one division per clock | carry4 = W * ceil((W+2)/4) + ceil((W+1)/4), dsp48 = 0, bram = 0, ff = ceil(W/PIPE) * (2*W + 1) + (ceil(W/PIPE) - 1) * W + ceil(W/PIPE) | no restore mux per iteration; the correction adder is in the last stage's path |

## Interface contract per variant

| Variant | Protocol | Reset and clock assumptions |
|---|---|---|
| `restoring_iter` | valid/ready on the input (a transfer is in_valid and in_ready on a rising edge; in_ready is low while a result is being computed and and is high again in the cycle out_valid is high), out_valid one clock wide, no back-pressure on the output, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `nonrestoring_iter` | valid/ready on the input (a transfer is in_valid and in_ready on a rising edge; in_ready is low while a result is being computed and and is high again in the cycle out_valid is high), out_valid one clock wide, no back-pressure on the output, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `restoring_pipe` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |
| `nonrestoring_pipe` | valid only: in_ready is constant 1, fixed latency, one result per clock, no stall or enable (a free-running pipeline); out_valid is in_valid delayed by the latency, results in input order | one clock, rising edge; rst is synchronous and must be held for at least one clock before the first in_valid (the formal harness assumes reset in the first cycle only); outputs and in_ready are defined from the first clock after reset; data-path registers are not reset |

## Integration

* Port timing: All inputs are sampled on the rising edge and all outputs change after it; there is no combinational path from in_data or in_valid to out_data or out_valid in any variant except that the unrolled pipelines' first stage logic is between the input pins and the first register, so register the inputs (the out-of-context wrapper does) when the source is slow. in_ready of an iterative variant is a registered state and may drive a source's enable directly.
* Constraints to carry: One clock constraint on clk. No multicycle or false-path exceptions are needed or valid: every path is single-cycle register to register. rst is synchronous: do not give it an asynchronous or set_false_path treatment. Do not retime across the valid pipeline of a multi-stage variant without re-running the harness (latency is part of the contract). Out-of-context numbers (Fmax, area, power) for the variants are not yet measured: see build/<variant>/<fabric>/build.yaml, prepared and not run.
* After integration: Rerun the packaged harness against your instance (harness/README.md): it checks values, order and the measured latency of every result and reports coverage of the target bins.

All variants are selected through `rtl/divider_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.

## What a user could guess wrong

* Division by zero does not raise anything: q is all ones and r is n. A caller that needs a flag must compare d with zero itself.
* The operands are unsigned. A signed division needs sign handling outside this block (take magnitudes, restore signs; the remainder takes the dividend's sign by convention there, not here).
* The iterative variants accept an input only while in_ready is high; an in_valid that is held through a busy period is accepted when the divider becomes idle (the harness checks this). An out_valid pulse can coincide with in_ready, so the next division may be accepted on the edge that samples the previous result.
* out_data is valid only while out_valid is high and is overwritten by the next accepted input on the same edge that samples it; sample it on that edge.
* Reset clears the valid flags and the busy flag only; a division in flight when rst is asserted is dropped, its data registers are not cleared (they are never read without a valid).
* The latency is a clock count, not a time; the Fmax of each variant is the Vivado runs' job (prepared, not run).
* PIPE above W is the same as PIPE = W; the register spacing of the last stage may be shorter than PIPE.

## Verification (everything before Vivado)

* Model: `model.py` is the specification (Python `//` and `%`, with the divide-by-zero convention) plus the two digit recurrences step by step with the RTL's register widths; tested exhaustively for W = 1 to 8 and by 2000 random pairs at each of W = 16 to 128.
* Simulation: every variant against the model, exhaustive for W = 2 to 8 (65536 pairs at W = 8) with random input gaps, 3000 edge and random pairs at W = 16, 24, 32 and 64, every pipeline depth at W = 7; the harness measures the latency of every result.
* Mutants: 16 seeded faults, all killed; one more mutant (E01) is equivalent by an argument given in `verif/mutants.yaml`.
* Formal: SymbiYosys with `abc pdr` proves each variant against an independent `/` and `%` reference for all input sequences at W = 4 to 6 (unbounded), and the restoring and non-restoring pipelines against each other; six seeded faults are caught by bounded model checking.
* Lean: the restoring recurrence equals `Nat.div` and `Nat.mod` for every width (division by zero included) and the non-restoring recurrence with its final correction does too (`formal/lean/Arith/Divide.lean`); both proved, statements not approved. The recurrences are Lean transcriptions of the RTL's steps, cross-checked against the Python model for W <= 5; the RTL's register widths are not modelled.

Finding while building it: While seeding mutants the first restoring mutant that survived showed that the restoring divider's shifted partial remainder never needs its top bit (it is a prefix of n, so below 2**W): the trial subtraction is W + 1 bits wide, not W + 2. The RTL was narrowed (one carry-chain bit and one flip-flop per stage saved) and the model asserts the bound.

## Vivado builds (prepared in brief 139b, run in brief 160)

`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_divider_build_rtl.py`. The runs were made in brief 160: see the Measured section below; the expected primitive use above was written before them.

## Measured (Vivado out-of-context, brief 160)

Vivado 2026.1 (build 6511674), out-of-context synthesis, placement and routing on one thread, one run per point, at the clock shown. LUT, FF and carry cells are as reported after routing for the wrapper (which registers every port, so the FF column includes the wrapper's register bits); WNS at the target clock gives Fmax = 1000 / (clock - WNS), a lower bound (marked `>=`) when WNS is positive; latency is the spec's, in clocks, without the wrapper's two. `F` marks a point on the area-against-Fmax front of its group, `L` on the area-against-latency front (see [../../results/160_arith_vivado/README.md](../../results/160_arith_vivado/README.md)). Records: [verif/results/](verif/results/), the pre-stated expectation and its verdict per point: [verif/results/vivado_surface.json](verif/results/vivado_surface.json).

| Variant | Part | Point | Clock ns | LUT | FF | SRL | Carry | DSP | BRAM | WNS ns | Fmax MHz | Logic levels | Latency | Fronts | Expectation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nonrestoring_iter | a7 | PIPE=1, W=16 | 2.0 | 79 | 124 | 0 | 10 | 0 | 0 | -1.312 | 301.9 | 7 | 18 | F | met |
| nonrestoring_iter | a7 | PIPE=1, W=32 | 2.0 | 141 | 237 | 0 | 18 | 0 | 0 | -2.168 | 239.9 | 11 | 34 |  | met |
| nonrestoring_iter | k26 | PIPE=1, W=16 | 1.4 | 77 | 124 | 0 | 6 | 0 | 0 | 0.039 | >=734.8 | 5 | 18 |  | met |
| nonrestoring_iter | k26 | PIPE=1, W=32 | 1.4 | 140 | 237 | 0 | 10 | 0 | 0 | -0.115 | 660.1 | 7 | 34 |  | met |
| nonrestoring_pipe | a7 | PIPE=1, W=16 | 2.0 | 345 | 636 | 28 | 84 | 0 | 0 | -2.424 | 226.0 | 11 | 16 | L | missed |
| nonrestoring_pipe | a7 | PIPE=4, W=16 | 2.0 | 348 | 212 | 16 | 84 | 0 | 0 | -8.719 | 93.3 | 24 | 4 | L | met |
| nonrestoring_pipe | a7 | PIPE=1, W=32 | 2.0 | 1209 | 2289 | 60 | 296 | 0 | 0 | -3.801 | 172.4 | 19 | 32 |  | missed |
| nonrestoring_pipe | a7 | PIPE=4, W=32 | 2.0 | 1228 | 677 | 48 | 296 | 0 | 0 | -11.173 | 75.9 | 42 | 8 |  | missed |
| nonrestoring_pipe | a7 | PIPE=8, W=32 | 2.0 | 1196 | 424 | 16 | 296 | 0 | 0 | -21.581 | 42.4 | 80 | 4 | L | met |
| restoring_iter | a7 | PIPE=1, W=16 | 2.0 | 61 | 123 | 0 | 5 | 0 | 0 | -1.438 | 290.9 | 7 | 17 | FL | met |
| restoring_iter | a7 | PIPE=1, W=32 | 2.0 | 109 | 236 | 0 | 9 | 0 | 0 | -2.066 | 245.9 | 11 | 33 | FL | met |
| restoring_pipe | a7 | PIPE=1, W=16 | 2.0 | 511 | 598 | 28 | 80 | 0 | 0 | -1.849 | 259.8 | 6 | 16 |  | missed |
| restoring_pipe | a7 | PIPE=4, W=16 | 2.0 | 393 | 203 | 16 | 80 | 0 | 0 | -8.371 | 96.4 | 25 | 4 |  | met |
| restoring_pipe | a7 | PIPE=1, W=32 | 2.0 | 2046 | 2212 | 60 | 288 | 0 | 0 | -2.364 | 229.1 | 10 | 32 |  | missed |
| restoring_pipe | a7 | PIPE=4, W=32 | 2.0 | 1569 | 656 | 48 | 288 | 0 | 0 | -10.869 | 77.7 | 40 | 8 |  | missed |
| restoring_pipe | a7 | PIPE=8, W=32 | 2.0 | 1535 | 416 | 16 | 288 | 0 | 0 | -22.717 | 40.5 | 78 | 4 |  | met |

## Traceability

The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements (DIV-F-MODEL, DIV-F-RTL-EXH, DIV-F-RTL-RAND, DIV-F-LAT, DIV-F-LINT, DIV-F-MUTANT, DIV-F-FORMAL-REF, DIV-F-FORMAL-PAIR, DIV-F-LEAN-RESTORING, DIV-F-LEAN-NONRESTORING, DIV-F-BUILD) and the evidence for each; every Lean statement shows "statement not approved" until a human records an approval.
