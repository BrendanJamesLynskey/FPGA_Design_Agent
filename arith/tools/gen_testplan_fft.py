"""The v1 testplan of the frequency-domain functions (arith brief 148): the same schema and the same evidence kinds as gen_testplan.plan, without the packaged harness and the Lean
statements these functions do not have (their gaps are stated in each spec.yaml and in the report), and with the directed bench named 'directed' (impulses, tones, corner values:
a basis, not every input) and, for the FFT, an accuracy measurement against NumPy.

Called by arith/tools/gen_testplan.py; not run on its own."""
from __future__ import annotations

import yaml

from arith.tools import arith_common as ac
from arith.tools.suite import job_kind

P = {"fft_cmul": "FCMUL", "fft_twiddle": "FTW", "fft_reorder": "FRO", "fft_window": "FWIN", "fft": "FFT", "fft_real": "FREAL", "fft_axis": "FAXIS",
     "fft_bfp": "FBFP", "fft_mdc2": "FMDC", "fft_real_axis": "FRAXIS", "fft_fastconv": "FFC", "fft_mdc2_axis": "FMAXIS"}      # the last four: brief 161; fft_mdc2_axis: brief 168
INDEP = {
    "fft_cmul": "a second formulation (the three-multiplication identity) in Python integers",
    "fft_twiddle": "high-precision (60 decimal digit) cosines and sines of every angle, with the stated rounding error bound",
    "fft_reorder": "a bit-string reversal of every position, and the involution and permutation properties for every LOGN up to 12",
    "fft_window": "exact rational arithmetic of the rounding rule and the bound |y| <= |x|",
    "fft_axis": "the wrapped variants' own models (arith/fft/model.py) and the packing of {imaginary, real} words",
    "fft_real": "numpy.fft.rfft (the N/2 + 1 bins, both scaling modes, both FFT variants as the core) and the equality of the complex-core path with a direct split",
    "fft": "NumPy's FFT (forward and inverse), checked for both variants at every N from 8 to 1024, and the identity that the inverse is the swap of a forward transform",
    "fft_bfp": "NumPy's FFT (the value of every word times 2**exponent against the transform, within the stated bound, both variants, N = 8 to 1024, three input levels), a brute-force search for the smallest shift after which every part fits, and the identities of the order and of the inverse",
    "fft_mdc2": "NumPy's FFT (forward and inverse, both scaling modes, N = 16 to 1024, the pairs put back into natural order) and the identities of the pair order, the swap and the even/odd split",
    "fft_real_axis": "the wrapped core's own model (arith/fft_real/model.py) and the packing of the AXI words (the even sample in the low half of the input word, the real part in the low half of the output word)",
    "fft_mdc2_axis": "the 2-parallel core's own model (arith/fft_common/fft_ref.py mdc2_frame at SCALE = 0), the block-floating-point rule shared with arith/fft_bfp (a brute-force exponent search is in that function's tests), and the packing of the AXI words (sample 0 in the low half, real part in the low half of a sample)",
    "fft_fastconv": "numpy.convolve of the same samples and the unquantised taps (the overlap-save identity, within the stated bound), the bit-exact FFT models it is built from, and the overlap-save and overlap-add models of arith/fft_common/fastconv.py",
}
EXACT_TEXT = {
    "fft_cmul": "every input is driven at the small points (4 operands of 2 to 4 bits); edge values and random inputs at the large ones. The function is exact, so there is no error bound.",
    "fft_twiddle": "every index of the circle is driven at every simulated point (up to the full 4096-point circle), and random indices at the others. The values are table entries, so there is no error bound beyond the stated rounding of the table.",
    "fft_reorder": "frames of distinct words (so a wrong address shows at once), back to back and after gaps of 0, 1, 2 and more clocks, up to N = 4096, and random words. The function is an exact permutation.",
    "fft_window": "every (xr, xi, w) is driven at the small points; edge values and random inputs at the large ones. The error bound (half a unit in the last place) is the model's rounding.",
    "fft_axis": "the directed points send the FFT bench's frames as AXI4-Stream beats with no pauses (the first-beat latency equals the formula); the random points send random frames, the burst variant with random tvalid pauses inside and between frames and a sink that stalls 40 per cent of the clocks, the sdf variant with the legal gaps. Every output frame equals the model bit for bit, tlast is on the right beat, and the protocol checkers (valid stability, data stability, no unknowns, tlast position, no stall for sdf, no pause inside a frame for sdf) count no error.",
    "fft_real": "the directed points drive impulses at several positions, tones, DC, Nyquist and corner values as pairs of real samples, with the shortest legal spacing and longer ones; the random points drive random real frames with random legal spacing up to N = 2048. Each output frame of N/2 + 1 bins equals the model bit for bit, the latency from in_sof to out_sof equals the formula, and out_valid is N/2 + 1 consecutive clocks.",
    "fft_bfp": "the directed points drive impulses at every position and tones at every bin (small N), DC, Nyquist, a chirp and corner values, forward and inverse, back to back and after the shortest legal gap; the random points drive random frames with random direction and legal gaps up to N = 4096 (sdf) and 1024 (burst); the level frames drive all-zero, one-LSB, quiet and loud noise, loud and quiet tones, the most negative value and a frame whose rounding carries and saturates, so that every exponent range is visited. Each output frame, its exponent word included, equals the model bit for bit, the latency from in_sof to out_sof equals the formula, out_valid is N consecutive clocks and the exponent is the same on every word of a frame.",
    "fft_mdc2": "the directed points drive impulses, tones, DC, Nyquist, a chirp and corner values as pairs (x[2m], x[2m+1]), forward and inverse, back to back and after the shortest legal gap (N/8); the random points drive random frames with random direction and legal gaps up to N = 4096. Each output frame of N/2 pairs equals the model bit for bit, the latency from in_sof to out_sof equals the formula and out_valid is N/2 consecutive clocks.",
    "fft_real_axis": "the directed points send the real-FFT bench's frames as AXI4-Stream beats from a source that never pauses: the wrapper itself opens the gap, which the bench measures and requires to equal N/8 exactly, and the first-beat latency equals the formula; the random points send random real frames with random idle times up to N = 2048. Every output frame of N/2 + 1 bins equals the model bit for bit, tlast is on the right beat and the protocol checkers count no error.",
    "fft_mdc2_axis": "the directed points send the bench's frames (impulses, tones, DC, Nyquist, a chirp, corner values, and frames whose largest part is 2**m - 1 so that the normalisation saturates), forward and inverse, from a source that never pauses into a sink that is always ready: every output frame equals the model bit for bit, the exponent on tuser equals the model's on every beat, the first-beat latency equals the formula, the idle clocks between frames are 0 or at least N/8, and the frame period equals N/2 when NB * N/2 >= latency + N/2; the random points send random frames with random idle clocks (including 1 to N/8 - 1, which the wrapper must turn into a legal gap) into a sink that is always ready and into one with random tready.",
    "fft_fastconv": "the directed points drive the register defaults, a zero filter (zero output), a filter loaded through the registers and a random stream through it with random stalls on both streams; the random points use random taps, random streams with random stalls, register traffic while the stream runs and a new filter after the stream drains. The whole output stream equals the model bit for bit (no sample lost, added or reordered), the latency from the last input beat of the first block to its first output beat equals the formula, and the three protocol checkers count no error.",
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
    bench = [f"{base}/tests/{fn}_cocotb.py", f"{base}/model.py"] + (["arith/fft_common/frames.py", "arith/fft_common/fft_ref.py"] if fn in ("fft", "fft_reorder", "fft_real", "fft_axis", "fft_bfp", "fft_mdc2", "fft_real_axis", "fft_mdc2_axis") else []) + (
        ["arith/fft_real/tests/fft_real_cocotb.py", "arith/fft_real/model.py"] if fn == "fft_real_axis" else ["arith/fft_common/fft_ref.py", "arith/fft_common/fastconv.py"] if fn == "fft_fastconv" else [])
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
    # ---- brief 161: the phase 1 functions -------------------------------------------------------------------------------------------------------
    if fn == "fft_bfp":
        R.append(dict(id=f"{pre}-F-ACCURACY", kind="functional", title="Accuracy against NumPy is measured beside the scaled and unscaled modes, and the stated bound holds",
                      text="For both architectures, every N from 8 to 4096 and four input levels (0, -20, -40 and -60 dB of a full-scale noise-like frame), the error of the bit-exact model (which the RTL equals) against numpy.fft is recorded in verif/results/accuracy.json for the block-floating-point mode, the scaled mode and the unscaled mode (worst and rms error in the mode's own output LSB, and the SQNR). The bound is: the error of every part is at most the unscaled core's own worst error plus 2**exponent (the final rounding at the frame's exponent); it holds at every recorded point. The recorded SQNR of the block-floating-point mode at full level is at least 80 dB, its worst error at full level at most 2 output LSB, and at -60 dB its SQNR is at least 30 dB where the scaled mode's is negative.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-LEVELS", kind="functional", title="Every exponent range is visited and the exponent word is bit exact",
                      text="Frames of very different level (all zero, one LSB, noise at six amplitudes, a loud and a quiet tone, the most negative value, a frame whose bin 0 is 2**W - 1 so that the rounding carries and the word saturates) are sent through both architectures; each output frame and its exponent equal the model, the frames reach at least six different exponents, and the exponent is the same on every word of its frame and travels with the data when frames follow each other at different levels.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-BACKPRESSURE", kind="functional", title="The burst variant honours out_ready, even when both frame banks fill",
                      text="With out_ready low in 40 per cent of the clocks, and again in 92 per cent (reading a frame then takes longer than the core needs for the next, so both banks fill and the core must wait), the burst variant's frames, exponents and order equal the model, and out_valid, out_sof, the data and the exponent stay unchanged in every clock in which out_valid is high and out_ready low. The sdf variant ignores out_ready (stated).",
                      source=f"{base}/spec.md", spec_status="draft"))
        item(f"V-{pre}-ACCURACY", [f"{pre}-F-ACCURACY"], "sim_measurement", "Error against NumPy at every recorded point, three modes (the record of the last run)",
             {"file": f"{res}/accuracy.json", "reader": "json"},
             pass_when=[{"field": "all_within_bound", "op": "eq", "value": True}, {"field": "bfp_sqnr_db_min_full_level", "op": "ge", "value": 80.0}, {"field": "bfp_worst_lsb_max_full_level", "op": "le", "value": 2.0},
                        {"field": "bfp_sqnr_db_min_minus60", "op": "ge", "value": 30.0}, {"field": "scaled_sqnr_db_min_minus60", "op": "le", "value": 0.0}, {"field": "points", "op": "ge", "value": 80}],
             checks=["arith/fft_common/fft_ref.py", f"{base}/model.py", "arith/tools/fft_bfp_accuracy.py"])
        item(f"V-{pre}-LEVELS", [f"{pre}-F-LEVELS"], "sim_test", "Frames of every level through the RTL, exponent included",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_levels_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-BACKPRESSURE", [f"{pre}-F-BACKPRESSURE"], "sim_test", "The burst variant under a stalled sink, including one that fills both frame banks",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_backpressure_rtl::*"]}, checks=rtl + bench)
    if fn == "fft_mdc2":
        R.append(dict(id=f"{pre}-F-GAPS", kind="functional", title="The frame-gap rule (0 or at least N/8 clocks) is measured, not assumed",
                      text="At N = 32, 64, 128 and 256 a source that leaves exactly N/8 idle clocks between frames gets every frame right, and one that leaves N/8 - 1 clocks corrupts at least one frame, so the stated rule is the real minimum, not a guess.",
                      source=f"{base}/spec.md", spec_status="draft"))
        item(f"V-{pre}-GAPS", [f"{pre}-F-GAPS"], "sim_test", "N/8 idle clocks work and N/8 - 1 do not",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_gaps_rtl::*"]}, checks=rtl + bench)
    if fn == "fft_real_axis":
        R.append(dict(id=f"{pre}-F-AXIS", kind="interface", title="The AXI4-Stream rules hold on both streams, and the checkers can fail",
                      text="On both streams the wrapper's SystemVerilog protocol checkers (fft_common/axis_checker.sv: valid stays high until accepted, tdata and tlast stable while stalled, no unknowns after reset, tlast on every (N/2)-th beat of the input and every (N/2 + 1)-th beat of the output, no stall on the output, no pause inside an input frame) count zero violations in every run of the directed and random benches, the source of which presents the next frame at once and waits on tready. A deliberate-violation test shows each checker can fail (a pause inside a frame, a stalled sink). tvalid is registered and independent of tready by construction.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-GAP", kind="interface", title="The wrapper enforces the transform's frame gap by back-pressure",
                      text="After every beat with tlast on the input stream s_axis_tready is low for N/8 clocks (the measured gap rule of the real-input core), and a source that never pauses sees exactly N/8 idle clocks between its frames; every such frame is correct. Mutants that remove the gap, shorten it or lengthen it are killed.",
                      source=f"{base}/spec.md", spec_status="draft"))
        item(f"V-{pre}-CHECKER", [f"{pre}-F-AXIS"], "sim_test", "The protocol checkers can fail (a pause inside a frame, a stalled sink)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_checker_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-GAP", [f"{pre}-F-GAP"], "sim_test", "A source that never pauses sees exactly N/8 idle clocks between frames; every frame is right",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_directed_rtl::*"]}, checks=rtl + bench)
    if fn == "fft_mdc2_axis":
        R.append(dict(id=f"{pre}-F-AXIS", kind="interface", title="The AXI4-Stream rules hold on both streams, also with a sink that stalls, and the checkers can fail",
                      text="On both streams the wrapper's SystemVerilog protocol checkers (fft_common/axis_checker.sv: valid stays high until accepted, tdata, tuser and tlast stable while stalled, no unknowns after reset, tlast on every (N/2)-th beat, no pause inside an input frame) count zero violations in every run of the directed, random, back-pressure and gap benches, including random tready and a sink that holds tready low for three frame times; the checker bench shows that a pause inside a frame and a withdrawn tvalid are counted.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-GAP", kind="interface", title="Whatever the source does, the core sees 0 or at least N/8 idle clocks between frames, and nothing is lost to the output store",
                      text="After every beat with tlast s_axis_tready is high for one clock (a frame may follow with no idle clock) and, when no beat is transferred in it, low for N/8 - 1 clocks; the bench measures the idle clocks between every pair of frames under source idles of 0, 1 .. N/8 + 1 clocks and requires 0 or at least N/8, and exactly max(source idle, N/8) for a source idle of 1 or more. At a frame start s_axis_tready is low while NB frames are in the block, so with a sink that stalls for three frame times no frame is lost or altered (every output frame equals the model). With NB * N/2 >= latency + N/2 and a ready sink the frame period is N/2.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-EXPONENT", kind="functional", title="The block exponent is on tuser from the first beat and the words are normalised to W bits",
                      text="Every output frame's m_axis_tuser equals the model's exponent on every beat (the first beat is the contract), and every output part equals the model's normalised word: including frames whose largest part makes the rounding carry (saturation), frames of very different level back to back (so the exponent of one frame never leaks into the next), and the inverse transform.",
                      source=f"{base}/spec.md", spec_status="draft"))
        item(f"V-{pre}-CHECKER", [f"{pre}-F-AXIS"], "sim_test", "The protocol checkers can fail (a pause inside a frame, a withdrawn tvalid)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_checker_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-GAPS", [f"{pre}-F-GAP"], "sim_test", "The idle clocks between frames under every source idle from 0 to N/8 + 1",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_gaps_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-BACKPRESSURE", [f"{pre}-F-GAP", f"{pre}-F-AXIS"], "sim_test", "A sink that stalls for three frame times and one that is ready one clock in four: no frame lost, the offered beat held, the source held off by the credit",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_backpressure_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-EXPONENT", [f"{pre}-F-EXPONENT"], "sim_test", "Exponent and normalised words against the model, saturation frames included",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_directed_rtl::*"]}, checks=rtl + bench)
    if fn == "fft_fastconv":
        R.append(dict(id=f"{pre}-F-AXIL", kind="interface", title="The AXI4-Lite register file follows the contract's register map and response rules",
                      text="The ID, CFG0 and CFG1 registers read their documented values; read-only and unmapped addresses answer SLVERR and change nothing; byte address bits [1:0] are ignored; writes with partial strobes are refused with SLVERR and no effect; COEF_ADDR masks its upper bits and wraps; the staging registers read back sign-extended; a commit auto-increments COEF_ADDR and wraps at the last bin; a commit while BUSY (during the clear after reset, and while a block is in flight) is refused with SLVERR, sets DROPPED, does not advance COEF_ADDR and changes nothing; DROPPED and SAT are cleared by writing 1; reads have no side effects; address and data may arrive in either order and the response channels may wait. The AXI4-Lite protocol checker (fft_common/axil_checker.sv) counts no violation. The handshake rules and the response of every executed write are also checked by bounded model checks (formal/jobs.yaml) against shadow state.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-SAT", kind="functional", title="Output saturation is exact and reported",
                      text="With a filter of gain 2**GB and a loud input the output parts that leave the W-bit range are clamped to the nearest end exactly as the model says, STATUS.SAT is set, and it is cleared by writing 1 to it.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-AXIS", kind="interface", title="The AXI4-Stream rules hold on both streams under random stalls",
                      text="The checkers on s_axis and m_axis (valid stays high until accepted, tdata stable while stalled, no unknowns after reset) count no violation while both streams stall at random, including a sink so slow that the block controller must wait for output room: no sample is lost, added or reordered. A mutant that makes tvalid depend on tready is killed.",
                      source=f"{base}/spec.md", spec_status="draft"))
        R.append(dict(id=f"{pre}-F-ACCURACY", kind="functional", title="The filter output equals numpy.convolve within a stated error",
                      text="For N = 64 to 4096, L from N/8 + 1 to 3N/4 + 1 taps (low-pass, random and delta filters of absolute gain at most 2**GB) and a random complex stream, the output of the model (which the RTL equals bit for bit) differs from numpy.convolve of the same samples and the unquantised taps by at most the recorded error (verif/results/accuracy.json: worst and rms error in output LSB, SQNR) at W = 16, TW = 18, WH = 24, FH = 14; the test enforces a worst error of at most 8 LSB.",
                      source=f"{base}/spec.md", spec_status="draft"))
        item(f"V-{pre}-AXIL", [f"{pre}-F-AXIL"], "sim_test", "The register contract, every access type, with the AXI4-Lite checker",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_axil_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-SATURATE", [f"{pre}-F-SAT"], "sim_test", "A loud input through a filter of gain 2**GB saturates as the model says",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_saturate_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-STREAMS", [f"{pre}-F-AXIS"], "sim_test", "Both streams under random stalls, with the protocol checkers (the random points)",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_random_rtl::*"]}, checks=rtl + bench)
        item(f"V-{pre}-ACCURACY", [f"{pre}-F-ACCURACY"], "sim_measurement", "Error against numpy.convolve at every recorded point (the record of the last run)",
             {"file": f"{res}/accuracy.json", "reader": "json"},
             pass_when=[{"field": "worst_lsb_max", "op": "le", "value": 8.0}, {"field": "sqnr_db_min", "op": "ge", "value": 40.0}, {"field": "points", "op": "ge", "value": 16}],
             checks=["arith/fft_common/fft_ref.py", "arith/fft_common/fastconv.py", f"{base}/model.py", "arith/tools/fft_fastconv_accuracy.py"])
    if fn in ac.HARNESS_FFT_FUNCTIONS:
        R.append(dict(id=f"{pre}-F-HARNESS", kind="functional", title="The packaged harness runs standalone, passes on the repository's variants and catches faults",
                      text="arith/" + fn + "/harness/ (model, bench, SystemVerilog checkers, coverage targets, standalone runner: owner decision 24) needs no other file of the repository. Run against each variant of this function with the checkers beside it, in every mode, it passes and meets every coverage target; against one planted fault (a mutant of verif/mutants.yaml), or with a latency two clocks off, it fails; its model, bench and checker files are the repository's own, generated by arith/tools/gen_harness_fft.py, so they cannot drift.",
                      source=f"{base}/harness/README.md", spec_status="draft"))
        item(f"V-{pre}-HARNESS", [f"{pre}-F-HARNESS"], "sim_test", "The harness against the repository's variants, a planted fault and a wrong latency",
             {"file": junit, "reader": "junit", "tests": [f"test_{fn}_harness_rtl::*"]}, checks=rtl + bench + [f"{base}/harness/{x}" for x in ("assertions.sv", "chk_top.sv", "coverage.yaml", "run_harness.py", f"{fn}_cocotb.py", "model.py")])
    doc = {"schema": "fpga-design-agent/testplan/v1", "design": f"arith_{fn}",
           "notes": (f"Frequency-domain suite, function {fn} (brief 148). Everything here is before Vivado: the model, the RTL variants, simulation, formal properties and the prepared out-of-context build files. "
                     "No performance requirement on LUTs, DSPs, Fmax or power exists because none has been measured; the Vivado runs (build/<variant>/build.yaml, queued in _handoff/fpga_agent/vivado_later_queue.md) will add them. "
                     "Every requirement is a draft written by the agent; none is agreed by a human. There are no Lean statements" + (" (the packaged harness of this function, in harness/, is evidenced by the harness item)" if fn in ac.HARNESS_FFT_FUNCTIONS else " and no packaged harness for this suite (stated in the report)") + ". Generated by arith/tools/gen_testplan_fft.py."),
           "discover": [{"glob": f"arith/{fn}/tests/test_*.py", "pattern": r"^def (test_\w+)"}],
           "requirements": R, "verification": V}
    head = (f"# {fn} testplan, schema v1 (brief 116) for the frequency-domain suite (brief 148). GENERATED by `python -m arith.tools.gen_testplan` from spec.yaml, formal/jobs.yaml and the\n"
            "# test files: edit those, not this file. Status is never typed here: `python -m flow.trace_v1 write` reads the recorded evidence in verif/results/ and computes it.\n")
    return head + yaml.safe_dump(doc, sort_keys=False, width=180, allow_unicode=True)
