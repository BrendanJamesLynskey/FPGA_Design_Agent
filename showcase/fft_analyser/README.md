# Streaming FFT power-spectrum core with windowing and averaging (brief 79, ladder project 5): phase 1, the specification and the evidence harness

A fixed-point FFT core that takes one 16-bit sample per clock and never stops, windows the samples (none, Hann or Hamming),
transforms frames of 64, 256 or 1024 points with a single-path delay-feedback pipeline scaled so that nothing can overflow,
and gives the power of each lower bin averaged over 1 to 16 frames. This folder holds what phase 1 of the project
produced: the request the FPGA Design Agent will receive, the formal specification with product-style numbers, and a
bit-exact Python reference model that exists in two forms (a frame at a time, and sample by sample through the pipeline)
that the tests prove identical. The agent has not been run on any of it and no hardware has been used: those are
phases 2 and 3 of the brief (there is no board phase for this project yet; the samples come from a replayed memory).

Project 5 of the difficulty ladder of brief 77. Its subsystems are probe tasks for the agent (a scaled butterfly, a window
multiplier, a delay-feedback stage, an output re-orderer, a power averager) and the whole core is the level-2 task; they
are written as benchmark tasks in the private repository and are not named here, because some of them will be held out.

## What is here

| File | What |
|---|---|
| [request.md](request.md) | the plain-English request, as a customer would write it; the only text the agent is given |
| [spec.yaml](spec.yaml) | the formal specification (planner's copy; not shown to the agent): sizes, windows, arithmetic, throughput, accuracy and SFDR numbers, register map, requirements with their proof method |
| [model/fft_ref.py](model/fft_ref.py) | the bit-exact reference model, integers only: window tables, twiddles, the scaled butterfly, a frame FFT, the delay-feedback stage and pipeline, the averaged spectrum |
| [model/product_numbers.py](model/product_numbers.py) | measures accuracy against a floating-point FFT, noise floor and SFDR at the three sizes |
| [records/model_numbers_2026-11-14.json](records/model_numbers_2026-11-14.json) | those numbers |
| [tests/test_fft_analyser.py](tests/test_fft_analyser.py) | 11 tests of the model and the specification |

## Technical parameters

| Item | Value |
|---|---|
| Board, part | Nexys A7-100T, `xc7a100tcsg324-1`; 100 MHz; samples from a memory replayed by the core (the converter comes later) |
| Frame sizes | 64, 256, 1024 (`N_MAX` = 1024); log2(N) radix-2 stages, one single-path delay-feedback stage per halving (delay N/2 down to 1) |
| Arithmetic | 16-bit signed parts; each butterfly scales both outputs by 1/2 with ties rounded up (S = (a + b + 1) >> 1, T = ((a - b) W + 32768) >> 16, W in Q1.15); overall scaling 1/N; limits at 16 bits that cannot act on 16-bit inputs |
| Windows | rectangular, Hann, Hamming (15-bit tables from the formulas in `spec.yaml`, rounded half up, in double precision) |
| Averaging | 1, 2, 4, 8, 16 frames; exact power I^2 + Q^2 (up to 2^31), 36-bit accumulation, mean rounded half up |
| Throughput | one sample per clock, no gaps; K frames take at least N K and at most N K + N + 64 clocks; the spectrum of a frame is complete N - 1 samples after the frame's last sample |
| Output | the N/2 lower bins in natural order, 32-bit unsigned, through a bin index register |

## How to run and reproduce

| Step | Command | Heavy slot | Time |
|---|---|---|---|
| model and specification tests | `python3 -m pytest -q showcase/fft_analyser/tests` | no | about 1 s |
| product numbers of the model | `python3 showcase/fft_analyser/model/product_numbers.py showcase/fft_analyser/records/model_numbers_2026-11-14.json` | no | under 1 s |

## What was verified

- `pytest showcase/fft_analyser/tests`: 11 passed. The pipeline streamed one sample per call equals the frame-at-a-time
  definition bit for bit at N = 64 (three window and averaging settings), 256 (two settings) and 1024; the delay-feedback
  latency is N - 1 samples; the window tables start 0, 79, 315, 705, 1247 (Hann) and 2621, 2694, 2911, 3270 (Hamming) with
  Hann 16384 at i = 16 and 32767 at i = 32; the twiddles of a 16-point FFT; a constant input appears in bin 0 and nowhere
  else; ties round up in both butterfly outputs; no value leaves 16 bits for 40 random full-scale inputs; `spec.yaml`
  validates against the agent's schema.
- The product numbers of `spec.yaml` hold on the model ([records/model_numbers_2026-11-14.json](records/model_numbers_2026-11-14.json)):

| Number | Specified | Model, N = 64 / 256 / 1024 |
|---|---|---|
| worst component error against the floating-point FFT scaled by 1/N, 0.9 full-scale tone, Hann | at most 2.0 LSB | 1.01 / 1.28 / 1.29 LSB |
| rms error (the quantisation noise of the transform) | below 0.5 LSB | 0.214 / 0.194 / 0.149 LSB |
| SFDR, coherent 0.9 full-scale tone with 2 LSB of dither, Hann, 8 frames averaged, bins within 2 of the tone excluded | at least 70 dB | 74.3 / 74.3 / 72.2 dB |

## What is illustrative

The SFDR figures depend on the 2 LSB of dither added to the tone, which stands in for a converter's noise; with no dither a coherent
tone's spurs are set by the arithmetic alone and would be lower. The model's figures are properties of the specification, not of a
build: they say what a correct design must achieve. No resource, timing or power figure exists.

## Known gaps and limits

- The agent has not built this, and nothing has run on the board (phases 2 and 3 do not exist yet for this project). No synthesis or
  timing result exists.
- The benchmark tasks derived from this project (five probes and the whole core) are written and pass their own checks in the
  private repository, but they are not frozen, submitted to the split ledger or drawn: see the brief's report. The whole-core task uses
  64-point frames because the shell's window addresses 64 words directly; sizes 256 and 1024 are specified here and checked on the model only.
- The specification asks a design to match the radix-2 arithmetic bit for bit or to meet the accuracy and SFDR numbers; a radix-2^2
  pipeline places some roundings differently, so it can only meet the numbers. Whether the benchmark should accept that is open.
- `spec.yaml` lists a `STIM_ADDR` register for loading memories larger than the shell's 64-word window; it is not in the reference
  model (there is no register-level model in this phase).
- The model is Python and slow for large runs; 1024-point frames take under a second.

## Next steps

1. Planner: decide the benchmark tasks' freeze and draw (report), then phase 2 after the weekly reset: the agent builds the probes
   and the whole core, k = 3 repeats each, with pass@1, pass@k, cost and the failure profile.
2. A board phase once a converter or a signal source is chosen; until then a replayed memory is the input.
3. A radix-2^2 variant of the reference model if the benchmark should accept that structure bit for bit.
