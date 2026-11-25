#!/usr/bin/env python3
"""Render arith/<function>/spec.md from spec.yaml plus the narrative below (brief 139b). `--check` fails when a committed spec.md differs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from arith.tools import gen_surface as gs

ARITH = Path(__file__).resolve().parents[1]

NARRATIVE = {
    "divider": {
        "title": "Divider (unsigned, quotient and remainder)",
        "intro": "Unsigned W-bit division n / d with quotient and remainder. Four implementations of the digit-recurrence family: restoring and non-restoring, each iterative (one quotient bit per clock, one shared subtractor) or unrolled and pipelined (PIPE quotient bits per register stage).",
        "verification": [
            "Model: `model.py` is the specification (Python `//` and `%`, with the divide-by-zero convention) plus the two digit recurrences step by step with the RTL's register widths; tested exhaustively for W = 1 to 8 and by 2000 random pairs at each of W = 16 to 128.",
            "Simulation: every variant against the model, exhaustive for W = 2 to 8 (65536 pairs at W = 8) with random input gaps, 3000 edge and random pairs at W = 16, 24, 32 and 64, every pipeline depth at W = 7; the harness measures the latency of every result.",
            "Mutants: 16 seeded faults, all killed; one more mutant (E01) is equivalent by an argument given in `verif/mutants.yaml`.",
            "Formal: SymbiYosys with `abc pdr` proves each variant against an independent `/` and `%` reference for all input sequences at W = 4 to 6 (unbounded), and the restoring and non-restoring pipelines against each other; six seeded faults are caught by bounded model checking.",
            "Lean: the restoring recurrence equals `Nat.div` and `Nat.mod` for every width (division by zero included) and the non-restoring recurrence with its final correction does too (`formal/lean/Arith/Divide.lean`); both proved, statements not approved. The recurrences are Lean transcriptions of the RTL's steps, cross-checked against the Python model for W <= 5; the RTL's register widths are not modelled.",
        ],
        "finding": "While seeding mutants the first restoring mutant that survived showed that the restoring divider's shifted partial remainder never needs its top bit (it is a prefix of n, so below 2**W): the trial subtraction is W + 1 bits wide, not W + 2. The RTL was narrowed (one carry-chain bit and one flip-flop per stage saved) and the model asserts the bound.",
    },
    "fxp_round": {
        "title": "Fixed-point rounding and saturation",
        "intro": "Drop S fractional bits from a signed W_IN-bit value with one of three rounding modes (truncate, round half up, convergent), then wrap or saturate to W_OUT bits. Three implementations: the rounding folded into one adder with a carry-in (`fold_add`), a shift followed by an increment (`inc_after`), and the fold adder with the saturation in its own clock (`two_stage`).",
        "verification": [
            "Model: `model.py` is the specification (exact integer rounding by the definitions) plus the single-adder carry-in form; tested exhaustively for W_IN = 2 to 9 over every S and mode, with the error bounds and 15000 random large-width cases.",
            "Simulation: every variant against the model, exhaustive over x at W_IN = 5 and 8 for every S, four W_OUT around the rounded width, three modes, wrap and saturate (954 configurations over the three variants), and 6 tie-heavy random configurations per variant at each of W_IN = 16, 24, 32 and 48.",
            "Mutants: 14 seeded faults, all killed.",
            "Formal: SymbiYosys with `abc pdr` proves each variant against a reference written from the definitions with wide signed arithmetic for 8 configurations (unbounded), the fold form against the increment form, and catches six seeded faults (bounded).",
            "Lean: convergent rounding computed by the carry-in form equals its definition for every x and every h = 2**(S-1) > 0; half-up and convergent errors are at most half a unit, truncation's error is below one unit, a tie rounds to even (`formal/lean/Arith/Rounding.lean`); all proved, statements not approved. Saturation and wrap are not in the Lean model (checked by simulation and the formal reference).",
        ],
        "finding": "The rounded value needs W_IN - S + 1 bits, not W_IN - S: the largest input rounds up to 2**(W_IN-S-1). A saturating output exactly W_IN - S bits wide therefore saturates for that one input; the model, the tests and the harness cover it.",
    },
    "isqrt": {
        "title": "Integer square root (floor root and remainder)",
        "intro": "Floor square root of an unsigned W-bit integer, with the remainder x - root**2, by the digit-by-digit recurrence: restoring iterative, restoring unrolled and pipelined, and non-restoring unrolled and pipelined (PIPE result bits per register stage).",
        "verification": [
            "Model: `model.py` is the specification (`math.isqrt`) plus the two recurrences step by step; exhaustive for W = 3 to 14 and by random values at W up to 200; the non-restoring remainder is shown to stay in [-(2q+1), 2q], which sets its register width.",
            "Simulation: every variant against the model, exhaustive for W = 3 to 16 (odd and even), 3000 random and near-square values at W = 24, 31, 32, 48, 64, every pipeline depth at W = 11.",
            "Mutants: 16 seeded faults, all killed.",
            "Formal: SymbiYosys with `abc pdr` proves each variant against the characterisation root**2 + rem = x and rem <= 2 * root for all input sequences at W = 6 to 10 (unbounded), and the two pipelines against each other; six seeded faults are caught (bounded).",
            "Lean: the restoring recurrence is a floor square root for every width (`formal/lean/Arith/Isqrt.lean`), proved, statement not approved. The non-restoring recurrence's correctness for all widths is NOT proved; its statement (invariant: -(2q+1) <= rem <= 2q, and rem + 2q + 1 is the corrected remainder when negative) is the next Lean target.",
        ],
        "finding": "W = 2 (a one-bit root) does not fit the coding (the trial term {root[RW-2:0], 01} has no bits); the spec says W >= 3.",
    },
    "lzc_norm": {
        "title": "Leading-zero count and normaliser",
        "intro": "Count the leading zeros of an unsigned W-bit word and shift the word left by that count so the first one sits in the MSB. Four implementations: a tree count then a barrel shifter, the same with a priority-loop count, a log-shifter whose stage decisions are the count (optionally pipelined, PIPE stages per register group), and the tree version with the count and the shift in separate clocks.",
        "verification": [
            "Model: `model.py` is the specification (`bit_length`) plus the stagewise log-shifter recurrence; exhaustive for W = 2 to 14 and random for W up to 256.",
            "Simulation: every variant against the model, exhaustive for W = 2 to 16 (powers of two and not), 3000 values at W = 24, 32, 33, 48, 64, 100, every pipeline depth of the stagewise variant.",
            "Mutants: 16 seeded faults, all killed; one mutant (E01, the loop variant wired to the tree) is equivalent by construction: the two variants differ only in how the count is written, which simulation cannot see.",
            "Formal: SymbiYosys with `abc pdr` proves each variant against the characterisation of the count and the word for all input sequences at W = 5 to 12 (unbounded), and proves the tree and the loop variants equal (the question simulation cannot answer); six seeded faults are caught (bounded).",
            "Lean: the recursive-halving tree is correct for every width 2**k: the count brackets the word, 2**(P-1-c) <= x < 2**(P-c) (`formal/lean/Arith/Lzc.lean`), proved, statement not approved. Non-power-of-two widths (zero padding), the stagewise variants and the barrel shift are not in the Lean model.",
        ],
        "finding": "The loop variant and the tree variant are the same function with the same latency: simulation cannot distinguish them, only the formal equivalence check shows they agree. Whether Vivado builds them as the same logic is the open question the prepared runs are for.",
    },    "sqrt_r4": {
        "title": "Radix-4 integer square root (floor root and remainder)",
        "intro": "The same function as arith/isqrt (floor square root of an unsigned W-bit integer, with the remainder) computed two root bits per step: the radix-4 digit recurrence with the non-redundant digit set {0,1,2,3}, the digit chosen by three trial subtractions in parallel. Two implementations: iterative (one digit per clock) and unrolled and pipelined (PIPE digit steps per register stage). It is the radix-4 counterpart of isqrt's radix-2 restoring recurrence; the redundant-digit (SRT) square root is not in this entry.",
        "verification": [
            "Model: `model.py` is the specification (`math.isqrt`) plus the radix-4 recurrence step by step with the RTL's register widths asserted; exhaustive for W = 5 to 14 and by random values to W = 200; the pairs and the packing are the same as arith/isqrt's (tested).",
            "Simulation: both variants against the model, exhaustive for W = 5 to 16 (odd and even, so RW odd and even), 3000 random and near-square values at W = 24, 31, 32, 48, 64, every pipeline depth at W = 13 (RP = 4).",
            "Mutants: 18 seeded faults, all killed.",
            "Formal: SymbiYosys with `abc pdr` proves each variant against the characterisation root**2 + rem = x and rem <= 2 * root for all input sequences at W = 6 to 14 (unbounded, 11 jobs); proves the radix-4 pipeline equal, cycle for cycle after delaying the shorter one, to arith/isqrt's restoring pipeline at W = 8, 10 and 12 (a different recurrence written for the same specification); six seeded faults are caught (bounded).",
            "Lean: the radix-4 recurrence is a floor square root for every number of steps (`formal/lean/Arith/SqrtR4.lean`), proved, statement not approved; the Lean recurrence is a transcription of the RTL's step, cross-checked against the Python model on every 8-bit and every 17th 12-bit radicand; register widths are not modelled.",
        ],
        "finding": "The coding needs the root to have at least two radix-4 digits (W >= 5): with one digit the trial values are formed from a zero-width slice of the root, so W = 3 and 4 are left to arith/isqrt. The third trial value, 24q + 9, needs its own adder in front of its comparator (8q + 1 and 16q + 4 are bit concatenations), so the three-subtractor step has one carry chain more than its name suggests; whether that costs Fmax against isqrt's single chain is the question the prepared Vivado runs are for.",
    },
    "divider_hr": {
        "title": "High-radix divider: radix-4 SRT, exact quotient and remainder",
        "intro": "Exact division of two normalised significands (MSB set), quotient with 2K fractional bits and the exact remainder, by the radix-4 SRT recurrence: signed digits {-2..2}, the digit chosen from the top bits of the partial remainder and three bits of the divisor, the quotient converted to binary on the fly. Three implementations: carry-save remainder, iterative (one digit per clock, no carry chain across the word inside the loop); carry-propagate remainder, iterative (one adder in the loop); carry-save, unrolled and pipelined (PIPE digit steps per register stage). The same pair as arith/divider (brief 139b) at width W + 2K, but two quotient bits per clock instead of one.",
        "verification": [
            "Model: `model.py` is the specification (Python `//` and `%`, equal to the 139b divider at the widened width) plus the carry-save and carry-propagate SRT recurrences step by step; the selection table is checked equal to an exhaustive exact-fraction search; the recurrences assert the convergence bound |u| <= 2b/3 after every step, the 0-or-1-unit estimate error and the exactness of every step for every pair at W = 7 and 8 (K = 1 to 4) and by random pairs to W = 64.",
            "Simulation: all variants against the model, exhaustive over every pair of normalised operands at W = 7 (K = 1, 3, 4), W = 8 (K = 2, 4, 5), W = 9 (K = 4, 5) with random input gaps, 3000 random and boundary-ratio pairs at W = 12 to 48, every pipeline depth at W = 8, K = 5.",
            "Mutants: 32 seeded faults, all killed; two more (E01, E02) are equivalent by arguments given in `verif/mutants.yaml`.",
            "Formal: the five step lemmas (first digit, carry-save step for any split of the remainder into two words, carry-propagate step, on-the-fly conversion, final correction) are proved by SymbiYosys for ALL inputs at W = 7, 8, 9, 10, 12 and 16 (combinational; no K appears); each variant equals the characterisation a * 4**K = quo * b + rem, 0 <= rem < b, for all input sequences at W = 7, K = 1 (unbounded, abc pdr) and without a counterexample to the bounded depth at W = 7, K = 3; the carry-save and carry-propagate iterative variants are proved equal; eight seeded faults are caught.",
            "Lean: for every number of digit steps K and every selection rule that keeps the remainder bounded, the recurrence with the final correction is exactly floor(4**K * a / b) and the remainder (`formal/lean/Arith/DividerHr.lean`, three theorems), proved, statements not approved. The selection table's containment is not in Lean: it is the exact-fraction search in the model and the step lemmas above.",
        ],
        "finding": "abc pdr proves the whole divider only at K = 1 (about a minute); at K = 2 the unrolled pipeline did not finish in 400 s, because the invariant relating the quotient and remainder registers is nonlinear. The step lemmas make the proof independent of K instead: every fact the induction needs is a combinational statement about one step, which SymbiYosys proves for all inputs at W = 16 in under a minute. One mutant looked like a bug and is not: the initial value of the Q-1 register is read only while Q is still zero, and a first digit of zero is always followed by a digit of at least one (tested for every pair), so it can be anything.",
    },
    "div_nr": {
        "title": "Reciprocal-multiply divider (Newton-Raphson and Goldschmidt)",
        "intro": "Approximate division of two normalised significands by a seed table and DSP multipliers: the quotient to about 1.5 units of the last place, no remainder. Two implementations with the same multiplier count and different structure: Newton-Raphson (the reciprocal of the divisor by IT Newton steps in series, then one multiply by the dividend) and Goldschmidt (the dividend and the divisor multiplied by the same correction factors, so the two multiplies of an iteration are independent and only IT + 1 multipliers are in series). Fully pipelined, one quotient per clock.",
        "verification": [
            "Model: `model.py` is the specification, in exact integer arithmetic with floor shifts and two guard bits, and the error against the exact rational quotient is measured: over every normalised pair at W = 8 (A = 2 to 6, IT = 1 to 3), W = 9 (A = 3 to 5, IT = 1 to 3) and W = 10 (A = 4, IT = 2), and over 15000 sampled pairs at ten (W, A, IT) points to W = 32; Newton is one-sided (never above the exact quotient), Goldschmidt is within -1/2 ulp.",
            "Simulation: both variants against the model, exhaustive over every pair at W = 8 (A = 2 to 6, IT = 1 to 3) and W = 9, 4000 random and extreme pairs at W = 12 to 32, every iteration count 1 to 4.",
            "Mutants: 16 seeded faults, all killed.",
            "Formal: SymbiYosys by k-induction (the datapath is a feed-forward pipeline, so an induction depth above the latency is an unbounded proof) proves each variant meets the stated error bound for all input sequences at W = 8 for three (A, IT) points each (6 jobs); six seeded faults and a deliberately too-tight bound are refuted. Not proved for other widths.",
            "Lean: the exact iteration identities (`formal/lean/Arith/Newton.lean`): multiplying numerator and denominator by the same factor keeps n * b = d * a, and the denominator update squares its distance from 1; proved, statements not approved. The truncations are not in Lean.",
        ],
        "finding": "Both variants stop improving at about 1.2 ulp once the iteration error is below the truncation floor: three floors (the residual, the correction, the final shift) lose up to about 1.25 ulp however many iterations follow, so IT above 2 buys nothing at A = 7 and W = 16. Goldschmidt's errors are not self-correcting: its result can exceed the exact quotient by up to about 0.5 ulp, which Newton's never does.",
    },
    "recip": {
        "title": "Reciprocal of a normalised significand",
        "intro": "The reciprocal 1 / B of a significand B in [1, 2), with W fractional bits, from a seed table and zero, one or two Newton-Raphson iterations. Three implementations: the table alone (no multiplier, one clock, about A + 1 correct bits), the table plus one Newton step (two DSP multipliers in series, 5 clocks, about 2A + 2 bits) and the table plus two (9 clocks, full precision). Fully pipelined, one result per clock; the error bound is stated per variant.",
        "verification": [
            "Model: `model.py` is the specification, in exact integer arithmetic with floor shifts and two guard bits, and the error against the exact rational value is measured: within the stated bound over every normalised input at W = 8 to 12 for every table width A from 2 to W - 2, at W = 16 for A = 7 and 8, and over sampled inputs to W = 32; the Newton variants never exceed the exact value; the residual word never overflows its width.",
            "Simulation: all three variants against the model, every input at W = 8 to 14 (every A at W = 8 and 9), 3000 random and seed-table-boundary inputs at W = 16 to 32, back to back at the stated latency.",
            "Mutants: 13 seeded faults, all killed; two more (E01, E02) are equivalent by arguments given in `verif/mutants.yaml`.",
            "Formal: SymbiYosys by k-induction (the datapath is a feed-forward pipeline, so an induction depth above the latency is an unbounded proof) proves each variant meets the stated error bound for all input sequences at W = 8, 10 and 12 (8 jobs); six seeded faults and a deliberately too-tight bound are refuted. Not proved for other widths.",
            "Lean: the exact Newton reciprocal step squares the residual, S*S - b*y1 = (S - b*y)**2, so it never overshoots (`formal/lean/Arith/Newton.lean`, two theorems), proved, statements not approved. The truncations and the seed table's accuracy are not in Lean.",
        ],
        "finding": "Two mutants of the residual (a reference value off by 2**W, a logical instead of arithmetic shift) are equivalent: the residual is kept in a word of F - A + 1 bits, so everything above that word, including exactly the bits those mutations change, is discarded. The word width is therefore a checked claim (the model asserts it at every step) and not an optimisation: a wider table error would silently wrap it.",
    },
    "rsqrt": {
        "title": "Reciprocal square root of a significand in [1, 4)",
        "intro": "The reciprocal square root 1 / sqrt(X) of a significand X in [1, 4) (a floating-point value whose exponent has been made even), with W fractional bits, from a seed table of 3 * 2**A entries and zero, one or two Newton-Raphson iterations. Three implementations: the table alone (one clock, about A + 2 correct bits), the table plus one Newton step (three multiplications in series, 6 clocks) and the table plus two (11 clocks). Fully pipelined, one result per clock; the error bound is stated per variant.",
        "verification": [
            "Model: `model.py` is the specification, in exact integer arithmetic with floor shifts and two guard bits, and the error against the exact value (an integer square root to 2**-64) is measured: within the stated bound over every input at W = 8 to 12 for every A from 2 to W - 3, at W = 14 (A = 6) and W = 16 (A = 7), and over sampled inputs to W = 32; the residual word never overflows its width.",
            "Simulation: all three variants against the model, every input at W = 8 to 14 (every A at W = 8 and 9), 3000 random and seed-table-boundary inputs at W = 16 to 24 (the seed constant limits W to 24), back to back at the stated latency.",
            "Mutants: 15 seeded faults, all killed; one more (E01) is equivalent by an argument given in `verif/mutants.yaml`.",
            "Formal: SymbiYosys by k-induction proves each variant meets the stated error bound (a comparison of squares) for all input sequences at W = 8, 10 and 12 (8 jobs); six seeded faults and a deliberately too-tight bound are refuted. Not proved for other widths.",
            "Lean: the exact Newton step 4*S**3 - T*(3S - T)**2 = (S - T)**2 * (4S - T), and so its one-sidedness when T <= 4S (`formal/lean/Arith/Newton.lean`, two theorems), proved with the `grind` ring solver, statements not approved. The truncations and the seed table's accuracy are not in Lean.",
        ],
        "finding": "Unlike the reciprocal's, the reciprocal-square-root variants can end slightly ABOVE the exact value (down to about -0.23 ulp at the tested points). The exact Newton map never overshoots (Lean, `rsqrt_step_one_sided`), so the overshoot comes only from the floors: the square, the product with x and the residual are each floored, and the sign of the combined effect on the residual is not fixed. The error bound states the small negative side.",
    },
}


def render(fn: str) -> str:
    spec = yaml.safe_load((ARITH / fn / "spec.yaml").read_text())
    n = NARRATIVE[fn]
    L = [f"# {n['title']}", "",
         f"Specification of `arith/{fn}` (brief {'139c' if fn in ('sqrt_r4', 'divider_hr', 'div_nr', 'recip', 'rsqrt') else '139b'}). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: {spec['spec_status']}`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.",
         "", n["intro"], "", "## Interface", ""]
    I = spec["interface"]
    L += [f"* clock `{I['clock'].split(' ')[0]}` (rising edge); reset {I['reset']}",
          f"* in: `in_valid`; `in_ready` ({I['in']['in_ready']}); `in_data`: {I['in']['in_data']}",
          f"* out: `out_valid`; `out_data`: {I['out']['out_data']}"]
    if "handshake" in I:
        L.append(f"* handshake: {I['handshake']}")
    L += ["", "## Parameters", "", "| Name | Meaning | Range |", "|---|---|---|"]
    for k, v in spec["parameters"].items():
        L.append(f"| `{k}` | {v['meaning']} | {v.get('range', '')} |")
    L += ["", "## The function", ""]
    fd = spec["function_definition"]
    if isinstance(fd, dict):
        L += [f"* {k.replace('_', ' ')}: {v}" for k, v in fd.items()]
    else:
        L.append(fd)
    L += ["", f"Error bound: {spec['error_bound']}.", "", f"Latency: {spec['latency_definition']}.", "", "## Variants", "",
          "| Variant | Module | Latency (clocks) | Throughput | Expected primitives (planning estimate, not measured) | Trade-off |", "|---|---|---|---|---|---|"]
    for v in spec["variants"]:
        ep = ", ".join(f"{k} = {x}" for k, x in v["expected_primitives"].items())
        L.append(f"| `{v['id']}` | `{v['module']}` | {v['latency']} | {v['throughput']} | {ep} | {v['trade_off']} |")
    L += ["", "## Interface contract per variant", "", "| Variant | Protocol | Reset and clock assumptions |", "|---|---|---|"]
    for v in spec["variants"]:
        L.append(f"| `{v['id']}` | {v['protocol']} | {v['reset_clock_assumptions']} |")
    L += ["", "## Integration", "", f"* Port timing: {spec['integration']['port_timing']}", f"* Constraints to carry: {spec['integration']['constraints_to_carry']}", f"* After integration: {spec['integration']['after_integration']}",
          "", "All variants are selected through `rtl/" + ("lznorm" if fn == "lzc_norm" else fn) + "_sel.sv`, the one module the testbench, the formal harness and the out-of-context wrapper use.", "",
          "## What a user could guess wrong", ""]
    L += [f"* {x}" for x in spec["what_a_user_could_guess_wrong"]]
    L += ["", "## Verification (everything before Vivado)", ""]
    L += [f"* {x}" for x in n["verification"]]
    L += ["", f"Finding while building it: {n['finding']}", "", ("## Vivado builds (prepared in brief 139b, run in brief 160)" if gs.measured_section(fn) else "## Prepared for Vivado (not run)"), "",
          f"`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_{fn}_build_rtl.py`. " + ("The runs were made in brief 160: see the Measured section below; the expected primitive use above was written before them." if gs.measured_section(fn) else "**No Vivado run has been made**: there are no Fmax, area or power figures for this function.") + "",
          *gs.measured_section(fn), "", "## Traceability", "",
          f"The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements ({', '.join(spec['requirements'])}) and the evidence for each; every Lean statement shows \"statement not approved\" until a human records an approval.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = 0
    for sp in sorted(ARITH.glob("*/spec.yaml")):
        fn = sp.parent.name
        if isinstance(yaml.safe_load(sp.read_text())["variants"], dict):      # brief 139a's functions: rendered by gen_spec_md
            continue
        p, t = sp.parent / "spec.md", render(fn)
        if a.check:
            if not p.exists() or p.read_text() != t:
                print("out of date:", p)
                bad = 1
        else:
            p.write_text(t)
    print("spec.md:", "FAIL" if bad else ("ok" if a.check else "written"))
    return bad


if __name__ == "__main__":
    sys.exit(main())
