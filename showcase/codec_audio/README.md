# Codec audio path on the ZedBoard (brief 78, ladder project 2): phase 1, the specification and the evidence harness

A stereo 48 kHz, 24-bit audio path on the ZedBoard ("bump"): line in, the ADAU1761 codec, I2S into the logic, a per-channel
gain and mute with click-free smoothing, per-channel peak, RMS and clip metering read over AXI4-Lite, I2S back out to the
codec, line and headphone out. This folder holds what phase 1 of the project produced: the request the FPGA Design Agent
will receive, the formal specification, a bit-exact Python model, the register map and its datasheet, and the PC-side
measurement scripts with a dry-run mode. The agent has not been run on any of it, and the board has not been used: those
are phases 2 and 3 of [the brief](../../README.md).

**Status of phase 1 (2026-11-14): complete for everything in this folder; the benchmark half is written but not frozen.**
Six benchmark tasks (five probes of one block each and one for the whole path) were written to the v2 task layout in the
private repository and pass their own checks, but they have not been frozen, submitted to the split ledger or drawn: the
batch's pre-freeze leak check still reports shared scaffolding text between sibling tasks, and how to treat it is for the
planner to decide (see "Known gaps"). Nothing in this folder names those tasks or quotes their hidden tests.

## What is here

| File | What |
|---|---|
| [request.md](request.md) | the plain-English request, as a customer would write it; the only text the agent is given |
| [spec.yaml](spec.yaml) | the formal specification (planner's copy; not shown to the agent): clocks, codec pins, parameters, behaviour, requirements with their proof method, the six board measurements |
| [model/audio_ref.py](model/audio_ref.py) | the bit-exact reference model of the processing and the metering, integers only, with the I2S slot encoding |
| [regmap/codec_audio.yaml](regmap/codec_audio.yaml) | the AXI4-Lite register file (house profile), 18 registers in a 4 KB window |
| [regmap/generated/](regmap/generated/) | the generated register block, C header, Python driver and datasheet ([codec_audio_regs.md](regmap/generated/codec_audio_regs.md)), checked current by `python3 -m hwsw.regmap check` |
| [measure/audio_measure.py](measure/audio_measure.py) | tone generator, analysers (frequency response, THD+N, noise floor, crosstalk, latency, click energy), the simulated rig, the ALSA rig |
| [measure/run_measure.py](measure/run_measure.py) | the runner, with `--dry-run` (no audio device, no board) |
| [records/dry_run_2026-11-14.json](records/dry_run_2026-11-14.json) | one dry-run record, marked `"dry_run": true` |
| [tests/](tests/) | 25 tests of the model, the register file against `spec.yaml`, and the measurement scripts |

## Technical parameters

| Item | Value |
|---|---|
| Board, part | ZedBoard, `xc7z020clg484-1` (pins from the knowledge bank, not yet read from the board) |
| Audio format | I2S, 24 bit, 48 kHz, 32 bit clocks per channel slot, codec is the clock master |
| Master clock | 12.288 MHz (256 x 48 kHz) from the logic |
| Gain | unsigned Q4.12, `0x1000` is 1.0; ramp step `RAMP_STEP = 16` per sample, so unity to silence takes 256 samples (5.33 ms) |
| Digital latency | one frame (one sample period) |
| Meters | peak (hold `HOLD`, default 32 samples, then falls by `max(1, peak >> 5)`), clip counter (16 bit, saturating, counts every sample at either end of the range), RMS over `2**RMS_LOG2` samples (default 256), all on the processed signal |
| Control | AXI4-Lite, house profile; codec set-up over I2C from the Arm (chosen default, reason in `spec.yaml`) |

## How to run and reproduce

| Step | Command | Heavy slot | Time |
|---|---|---|---|
| model, register file and measurement tests | `python3 -m pytest -q showcase/codec_audio/tests` | no | about 2 s |
| regenerate and check the register block | `python3 -m hwsw.regmap gen showcase/codec_audio/regmap/codec_audio.yaml --out showcase/codec_audio/regmap/generated` then `check` | no | seconds |
| dry run of every measurement | `python3 showcase/codec_audio/measure/run_measure.py --dry-run --out showcase/codec_audio/records/dry_run_2026-11-14.json` | no | under a second |
| a real run (phase 3, not done) | `run_measure.py --play-device D --record-device D --confirm-owner-warned --baseline records/pc_loopback.json` | board lock | minutes |

A real run refuses to start without `--confirm-owner-warned` (the owner must be told a test tone is about to play; the line
out starts at -30 dBFS with a 50 ms fade in). Operating conditions (the interface, the levels, and the die temperature and
rails when `--conditions-cmd` supplies them) go into the record.

## What was verified

- `pytest showcase/codec_audio/tests`: 25 passed. They check the model's arithmetic (slew, floor, saturation, peak hold and
  fall, clip counting, RMS floor roots, the I2S slot round trip), that `spec.yaml` validates against the agent's spec schema
  and agrees with the register file, that the generated datasheet is current, and the analysers against signals of known
  content: a -40 dB third harmonic reads -40 dB THD+N, white noise of -90 dBFS reads -90 dBFS in band, a -80 dB leak reads
  -80 dB crosstalk, a delay of 123.5 samples reads 123.5, and a gain step through the ramp clicks at least 12 dB less than
  a step without it.
