# Frequency-domain IP suite, phase 0: the FFT, its helper blocks and the fast-convolution plan (brief 148)

Owner decision 27 (2026-11-21): a configurable FFT, "ideally configurable in size, real/complex, forward/inverse, precision, latency", as the first block of a suite of frequency-domain IP
that can do, for example, fast convolution. This page is the study behind the blocks in [arith/](../arith/README.md) (functions `fft`, `fft_cmul`, `fft_twiddle`, `fft_reorder`, `fft_window`), what was built
and what was not, the measured results, the expectations written down before any Vivado run, and the plan for fast convolution and the real-input transform. **Nothing here has been through
Vivado.** Every number below is from a recorded run in the repository, with its file named, or is labelled an expectation.

## 1. Where it lives, and why

The blocks are functions of the existing `arith/` library, not a new `freq/` tree: its tools (`arith/tools`: model/RTL/package checks, the mutation runner, the formal runner, the build and testplan
generators) take a function name and a folder, so the suite uses them unchanged, and the traceability gate (`flow/trace_v1.py`) already reads `arith/*/verif/testplan.yaml`. The only change to shared tooling is
the list of function names (`arith/tools/arith_common.py`: `FFT_FUNCTIONS`), a testplan generator for frame-based blocks (`arith/tools/gen_testplan_fft.py`, which leaves out the packaged harness and the Lean
statements these blocks do not have), and `ARITH_VARIANT` in the bench environment. The branch is based on the 139e branch (it has the `deps` extension and every function the suite
extends) until 139a/139b land on `main`.

## 2. Architectures, their costs and when each wins

N = 2^n points, W-bit data, complex. "Complex multiplier" counts the twiddle multipliers; a trivial multiplication (by 1, -1, j, -j) is wiring plus an adder, not a multiplier. Costs are approximate textbook figures (sources
at the end; they were not re-derived here); the measured latency of our two variants is in section 3.

