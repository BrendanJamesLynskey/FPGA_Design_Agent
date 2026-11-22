#!/usr/bin/env python3
"""Write arith/<function>/verif/testplan.yaml (schema v1 of docs/traceability_v1.md, brief 116) and the empty lean_approvals.yaml, from spec.yaml and the
test files (arith brief 139a). Every test file of the function is named by exactly one item, so the 116 orphan gate passes; every requirement is
traced; no status is typed (flow/trace_v1.py computes them from the recorded evidence).

    python3 -m arith.tools.gen_testplan [adder multiplier mac] [--check]"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from arith.tools import arith_common as ac
from arith.tools.suite import job_kind

P = {"adder": "ADD", "multiplier": "MUL", "mac": "MAC", "exp2": "EXP", "log2": "LOG", "sincos": "SIN", "atan2_mag": "ATN", "fp_add": "FPADD", "fp_mul": "FPMUL", "fp_fma": "FPFMA"}
ELEM = ("exp2", "log2", "sincos", "atan2_mag")          # the elementary functions of brief 139d: not exact, an error bound against the exact function, a model per variant
INDEP = {"adder": "a bit-serial chain of full adders", "multiplier": "a shift-and-add formulation (and, for the Booth recoding, the digit-sum identity)",
         "mac": "a structure-free reference that applies the samples one at a time with Python integers",
         "exp2": "exact rational (Fraction) evaluations of the interpolation and Horner formulas, a floating-point hyperbolic CORDIC, and the maths library's 2**x",
         "log2": "exact rational (Fraction) evaluations of the interpolation and Horner formulas, a floating-point hyperbolic CORDIC, and the maths library's log2",
         "sincos": "an exact rational (Fraction) evaluation of the interpolation formula, a floating-point CORDIC, and the maths library's sin and cos",
         "atan2_mag": "a floating-point CORDIC and the maths library's atan2 and hypot",
         "fp_add": "an enumeration of every finite value of a tiny format (the nearest one, ties to even) and NumPy's hardware float32 addition",
         "fp_mul": "an enumeration of every finite value of a tiny format (the nearest one, ties to even) and NumPy's hardware float32 multiplication",
         "fp_fma": "an enumeration of every finite value of a tiny format (the nearest one, ties to even), the multiplier and adder models, and the identities a * 1 + c = c + a and a * b + 0 = a * b"}


def lines_of(fn: str, rel: str, start: str, end: str) -> str:
    """The line range (A-B, 1-based) of a file from the first line containing `start` to the first line after it containing `end`."""
    ls = (ac.ARITH / fn / rel).read_text().splitlines()
    a = next(i for i, l in enumerate(ls, 1) if start in l)
    b = next(i for i, l in enumerate(ls, 1) if i >= a and end in l)
    return f"{a}-{b}"


LEAN = {
    "adder": [
        ("CS", "ArithAdder.cs_correct", "Arith.Adder", "Carry-select composition adds", "A carry-select adder (a low block, and a high block computed for carry in 0 and 1 and selected by the low block's carry out) returns the same sum and carry out as plain addition, for every block widths m and k and every pair of operands",
         "rtl/adder_carry_select.sv", ("if (i == 0) begin : g_first", "assign c[i+1]"), "arith/adder/rtl/adder_carry_select.sv (g_first and g_sel blocks, two blocks)", "formal/lean/Arith/Adder.lean (csSum, csCarry, sumN, carryN)"),
        ("SUB", "ArithAdder.sub_is_add_complement", "Arith.Adder", "Subtraction is addition of the complements", "For every width n, a + ~b + ~bin on n bits equals a - b - bin modulo 2^n, and its carry out is 1 exactly when there is no borrow: the identity every variant's subtract path rests on",
         "rtl/adder_ripple.sv", ("assign be = b ^", "assign {co, s}"), "arith/adder/rtl/adder_ripple.sv (be, ce, the one adder)", "formal/lean/Arith/Adder.lean (sumN, carryN, the statement itself)"),
    ],
    "multiplier": [
        ("BOOTH", "ArithBooth.booth_correct", "Arith.Booth", "Radix-4 Booth digits sum to the multiplier's value", "For every multiplier width, the radix-4 Booth digits d_i = -2 b[2i+1] + b[2i] + b[2i-1] of an even-length bit pattern sum, weighted by 4^i, to its two's-complement value",
         "rtl/mult_booth_r4.sv", ("localparam int WBX", "assign bxe"), "arith/multiplier/rtl/mult_booth_r4.sv (WBX, NP, bwide, bxe, the digit case table)", "formal/lean/Arith/Booth.lean (gval, top, boothSum)"),
        ("BOOTH-UNS", "ArithBooth.booth_unsigned", "Arith.Booth", "An unsigned multiplier extended by a zero bit has non-negative digits summing to its value", "For every pattern whose top bit is 0 (an unsigned multiplier given the RTL's extra zero bit), the Booth digit sum equals the unsigned value",
         "rtl/mult_booth_r4.sv", ("localparam int WBX", "assign bxe"), "arith/multiplier/rtl/mult_booth_r4.sv (WBX, NP, bwide, bxe)", "formal/lean/Arith/Booth.lean (gval, top, boothSum)"),
    ],
    "mac": [
        ("NOCLR", "ArithMac.run_noclr", "Arith.Mac", "A clear-free run adds up modulo 2^ACCW", "For every modulus M and run length, applying samples that never clear gives the initial accumulator plus the sum of the products, reduced modulo M: no saturation, no loss, however long the run",
         "rtl/mac_dsp.sv", ("always_ff @(posedge clk) begin\n        if (rst)       acc", "endmodule"), "arith/mac/rtl/mac_dsp.sv (the accumulator always_ff block; the same line in mac_fabric.sv and mac_dsp_cascade.sv)", "formal/lean/Arith/Mac.lean (step, run)"),
        ("CLR", "ArithMac.run_after_clr", "Arith.Mac", "A clear makes the history irrelevant", "Whatever the accumulator held, a sample with clr followed by clear-free samples gives that sample's product plus the others, reduced modulo M",
         "rtl/mac_dsp.sv", ("always_ff @(posedge clk) begin\n        if (rst)       acc", "endmodule"), "arith/mac/rtl/mac_dsp.sv (the accumulator always_ff block)", "formal/lean/Arith/Mac.lean (step, run)"),
    ],
}


_LERP = ("LERP", "ArithLerp.lerp_between", "Arith.Lerp", "Linear interpolation stays between the segment's end values",
         "In a rising segment with break-point value c0 and slope s, the interpolated value (c0 * 2^D + s * d) / 2^D lies between c0 and c0 + s for every position d below 2^D and every D: the table variant cannot overshoot its segment",
         "{rtl}", ("assign prod_{l}", "assign sh_{l}"), "arith/{fn}/{rtl} (the product, sum and shift lines of the interpolation)", "formal/lean/Arith/Lerp.lean (interp)")
_MONO = ("LERP-MONO", "ArithLerp.lerp_mono", "Arith.Lerp", "Linear interpolation does not fall as the position grows",
         "Within a segment of non-negative slope the interpolated value is non-decreasing in the position d, for every D, c0 and s",
         "{rtl}", ("assign prod_{l}", "assign sh_{l}"), "arith/{fn}/{rtl} (the product, sum and shift lines of the interpolation)", "formal/lean/Arith/Lerp.lean (interp)")
_HYP = ("HYP", "ArithCordic.hyp_step_invariant", "Arith.Cordic", "A hyperbolic CORDIC step scales x^2 - y^2 by a constant",
        "For every direction d = +-1 and every shift (scaled by u = 2^i), the step (u x + d y, u y + d x) multiplies x^2 - y^2 by exactly u^2 - 1, whatever the data: the hyperbolic gain is a data-independent constant",
        "rtl/{fn}_cordic.sv", ("xr <= dpos ? xi + (yi >>> SHI)", "yr <= dpos ? yi + (xi >>> SHI)"), "arith/{fn}/rtl/{fn}_cordic.sv (the x and y adders of one stage)", "formal/lean/Arith/Cordic.lean (the statement itself)")
_CIRC = ("CIRC", "ArithCordic.circ_step_norm", "Arith.Cordic", "A circular CORDIC step scales the squared length by a constant",
         "For every direction d = +-1 and every shift (scaled by u = 2^i), the step (u x - d y, u y + d x) multiplies x^2 + y^2 by exactly u^2 + 1, whatever the data: the CORDIC gain is a data-independent constant",
         "{rtl}", ("{c1}", "{c2}"), "arith/{fn}/{rtl} (the x and y adders of one stage)", "formal/lean/Arith/Cordic.lean (the statement itself)")


def _fill(e, **kw):
    return tuple(x.format(**kw) if isinstance(x, str) else tuple(y.format(**kw) for y in x) for x in e)


LEAN["exp2"] = [_fill(_LERP, rtl="rtl/exp2_lerp.sv", l="y", fn="exp2"), _fill(_MONO, rtl="rtl/exp2_lerp.sv", l="y", fn="exp2"), _fill(_HYP, fn="exp2")]
LEAN["log2"] = [_fill(_LERP, rtl="rtl/log2_lerp.sv", l="y", fn="log2"), _fill(_MONO, rtl="rtl/log2_lerp.sv", l="y", fn="log2"),
                (_HYP[0], _HYP[1], _HYP[2], _HYP[3], _HYP[4], "rtl/log2_cordic.sv", ("xr <= dpos ? xi + (yi >>> SHI)", "yr <= dpos ? yi + (xi >>> SHI)"),
                 "arith/log2/rtl/log2_cordic.sv (the x and y adders of one stage)", _HYP[8])]
LEAN["sincos"] = [
    ("QUAD-SPLIT", "ArithQuadrant.quadrant_split", "Arith.Quadrant", "The phase splits into a quadrant and an angle without loss",
     "For every width k, a phase below 4 * 2^k splits into a quadrant (its top two bits) below 4 and an angle (the rest) so that quadrant * 2^k + angle is the phase again",
     "rtl/sincos_lerp.sv", ("assign {q, idx, d} = phase;", "assign {q, idx, d} = phase;"), "arith/sincos/rtl/sincos_lerp.sv (the bit-field split of the phase)", "formal/lean/Arith/Quadrant.lean (the statement itself)"),
    ("QUAD-JOIN", "ArithQuadrant.quadrant_join", "Arith.Quadrant", "Every quadrant and angle pair is one phase",
     "For every width k, any quadrant and any angle below 2^k put together split back into the same quadrant and the same angle: the split is a bijection",
     "rtl/sincos_lerp.sv", ("assign {q, idx, d} = phase;", "assign {q, idx, d} = phase;"), "arith/sincos/rtl/sincos_lerp.sv (the bit-field split of the phase)", "formal/lean/Arith/Quadrant.lean (the statement itself)"),
    _fill(_LERP, rtl="rtl/sincos_lerp.sv", l="s", fn="sincos"),
    _fill(_CIRC, rtl="rtl/sincos_cordic.sv", c1="xr <= dpos ? xi - (yi >>> k)", c2="yr <= dpos ? yi + (xi >>> k)", fn="sincos")]
LEAN["atan2_mag"] = [_fill(_CIRC, rtl="rtl/atan2_cordic.sv", c1="xn = xt + (yt >>> (s * GR + j));", c2="yn = yt - (xt >>> (s * GR + j));", fn="atan2_mag")]


_FLOAT_LEAN = [
    ("CARRY", "ArithFloat.pack_inc_carry", "Arith.Float", "Rounding increment carries into the exponent",
     "For a packed pattern e * m + f with fraction f < m (m = 2^MAN), adding the rounding increment 1 either raises the fraction by one or, when the fraction is all ones, raises the exponent by one and leaves a zero fraction: the identity fp_pack's single add on the packed {exponent, fraction} pattern rests on, so a significand overflow, a subnormal rounding up to the smallest normal number and a largest finite number rounding up to infinity need no special case",
     "arith/fp_common/fp_pack.sv", ("assign wsum", "assign wsum"), "arith/fp_common/fp_pack.sv (wsum: the increment added to the packed pattern)", "formal/lean/Arith/Float.lean (pack_inc_carry)"),
    ("NORM", "ArithFloat.norm_shift", "Arith.Float", "Normalising left by NW - 1 - msb puts the leading one at the top",
     "For a value v with its leading one at bit k (2^k <= v < 2^(k+1)) and k < NW, shifting left by NW - 1 - k places gives a value in [2^(NW-1), 2^NW): the leading one is at bit NW - 1, which is what fp_norm's count lz = NW - 1 - msb does",
     "arith/fp_common/fp_norm.sv", ("n = v << lz;", "n = v << lz;"), "arith/fp_common/fp_norm.sv (the shift by the leading-zero count)", "formal/lean/Arith/Float.lean (norm_shift)"),
    ("RNE", "ArithFloat.rne_nearest_even", "Arith.Float", "The rounding decision is round-to-nearest, ties to even",
     "For a kept part hi and a discarded part lo below the threshold 2h, incrementing hi exactly when lo > h, or lo = h and hi is odd (the guard-and-sticky rule of fp_pack), gives a value within h of the exact one and, when it is exactly h away, even",
     "arith/fp_common/fp_pack.sv", ("assign inc", "assign inc"), "arith/fp_common/fp_pack.sv (guard, rest and inc)", "formal/lean/Arith/Float.lean (rneInc, rne_nearest_even)"),
]
LEAN["fp_add"] = LEAN["fp_mul"] = LEAN["fp_fma"] = _FLOAT_LEAN


def lean_lines(fn: str, rtlf: str, rng: tuple) -> tuple[str, str]:
    """(file path as the testplan names it, line range): a path starting arith/ is relative to the repository, else to the function's folder."""
    if rtlf.startswith("arith/"):
        ls = (ac.ROOT / rtlf).read_text().splitlines()
        a = next(i for i, l in enumerate(ls, 1) if rng[0] in l)
        b = next(i for i, l in enumerate(ls, 1) if i >= a and rng[1] in l)
        return rtlf, f"{a}-{b}"
    return f"arith/{fn}/{rtlf}", lines_of(fn, rtlf, rng[0], rng[1])