- The simulated rig's gain stage is bit-exact with `model/audio_ref.py` (a test drives both with random samples and gain and
  mute events).

## What is illustrative

Every number in [records/dry_run_2026-11-14.json](records/dry_run_2026-11-14.json) is a property of the simulated rig's own
settings (converter noise -108 dBFS, crosstalk -96 dB, a delay of 41 samples, and so on, listed in the record's
`rig_settings`), not a measurement of any hardware. It shows that the analysers recover what was put in. The codec
datasheet limits used to attribute a measurement to the codec are not yet filled in (`--datasheet`), so a dry run reports
`design_or_unknown` unless a baseline is given.

## Known gaps and limits

- The agent has not built any of this and the board has not been touched (phases 2 and 3).
- The six benchmark tasks are unfrozen. The pre-freeze check ran `site/leak_guard.py`'s windowing between the six pending
  tasks (each in turn as the secret) and found 80-byte runs shared between sibling tasks in standard scaffolding: the
  opening and port rows of a hidden `spec.yaml`, the board top's parameter list, the register-window read multiplexer of a
  reference design, the identity-and-reset skeleton of a hidden test. Task-specific text (spec wording, models, mutants, the
  logic of the reference designs, test bodies) was reworded until it no longer matched. Publishing the shared scaffolding
  as public text, so that the guard would clear it, was not done, because it would make the guard pass without making
  the tasks differ. The planner needs to decide between rewording the scaffolding in each task (more effort, no change to
  the guard) and a documented allowance in the guard.
- The benchmark harness is Nexys A7-100T only (the test shell is on its USB-UART), so the six tasks use the Nexys board and
  Pmod JA for the I2S pins; the ZedBoard realisation is the project in this folder. The ZedBoard board pack is not on
  `main` yet (it is on branch `b64b-zedboard`).
- `AlsaRig` (`aplay` and `arecord`) and the controller hook for gain and mute writes are written but have not run on any
  hardware; the timing of control events on a real rig is approximate and the analysers find the gain step in the data.
- The click measurement against an unsmoothed control needs a second build with the ramp removed (`RAMP_STEP = 0xFFFF`) on
  the board; the dry run uses the same simulated rig without the ramp.
- The codec's own figures and the PC interface's baseline are inputs (`--datasheet`, `--baseline`), not yet recorded.
- Pin numbers in `spec.yaml` come from the knowledge bank and the Avnet constraints; none is read from the board.

## Next steps

1. Planner: decide how sibling-task scaffolding is handled, then freeze, submit and draw the six tasks (batch order and
   commands are in the brief's report), and add the development ones to `benchmark/v2/tasks`.
2. Phase 2 (after the weekly reset): the agent builds the five probes and the whole-path task, k = 3 repeats each; record
   pass@1, pass@k, cost and the failure profile.
3. Phase 3: after the ZedBoard is power-cycled and bring-up is complete, run the best build, take the baseline with the PC
   interface alone, then the six measurements with the operating conditions recorded.
