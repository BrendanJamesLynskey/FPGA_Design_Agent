"""The v1 testplan of the frequency-domain functions (arith brief 148): the same schema and the same evidence kinds as gen_testplan.plan, without the packaged harness and the Lean
statements these functions do not have (their gaps are stated in each spec.yaml and in the report), and with the directed bench named 'directed' (impulses, tones, corner values:
a basis, not every input) and, for the FFT, an accuracy measurement against NumPy.

Called by arith/tools/gen_testplan.py; not run on its own."""
from __future__ import annotations

import yaml

from arith.tools import arith_common as ac
from arith.tools.suite import job_kind

P = {"fft_cmul": "FCMUL", "fft_twiddle": "FTW", "fft_reorder": "FRO", "fft_window": "FWIN", "fft": "FFT", "fft_real": "FREAL", "fft_axis": "FAXIS"}
INDEP = {
    "fft_cmul": "a second formulation (the three-multiplication identity) in Python integers",
    "fft_twiddle": "high-precision (60 decimal digit) cosines and sines of every angle, with the stated rounding error bound",
    "fft_reorder": "a bit-string reversal of every position, and the involution and permutation properties for every LOGN up to 12",
    "fft_window": "exact rational arithmetic of the rounding rule and the bound |y| <= |x|",
    "fft_axis": "the wrapped variants' own models (arith/fft/model.py) and the packing of {imaginary, real} words",
    "fft_real": "numpy.fft.rfft (the N/2 + 1 bins, both scaling modes, both FFT variants as the core) and the equality of the complex-core path with a direct split",
    "fft": "NumPy's FFT (forward and inverse), checked for both variants at every N from 8 to 1024, and the identity that the inverse is the swap of a forward transform",
}
EXACT_TEXT = {
    "fft_cmul": "every input is driven at the small points (4 operands of 2 to 4 bits); edge values and random inputs at the large ones. The function is exact, so there is no error bound.",
    "fft_twiddle": "every index of the circle is driven at every simulated point (up to the full 4096-point circle), and random indices at the others. The values are table entries, so there is no error bound beyond the stated rounding of the table.",
    "fft_reorder": "frames of distinct words (so a wrong address shows at once), back to back and after gaps of 0, 1, 2 and more clocks, up to N = 4096, and random words. The function is an exact permutation.",
    "fft_window": "every (xr, xi, w) is driven at the small points; edge values and random inputs at the large ones. The error bound (half a unit in the last place) is the model's rounding.",
    "fft_axis": "the directed points send the FFT bench's frames as AXI4-Stream beats with no pauses (the first-beat latency equals the formula); the random points send random frames, the burst variant with random tvalid pauses inside and between frames and a sink that stalls 40 per cent of the clocks, the sdf variant with the legal gaps. Every output frame equals the model bit for bit, tlast is on the right beat, and the protocol checkers (valid stability, data stability, no unknowns, tlast position, no stall for sdf, no pause inside a frame for sdf) count no error.",
    "fft_real": "the directed points drive impulses at several positions, tones, DC, Nyquist and corner values as pairs of real samples, with the shortest legal spacing and longer ones; the random points drive random real frames with random legal spacing up to N = 2048. Each output frame of N/2 + 1 bins equals the model bit for bit, the latency from in_sof to out_sof equals the formula, and out_valid is N/2 + 1 consecutive clocks.",
    "fft": "the directed points drive impulses at every position and tones at every bin (small N), DC, Nyquist, a chirp and corner values, forward and inverse, back to back and after the shortest legal gap; the random points drive random frames with random direction and legal gaps up to N = 4096. Each output frame equals the model bit for bit, the latency from in_sof to out_sof equals the formula, and out_valid is N consecutive clocks.",
}


