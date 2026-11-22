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

P = {"adder": "ADD", "multiplier": "MUL", "mac": "MAC"}
INDEP = {"adder": "a bit-serial chain of full adders", "multiplier": "a shift-and-add formulation (and, for the Booth recoding, the digit-sum identity)",
         "mac": "a structure-free reference that applies the samples one at a time with Python integers"}


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
    rtl = [f"{base}/{v['file']}" for v in s["variants"].values()]
    res = f"{base}/verif/results"
    junit = f"{res}/pytest_junit.xml"
    bench = [f"{base}/tests/{fn}_cocotb.py", f"{base}/model.py"]
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
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_model::*"]}, checks=[f"{base}/model.py"])
    item(f"V-{pre}-EXHAUSTIVE", [f"{pre}-F-EXACT"], "sim_test", "Every variant against the model, every input, at the small points (Icarus + cocotb)",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_exhaustive_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-RANDOM", [f"{pre}-F-EXACT"], "sim_test", "Every variant against the model at the large points: edge values, carry runs and random inputs (Icarus + cocotb)",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_random_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-LATENCY", [f"{pre}-F-LAT"], "sim_test", "The bench passes at the stated latency and fails two clocks off, for every variant",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_latency_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-FORMAL-PROOF", [f"{pre}-F-EQUIV"], "formal", f"k-induction proofs of the variants against the reference ({len(proofs)} jobs; widths in formal/jobs.yaml)",
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
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_harness_rtl::*"]}, checks=rtl + [f"{base}/harness/{x}" for x in ("assertions.sv", "chk_top.sv", "coverage.yaml", "run_harness.py", "model.py", "bench.py")])
    item(f"V-{pre}-PACKAGE", [f"{pre}-F-PACKAGE"], "sim_test", "spec.yaml against the RTL headers, spec.md against spec.yaml, Verilator -Wall at every point, wrappers and build.yaml current and lint-clean",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_package::*"]}, checks=rtl + [f"{base}/spec.yaml", f"{base}/spec.md"] + [f"{base}/build/{v}/build.yaml" for v in s["variants"]])
    for key, thm, mod, title, text, rtlf, rng, rtls, trans in LEAN[fn]:
        if fn == "mac":
            lines = acc_lines(fn)
        else:
            lines = lines_of(fn, rtlf, rng[0], rng[1])
        item(f"V-{pre}-LEAN-{key}", [f"{pre}-F-LEAN-{key}"], "formal_lean", title, None, lean={"module": mod, "theorem": thm},
             rtl_link={"kind": "transcription_untested", "source": [{"file": f"{base}/{rtlf}", "lines": lines}], "transcribed_in": trans})
    doc = {"schema": "fpga-design-agent/testplan/v1", "design": f"arith_{fn}",
           "notes": (f"Arithmetic library, function {fn} (brief 139a). Everything here is before Vivado: the model, the RTL variants, simulation, formal equivalence, Lean statements and the prepared out-of-context build files. "
                     "No performance requirement exists because nothing about LUTs, DSPs, Fmax or power has been measured yet; the Vivado runs (build/<variant>/build.yaml) will add them. "
                     "Every requirement is a draft written by the agent; none is agreed by a human. Lean statements are not approved. Generated by arith/tools/gen_testplan.py."),
           "discover": [{"glob": f"arith/{fn}/tests/test_*.py", "pattern": r"^def (test_\w+)"}],
           "requirements": R, "verification": V}
    head = (f"# {fn} testplan, schema v1 (brief 116) for the arithmetic library (brief 139a). GENERATED by `python -m arith.tools.gen_testplan` from spec.yaml, formal/jobs.yaml and the\n"
            "# test files: edit those, not this file. Status is never typed here: `python -m flow.trace_v1 write` reads the recorded evidence in verif/results/ and computes it.\n")
    return head + yaml.safe_dump(doc, sort_keys=False, width=180, allow_unicode=True)


APPROVALS = ("# Human approvals of Lean theorem statements (brief 125). THE OWNER EDITS THIS FILE; no agent and no tool in this repository writes it.\n"
             "# Empty: every Lean statement of this function shows \"statement not approved\" and its proof is not counted as verification. To approve one, read it with\n"
             "#     python -m flow.trace_v1 lean-statement arith/{fn} V-<ITEM>\n"
             "# and add an entry as designs/b96_kr260_10g/verif/lean_approvals.yaml describes.\n"
             "schema: fpga-design-agent/lean-approvals/v1\napprovals: []\n")


def outputs(fn: str) -> dict[Path, str]:
    return {ac.ARITH / fn / "verif" / "testplan.yaml": plan(fn), ac.ARITH / fn / "verif" / "lean_approvals.yaml": APPROVALS.format(fn=fn)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("functions", nargs="*", default=list(ac.FUNCTIONS))
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
