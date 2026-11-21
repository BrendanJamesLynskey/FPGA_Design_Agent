#!/usr/bin/env python3
"""Render arith/<function>/spec.md from spec.yaml plus the narrative below (brief 139b). `--check` fails when a committed spec.md differs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

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
    },
}


def render(fn: str) -> str:
    spec = yaml.safe_load((ARITH / fn / "spec.yaml").read_text())
    n = NARRATIVE[fn]
    L = [f"# {n['title']}", "",
         f"Specification of `arith/{fn}` (brief 139b). Machine-readable form: [spec.yaml](spec.yaml). `spec_status: {spec['spec_status']}`: written by the agent from the owner's request, not agreed by a human (only a human sets `agreed`). Generated from spec.yaml by `arith/tools/gen_spec.py`; do not edit.",
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
    L += ["", f"Finding while building it: {n['finding']}", "", "## Prepared for Vivado (not run)", "",
          f"`build/<variant>/a7/build.yaml` (Artix-7 xc7a100t) and `build/<variant>/k26/build.yaml` (K26, xck26) describe an out-of-context run of each variant at the points in spec.yaml, with the expected primitive use evaluated for each point (a planning estimate). They are generated by `arith/tools/gen_build.py` and checked by `tests/test_{fn}_build_rtl.py`. **No Vivado run has been made**: there are no Fmax, area or power figures for this function.",
          "", "## Traceability", "",
          f"The packaged harness for reruns against a user's instance is in [harness/](harness/README.md). `verif/testplan.yaml` (schema v1) lists the requirements ({', '.join(spec['requirements'])}) and the evidence for each; every Lean statement shows \"statement not approved\" until a human records an approval.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = 0
    for sp in sorted(ARITH.glob("*/spec.yaml")):
        fn = sp.parent.name
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