def plan(fn: str) -> str:
    s = ac.load_spec(fn)
    pre = P[fn]
    base = f"arith/{fn}"
    d = ac.ARITH / fn
    jobs = yaml.safe_load((d / "formal" / "jobs.yaml").read_text())["jobs"] if (d / "formal" / "jobs.yaml").exists() else []
    rtl = []
    for v in s["variants"].values():
        for x in [f"{base}/{v['file']}"] + [f"arith/{p}" for p in v.get("deps", [])]:
            if x not in rtl:
                rtl.append(x)
    res = f"{base}/verif/results"
    junit = f"{res}/pytest_junit.xml"
    bench = [f"{base}/tests/{fn}_cocotb.py", f"{base}/model.py"] + (["arith/fft_common/frames.py", "arith/fft_common/fft_ref.py"] if fn in ("fft", "fft_reorder", "fft_real", "fft_axis") else [])
    formal_files = [f"{base}/formal/{x.name}" for x in sorted((d / "formal").glob("*.sv"))] + [f"{base}/formal/jobs.yaml"] if jobs else []
    lat = {v: vd["latency"] for v, vd in s["variants"].items()}
    nv = len(s["variants"])
    kinds = {job_kind(j) for j in jobs}
    R = [
        dict(id=f"{pre}-F-MODEL", kind="functional", title="The bit-exact model is right",
             text=f"{base}/model.py gives, for every input, the result that spec.md defines. It agrees with an independent formulation ({INDEP[fn]}), and the conventions that a user could guess wrong (spec.md, last section) are pinned by examples.",
             source=f"{base}/spec.md", spec_status="draft"),
        dict(id=f"{pre}-F-EXACT", kind="functional", title="Every variant is bit-exact against the model",
             text=f"At every parameter point listed in spec.yaml ({sum(len(v['exhaustive_points']) for v in s['variants'].values())} directed or exhaustive points, {sum(len(v['random_points']) for v in s['variants'].values())} random ones, across {nv} variants), each variant's outputs equal the model's: {EXACT_TEXT[fn]}",
             source=f"{base}/spec.md", spec_status="draft"),
        dict(id=f"{pre}-F-LAT", kind="functional", title="Latency is as specified and the bench would notice if it were not",
             text="Each variant's latency in clocks is the expression in spec.yaml (" + "; ".join(f"{v}: {x}" for v, x in lat.items()) + "), and the bench, run with a latency two clocks off, fails for every variant, so the passing runs prove the latency rather than assume it.",
             source=f"{base}/spec.md", spec_status="draft"),
    ]
    if jobs:
        R.append(dict(id=f"{pre}-F-EQUIV", kind="functional", title="The properties named in formal/jobs.yaml hold, by proof where the tools allow",
                      text="SymbiYosys with the slang front end checks the properties of formal/jobs.yaml: a proof is by k-induction (for all inputs, any run length) at the parameters listed there, a bounded check holds only to its stated depth. What the jobs say is in each job's `claim`; parameters beyond the listed ones are covered by simulation, not by proof.",
                      source=f"{base}/formal/jobs.yaml", spec_status="draft"))
    R += [
        dict(id=f"{pre}-F-BENCH", kind="functional", title="The bench catches seeded faults",
             text="Every one of the mutants in verif/mutants.yaml (one exact text change each: an inverted condition, a wrong constant, a dropped connection, a wrong width) makes the cocotb bench fail, or is argued equivalent in the file's header; mutants that survive or do not build are reported, never hidden.",
             source=f"{base}/verif/mutants.yaml", spec_status="draft"),
        dict(id=f"{pre}-F-PACKAGE", kind="functional", title="The RTL is lint-clean, and its files agree with the specification and with the Vivado build files",
             text="spec.yaml states an interface contract (protocol, throughput, latency, reset, clock, stalls) and integration guidance (port timing, constraints to carry). Every variant passes Verilator -Wall at every point of spec.yaml; its ports and default parameters are the ones spec.yaml states; its header states the intended primitive use before any Vivado run; spec.md is the rendering of spec.yaml; the out-of-context wrapper and the build.yaml for each variant (Artix-7 xc7a100t and K26 xck26, prepared and not run) are current and lint-clean at every point they list, so a Vivado run can start from the repository alone.",
             source=f"{base}/spec.yaml", spec_status="draft"),
    ]
    if fn == "fft_axis":
        R.append(dict(id=f"{pre}-F-AXIS", kind="interface", title="The AXI4-Stream handshake rules hold, and the checkers can fail",
                      text="On both streams of both variants the wrapper's SystemVerilog protocol checkers (fft_common/axis_checker.sv: valid stays high until accepted, tdata and tlast stable while stalled, no unknowns after reset, tlast on every N-th beat, no stall on the streaming variant, no pause inside a frame where the variant forbids it) count zero violations in every run of the directed and random benches, which stall the burst variant's sink and pause its source at random; tvalid is registered and independent of tready by construction (a mutant that makes it depend on tready is killed by the valid-stability rule). A deliberate-violation test shows each checker can fail. The back-pressure of each variant is stated in spec.yaml (sdf none, burst full).",
                      source=f"{base}/spec.md", spec_status="draft"))
    if fn == "fft":
        R.append(dict(id=f"{pre}-F-BACKPRESSURE", kind="functional", title="The burst variant honours out_ready: stalling the sink changes nothing but the timing",
                      text="With out_ready driven low at random (40 per cent of the clocks) the burst variant's output frames equal the model bit for bit, and out_valid, out_sof and the data stay unchanged in every clock in which out_valid is high and out_ready low. The sdf variant ignores out_ready (stated).",
                      source=f"{base}/spec.md", spec_status="draft"))
    if fn == "fft":
        R.append(dict(id=f"{pre}-F-ACCURACY", kind="functional", title="Accuracy against NumPy's FFT is measured and stated, per scaling mode",
                      text="For each variant, scaling mode and several N and twiddle widths, the error of the model (which the RTL equals bit for bit) against the double-precision FFT of NumPy is recorded in verif/results/accuracy.json: worst and rms error in units of the output LSB, and the SQNR and SFDR for a full-scale tone. The recorded worst error of the scaled mode is at most 6 LSB at every recorded point, and the unscaled mode's SQNR for noise-like input is at least 80 dB at every recorded point with twiddles of 16 bits or more (the unscaled word is W + LOGN bits wide, so its error in output LSBs is large for narrow twiddles: the SQNR is the figure to read); these are the bounds the test enforces, and the figures are what the report states, with no claim beyond them.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-ROUNDTRIP", kind="functional", title="A forward transform followed by an inverse transform returns the input within the stated error",
                      text="Through the RTL (both variants, the scaled mode), forward then inverse of the same frames returns the input divided by N (the scaled mode divides by N in both directions) to within 3 LSB, at the point of the round-trip test; the inverse is the swap of a forward transform, so forward and inverse results are related exactly by the swap.",
                      source=f"{base}/spec.md", spec_status="draft"))
    if fn == "fft":
        R.append(dict(id=f"{pre}-F-FASTCONV", kind="functional", title="Fast convolution built on the FFT models equals direct convolution within the stated error (model only, phase 0)",
                      text="arith/fft_common/fastconv.py (overlap-save and overlap-add on the bit-exact FFT models, both variants) equals numpy.convolve of the same samples and taps to within 8 LSB of the output word (N = 128 to 512, L = 1 to 65 taps, W = 16, TW = 18, WH = 24, FH = 14), the two methods agree with each other within the same bound, a unit filter passes the signal within 3 LSB, and a complex input is filtered part by part. This is a Python model and an interface proposal (docs/fft_suite_plan.md section 5), not RTL: the fast-convolution block is the next phase.",
                      source="docs/fft_suite_plan.md", spec_status="draft"))
    V = []

    def item(id_, reqs, method, title, evidence, **kw):
        dd = dict(id=id_, requirements=reqs, method=method, title=title)
        if evidence:
            dd["evidence"] = evidence
        dd.update(kw)
        V.append(dd)

    item(f"V-{pre}-MODEL", [f"{pre}-F-MODEL"], "sim_test", "The model against independent formulations and the pinned conventions",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_model::*"]}, checks=[f"{base}/model.py"] + (["arith/fft_common/fft_ref.py"] if fn.startswith("fft") else []))
    item(f"V-{pre}-DIRECTED", [f"{pre}-F-EXACT"], "sim_test", "Every variant against the model at the small points (Icarus + cocotb): directed or exhaustive stimuli",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_directed_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-RANDOM", [f"{pre}-F-EXACT"] + ([f"{pre}-F-AXIS"] if fn == "fft_axis" else []), "sim_test", "Every variant against the model at the large points: random stimuli (Icarus + cocotb)",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_random_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-LATENCY", [f"{pre}-F-LAT"], "sim_test", "The bench passes at the stated latency and fails two clocks off, for every variant",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_latency_rtl::*"]}, checks=rtl + bench)
    if "proof" in kinds:
        item(f"V-{pre}-FORMAL-PROOF", [f"{pre}-F-EQUIV"], "formal", f"k-induction proofs ({len([j for j in jobs if job_kind(j) == 'proof'])} jobs; parameters in formal/jobs.yaml)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_formal_proof_rtl::*"]}, checks=rtl + formal_files)
    if "bounded" in kinds:
        bj = [j for j in jobs if job_kind(j) == "bounded"]
        item(f"V-{pre}-FORMAL-BOUNDED", [f"{pre}-F-EQUIV"], "formal", f"Bounded model checks from an arbitrary state ({len(bj)} jobs; depths in formal/jobs.yaml)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_formal_bounded_rtl::*"]}, checks=rtl + formal_files, bounded={"depth": max(j["depth"] for j in bj)})
    if "refute" in kinds:
        item(f"V-{pre}-FORMAL-REFUTE", [f"{pre}-F-EQUIV"], "formal", "Each formal check refutes a planted fault (the check can fail)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_formal_refute_rtl::*"]}, checks=rtl + formal_files)
    item(f"V-{pre}-MUTANT-TEST", [f"{pre}-F-BENCH"], "sim_test", "The mutation run as a test: no mutant survives, none fails to build",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_mutants_rtl::*"]}, checks=rtl + bench)
    item(f"V-{pre}-MUTANT-SCORE", [f"{pre}-F-BENCH"], "sim_measurement", "Mutants killed of valid mutants (the record of the last full run)",
         {"file": f"{res}/mutation.json", "reader": "json"},
         pass_when=[{"field": "survived", "op": "eq", "value": []}, {"field": "invalid", "op": "eq", "value": []}, {"field": "valid", "op": "ge", "value": 6},
                    {"field": "score_pct", "op": "eq", "value": 100.0}], checks=rtl + bench + [f"{base}/verif/mutants.yaml"])
    item(f"V-{pre}-PACKAGE", [f"{pre}-F-PACKAGE"], "sim_test", "spec.yaml against the RTL headers, spec.md against spec.yaml, Verilator -Wall at every point, wrappers and build.yaml current and lint-clean",
         {"file": junit, "reader": "junit", "tests": [f"test_{fn}_package::*"]}, checks=rtl + [f"{base}/spec.yaml", f"{base}/spec.md"] + [f"{base}/build/{v}/build.yaml" for v in s["variants"]])
    if fn == "fft_axis":
        item(f"V-{pre}-CHECKER", [f"{pre}-F-AXIS"], "sim_test", "The protocol checkers can fail (a stalled sink on sdf, a withdrawn tvalid on burst)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_checker_rtl::*"]}, checks=rtl + bench)
    if fn == "fft":
        item(f"V-{pre}-BACKPRESSURE", [f"{pre}-F-BACKPRESSURE"], "sim_test", "The burst variant under a randomly stalled sink",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_backpressure_rtl::*"]}, checks=rtl + bench)
    if fn == "fft":
        item(f"V-{pre}-ACCURACY", [f"{pre}-F-ACCURACY"], "sim_measurement", "Worst error against NumPy at every recorded point (the record of the last run)",
             {"file": f"{res}/accuracy.json", "reader": "json"},
             pass_when=[{"field": "worst_lsb_scaled_max", "op": "le", "value": 6.0}, {"field": "sqnr_db_min_unscaled_tw16plus", "op": "ge", "value": 80.0}, {"field": "sfdr_db_min_tw16plus", "op": "ge", "value": 75.0}, {"field": "points", "op": "ge", "value": 20}],
             checks=["arith/fft_common/fft_ref.py", f"{base}/model.py", "arith/tools/fft_accuracy.py"])
        item(f"V-{pre}-FASTCONV", [f"{pre}-F-FASTCONV"], "sim_test", "Overlap-save and overlap-add models against direct convolution",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_fastconv::*"]}, checks=["arith/fft_common/fastconv.py", "arith/fft_common/fft_ref.py", f"{base}/model.py"])
        item(f"V-{pre}-ROUNDTRIP", [f"{pre}-F-ROUNDTRIP"], "sim_test", "Forward then inverse through the RTL returns the input; the inverse is the swap of a forward transform",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_roundtrip_rtl::*"]}, checks=rtl + bench)
    doc = {"schema": "fpga-design-agent/testplan/v1", "design": f"arith_{fn}",
           "notes": (f"Frequency-domain suite, function {fn} (brief 148). Everything here is before Vivado: the model, the RTL variants, simulation, formal properties and the prepared out-of-context build files. "
                     "No performance requirement on LUTs, DSPs, Fmax or power exists because none has been measured; the Vivado runs (build/<variant>/build.yaml, queued in _handoff/fpga_agent/vivado_later_queue.md) will add them. "
                     "Every requirement is a draft written by the agent; none is agreed by a human. There are no Lean statements and no packaged harness for this suite (stated in the report). Generated by arith/tools/gen_testplan_fft.py."),
           "discover": [{"glob": f"arith/{fn}/tests/test_*.py", "pattern": r"^def (test_\w+)"}],
           "requirements": R, "verification": V}
    head = (f"# {fn} testplan, schema v1 (brief 116) for the frequency-domain suite (brief 148). GENERATED by `python -m arith.tools.gen_testplan` from spec.yaml, formal/jobs.yaml and the\n"
            "# test files: edit those, not this file. Status is never typed here: `python -m flow.trace_v1 write` reads the recorded evidence in verif/results/ and computes it.\n")
    return head + yaml.safe_dump(doc, sort_keys=False, width=180, allow_unicode=True)
