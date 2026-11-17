# PDM microphone to 48.828 kHz audio on the Nexys A7-100T (brief 79, ladder project 1): phase 1, the specification and the evidence harness

The Nexys A7-100T's on-board digital microphone gives a one-bit stream. This project turns it into 16-bit audio at
48.828125 kHz (100 MHz divided by 2048) entirely in the FPGA, with a capture memory read back over the UART, and
measures it on the board with the PC's loudspeaker. This folder holds what phase 1 produced: the request the FPGA Design
Agent will receive, the formal specification with product-style numbers, a bit-exact Python reference model, the numbers
it gives, and the PC-side measurement scripts with a dry-run mode. The agent has not been run on any of it and the board
has not been used: those are phases 2 and 3 of the brief.

Project 1 of the difficulty ladder of brief 77. Its subsystems are probe tasks for the agent (a CIC decimator, a
half-band stage, a compensating FIR, a DC blocker, a PDM front end) and the whole path is the level-2 task; they are
written as benchmark tasks in the private repository and are not named here, because some of them will be held out.

## What is here

| File | What |
|---|---|
| [request.md](request.md) | the plain-English request, as a customer would write it; the only text the agent is given |
| [spec.yaml](spec.yaml) | the formal specification (planner's copy; not shown to the agent): clocks, pins, stages, capture rules, register map, requirements with their proof method, the four board measurements |
| [model/pdm_chain_ref.py](model/pdm_chain_ref.py) | the bit-exact reference model, integers only: bits in, 16-bit audio out |
| [model/product_numbers.py](model/product_numbers.py) | measures the product numbers on the model |
| [records/model_numbers_2026-11-14.json](records/model_numbers_2026-11-14.json) | the model's passband, alias rejection, SNR, full-scale behaviour and latency |
| [measure/pdm_measure.py](measure/pdm_measure.py) | capture, tone-level and noise analysers, the loudspeaker hook, the simulated board and room |
| [measure/run_measure.py](measure/run_measure.py) | the runner, with `--dry-run` (no board, no audio device) |
| [records/dry_run_2026-11-14.json](records/dry_run_2026-11-14.json) | one dry-run record, marked `"dry_run": true` |
| [tests/test_pdm_decimator.py](tests/test_pdm_decimator.py) | 12 tests of the model, the specification and the measurement scripts |

## Technical parameters

| Item | Value |
|---|---|
| Board, part | Nexys A7-100T, `xc7a100tcsg324-1`; microphone pins `M_CLK` J5, `M_DATA` H5, `M_LRSEL` F5 |
| Clock | 100 MHz; `M_CLK` = 100 MHz / 32 = 3.125 MHz (parameter `CLK_HALF` = 16), `M_LRSEL` low |
| Chain | CIC (3 stages, decimation 16, two fills dropped), x8 scale, two half-band decimators by 2, 9-tap compensating FIR, DC blocker with pole 1 - 2^-7 |
| Output | 16-bit signed at 48.828125 kHz; total decimation 64; first sample after 96 PDM samples (30.7 microseconds), then one per 64 |
| Capture | 64 samples (1.31 ms) per run, armed with `ARM`, read over the UART shell window at 0x40 |
| Limit handling | every stage limits at the 16-bit ends and a sticky `SAT` flag reports it; an all-ones or all-zeros stream saturates the scale stage (full scale is x8 of +-4096) |

## How to run and reproduce

| Step | Command | Heavy slot | Time |
|---|---|---|---|
| model, specification and measurement tests | `python3 -m pytest -q showcase/pdm_decimator/tests` | no | about 20 s |
| product numbers of the model | `python3 showcase/pdm_decimator/model/product_numbers.py showcase/pdm_decimator/records/model_numbers_2026-11-14.json` | no | about 15 s |
| dry run of the whole measurement plan | `python3 showcase/pdm_decimator/measure/run_measure.py --dry-run --out showcase/pdm_decimator/records/dry_run_2026-11-14.json` | no | about 10 s |
| a real run (phase 3, not done) | `run_measure.py --port DEV --confirm-owner-warned --conditions-cmd CMD --out RECORD.json` | board lock | minutes |

A real run refuses to start without `--confirm-owner-warned` (test tones play from the PC loudspeaker; start low), checks the
design ID, and takes the operating conditions (die temperature and VCCINT, VCCAUX, VCCBRAM from the XADC, at the start and
end) from `--conditions-cmd`. The board is programmed through SRAM only and `_handoff/board.lock` is taken by the caller.

## Measurements planned for the board (phase 3)

| Id | What | What limits it |
|---|---|---|
| M1 | the microphone's self-noise in a quiet room: rms of 120 captures with the mean of each removed, in dBFS | the microphone's own noise, not the design's |
| M2 | the level of loudspeaker tones at 1, 2, 4, 8, 12 and 15 kHz relative to 1 kHz (a least-squares sine fit per capture, averaged) | the loudspeaker, the room and the microphone response bound this: it is the response of the whole measured chain, not the design's |
| M3 | the tone-to-noise ratio: each tone against M1 | acoustic and electrical interference are included |
| M4 | the operating conditions at the start and end | the XADC samples at about 1 MSPS and cannot see fast supply droop |

A 64-sample capture holds 1.3 cycles of 1 kHz, so the board plan starts at 1 kHz; the passband down to 200 Hz is checked on
the model only. The alias rejection of tones above 40 kHz is checked on the model only (the loudspeaker cannot make them).

## What was verified

- `pytest showcase/pdm_decimator/tests`: 12 passed. The streaming model equals a second implementation written as
  whole-array steps on three random streams of 9000 bits; full-scale input saturates and a quiet tone does not; the first audio sample
  appears at PDM sample 96 and the next 64 later; the CIC, the half-band rounding of exact ties (16 gives 0, 48 gives 2,
  -16 gives 0, -48 gives -2) and the DC blocker's floor shift behave as `spec.yaml` says; `spec.yaml` validates against the agent's
  schema and agrees with the register offsets the measurement scripts use; the tone estimator recovers a known amplitude at every
  planned frequency and random phase, and the noise estimator recovers white noise of -80 dBFS; the simulated board follows the
  ARM, DONE and CAP rules; the runner's dry run passes and a real run without `--confirm-owner-warned` is refused.
- The product numbers of `spec.yaml` hold on the model ([records/model_numbers_2026-11-14.json](records/model_numbers_2026-11-14.json)):

| Number | Specified | Model |
|---|---|---|
| passband, 200 Hz to 15 kHz, relative to 1 kHz | within +-1.0 dB | worst 0.46 dB (at 200 Hz, the DC blocker's roll-off) |
| alias rejection, tones from 40 kHz up that land in 0 to 15 kHz | at least 35 dB | worst 37.0 dB (63.8 kHz) |
| SNR, 1 kHz at -6 dBFS, 100 Hz to 15 kHz | at least 70 dB | 76.7 dB (second-order delta-sigma source) |
| output rate | 48.828125 kHz | 100 MHz / 2048 exactly |

## What is illustrative

The numbers in [records/dry_run_2026-11-14.json](records/dry_run_2026-11-14.json) are properties of the simulated rig's settings
(a tone of 0.05 of full scale, white room noise of -72 dBFS per PDM sample, a second-order delta-sigma microphone) and of the model,
not measurements of any hardware or of any design. They show that the analysers and the runner work. The model's figures are
properties of the specification, not of a build: they say what a correct design must achieve.

## Known gaps and limits

- The agent has not built this and the board has not been touched (phases 2 and 3). No synthesis or timing result exists; the
  resource estimate in `spec.yaml` is not measured.
- The benchmark tasks derived from this project (five probes and the whole path) are written and pass their own checks in the
  private repository, but they are not frozen, submitted to the split ledger or drawn: see the brief's report.
- The model's microphone is a second-order delta-sigma modulator in software. The real microphone's noise and distortion are
  unknown until M1 and M2 are measured; the 70 dB SNR figure is the model's, not the microphone's.
- The 48.828125 kHz output rate is not 48 kHz; exactly 48 kHz needs a PLL and is out of scope.
- A 64-sample capture cannot measure below 1 kHz (see above) and cannot resolve a 70 dB SNR; the SNR is verified on the model.
- The loudspeaker hook (`aplay`) and the UART path are written and not run on hardware. Tone levels are fractions of the PC's
  output, not calibrated sound pressure.
- Operating conditions are an input (`--conditions-cmd`); the dry run records none.

## Next steps

1. Planner: decide the benchmark tasks' freeze and draw (report), then phase 2 after the weekly reset: the agent builds the
   probes and the whole path, k = 3 repeats each, with pass@1, pass@k, cost and the failure profile.
2. Phase 3: with the board and `board.lock`, load the best build and take M1 to M4 with the operating conditions.
3. A longer capture memory (or a streaming read-out) would let the board measure the 200 Hz and 500 Hz points of the passband.