def acc_lines(fn: str) -> str:
    ls = (ac.ARITH / fn / "rtl/mac_dsp.sv").read_text().splitlines()
    a = next(i for i, l in enumerate(ls, 1) if "else if (en_m) acc <=" in l)
    return f"{a - 1}-{a}"


def plan(fn: str) -> str:
    s = ac.load_spec(fn)
    pre = P[fn]
    base = f"arith/{fn}"
    jobs = yaml.safe_load((ac.ARITH / fn / "formal" / "jobs.yaml").read_text())["jobs"]
    kinds = {job_kind(j) for j in jobs}
    rtl = []                                                  # every file whose change makes the evidence stale: the variants and the shared files they need
    for v in s["variants"].values():
        for x in [f"{base}/{v['file']}"] + [f"arith/{d}" for d in v.get("deps", [])]:
            if x not in rtl:
                rtl.append(x)
    res = f"{base}/verif/results"
    junit = f"{res}/pytest_junit.xml"
    bench = [f"{base}/tests/{fn}_cocotb.py", f"{base}/model.py"] + (["arith/tools/fxlib.py"] if fn in ELEM else [])
    formal_files = [f"{base}/formal/{x.name}" for x in sorted((ac.ARITH / fn / "formal").glob("*.sv"))] + [f"{base}/formal/jobs.yaml"]
    lat = {v: vd["latency"] for v, vd in s["variants"].items()}
    nv = len(s["variants"])
    proofs = [j for j in jobs if job_kind(j) == "proof"]
    bounded = [j for j in jobs if job_kind(j) == "bounded"]

    R = [
        dict(id=f"{pre}-F-MODEL", kind="functional", title="The bit-exact model is right",
             text=f"{base}/model.py gives, for every input, the result that spec.md defines. It agrees with an independent formulation ({INDEP[fn]}) on every input at small widths and with Python's integer arithmetic on random large-width inputs, and the conventions that a user could guess wrong (spec.md, last section) are pinned by examples.",
             source=f"{base}/spec.md", spec_status="draft"),
        dict(id=f"{pre}-F-EXACT", kind="functional", title="Every variant is bit-exact against the model",
             text=f"At every parameter point listed in spec.yaml ({sum(len(v['exhaustive_points']) for v in s['variants'].values())} exhaustive points, {sum(len(v['random_points']) for v in s['variants'].values())} random ones, across {nv} variants), each variant's outputs equal the model's in every clock: every input is driven at the small points; edge values, runs of ones, and random inputs at the large ones. The function is exact, so there is no error bound.",
             source=f"{base}/spec.md", spec_status="draft"),
        dict(id=f"{pre}-F-LAT", kind="functional", title="Latency is as specified and the bench would notice if it were not",
             text="Each variant's latency in clocks is the expression in spec.yaml (" + "; ".join(f"{v}: {x}" for v, x in lat.items()) + "), and the bench, run with a latency two clocks off, fails for every variant, so the passing runs prove the latency rather than assume it.",
             source=f"{base}/spec.md", spec_status="draft"),
        dict(id=f"{pre}-F-EQUIV", kind="functional", title="The variants are equivalent to a plain reference, by proof where the tools allow",
             text="SymbiYosys with the slang front end checks the variants against each other and a plain reference (a single `+` or `*`, or the specification written as RTL). The jobs in formal/jobs.yaml name the widths; a proof is by k-induction (for all inputs, any run length) at the widths listed there, a bounded check holds only to its stated depth. Widths beyond the listed ones are covered by simulation, not by proof.",
             source=f"{base}/formal/jobs.yaml", spec_status="draft"),
        dict(id=f"{pre}-F-BENCH", kind="functional", title="The bench catches seeded faults",
             text=f"Every one of the mutants in verif/mutants.yaml (one exact text change each, in the variant's RTL: an inverted condition, a wrong constant, a dropped connection, a lost reset) makes the cocotb bench fail; mutants that survive or do not build are reported, never hidden.",
             source=f"{base}/verif/mutants.yaml", spec_status="draft"),
        dict(id=f"{pre}-F-HARNESS", kind="functional", title="The packaged verification harness is a standalone deliverable that works",
             text=f"{base}/harness holds the model, the cocotb bench, a SystemVerilog checker, coverage targets and a runner that needs nothing else from the repository. Run standalone against every variant (one small exhaustive point and one large random point each, with the checker beside the instance) it passes and the random runs meet every coverage target; run against a planted fault it fails, with and without the checker. Its generated files are the repository's own bench, so they cannot drift.",
             source=f"{base}/harness/README.md", spec_status="draft"),
        dict(id=f"{pre}-F-PACKAGE", kind="functional", title="The RTL is lint-clean, and its files agree with the specification and with the Vivado build files",
             text="spec.yaml states an interface contract (protocol, throughput, latency, reset, clock, stalls) and integration guidance (port timing, constraints to carry). Every variant passes Verilator -Wall at every point of spec.yaml; its ports and default parameters are the ones spec.yaml states; its header states the intended primitive use before any Vivado run; spec.md is the rendering of spec.yaml; the out-of-context wrapper and the build.yaml for each variant (Artix-7 xc7a100t and K26 xck26, prepared and not run) are current and lint-clean at every point they list, so a Vivado run can start from the repository alone.",
             source=f"{base}/spec.yaml", spec_status="draft"),
    ]
    if fn in ELEM:
        npts = sum(len(v["accuracy_points"]) for v in s["variants"].values())
        for r in R:
            if r["id"] == f"{pre}-F-EXACT":
                r["title"] = "Every variant is bit-exact against its own model"
                r["text"] = (f"At every parameter point listed in spec.yaml ({sum(len(v['exhaustive_points']) for v in s['variants'].values())} exhaustive points, {sum(len(v['random_points']) for v in s['variants'].values())} random ones, "
                             f"across {nv} variants), each variant's outputs equal its own model's (model.py, selected by variant) in every clock: every input is driven at the small points; edge values, table break points and random "
                             "inputs at the large ones. The variants round differently and are not bit-identical to each other; the model of each is the bit-exact definition of that variant, and its distance from the exact function is "
                             "the accuracy requirement.")
            if r["id"] == f"{pre}-F-EQUIV":
                r["title"] = "The error against the exact function is bounded for all inputs, by proof, at a small input width"
                r["text"] = ("SymbiYosys with the slang front end compares each variant, delayed by its latency, with the exact function on 8 input bits to 24 fractional bits (a reference ROM written from the maths library, formal/*_ref.sv) "
                             "and asserts the error stays within the bound of the job, which is the model's measured error at that point plus one unit for the reference's own rounding. A proof is by k-induction (for all inputs, any run length) "
                             "at the widths in formal/jobs.yaml; wider points are covered by the exhaustive scan of the accuracy requirement and by simulation, not by proof. The quadrant map and the variants' structural identities are inside the checks.")
        R.insert(next(i for i, r in enumerate(R) if r["id"] == f"{pre}-F-LAT"),
                 dict(id=f"{pre}-F-ACC", kind="functional", title="The error against the exact function is within the stated bound, at every listed point",
                      text=(f"Each of the {npts} accuracy points of spec.yaml states a bound in last places; the model's error against the exact function (the maths library, real arithmetic, unrounded) over EVERY input of that point is at most the bound "
                            "and within 0.06 of it (so the bound is neither false nor loose). A point not listed has no stated bound."),
                      source=f"{base}/spec.md", spec_status="draft"))
    for key, thm, mod, title, text, rtlf, rng, rtls, trans in LEAN[fn]:
        R.append(dict(id=f"{pre}-F-LEAN-{key}", kind="functional", title=f"{title}, for every width",
                      text=text + ". The statement is the specification and is NOT approved by a human (verif/lean_approvals.yaml is empty), so the proof is shown but not counted as verification. The Lean text is a hand transcription of the RTL's structure; it models no timing or clocking.",
                      source=rtls, spec_status="draft"))
    V = []

    def item(id_, reqs, method, title, evidence, **kw):
        d = dict(id=id_, requirements=reqs, method=method, title=title)
        if evidence:
            d["evidence"] = evidence
        d.update(kw)
        V.append(d)

    item(f"V-{pre}-MODEL", [f"{pre}-F-MODEL"], "sim_test", "The model against independent formulations (exhaustive small, random large) and the pinned conventions",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_model::*"]}, checks=[f"{base}/model.py"] + (["arith/tools/fxlib.py"] if fn in ELEM else []))
    item(f"V-{pre}-EXHAUSTIVE", [f"{pre}-F-EXACT"], "sim_test", "Every variant against the model, every input, at the small points (Icarus + cocotb)",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_exhaustive_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-RANDOM", [f"{pre}-F-EXACT"], "sim_test", "Every variant against the model at the large points: edge values, carry runs and random inputs (Icarus + cocotb)",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_random_rtl::*"]}, checks=rtl + bench)
    if fn in ELEM:
        item(f"V-{pre}-ACCURACY", [f"{pre}-F-ACC"], "sim_test", "The model's error against the exact function over every input of every listed point, against the stated bounds",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_accuracy::*"]}, checks=[f"{base}/model.py", f"{base}/spec.yaml", "arith/tools/fxlib.py"])
    item(f"V-{pre}-LATENCY", [f"{pre}-F-LAT"], "sim_test", "The bench passes at the stated latency and fails two clocks off, for every variant",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_latency_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-FORMAL-PROOF", [f"{pre}-F-EQUIV"], "formal", (f"k-induction proofs of the variants' error bounds against the exact function ({len(proofs)} jobs; widths in formal/jobs.yaml)" if fn in ELEM else f"k-induction proofs of the variants against the reference ({len(proofs)} jobs; widths in formal/jobs.yaml)"),
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_formal_proof_rtl::*"]}, checks=rtl + formal_files)
    if "bounded" in kinds:
        item(f"V-{pre}-FORMAL-BOUNDED", [f"{pre}-F-EQUIV"], "formal", f"Bounded model checking from reset ({len(bounded)} job: a larger width than the proofs reach)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_formal_bounded_rtl::*"]}, checks=rtl + formal_files, bounded={"depth": max(j["depth"] for j in bounded)})
    item(f"V-{pre}-FORMAL-REFUTE", [f"{pre}-F-EQUIV"], "formal", "Each formal check refutes a planted fault (the check can fail)",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_formal_refute_rtl::*"]}, checks=rtl + formal_files)
    item(f"V-{pre}-MUTANT-TEST", [f"{pre}-F-BENCH"], "sim_test", "The mutation run as a test: no mutant survives, none fails to build",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_mutants_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-MUTANT-SCORE", [f"{pre}-F-BENCH"], "sim_measurement", "Mutants killed of valid mutants (the record of the last full run)",
         {"file": f"{res}/mutation.json", "reader": "json"},
         pass_when=[{"field": "survived", "op": "eq", "value": []}, {"field": "invalid", "op": "eq", "value": []}, {"field": "valid", "op": "ge", "value": 10},
                    {"field": "score_pct", "op": "eq", "value": 100.0}], checks=rtl + bench + [f"{base}/verif/mutants.yaml"])
    item(f"V-{pre}-HARNESS", [f"{pre}-F-HARNESS"], "sim_test", "The packaged harness run standalone on every variant (with the checker and the coverage targets) and on a planted fault",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_harness_rtl::*"]}, checks=rtl + [f"{base}/harness/{x}" for x in ("assertions.sv", "chk_top.sv", "coverage.yaml", "run_harness.py", "model.py", "bench.py") + (("fp_ref.py", "fpx_ref.sv") if fn.startswith("fp_") else ())])
    item(f"V-{pre}-PACKAGE", [f"{pre}-F-PACKAGE"], "sim_test", "spec.yaml against the RTL headers, spec.md against spec.yaml, Verilator -Wall at every point, wrappers and build.yaml current and lint-clean",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_package::*"]}, checks=rtl + [f"{base}/spec.yaml", f"{base}/spec.md"] + [f"{base}/build/{v}/build.yaml" for v in s["variants"]])
    for key, thm, mod, title, text, rtlf, rng, rtls, trans in LEAN[fn]:
        if fn == "mac":
            lines, rfile = acc_lines(fn), f"{base}/{rtlf}"
        else:
            rfile, lines = lean_lines(fn, rtlf, rng)
        item(f"V-{pre}-LEAN-{key}", [f"{pre}-F-LEAN-{key}"], "formal_lean", title, None, lean={"module": mod, "theorem": thm},
             rtl_link={"kind": "transcription_untested", "source": [{"file": rfile, "lines": lines}], "transcribed_in": trans})
    doc = {"schema": "fpga-design-agent/testplan/v1", "design": f"arith_{fn}",
           "notes": (f"Arithmetic library, function {fn} (brief {'139d' if fn in ELEM else '139e' if fn.startswith('fp_') else '139a'}). Everything here is before Vivado: the model, the RTL variants, simulation, formal equivalence, Lean statements and the prepared out-of-context build files. "
                     "No performance requirement exists because nothing about LUTs, DSPs, Fmax or power has been measured yet; the Vivado runs (build/<variant>/build.yaml) will add them. "
                     "Every requirement is a draft written by the agent; none is agreed by a human. Lean statements are not approved. Generated by arith/tools/gen_testplan.py."),
           "discover": [{"glob": f"arith/{fn}/tests/test_*.py", "pattern": r"^def (test_\w+)"}],
           "requirements": R, "verification": V}
    head = (f"# {fn} testplan, schema v1 (brief 116) for the arithmetic library (brief {ac.brief_of(fn)}). GENERATED by `python -m arith.tools.gen_testplan` from spec.yaml, formal/jobs.yaml and the\n"
            "# test files: edit those, not this file. Status is never typed here: `python -m flow.trace_v1 write` reads the recorded evidence in verif/results/ and computes it.\n")
    return head + yaml.safe_dump(doc, sort_keys=False, width=180, allow_unicode=True)


APPROVALS = ("# Human approvals of Lean theorem statements (brief 125). THE OWNER EDITS THIS FILE; no agent and no tool in this repository writes it.\n"
             "# Empty: every Lean statement of this function shows \"statement not approved\" and its proof is not counted as verification. To approve one, read it with\n"
             "#     python -m flow.trace_v1 lean-statement arith/{fn} V-<ITEM>\n"
             "# and add an entry as designs/b96_kr260_10g/verif/lean_approvals.yaml describes.\n"
             "schema: fpga-design-agent/lean-approvals/v1\napprovals: []\n")


def outputs(fn: str) -> dict[Path, str]:
    if fn in ac.FFT_FUNCTIONS:                                # brief 148: the frequency-domain suite has its own plan (no harness, no Lean)
        from arith.tools import gen_testplan_fft
        return {ac.ARITH / fn / "verif" / "testplan.yaml": gen_testplan_fft.plan(fn)}
    return {ac.ARITH / fn / "verif" / "testplan.yaml": plan(fn), ac.ARITH / fn / "verif" / "lean_approvals.yaml": APPROVALS.format(fn=fn)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("functions", nargs="*", default=list(ac.ALL_FUNCTIONS))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = 0
    for fn in a.functions:
        for p, t in outputs(fn).items():
            if a.check:
                if not p.exists() or p.read_text() != t:
                    print("out of date:", p.relative_to(ac.ROOT))
                    bad = 1
            else:
                p.write_text(t)
                print("wrote", p.relative_to(ac.ROOT))
    return bad


if __name__ == "__main__":
    sys.exit(main())
