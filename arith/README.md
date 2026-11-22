# Arithmetic library

Two briefs built the first functions side by side, each with its own layout and tools; both are on main and both are checked by the 116 gate. Part A (139a) covers the adder, multiplier and MAC (and 139d's exp2, log2, sincos and atan2_mag); the second (139b) the divider, rounding and saturation, integer square root and leading-zero count. The generators are shared where they could be: `python -m arith.tools.gen_build` writes the build descriptions of both (139a's under `<fn>/ooc/` and `<fn>/build/<variant>/build.yaml`, 139b's under `<fn>/build/<variant>/{a7,k26}/`).

## Adders, multipliers, multiply-accumulate (brief 139a)

The first functions of a library of FPGA arithmetic, taken as far as they can go before Vivado: each has a specification, a bit-exact model, 2 to 3 RTL variants
that differ in a real PPA trade-off, simulation against the model (exhaustive at small widths, edge-value and random at large ones, with seeded faults to show the
bench can fail), formal equivalence between the variants where SymbiYosys allows, Lean statements for all widths, an interface contract and integration guidance, a packaged verification harness, a traced testplan, and prepared out-of-context
Vivado builds for Artix-7 (xc7a100t) and Kria K26 (xck26). **Nothing here has been run through Vivado**: every statement about LUTs, carry chains, DSPs, Fmax or power
is an expectation written down before measuring (marked "intended primitive use" in each RTL header and in each spec), and there is no performance requirement in the
testplans until the runs exist. The plan this sits in is [docs/arithmetic_pareto_plan.md](../docs/arithmetic_pareto_plan.md) (brief 137; at the time of writing it is a draft in that brief's
worktree, not yet merged, so this layout follows the brief's own and is mapped to the plan's library format under "Layout" below).

### Functions

| Function | Variants | Specification | Testplan and evidence |
|---|---|---|---|
| Integer adder and subtractor, with carry/borrow in and out and signed overflow | `ripple` (one carry chain), `carry_select` (blocks computed for carry 0 and 1), `pipelined` (a chunk of the carry chain per clock) | [adder/spec.md](adder/spec.md) | [adder/verif/testplan.yaml](adder/verif/testplan.yaml), [matrix](adder/verif/matrix.md) |
| Multiplier, exact WA + WB bit product, signed or unsigned | `dsp` (DSP blocks, 0 to 3 registers), `lut_array` (shifted partial products in LUTs), `booth_r4` (radix-4 Booth array in LUTs) | [multiplier/spec.md](multiplier/spec.md) | [multiplier/verif/testplan.yaml](multiplier/verif/testplan.yaml), [matrix](multiplier/verif/matrix.md) |
| Multiply-accumulate, LANES products per clock into one wrapping accumulator | `dsp` (DSP-mapped, 1 to 3 registers), `dsp_cascade` (lanes chained like a DSP cascade), `fabric` (no DSP) | [mac/spec.md](mac/spec.md) | [mac/verif/testplan.yaml](mac/verif/testplan.yaml), [matrix](mac/verif/matrix.md) |
| Base-2 exponential of a fraction, 2**x for x in [0, 1) (brief 139d) | `table` (256-entry ROM), `lerp` (segment table + linear interpolation, 1 DSP), `poly2` (segment table + quadratic, 2 DSPs), `cordic` (hyperbolic rotation, no DSP in the iterations) | [exp2/spec.md](exp2/spec.md) | [exp2/verif/testplan.yaml](exp2/verif/testplan.yaml), [matrix](exp2/verif/matrix.md) |
| log2 of a mantissa in [1, 2) (brief 139d) | `table`, `lerp`, `poly2`, `cordic` (hyperbolic vectoring) | [log2/spec.md](log2/spec.md) | [log2/verif/testplan.yaml](log2/verif/testplan.yaml), [matrix](log2/verif/matrix.md) |
| Sine and cosine of a phase (brief 139d; the alternatives to brief 137's CORDIC design) | `lerp`, `poly2` (quarter-wave tables), `cordic` (rotation mode) | [sincos/spec.md](sincos/spec.md) | [sincos/verif/testplan.yaml](sincos/verif/testplan.yaml), [matrix](sincos/verif/matrix.md) |
| atan2 and vector magnitude (brief 139d) | `cordic` (a register per iteration), `cordic_g2` (a register per GRP iterations) | [atan2_mag/spec.md](atan2_mag/spec.md) | [atan2_mag/verif/testplan.yaml](atan2_mag/verif/testplan.yaml), [matrix](atan2_mag/verif/matrix.md) |

### Floating-point functions (brief 139e)

IEEE-754-style binary formats of any exponent and fraction width (`EXP`, `MAN`: binary32 is 8/23, bfloat16 8/7, binary16 5/10), round to nearest even, a canonical quiet NaN, no exception
flags, full subnormal support or flush-to-zero (`SUBNORM`), and `STAGES` register ranks. All three share one reference ([fp_common/fp_ref.py](fp_common/fp_ref.py): exact rational arithmetic, one rounding), one
rounding-and-packing stage ([fp_common/fp_pack.sv](fp_common/fp_pack.sv)), one normaliser ([fp_common/fp_norm.sv](fp_common/fp_norm.sv)) and one specification written as wide-integer RTL for the proofs and the
harness checkers ([fp_common/fpx_ref.sv](fp_common/fpx_ref.sv)). Each variant lists the shared files it needs in `deps` in its `spec.yaml`.

| Function | Variants | Specification | Testplan and evidence |
|---|---|---|---|
| Floating-point adder | `single_path` (one datapath, two full-width shifters), `dual_path` (near and far path, no path with both a full aligner and a full normaliser) | [fp_add/spec.md](fp_add/spec.md) | [fp_add/verif/testplan.yaml](fp_add/verif/testplan.yaml), [matrix](fp_add/verif/matrix.md) |
| Floating-point multiplier | `dsp` (significand product on DSP blocks), `lut` (shift-and-add array in fabric) | [fp_mul/spec.md](fp_mul/spec.md) | [fp_mul/verif/testplan.yaml](fp_mul/verif/testplan.yaml), [matrix](fp_mul/verif/matrix.md) |
| Floating-point multiply-add | `fused` (one rounding, 3 * SP + 3 bit window), `cascade` (multiplier then adder: two roundings, NOT the same function) | [fp_fma/spec.md](fp_fma/spec.md) | [fp_fma/verif/testplan.yaml](fp_fma/verif/testplan.yaml), [matrix](fp_fma/verif/matrix.md) |

What is different from the integer functions: the bit-exact model is a reference with exact rational arithmetic (it needs no float of the host); the variants are proved equal to the wide-integer specification
by SymbiYosys only at TINY formats (EXP up to 3 or 4, MAN up to 3; the proofs are unbounded in time and cover every input there) and by simulation at binary32, bfloat16 and binary16; Lean states only three small
integer facts (the rounding increment carries into the exponent, the normalisation shift, ties-to-even), because core Lean has no IEEE-754 library, and the rest is marked research in each `spec.md`.

### Frequency-domain suite: FFT and its helper blocks (brief 148, phase 0)

A configurable FFT and the small blocks it is made of, each taken as far as it can go before Vivado, in the same form as the functions above (specification, bit-exact model, variants, simulation
against the model, seeded faults, formal properties, a traced testplan, prepared out-of-context builds for Artix-7 and K26). They sit in this folder because they use its tooling unchanged
(`tools/`, `verif/`, `formal/`, `build/` of each function); their shared files are in [fft_common/](fft_common/). The study, the architectures and when each wins, the scaling and the real-input
arrangement, and the fast-convolution plan are in [../docs/fft_suite_plan.md](../docs/fft_suite_plan.md). **Nothing here has been run through Vivado**: every statement about LUTs, DSPs, RAM or Fmax is an
expectation written down before measuring, and the runs are queued in `_handoff/fpga_agent/vivado_later_queue.md`.

| Function | Variants | Specification | Testplan and evidence |
|---|---|---|---|
| Configurable FFT, N = 8 to 4096, complex, forward or inverse per frame, scaled or growing, natural or bit-reversed output | `sdf` (radix-2^2 streaming, one sample per clock), `burst` (memory-based, one butterfly, one frame at a time) | [fft/spec.md](fft/spec.md) | [fft/verif/testplan.yaml](fft/verif/testplan.yaml), [matrix](fft/verif/matrix.md), [accuracy](fft/verif/results/accuracy.json) |
| Complex multiplier, exact | `m4` (four real multipliers), `m3` (three) | [fft_cmul/spec.md](fft_cmul/spec.md) | [fft_cmul/verif/testplan.yaml](fft_cmul/verif/testplan.yaml), [matrix](fft_cmul/verif/matrix.md) |
| Twiddle-factor generator, any circle up to 4096 points | `quarter` (one quarter-wave ROM) | [fft_twiddle/spec.md](fft_twiddle/spec.md) | [fft_twiddle/verif/testplan.yaml](fft_twiddle/verif/testplan.yaml), [matrix](fft_twiddle/verif/matrix.md) |
| Bit-reverse reorder buffer, continuous frames | `pingpong` (two banks) | [fft_reorder/spec.md](fft_reorder/spec.md) | [fft_reorder/verif/testplan.yaml](fft_reorder/verif/testplan.yaml), [matrix](fft_reorder/verif/matrix.md) |
| Window multiplier | `dsp` | [fft_window/spec.md](fft_window/spec.md) | [fft_window/verif/testplan.yaml](fft_window/verif/testplan.yaml), [matrix](fft_window/verif/matrix.md) |
| AMBA AXI4-Stream FFT: the two FFT variants behind `s_axis`/`m_axis` (tdata, tvalid, tready, tlast, tuser = inverse), `sdf` with no back-pressure and `burst` with full back-pressure, with simulation protocol checkers | `sdf`, `burst` | [fft_axis/spec.md](fft_axis/spec.md) | [fft_axis/verif/testplan.yaml](fft_axis/verif/testplan.yaml), [matrix](fft_axis/verif/matrix.md) |
| Real-input FFT: N real samples (two per clock) through an N/2-point complex FFT and post-processing, bins 0 .. N/2 | `post` | [fft_real/spec.md](fft_real/spec.md) | [fft_real/verif/testplan.yaml](fft_real/verif/testplan.yaml), [matrix](fft_real/verif/matrix.md) |

Differences from the functions above, so nothing is assumed: these blocks stream frames of N samples (the benches in `fft_common/frames.py` drive frames, not single operands); the directed bench
is a basis of stimuli (impulses, tones, corner values), not every input; the FFT is checked against NumPy's FFT for accuracy, and its results are bit-exact against its own models only; the AXI4-Stream interface (owner direction 2026-11-21: favour AMBA AXI) is on the `fft_axis` wrappers of the two FFT variants only: the cores (`fft`, `fft_real`) and the helper blocks keep plain valid/start-of-frame or fixed-latency pipeline ports, because they are internal datapath blocks whose handshake would add logic without adding a stream to connect to (comparison with AMD's FFT interface in the plan, section 9); there is **no
packaged harness** and **no Lean statement** for any of them (not built in this phase; stated in each `spec.md`); the formal jobs are properties of the parts (the reorder address map, the complex
multiplier, the twiddle symmetry, the window rounding, the delay-feedback stage) and not of the whole FFT. The fast-convolution model is `fft_common/fastconv.py` (Python only, with an interface proposal in the plan: its RTL is the next phase); the real-input transform is built (`fft_real`).

### Phase 1 (brief 161): block floating point, 2-parallel, real-input AXI4-Stream, fast convolution

Four more entries, in the same form and with a packaged harness each (owner decision 24; the phase 0 entries above have none). The two data-path entries have plain ports; the two system-facing ones
have AMBA AXI interfaces (owner decision 28). Study and measured results: [../docs/fft_suite_plan.md](../docs/fft_suite_plan.md) section 9. **Nothing here has been run through Vivado**; the prepared builds
are queued in `_handoff/fpga_agent/vivado_later_queue.md`.

| Function | Variants | Specification | Testplan and evidence | Harness |
|---|---|---|---|---|
| Block-floating-point FFT: the unscaled transform, one exponent per frame, W-bit output words, the exponent on a side channel (`out_exp`) | `sdf`, `burst` | [fft_bfp/spec.md](fft_bfp/spec.md) | [fft_bfp/verif/testplan.yaml](fft_bfp/verif/testplan.yaml), [matrix](fft_bfp/verif/matrix.md), [accuracy](fft_bfp/verif/results/accuracy.json) | [fft_bfp/harness/README.md](fft_bfp/harness/README.md) |
| 2-parallel FFT: two samples per clock, N/2-clock frames of pairs, built as two N/2-point `sdf` pipelines and a combining stage | `par2` | [fft_mdc2/spec.md](fft_mdc2/spec.md) | [fft_mdc2/verif/testplan.yaml](fft_mdc2/verif/testplan.yaml), [matrix](fft_mdc2/verif/matrix.md) | [fft_mdc2/harness/README.md](fft_mdc2/harness/README.md) |
| AXI4-Stream real-input FFT: the wrapper of `fft_real`, the N/8 frame gap enforced by back-pressure | `post` | [fft_real_axis/spec.md](fft_real_axis/spec.md) | [fft_real_axis/verif/testplan.yaml](fft_real_axis/verif/testplan.yaml), [matrix](fft_real_axis/verif/matrix.md) | [fft_real_axis/harness/README.md](fft_real_axis/harness/README.md) |
| Fast convolution FIR (overlap-save): AXI4-Stream samples in and out, the filter spectrum loaded over AXI4-Lite | `os` | [fft_fastconv/spec.md](fft_fastconv/spec.md) | [fft_fastconv/verif/testplan.yaml](fft_fastconv/verif/testplan.yaml), [matrix](fft_fastconv/verif/matrix.md), [accuracy](fft_fastconv/verif/results/accuracy.json) | [fft_fastconv/harness/README.md](fft_fastconv/harness/README.md) |

New shared files in [fft_common/](fft_common/): `fft_bfp_out.sv` (the exponent and normalisation stage), `frame_checker.sv`, `axil_checker.sv` (simulation checkers), `fcover.py` (event coverage). The build
generator is `tools/gen_build.py` (one generator for every function here); the harness generator is `tools/gen_harness_fft.py`; mutants of the phase 1 functions are in `tools/mutants_p1.py`.
`python -m flow.verified` records (PR #271) are not produced: #271 was not on main when this phase ran. No Lean statement. The AXI4-Lite register file of `fft_fastconv` has bounded model checks
([fft_fastconv/formal/jobs.yaml](fft_fastconv/formal/jobs.yaml)); the datapaths are checked by simulation only.

### Layout (one folder per function)

| Path | What |
|---|---|
| `<fn>/spec.yaml`, `spec.md` | the specification: ports, parameters, semantics, signedness, exactness, latency per variant, expected primitive use, and "what a user could guess wrong". `spec.md` is rendered from `spec.yaml` (`tools/gen_spec_md.py`) |
| `<fn>/model.py` | the bit-exact model, in Python integers |
| `<fn>/rtl/` | the variants, SystemVerilog (FDA-HDL: synchronous reset, no initial values, no latches), each with a header stating the intended primitive use |
| `<fn>/harness/` | the packaged verification harness, a deliverable a user reruns against their own instance after integration: model, cocotb bench, SystemVerilog checker (`assertions.sv`, `chk_top.sv`), coverage targets, and a standalone `run_harness.py`; its README says how |
| `<fn>/tests/` | the cocotb bench (`<fn>_cocotb.py`) and the pytest files that run it; a test file per kind of evidence |
| `<fn>/verif/` | `mutants.yaml` (seeded faults), `testplan.yaml` (schema v1, generated by `tools/gen_testplan.py`), `lean_approvals.yaml` (empty: no Lean statement is approved), `matrix.md`/`.html`, `results/` (the recorded evidence) |
| `<fn>/formal/` | the SymbiYosys tops and `jobs.yaml` |
| `<fn>/ooc/`, `<fn>/build/<variant>/build.yaml` | the generated register wrapper and the out-of-context build file of each variant (`tools/gen_build.py`) |
| `tools/` | the shared pieces: `arith_common.py`, `bench.py`, `suite.py`, `run_mutants.py`, `run_formal.py`, `gen_*.py` |
| `fp_common/` | what the floating-point functions share (brief 139e): `fp_ref.py`, `fp_pack.sv`, `fp_norm.sv`, `fpx_ref.sv` |
| `../formal/lean/Arith/` | the Lean statements and proofs (`Adder.lean`, `Booth.lean`, `Mac.lean`, `Float.lean`; brief 139d: `Lerp.lean`, `Quadrant.lean`, `Cordic.lean`) in the repository's Lean project |

The plan of brief 137 describes `library/<function>/` with `spec`, `model/`, `lean/`, `impl/<variant>/` and `surface/<fabric>/`. Here `model.py` is the model, `rtl/<variant>.sv`
is `impl/<variant>/` (flat, one file per variant), the Lean files are in the repository's one Lean project, and `surface/<fabric>/` does not exist yet: it is where the Vivado
runs will write their records. Moving to the plan's exact layout is a mechanical rename.

### What is checked, and how far

| Evidence | adder | multiplier | MAC |
|---|---|---|---|
| Model against an independent formulation | exhaustive to width 6, 4000 random up to 128 | exhaustive on 8 shapes, 3000 random | 300 random configurations against a structure-free reference |
| Variants against the model (Icarus + cocotb) | 4 + 6 + 6 exhaustive points, 4 + 5 + 5 random | 7 + 8 + 9 exhaustive, 5 + 4 + 5 random | 6 + 5 + 5 exhaustive, 5 + 4 + 3 random |
| Seeded faults killed by the bench | see [adder/verif/results/mutation.json](adder/verif/results/mutation.json) | [multiplier/verif/results/mutation.json](multiplier/verif/results/mutation.json) | [mac/verif/results/mutation.json](mac/verif/results/mutation.json) |
| Formal (SymbiYosys, slang) | variants against each other and a plain `+`: proved for all inputs at widths 8, 16, 32, 33, 64 | against a plain `*`: proved at 8 x 8, 9 x 6, 6 x 9 (and 10 x 10 when the record says so); larger widths by simulation only | against the specification as RTL: proved at three small shapes, bounded at one larger |
| Lean (for all widths) | carry-select composition adds; subtraction is addition of complements | radix-4 Booth digits sum to the multiplier's value | a clear-free run adds modulo 2^ACCW; a clear forgets the history |

Exact numbers and their dates are in each `verif/results/` and in the function's report; they are not repeated here so they cannot go stale. Limits to keep in mind:

- A formal proof is at the widths listed in `formal/jobs.yaml`. A multiplier equivalence is an SMT problem that grows quickly with width, so wide multipliers are checked by simulation only.
- The Lean statements are **not approved**: only a human approves a statement (`verif/lean_approvals.yaml`), and until then the matrix shows "statement not approved" and does not count the proof as verification. The Lean text is a hand transcription of the RTL's structure (kind `transcription_untested`): it proves the algorithm, not the RTL.
- The Lean proofs use Lean 4.36 core only (no Mathlib) and are checked by `lake build` in `formal/lean`.
- Simulation uses Icarus; Verilator is used for lint only.

### Elementary functions (brief 139d): exp2, log2, sincos, atan2_mag

These four differ from the first three in one way that changes what "verified" means: they are **not exact**. Each variant is bit-exact against **its own model** (`model.compute(variant, params, ...)`; the
variants round differently and are not bit-identical to each other, except the two atan2_mag variants, which are), and its distance from the exact function is a separate, stated, **measured** error bound per
variant and listed point (`spec.yaml` `accuracy_points`, rendered in each `spec.md` under "Accuracy"; `tests/test_<fn>_accuracy.py` scans every input of the point and fails if the bound is false or loose).

| What | Where |
|---|---|
| shared constants (table break points and slopes, Chebyshev-fitted quadratics, CORDIC angle and gain constants) and the integer table-plus-polynomial arithmetic | [tools/fxlib.py](tools/fxlib.py): the one place a constant is defined; the models, the RTL and the tests all use it |
| the generated RTL | [tools/gen_rtl.py](tools/gen_rtl.py) writes every `rtl/*.sv` of these four functions and the formal reference ROMs `formal/*_ref.sv`; `--check` (a test and CI) fails if a committed file differs, so a table in the RTL is the model's table |
| table variants (`table`, `lerp`, `poly2`) | a 256-entry direct ROM, or a 2**SB-segment table of break-point values and slopes (one DSP) or quadratic coefficients (two DSPs in a Horner chain); coefficients have 20 fractional bits, the datapath rounds once at the end |
| CORDIC variants | circular rotation (sincos), circular vectoring (atan2_mag), hyperbolic rotation (exp2: z = x ln 2) and hyperbolic vectoring (log2: z = atanh((m-1)/(m+1))); one stage per iteration, no DSP in the iterations |
| formal | SymbiYosys against a reference ROM written straight from the maths library (`formal/*_ref.sv`, 8 input bits): the error bound of each variant proved by k-induction for all inputs at that width, the quadrant map included, planted faults refuted; a constant table is a read-only memory, so every formal script runs `memory_map` (otherwise a k-induction step would treat the table as free) |
| Lean | statements about the pieces that hold for every width: linear interpolation stays between the segment's end values and is monotone, the quadrant split of the phase is a bijection, a CORDIC step scales the squared length (circular) or x**2 - y**2 (hyperbolic) by a data-independent constant. The error bounds of the table-plus-polynomial and CORDIC variants are NOT proved for all widths: they are an exhaustive computation per listed point, and a proof (interval arithmetic on the second and third derivatives, or a CORDIC convergence argument) is a research item |
| harness | as for the first three, plus `--variant` (which model to compare bit for bit) and `--err-ulp` (the SystemVerilog checker's error bound, which uses the maths library's `$sin`, `$atan2`, `$pow`, `$ln`, `$hypot` in simulation) |

Limits specific to these four: the clamps of the exp2 and log2 variants are unreachable (their results are inside the range by construction) and so are not mutated; accuracy is stated at listed points only and the
error moves with the parameters (`model.max_error` measures any other point); the formal error bounds hold at 8 input bits (4 bits per coordinate for atan2_mag), wider points are covered by simulation and the exhaustive
accuracy scan; Verilator is used for lint only; the CORDIC constants and table values come from double-precision arithmetic (53 bits for 20 to 28-bit constants, no ties in practice, and a test pins the generated RTL to the
model's). The sincos entry is the table-based alternative to brief 137's CORDIC design; its cordic variant uses the same interface as the table variants, not 137's.

Next steps for the engineer who picks this up: (1) the Vivado characterisation of every `build/<variant>/build.yaml` on xc7a100t and xck26 (see "Running the Vivado characterisation"), with a clock sweep, and one run per parameter point of `ooc_points`, to turn the expectations in the RTL headers into surfaces (the table variants' BRAM against distributed-RAM choice, the DSP count of poly2, the CORDIC stage cost per bit are the open questions); (2) range-reduction wrappers that make `exp`, `exp2` of any fixed-point number, and `log2`, `ln`, `log10` of any positive number from these cores, with `lzc_norm` of brief 139b for the mantissa, each as its own verified entry; (3) a proof of the error bounds for all widths of the table variants (interval arithmetic over the second and third derivative bounds of the function, per segment) and a convergence argument for the CORDIC variants, both research; (4) formal error bounds at wider inputs than 8 bits (a reference ROM does not scale: a real-number reference or a high-precision second implementation would); (5) a bounded mutation of the clamps, if a use makes them reachable.

### Running it

```
pip install pyyaml pytest cocotb==2.0.1          # Icarus (iverilog), Verilator and the OSS CAD Suite (yosys, sby, boolector) are on PATH or in ~/.local/opt/oss-cad-suite
python -m pytest -q arith/adder/tests             # one function: model, simulation, latency, mutants, formal, package checks
python -m arith.tools.run_mutants adder           # the mutation run, writing verif/results/mutation.json
python -m arith.tools.run_formal adder            # the formal jobs, writing verif/results/formal.json
python -m arith.tools.gen_rtl; python -m arith.tools.gen_build; python -m arith.tools.gen_spec_md; python -m arith.tools.gen_harness; python -m arith.tools.gen_testplan    # regenerate; add --check to compare
python -m flow.trace_v1 check                     # the 116 gate: every test named by an item, every requirement traced
```

### Running the Vivado characterisation (not done yet)

Each `<fn>/build/<variant>/build.yaml` is in the format of `flow/prepare.py` (`top`, `part`, `sources`, `generics`) with the out-of-context keys of `flow/ipchar.tcl`: the wrapper
top (every input and output registered, clock on port `clk`), the two parts and a target clock for each, the points to run (`points`) and the primitive use expected at each part.
A run is `synth_design -mode out_of_context`, `opt_design`, `place_design`, `route_design` on one thread, with a heavy slot (`_handoff/take_heavy_slot.sh`, peak declared from
`_handoff/fpga_agent/resources/vivado_peak.py`). A tight target clock matters: at an easy clock the tool stops optimising and Fmax is hidden (the FPGA course's Part 8), so the
clocks in the build files are starting points and the characterisation should sweep them. The results go to `<fn>/surface/<part>/`, one row per variant and point with the Vivado
release, the target clock, utilisation, WNS and WHS, vectorless power and the latency from `spec.yaml`.

## Fixed-point, divide, square root, reciprocal, leading-zero count (briefs 139b and 139c)

The first functions of the owner's FPGA arithmetic library (brief 139b: divider, fxp_round, isqrt, lzc_norm; brief 139c adds the high-radix and iterative functions: sqrt_r4, divider_hr, div_nr, recip, rsqrt, compared against the 139b divider and isqrt) (plan: [docs/arithmetic_pareto_plan.md](../docs/arithmetic_pareto_plan.md) on brief 137's branch `b137-arith-pareto`, not yet on main when this was written; the layout below is the brief's own, one folder per function, and is to be aligned with brief 137's library format when that merges). Each function is specified, modelled bit-exactly, implemented in several variants that differ in a real power/performance/area trade-off, verified in simulation, checked formally, given a Lean statement where one is tractable, and **prepared for Vivado but not built**: there is no Fmax, area or power figure anywhere in this folder.

| Function | Variants | Spec | Lean (all widths, statements not approved) |
|---|---|---|---|
| [divider](divider/spec.md): unsigned quotient and remainder | restoring and non-restoring, each iterative or unrolled with PIPE bits per stage | [spec.md](divider/spec.md), [spec.yaml](divider/spec.yaml) | restoring and non-restoring recurrences equal `Nat.div`/`Nat.mod`: proved |
| [fxp_round](fxp_round/spec.md): truncate, round half up, convergent, then wrap or saturate | fold-add (one adder with carry-in), shift-then-increment, two-stage | [spec.md](fxp_round/spec.md), [spec.yaml](fxp_round/spec.yaml) | carry-in form equals the definition, error bounds, tie to even: proved |
| [isqrt](isqrt/spec.md): floor square root and remainder | restoring iterative, restoring pipelined, non-restoring pipelined | [spec.md](isqrt/spec.md), [spec.yaml](isqrt/spec.yaml) | restoring recurrence is a floor square root: proved (non-restoring: statement only, unproved) |
| [lzc_norm](lzc_norm/spec.md): leading-zero count and normaliser | tree + barrel, loop + barrel, stagewise (pipelined), two-clock tree + barrel | [spec.md](lzc_norm/spec.md), [spec.yaml](lzc_norm/spec.yaml) | recursive-halving count is correct for every width 2^k: proved |
| [sqrt_r4](sqrt_r4/spec.md): floor square root and remainder, two root bits per step (brief 139c) | radix-4 iterative, radix-4 pipelined (PIPE steps per stage) | [spec.md](sqrt_r4/spec.md), [spec.yaml](sqrt_r4/spec.yaml) | radix-4 recurrence is a floor square root: proved |
| [divider_hr](divider_hr/spec.md): exact radix-4 SRT division of normalised significands, quotient and remainder (brief 139c) | carry-save iterative, carry-propagate iterative, carry-save pipelined | [spec.md](divider_hr/spec.md), [spec.yaml](divider_hr/spec.yaml) | the SRT recurrence with any contained digit selection is a floor division for every K: proved (selection table not in Lean) |
| [div_nr](div_nr/spec.md): approximate division by seed table, DSP multipliers and Newton or Goldschmidt iterations (brief 139c) | Newton, Goldschmidt | [spec.md](div_nr/spec.md), [spec.yaml](div_nr/spec.yaml) | Newton residual squares, Goldschmidt ratio kept: proved (exact map; truncation not in Lean) |
| [recip](recip/spec.md): reciprocal of a normalised significand (brief 139c) | table, table + 1 Newton step, table + 2 | [spec.md](recip/spec.md), [spec.yaml](recip/spec.yaml) | Newton step squares the residual and never overshoots: proved |
| [rsqrt](rsqrt/spec.md): reciprocal square root of a significand in [1, 4) (brief 139c) | table, table + 1 Newton step, table + 2 | [spec.md](rsqrt/spec.md), [spec.yaml](rsqrt/spec.yaml) | Newton step identity and one-sidedness: proved |

### Layout (one folder per function)

```
spec.md, spec.yaml      the specification (spec.md is generated from spec.yaml by arith/tools/gen_spec.py)
model.py                the bit-exact Python model (the specification in code) and the vector generators
rtl/                    one module per variant, <function>_sel.sv (one selector the testbench, the proofs and the wrapper share), <function>_ooc.sv (generated out-of-context wrapper)
tb/                     tb_<function>.sv, connects the selector to arith/common/tb_stream.sv (the generic stream harness: order, value, measured latency of every result)
tests/                  test_<f>_model.py (no simulator), test_<f>_rtl.py (Icarus, Verilator, mutants), test_<f>_formal_rtl.py (SymbiYosys), test_<f>_build_rtl.py
harness/                the packaged verification harness a user reruns against their own instance (run.py, coverage.yaml, README.md; owner decision 24)
formal/                 <function>_fv.sv, the SymbiYosys harness (reference or characterisation, variant against variant)
verif/                  testplan.yaml (schema v1, the 116 gate), mutants.yaml, lean_approvals.yaml (the owner's, empty), generated matrix.md and matrix.html
build/<variant>/{a7,k26}/   build.yaml and ooc.xdc for an out-of-context Vivado run (generated by arith/tools/gen_build.py; not run)
```

The Lean files are in [formal/lean/Arith](../formal/lean/Arith/Divide.lean) (`Divide`, `Rounding`, `Isqrt`, `Lzc`, `SqrtR4`, `DividerHr`, `Newton`, and the generated `CrossCheck.lean`).

Every spec states, per variant, the interface contract (protocol, latency, throughput, reset and clock assumptions), what a user could guess wrong, and an integration section (port timing, constraints to carry); the entry is meant to be retrieved without knowledge of the larger design.

### Run it

```
python -m pytest -q arith                    # model tests, RTL against the models, lint, mutants, formal proofs, build descriptions (about 8 minutes for the first four functions, about 25 more for the five of brief 139c; the formal jobs dominate)
python -m arith.tools.gen_build --check      # the out-of-context descriptions are current
python -m flow.trace_v1 check arith/divider arith/fxp_round arith/isqrt arith/lzc_norm arith/sqrt_r4 arith/divider_hr arith/recip arith/rsqrt arith/div_nr
```

Tools: Icarus Verilog, Verilator and SymbiYosys with the slang front end, from the pinned OSS CAD Suite (`FDA_OSS_CAD`, or `~/.local/opt/oss-cad-suite`); a test that needs one and cannot find it skips (fails with `FDA_REQUIRE_FORMAL=1`, as CI sets). The measured results, with the evidence files, are in [results/139b_arith](../results/139b_arith/README.md) and [results/139c_arith](../results/139c_arith/README.md).

### What is not done

Vivado out-of-context runs (the prepared `build.yaml` files are for a free heavy slot), post-implementation simulation, a structural netlist, Lean proofs of the non-restoring square root and of the stagewise normaliser, and the human approval of any specification or Lean statement. Every requirement is `spec_status: draft`.
