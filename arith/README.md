# Arithmetic library: adders, multipliers, multiply-accumulate (brief 139a)

The first functions of a library of FPGA arithmetic, taken as far as they can go before Vivado: each has a specification, a bit-exact model, 2 to 3 RTL variants
that differ in a real PPA trade-off, simulation against the model (exhaustive at small widths, edge-value and random at large ones, with seeded faults to show the
bench can fail), formal equivalence between the variants where SymbiYosys allows, Lean statements for all widths, an interface contract and integration guidance, a packaged verification harness, a traced testplan, and prepared out-of-context
Vivado builds for Artix-7 (xc7a100t) and Kria K26 (xck26). **Nothing here has been run through Vivado**: every statement about LUTs, carry chains, DSPs, Fmax or power
is an expectation written down before measuring (marked "intended primitive use" in each RTL header and in each spec), and there is no performance requirement in the
testplans until the runs exist. The plan this sits in is [docs/arithmetic_pareto_plan.md](../docs/arithmetic_pareto_plan.md) (brief 137; at the time of writing it is a draft in that brief's
worktree, not yet merged, so this layout follows the brief's own and is mapped to the plan's library format under "Layout" below).

## Functions

| Function | Variants | Specification | Testplan and evidence |
|---|---|---|---|
| Integer adder and subtractor, with carry/borrow in and out and signed overflow | `ripple` (one carry chain), `carry_select` (blocks computed for carry 0 and 1), `pipelined` (a chunk of the carry chain per clock) | [adder/spec.md](adder/spec.md) | [adder/verif/testplan.yaml](adder/verif/testplan.yaml), [matrix](adder/verif/matrix.md) |
| Multiplier, exact WA + WB bit product, signed or unsigned | `dsp` (DSP blocks, 0 to 3 registers), `lut_array` (shifted partial products in LUTs), `booth_r4` (radix-4 Booth array in LUTs) | [multiplier/spec.md](multiplier/spec.md) | [multiplier/verif/testplan.yaml](multiplier/verif/testplan.yaml), [matrix](multiplier/verif/matrix.md) |
| Multiply-accumulate, LANES products per clock into one wrapping accumulator | `dsp` (DSP-mapped, 1 to 3 registers), `dsp_cascade` (lanes chained like a DSP cascade), `fabric` (no DSP) | [mac/spec.md](mac/spec.md) | [mac/verif/testplan.yaml](mac/verif/testplan.yaml), [matrix](mac/verif/matrix.md) |

## Floating-point functions (brief 139e)

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

## Frequency-domain suite: FFT and its helper blocks (brief 148, phase 0)

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

## Layout (one folder per function)

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
| `../formal/lean/Arith/` | the Lean statements and proofs (`Adder.lean`, `Booth.lean`, `Mac.lean`, `Float.lean`) in the repository's Lean project |

The plan of brief 137 describes `library/<function>/` with `spec`, `model/`, `lean/`, `impl/<variant>/` and `surface/<fabric>/`. Here `model.py` is the model, `rtl/<variant>.sv`
is `impl/<variant>/` (flat, one file per variant), the Lean files are in the repository's one Lean project, and `surface/<fabric>/` does not exist yet: it is where the Vivado
runs will write their records. Moving to the plan's exact layout is a mechanical rename.

## What is checked, and how far

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

## Running it

```
pip install pyyaml pytest cocotb==2.0.1          # Icarus (iverilog), Verilator and the OSS CAD Suite (yosys, sby, boolector) are on PATH or in ~/.local/opt/oss-cad-suite
python -m pytest -q arith/adder/tests             # one function: model, simulation, latency, mutants, formal, package checks
python -m arith.tools.run_mutants adder           # the mutation run, writing verif/results/mutation.json
python -m arith.tools.run_formal adder            # the formal jobs, writing verif/results/formal.json
python -m arith.tools.gen_build; python -m arith.tools.gen_spec_md; python -m arith.tools.gen_harness; python -m arith.tools.gen_testplan    # regenerate; add --check to compare
python -m flow.trace_v1 check                     # the 116 gate: every test named by an item, every requirement traced
```

## Running the Vivado characterisation (not done yet)

Each `<fn>/build/<variant>/build.yaml` is in the format of `flow/prepare.py` (`top`, `part`, `sources`, `generics`) with the out-of-context keys of `flow/ipchar.tcl`: the wrapper
top (every input and output registered, clock on port `clk`), the two parts and a target clock for each, the points to run (`points`) and the primitive use expected at each part.
A run is `synth_design -mode out_of_context`, `opt_design`, `place_design`, `route_design` on one thread, with a heavy slot (`_handoff/take_heavy_slot.sh`, peak declared from
`_handoff/fpga_agent/resources/vivado_peak.py`). A tight target clock matters: at an easy clock the tool stops optimising and Fmax is hidden (the FPGA course's Part 8), so the
clocks in the build files are starting points and the characterisation should sweep them. The results go to `<fn>/surface/<part>/`, one row per variant and point with the Vivado
release, the target clock, utilisation, WNS and WHS, vectorless power and the latency from `spec.yaml`.