| Architecture | Throughput | Complex multipliers | Delay/data memory | Adders (real) | Latency | Wins when |
|---|---|---|---|---|---|---|
| Streaming single-path delay feedback (SDF), radix-2 | 1 sample/clock | n - 1 | N - 1 words | 4n | about N | continuous streams at one sample per clock and N small; simplest control |
| SDF radix-2^2 (**built, `sdf`**) | 1 sample/clock | floor((n - 1)/2), about log4(N) - 1 | N - 1 words | 4n | about N | the same, with half the multipliers: the multiplication by -j is folded into the butterfly, so a twiddle multiplier is needed only after every second stage |
| SDF radix-2^3 | 1 sample/clock | about n/3 | N - 1 words | 4n | about N | fewer multipliers again (the 45-degree twiddle is a shift-add); not built |
| Multi-path delay commutator (MDC), radix-2^2, 2 or 4 samples/clock | 2 or 4 samples/clock | about n - 2 for 2 paths (each stage's multipliers are shared by fewer words per path) | about 3N/2 words | about 4n * paths | about N / paths | line rates above one sample per clock (a clock slower than the sample rate); costs memory and multipliers; not built |
| Memory-based iterative, one radix-2 butterfly (**built, `burst`**) | one frame per N/2 * n + N + N clocks | 1 | N words in 2 banks | 4 | N/2 * n + 2N | small area, frames separated by idle time; the multiplier count does not grow with N |
| Memory-based iterative, radix-4 (AMD's "Radix-4, Burst I/O") | one frame per N/4 * log4(N) + 2N clocks | 3 (or 1 with time-sharing) | N words | 8 | about N/4 * log4(N) + 2N | middle ground; roughly halves the burst compute time for three times the multipliers; not built |
| Real-input FFT through an N/2 complex transform plus post-processing (**built, `fft_real`**) | N real samples per N/2 clocks (2 per clock) | those of an N/2 transform + 1 for the post-processing | one extra N/2-word buffer (the transform's natural-order buffer is reused) | those of an N/2 transform + 8 | N/2-transform latency + N/2 + 3 | any real signal: it halves memory and multipliers against feeding the real signal as a complex transform with zero imaginary part; output is the N/2 + 1 distinct bins |

Costs are per unit of throughput: the SDF family has a fixed multiplier count per stream; the memory-based family trades clocks for area, so for a given sample rate and clock rate the choice is
(samples per clock needed) -> SDF (1/clock) or MDC (more); (frames far apart) -> burst. Where the clock is much faster than the sample rate, a burst core also wins on area because one
butterfly serves a whole frame.

### Scaling, three ways

| Mode | What it does | Word growth | Cost | Our status |
|---|---|---|---|---|
| Unscaled with growth | no division, every butterfly stage adds one bit | n bits over the whole transform | widest memories and adders; exact apart from the twiddle and multiplier rounding | **built** (`SCALE = 0`, output W + LOGN bits) |
| Scaled, per stage /2 | every butterfly sum and difference is halved | none: the word stays W bits | narrowest; signal-to-noise falls as 1/N-scaled output approaches the LSB: the output of an N-point transform of white noise has rms about 1/sqrt(N) of the input's | **built** (`SCALE = 1`, total 1/N in both directions) |
| Block floating point | one exponent per frame; the frame is shifted right by 0 or 1 bit per stage only when the largest word needs it | variable | needs a stage-wide maximum detector and a frame buffer for the exponent decision (in a streaming core the decision is made one frame late or the data are delayed) | phase 1 builds the OUTPUT form (`fft_bfp`, section 9.1): the unscaled wide core, then one exponent per frame and a W-bit output; the per-stage form above is not built |

Overflow rule used here: no overflow occurs if re^2 + im^2 < 2^(2W-2) at the input (magnitude below full scale), in both built modes; a full-scale corner can overflow and wraps without a flag.

## 3. What was built (all measured in simulation; no Vivado)

`fft` (two variants, the same ports and parameters): LOGN 3 to 12 (N = 8 to 4096; 4096 is simulated), complex input, forward or inverse per frame (`in_inverse` sampled with `in_sof`: the swap
trick, ifft(x) = swap(fft(swap(x))), so the twiddles are the same and no conjugate ROM is needed), W, TW, `SCALE`, `RND`, `ORDER` (natural or bit-reversed), `CMUL` (3 or 4 real multipliers), `TWSTAGES` (1 or 2),
`MULSTAGES` (0 to 3).

| Variant | Throughput | Latency in_sof to out_sof (formula, checked in simulation for every parameter set of spec.yaml) |
|---|---|---|
| `sdf` | one sample per clock, a frame every N clocks (gap 0 or at least N/4) | bit-reversed: N - 1 + LOGN + ((LOGN-1)//2) * (TWSTAGES + MULSTAGES + 1); natural: that + N + 1 |
| `burst` | one frame per N + LOGN * (N/2 + MULSTAGES + 3) + N clocks | N + LOGN * (N/2 + MULSTAGES + 3) + 1, both orders |

The helper blocks, each a function with its own specification, model, bench, mutants and formal properties: `fft_cmul` (`m4`, `m3`: exact complex product, WA+WB+1-bit outputs), `fft_twiddle` (`quarter`: one
1025 x 31 bit quarter-wave ROM, quadrant folding, rounding half up after the 30-bit master, so +1, -1 and 0 are exact: scale 2^(TW-2)), `fft_reorder` (`pingpong`: bit-reverse buffer, N + 1 clocks, any gap), `fft_window` (`dsp`).

### Accuracy against NumPy (arith/fft/verif/results/accuracy.json, 2026-11-21, W = 16, TW = 18)

Error of the bit-exact model (the RTL equals it) against numpy.fft in units of the output LSB, for noise-like input (components uniform in +-0.65 full scale); SFDR for a coherent tone of 0.9 full
scale (values above 150 dB mean the model's output has no spur at all). All 80 recorded points (both variants, N = 8 to 4096, TW 12, 16, 18, 24, both scaling modes) are in the file.

| Variant | N | SCALE | worst (LSB) | rms (LSB) | SQNR (dB) | SFDR (dB) |
|---|---|---|---|---|---|---|
| sdf | 8 | 1 | 1.276 | 0.829 | 76.8 | 269.4 |
| sdf | 64 | 1 | 1.791 | 0.987 | 66.6 | 86.4 |
| sdf | 256 | 1 | 2.121 | 0.968 | 61.2 | 86.4 |
| sdf | 1024 | 1 | 2.615 | 1.013 | 54.7 | 86.4 |
| sdf | 4096 | 1 | 3.497 | 1.008 | 48.6 | 86.4 |
| sdf | 8 | 0 | 0.437 | 0.293 | 103.9 | 107.5 |
| sdf | 64 | 0 | 4.392 | 1.938 | 96.9 | 100.9 |
| sdf | 256 | 0 | 8.867 | 4.142 | 96.7 | 102.9 |
| sdf | 1024 | 0 | 25.704 | 8.506 | 96.5 | 107.1 |
| sdf | 4096 | 0 | 62.06 | 18.297 | 95.7 | 108.7 |
| burst | 1024 | 1 | 2.615 | 0.996 | 54.9 | 86.4 |
| burst | 1024 | 0 | 33.206 | 10.872 | 94.3 | 105.0 |
| burst | 4096 | 1 | 3.497 | 1.006 | 48.6 | 82.4 |
| burst | 4096 | 0 | 78.088 | 22.636 | 93.8 | 107.4 |

Reading it: in the scaled mode the output word is W bits and the worst error stays within 3.6 LSB at every recorded point (the rounding at each of the n halvings, about 1 LSB rms, is the floor); the
SQNR falls with N only because the scaled output of noise-like input has a rms of about 1/sqrt(N) of the input. In the unscaled mode the output word is W + LOGN bits, so the same rounding
noise is larger in output LSBs; the SQNR (about 94 to 104 dB at TW = 18) is the figure to read. Twiddles of 12 bits are visibly worse at large N (the file has them). `sdf` is slightly better than `burst` in
the unscaled mode because it rounds after a pair of stages, not after every butterfly.

## 4. Real-input transform (built: `fft_real`)

An N-point transform of N real samples is computed as an N/2-point complex transform of z[m] = x[2m] + j x[2m+1] followed by post-processing:
E[k] = Z[k] + conj Z[N/2-k], O[k] = Z[k] - conj Z[N/2-k], X[k] = E[k]/2 + W_N^k (-j O[k])/2 for k = 0 .. N/2 (indices of Z modulo N/2), where W_N^k is the twiddle of fft_twiddle and
the product is one fft_cmul and a rounded shift. The model is `fft_ref.real_frame` / `real_post`, checked against `numpy.fft.rfft` in `arith/fft/tests/test_fft_model.py` (both variants, N = 16, 64, 256,
both scalings). Arrangement built (`arith/fft_real`, variant `post`): the N/2-point `sdf` core on W + 1 bit words (a full-scale real input cannot overflow it) with the bit-reversed output (`ORDER = 1`) and no reorder buffer; the
post-processing memory (two banks of two copies of N/2 words, so Z[k] and Z[N/2-k] are read together while the next frame is written) is addressed at the bit-reverse of the arrival counter, so it replaces the reorder buffer;
the output takes N/2 + 1 clocks per frame, one more than the input, so frames cannot be back to back and are spaced by an idle gap of at least N/8 clocks (the N/2-point core's rule); the scaled mode shifts E and O by 2 instead of 1 so
the result is X/N like the complex transform's. Input is two real samples per clock (a real stream at one sample per clock needs a 2:1 gearbox in front, not built). Latency: (N/2 - 1) + (LOGN - 1) + ((LOGN - 2) // 2) * (TWSTAGES +
MULSTAGES + 1) + N/2 + MULSTAGES + 3 clocks, checked in simulation. A first single-bank version failed its bench: the read-out of a frame can start only after the whole frame is stored, so the next frame's writes (a period of N/2 + N/8 later) overwrote words that were not yet read; which is why the memory has two banks.

## 5. Fast convolution (model and interface proposal; the RTL is built in phase 1: section 9.4)

`fft_common/fastconv.py` models overlap-save and overlap-add FIR filtering on top of the FFT models: a filter of L taps, transforms of N points, B = N - L + 1 new input samples per block. The pipeline:
forward FFT unscaled (W + LOGN bits) -> multiply by the resident filter spectrum Hq = round(FFT(h) * 2^FH) (WH bits, computed once, offline) -> exact complex product, rounded shift of FH -> inverse FFT scaled by 1/N
(so the result is the plain circular convolution). Overlap-save drops the first L - 1 outputs of each block (wrap-around); overlap-add pads B samples with zeros and adds the overlapping tails.

Measured equivalence to direct convolution (`arith/fft/tests/test_fft_fastconv.py`; N = 256, L = 33, W = 16, TW = 18, WH = 24, FH = 14, 900 random samples, both FFT variants): the worst difference from numpy.convolve is below 8 LSB
for both methods (about 2 to 5 LSB in the exploratory runs), the two methods agree with each other within the same bound, a unit filter passes the signal within 3 LSB, and a complex input is filtered part by part.

Interface proposal for `fft_fastconv` (phase 1): ports `in_valid, in_re, in_im` (a continuous stream, no frames: the block forms them), `out_valid, out_re, out_im`, a coefficient-load port (`h_we, h_addr, h_re, h_im`, loading
Hq into an N-word RAM, written while idle), parameters LOGN, L (taps), W, WH, FH, METHOD (save or add), the FFT variant. Overlap-save at one sample per clock needs two FFT cores of N points (one forward, one inverse) running
at 1 frame per B clocks, a spectral multiplier (the `fft_cmul`) fed at one word per clock, and an input buffer of L - 1 samples; its throughput is B / N of the transform rate. The `burst` variant fits low-rate use (frames
far apart). The `sdf` variant takes one frame of N words every N clocks but each frame carries only B new samples, so a continuous input stream arrives at B/N of the clock: the stream must be gated (the
SDF has no clock enable and frames must be contiguous, so the block would need an input FIFO that forms frames) or the transform clock must be faster than the sample clock by N/B.
The decision between METHOD values is open: overlap-save wins on input buffering (no adder, no zero padding), overlap-add on output simplicity when filters are short.

## 6. Expectations before any Vivado run (to be tested by the queued runs)

Written 2026-11-21; each is a prediction, not a result. Parts xc7a100t-1 and xck26 (2LV), out of context, one thread. Per-variant detail with the intended primitive use is in each `spec.md`.

| Block / point | Expected on xc7a100t | Expected Fmax |
|---|---|---|
| `fft_cmul` m4, 16 x 16, STAGES 3 | 4 DSP48E1, under 100 LUT, 0 BRAM | 350 to 450 MHz |
| `fft_cmul` m3, 16 x 16, STAGES 3 | 3 DSP48E1, 80 to 150 LUT | 300 to 400 MHz |
| `fft_twiddle` quarter, 12-bit circle, TW 18, STAGES 2 | 0 DSP; 500 to 700 LUT (distributed) or 1 RAMB18; about 80 LUT of folding | 300 to 400 MHz |
| `fft_reorder` pingpong, N 1024, 32-bit | 4 RAMB18, about 50 LUT | 350 to 450 MHz |
| `fft_window` dsp, 16 x 16 | 2 DSP48E1, under 60 LUT | 350 to 450 MHz |
| `fft` sdf, N 1024, W = TW = 16, SCALE 1, ORDER 0, CMUL 4, MULSTAGES 3 | 16 DSP48E1, 2 to 4 k LUT, 3 to 4 k FF, about 10 RAMB18 | 250 to 350 MHz |
| `fft` burst, N 1024, same | 4 DSP48E1, 500 to 800 LUT, 700 to 1000 FF, 4 RAMB18 | 250 to 350 MHz |
| `fft_real` post, N 1024 real samples (512-point core), W = TW = 16, MULSTAGES 3 | 20 DSP48E1, 3 to 5 k LUT, about 8 RAMB18 for the post-processing memory plus the core's | 250 to 350 MHz |

Fmax expectations on xck26 are higher by about 40 to 60 per cent (UltraScale+ DSP48E2 and faster fabric). The runs are queued in `_handoff/fpga_agent/vivado_later_queue.md`.

## 7. Verification summary

Per function: a bit-exact model checked against an independent formulation; the RTL against the model in Icarus + cocotb (directed or exhaustive points, random points, latency exact: the bench fails with a stated
latency two clocks off); seeded faults (mutants) all killed; SymbiYosys properties (the reorder address map is a permutation and an involution for 3 to 12 address bits, both complex multipliers equal the plain formula at
small widths, the twiddle table's quarter-turn symmetry for every index, the window's rounding formula, and the delay-feedback stage's butterfly, bounded); a v1 testplan under the 116 gate. The results are in each
function's `verif/results/`. What is not covered is in the report: no formal proof of the whole FFT, no packaged harness, no Lean, no hardware.

## 8a. AMBA AXI4-Stream interface, and how it compares with AMD's FFT IP

Owner direction (2026-11-21): "favour AMBA AXI where appropriate". Built: `arith/fft_axis`, AXI4-Stream wrappers of the two FFT variants (`fft_axis_sdf`, `fft_axis_burst`).

| | `fft_axis` (this suite) | AMD FFT IP, PG109 (as we understand it; read the guide before relying on this column) |
|---|---|---|
| Data in | one slave stream, tdata = {imaginary, real}, W bits each (not byte-padded), tlast on the N-th beat, tuser[0] = inverse on the first beat | one data stream; per-frame options go on a separate configuration stream |
| Per-frame options | forward or inverse on tuser (a bit of the data stream, read on the first beat) | a configuration stream carries forward or inverse, the scaling schedule and the cyclic-prefix length, once per frame |
| Data out | one master stream, tdata = {imaginary, real}, tlast on the N-th beat | one data stream, tdata the same pair, the bin index on tuser |
| Status and events | none | an optional status stream and event signals (for example a missing or unexpected tlast, a halted pipeline) |
| Back-pressure | stated per variant: `sdf` none (tready fixed, a pure streaming interface), `burst` full on both streams | depends on the architecture chosen: the streaming one needs the sink to keep up unless it is given extra buffering; the burst ones use the handshake |
| Size, scaling | N and scaling are compile-time parameters (SCALE: scaled by 1/N or growing) | N can be run-time configurable up to a maximum; scaling can be unscaled, scaled with a schedule, or block floating point |
| Registers | none, so no AXI4-Lite | none for the core itself (configuration goes by stream); AXI4-Lite appears only in the surrounding wrappers a tool may generate |

What this means in practice: our interface is smaller and fixed; where AMD's lets a user change N or the scaling schedule per frame, ours needs a different instance. The two things a user could get wrong are
stated in `arith/fft_axis/spec.md`: the `sdf` variant must be fed without pauses inside a frame and read without stalls, and tdata is not padded to a byte boundary.

Handshake rules followed (AMBA AXI4-Stream, ARM IHI 0051, in our words): a beat transfers when tvalid and tready are both high; a source that has raised tvalid must keep it, and keep tdata and tlast, until
the beat transfers; tvalid must not depend on tready (here: it comes from registers); tready may depend on tvalid but ours does not. `arith/fft_common/axis_checker.sv` checks these in simulation on both streams
(immediate assertions on the clock edge, not concurrent SVA properties, because the open-source simulators used here do not run those), plus tlast position, no unknowns after reset, no stall for the no-back-pressure variant
and no pause inside a frame where the variant forbids it; a deliberate-violation test shows the checkers can fail, and a mutant that makes tvalid depend on tready is killed by them. The burst core also gained an
`out_ready` input (the unload stalls and holds out_valid, out_sof and the data; the sdf core ignores it).

What was not done: AXI4-Stream ports on the helper blocks (`fft_cmul`, `fft_twiddle`, `fft_reorder`, `fft_window`) and on `fft_real` and the cores themselves: they are fixed-latency pipelines or internal blocks
with a start-of-frame interface, and a handshake on them would add logic and stall paths without a stream to connect to. An AXI4-Stream wrapper of `fft_real`, an AXI4-Stream
input/output FIFO that gives the `sdf` variant back-pressure, an AXI4-Lite configuration block (needed only if run-time scaling or run-time N are added), and concurrent-SVA or formal proofs of the handshake rules are
the follow-ups (phase 1, section 9, built the AXI4-Stream wrapper of `fft_real`, the AXI4-Stream/AXI4-Lite fast-convolution block and the BFP and 2-parallel entries).

## 9. Phase 1 (brief 161): block floating point, 2-parallel, real-input AXI4-Stream, fast-convolution RTL

Four entries added to `arith/` (same form as phase 0: specification, bit-exact model, RTL, bench, seeded faults, traced testplan, prepared Vivado builds, now also a packaged harness). **Nothing here has been through Vivado**; every resource and Fmax statement is a prediction in `expected_primitives` and in `_handoff/fpga_agent/vivado_later_queue.md`.

### 9.1 Block floating point: `fft_bfp` (variants `sdf`, `burst`)

Design: the unscaled core (`SCALE = 0`, bit-reversed output, W + LOGN bit words) writes a frame into a two-bank store while the OR of the ones-complement magnitudes of every part is collected; at the end of
the frame the bit length BL of that OR gives the exponent `s = BL + 1 - W`; the frame is read out in natural or bit-reversed order with every part shifted by `s` (right, rounded half up, saturated if the rounding
carries; or left, exactly, for a quiet frame), and `out_exp = s` rides with every word. The value of a word is `(out_re + j out_im) * 2**s`. The exponent is a documented SIDE CHANNEL (`out_exp`, valid with every word, constant over the frame); an AXI4-Stream wrapper that carries it on `m_axis_tuser` is not built. The latency is the core's plus N + 2 clocks (the frame store). **This is block floating point at the output of a wide unscaled transform, not a per-stage scaling schedule**:
the datapath is W + LOGN bits whatever the signal level, which costs DSP width and memory against a per-stage scheme (a 26-bit operand needs two DSP48E1 blocks), in return for no overflow and no
schedule. The bound stated in `arith/fft_bfp/spec.md` and enforced by a test: every part's error is at most the unscaled core's own worst error plus `2**s` (the final rounding).

Measured (the records are `arith/fft_bfp/verif/results/accuracy.json`, 80 points: both architectures, every N from 8 to 4096, input levels 0, -20, -40 and -60 dB of a noise-like frame, W = 16, TW = 18; the
bit-exact models, equal to the RTL, against `numpy.fft`); "worst / rms" in the mode's own output LSB (scaled: N units of the transform; unscaled: 1; BFP: `2**s`), SQNR in dB, `sdf` rows:

| N | level (dB) | scaled: worst / rms / SQNR | unscaled: worst / rms / SQNR | BFP exponent | BFP: worst / rms / SQNR |
|---|---|---|---|---|---|
| 8 | 0 | 0.848 / 0.708 / 79.2 | 0.472 / 0.266 / 105.7 | 2 | 0.5 / 0.454 / 89.1 |
| 8 | -40 | 0.87 / 0.595 / 41.9 | 0.373 / 0.274 / 66.7 | -4 | 5.971 / 4.384 / 66.7 |
| 8 | -60 | 1.375 / 0.835 / 19.1 | 0.373 / 0.25 / 47.7 | -8 | 95.381 / 63.991 / 47.7 |
| 64 | 0 | 1.938 / 0.989 / 67.3 | 3.446 / 1.78 / 98.3 | 4 | 0.683 / 0.442 / 86.3 |
| 64 | -40 | 2.219 / 1.05 / 26.3 | 3.262 / 1.425 / 59.8 | -3 | 26.096 / 11.398 / 59.8 |
| 64 | -60 | 1.835 / 1.011 / 6.8 | 2.565 / 1.358 / 40.4 | -6 | 164.132 / 86.942 / 40.4 |
| 1024 | 0 | 2.851 / 0.999 / 54.7 | 23.824 / 8.546 / 96.3 | 6 | 0.766 / 0.431 / 86.1 |
| 1024 | -40 | 3.421 / 1.023 / 14.2 | 18.184 / 6.552 / 58.3 | -1 | 36.368 / 13.104 / 58.3 |
| 1024 | -60 | 3.022 / 1.007 / -5.1 | 16.877 / 6.531 / 38.9 | -4 | 270.025 / 104.492 / 38.9 |
| 4096 | 0 | 3.651 / 1.006 / 48.6 | 48.331 / 18.161 / 95.7 | 7 | 0.819 / 0.432 / 86.0 |
| 4096 | -40 | 2.947 / 1.007 / 8.6 | 41.118 / 13.074 / 58.6 | 1 | 21.059 / 6.551 / 58.6 |
| 4096 | -60 | 3.19 / 0.975 / -11.0 | 39.896 / 12.954 / 38.8 | -3 | 319.17 / 103.633 / 38.8 |

Reading it: at full level the BFP output is within 1.2 output LSB (`2**s`) everywhere and its SQNR is at least 85.8 dB over all N (the scaled mode falls to 48.6 dB at N = 4096, the unscaled mode keeps 93.7 dB but
needs W + LOGN output bits); at -60 dB the BFP SQNR equals the unscaled mode's (35.4 dB at worst, 38.8 dB at N = 4096) because the error is then the core's absolute rounding noise, which the output
normalisation cannot recover, while the scaled mode has no signal left (-11 dB). So BFP gives the unscaled mode's accuracy in a W-bit word with an exponent; it does not give a quiet frame more precision
than the wide core has. The worst error in BFP LSB looks large for quiet frames (319 LSB at -60 dB) because the LSB is then tiny (`2**s`, s = -3 to -8).

### 9.2 2-parallel pipeline: `fft_mdc2` (variant `par2`)

Two samples per clock: a frame is N/2 clocks of the pair (x[2m], x[2m + 1]) and the output is N/2 clocks of the pair (X[k], X[k + N/2]). Built as two N/2-point radix-2^2 `sdf` pipelines (even and odd samples)
and one combining radix-2 stage (one complex multiplier, the same twiddle ROM, rounding as stated in the spec). **It is the decimation-in-time split, not the delay-commutator network usually called
MDC**: it has the throughput and the delay memory (N - 2 words) of the radix-2^2 MDC, but 2 * ((LOGN - 2) // 2) + 1 complex multipliers where the MDC needs about LOGN - 2 (the commutator form was costed
in section 2 and not built, because its bit-exact model and a verified control network would have been a second architecture rather than a variant). Latency formula, checked in simulation at every point:
N/2 - 1 + (LOGN - 1) + ((LOGN - 2) // 2) * LMUL (+ N/2 + 1 for natural order) + LMUL + 1, LMUL = TWSTAGES + MULSTAGES + 1; throughput exactly 2 samples per clock. **Frame-gap rule measured**
(`tests/test_fft_mdc2_gaps_rtl.py`, N = 32 to 256 and both orders): a frame may follow after no gap or at least N/8 idle clocks (the N/2-point sub-pipelines' N'/4); N/8 - 1 corrupts a frame.

### 9.3 Real-input FFT behind AXI4-Stream: `fft_real_axis`

The wrapper of `fft_real` (tdata in = {x[2m+1], x[2m]}, N/2 beats, tlast; tdata out = {imaginary, real}, N/2 + 1 beats, tlast). Its measured gap rule (N/8 idle clocks, no back-to-back frames) is enforced by
back-pressure: `s_axis_tready` is low for N/8 clocks after every tlast beat, and the bench measures exactly N/8 idle clocks for a source that never pauses. Inside a frame the stream cannot pause and the
output cannot stall (both stated, and flagged by the simulation checkers). No register is added: the first-beat latency equals the core's.

### 9.4 Fast convolution, overlap-save: `fft_fastconv` (variant `os`)

AXI4-Stream samples in, AXI4-Stream filtered samples out (full back-pressure), the filter spectrum (N complex words of WH bits) loaded over AXI4-Lite (eight 32-bit registers; the register map and every response
rule are in the spec's contract and tested). Data path: a ring buffer holds the last N samples (so the L - 1 overlap needs no copy); a four-state controller (clear, collect B = N - L + 1 samples, wait for output
room, feed the ring to the forward transform) forms blocks; forward `sdf` unscaled (W + LOGN bits, natural order), the exact complex product with the filter word and a rounded shift of FH bits, inverse `sdf`
scaled by 1/N on W + LOGN + GB bit words (GB: headroom bits for the filter's absolute gain), the first L - 1 outputs dropped, the rest saturated to W bits and stored in a FIFO of 4N words behind a credit counter
(a block starts only when its B results fit, because the pipelines cannot stall; 4N words hold the results of the up to three blocks that are in flight at once, since a block's results arrive about 4N clocks
after it starts: a first version with N words throttled the input whenever B was above N/2, found while checking the throughput formula). Overlap-add is not built (it needs an output accumulator RAM). The output is bit-exact against `arith/fft_fastconv/model.py`
for streams with random stalls on both sides, filter changes between blocks and random register traffic; the latency from the last input beat of a block to its first output is
2 * (2N + LOGN + ((LOGN - 1) // 2) * LMUL) + MULSTAGES + L + 7 (checked exactly). Against `numpy.convolve` of the unquantised taps and the same samples (W = 16, TW = 18, WH = 24, FH = 14, GB = 1;
`arith/fft_fastconv/verif/results/accuracy.json`, 16 points, N = 64 to 4096, L from N/8 + 1 to 3N/4 + 1): worst error 3.6 LSB, rms about 1 LSB, SQNR at least 44.5 dB (the minimum is a small-gain random filter,
whose output is small).
Throughput is B / (B + N + 1) samples per clock (the input pauses N + 1 clocks per block; the bench measures the block period B + N + 1 exactly): 0.47 samples per clock at N = 1024, L = 129. The coefficient memory can be written only while STATUS.BUSY is 0; with a continuous
stream BUSY is nearly always 1, so a filter is changed with the input stopped. The AXI4-Lite register file is also checked by bounded model checks (SymbiYosys, `arith/fft_fastconv/formal`).

### 9.5 What phase 1 did not do

No per-stage block floating point; no commutator-network MDC; no radix-4 burst; no overlap-add RTL; no AXI4-Stream wrapper for `fft_bfp` (exponent on tuser) or `fft_mdc2`; no back-pressured `sdf` (an input/output FIFO); no run-time N; no Vivado run;
`python -m flow.verified` records (PR #271, not on main when this phase ran) are not produced; no Lean statement.

## 10. Sources

Cited by name; they were not re-fetched in this run, and the AMD guide is for comparison only (no vendor code or text is used): Cooley and Tukey, "An algorithm for the machine calculation of complex Fourier series",
Math. Comp. 1965; S. He and M. Torkelson, "A new approach to pipeline FFT processor", IPPS 1996 (radix-2^2 SDF); E. H. Wold and A. M. Despain, "Pipeline and parallel-pipeline FFT processors for VLSI
implementations", IEEE Trans. Computers 1984 (SDF and MDC); M. Garrido, K. K. Parhi and J. Grajal, "A pipelined FFT architecture for real-valued signals", IEEE TCAS-I 2009; M. Garrido, "Pipelined radix-2^k feedforward FFT
architectures", IEEE TVLSI 2013; H. V. Sorensen, D. L. Jones, M. T. Heideman and C. S. Burrus, "Real-valued fast Fourier transform algorithms", IEEE Trans. ASSP 1987; P. D. Welch, "A fixed-point fast Fourier
transform error analysis", IEEE Trans. Audio and Electroacoustics 1969; A. V. Oppenheim and R. W. Schafer, "Discrete-Time Signal Processing" (overlap-save, overlap-add, FFT roundoff); D. E. Knuth, "The Art of Computer
Programming" vol. 2 (the three-multiplication complex product); AMD PG109, "Fast Fourier Transform" LogiCORE IP product guide (architectures and scaling options, for comparison only).
