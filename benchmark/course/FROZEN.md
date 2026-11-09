# Benchmark course tier: course v1 frozen 2026-11-06, course v1.1 frozen 2026-11-06, course v1.2 frozen 2026-11-07, course v1.3 frozen 2026-11-08, course v1.3.1 2026-11-09 (see the end)

Written by brief 07a1 before any agent run on these tasks. The tier ports the course projects of Parts 13-16 to the benchmark v1 layout; v1 itself (`benchmark/tasks`, `pool`, `lib`, the scoring tools) is unchanged.
Nothing in `benchmark/course/tasks`, `benchmark/lib` or the scoring tools may change after this point without a new version and a new freeze; a change found necessary is recorded here.

| What | Value |
|---|---|
| Split | `split.yaml`, seed 20261106, `random.Random(seed).sample(sorted(ids), round(n/3))` per course part (tier C13..C16), 19 ids; SHA-256 `9d4262ae11cdc67a11a78e227f0606cddb793dbf182b23305a1fbf41951a96f7`. Drawn and committed before any agent run (and before the tasks were checked). Held out 7 of 19 (C13 2, C14 1, C15 2, C16 2), development 12 |
| Tasks built | v1: 15 (development 10, held out 5; four split ids had no task: `PENDING.yaml`). v1.1: 19 (development 12 in this repository, held out 7 in the private repository, by digest here); every split id has a task |
| Manifest | `MANIFEST.json` (22 units: 15 tasks, 7 shared; per unit the SHA-256 of its sorted `sha256  path` lines; held-out units by digest only) |
| Private manifest | `benchmark_private/course/MANIFEST_full.json` in the private repository (every file of every unit) |
| Tools | Python 3.12.3, cocotb 2.0.1, Icarus 12.0, Verilator 5.048, Vivado 2025.2, PyYAML 6.0.1 |

## How to verify

```bash
python3 benchmark/course/tools/freeze.py verify                              # public units, from a fresh clone
python3 benchmark/course/tools/freeze.py verify --private <private>/benchmark_private   # every unit
python3 benchmark/tools/split.py show benchmark/course/split.yaml
python3 benchmark/course/tools/bank_grep.py                                  # the knowledge bank holds no task phrase: 0 hits at freeze
```

`benchmark/course/tests/test_course_static.py` (CI) re-runs the draw from the recorded seed, checks every task and verifies the manifest.

## Rules from here

- Held-out tasks are never used while tuning the agent; they are run once, at a milestone the planner names, as one measurement. A held-out `spec.md` is published only after scoring.
- No fix may be motivated by a held-out run. Model errors and spec ambiguities found on development tasks are recorded, not repaired by editing a task.
- Nothing from the course repository (lessons, exercises, labs, reference RTL) goes into the agent's knowledge bank or prompts. The reference RTL here is a copy of the course reference, wrapped for the shell.

## Tool change after the freeze (brief 07a2-prep, 2026-11-06)

`benchmark/course/tools/no_shell.py` (a shared unit; its digest changed in the public and the private manifest, no task changed):
the course scoring entry now (1) compiles the sources in dependency order, packages and interfaces first (`flow/srcorder.py`),
where it used to compile in file-name order, so an agent's `foo_pkg.sv` next to `foo_core.sv` builds; (2) links a task's
`data/` files into the simulator's working directory (`hidden/`) for the length of a scoring run, only where no file of that name
exists, so `$readmemh("x.hex")` and `$readmemh("data/x.hex")` find the task's data as they do in the agent's own simulation.
A design that already scored the same way still does; the reference of every task passes unchanged (checked below).

## Course v1.1 (brief 07a1b, 2026-11-06)

Added before any agent run on a Part 13 task; split, seed and the 15 v1 tasks are unchanged (their digests in `MANIFEST.json` are the same as in v1; `split.yaml` is byte-identical, SHA-256 above).

| What | Why |
|---|---|
| `c13_histogram_equaliser`, `c13_stereo_disparity` added (held out; private repository, by digest here) | the v1 freeze had no complete reference for them: the course only had lesson-level cores. Brief 07a1b wrote complete reference systems (stream control, line buffers, table build) in the course repository first (model, check.py, simulation), then ported them with the 07a1 recipe. Their spec text is the course spec text as drawn, plus the same test-shell paragraph the other tasks have |
| `c13_nexys_blob_tracker`, `c13_nexys_harris_vga` added (development; this repository), **re-scoped** | the course reference implements a labeller and a Harris response with non-maximum suppression, not the VGA output, overlay, seven-segment display or switches the course specs asked for. The tasks are the narrower block behind the shell; each `hidden/spec.yaml` has a `scope:` section (dropped, kept, glue added) |
| `PENDING.yaml` removed; `test_course_static.py` checks that the development ids and the public tasks coincide | nothing is pending |
| Course project specs and models | `p13_nexys_blob_tracker` and `p13_nexys_harris_vga` re-scoped the same way; the histogram model's Otsu search uses exact integer comparison instead of floats (the same answer on the course pictures, and on 300 random histograms) |

The split is not redrawn: the ids did not change. Tool versions as above (Python 3.12.3, cocotb 2.0.1, Icarus 12.0, Verilator 5.048). The shell wrapper of these four tasks uses `CLKS_PER_BIT: 2` in its bench (the shell works at 2; the transfers are
long). Shared units (`benchmark/lib`, the scoring tools, `benchmark/course/tools`) are unchanged by v1.1.

## Course v1.2 (brief 07a4 step 3, 2026-11-07)

Parts 9-12 join the tier before any agent run on them. Nothing earlier changed: `split.yaml` is byte-identical (SHA-256 above), and the digest of every v1 and v1.1 task in `MANIFEST.json` is the same as before (the 19 task units and the 7 shared units are unchanged).

| What | Value |
|---|---|
| Split | `split_c9_c12.yaml`, seed 20261106, the same rule (`random.Random(seed).sample(sorted(ids), round(n/3))` per course part, tiers C9..C12), 10 ids; SHA-256 `db737086b1eb708b8043268ae2860a6f628f7d9cdbd0d7701011f2a6e5546f84`. Drawn with `tools/split.py` and committed (`d24107f`) before any task was ported or checked. Held out 4 of 10 (C9 1, C10 1, C11 1, C12 1), development 6 |
| Tasks added | ten, from the course specs `projects/p9_*` .. `p12_*` (course repository, `3680a9c`): development 6 in this repository (`c9_median3x3`, `c9_nexys_vga_720p`, `c10_dds_sine`, `c11_nco_mixer`, `c12_adsr_envelope`, `c12_nexys_pwm_audio`), held out 4 in the private repository (by digest here) |
| Manifest | `MANIFEST.json`: 36 units (29 tasks, 7 shared; the 26 earlier units have the same digests as before) and both split digests (`split_sha256`, `split_c9_c12_sha256`); private manifest `benchmark_private/course/MANIFEST_full.json` |
| Tools | `tools/freeze.py` reads both split files; `tests/test_course_static.py` reproduces both draws. Shared units are unchanged |

The streaming blocks of Parts 9-12 are exercised behind the shell with bursts (a 32-clock enable pattern, a 64-clock run, results in order with a count and, where the spec fixes a latency, a record of the clocks on which results appeared); see `README.md`. The 720p video task is scored by one whole frame (about 4 minutes in Icarus, 3.7 on the reference); there is no reduced bench.

## Course v1.3 (brief 07a1c, 2026-11-08)

Four development references are rewritten so that Vivado can build them. No spec text, hidden model, acceptance bench, split or private (held-out) unit changed; `split.yaml` and `split_c9_c12.yaml` are byte-identical. None of the four is held out.

| Task | What changed in `ref/rtl` (and why) |
|---|---|
| `c13_nexys_harris_vga` | picture in seven block-RAM copies with a registered address; `harris.sv` pipelined with one shared response unit (the parallel form needed 155,527 LUTs, the device has 63,400). Bit-exact against the model |
| `c13_nexys_blob_tracker` | `ccl.sv` rewritten as a state machine with sized registers (the unrolled form did not finish in 60 minutes); `blob_report.sv` divides bit-serially |
| `c13_hough_lines` | counts in two block RAMs plus a valid bit per cell (one-clock `clear` kept); busy is 4 clocks longer after a point |
| `c9_nexys_vga_720p` | BTNC, SW and MMCM LOCKED pass through two-flop synchronisers (`cdc_no_critical` failed) |

Mutants whose search text was in rewritten code were re-expressed against the new code (`mutants.yaml` of blob tracker and Harris); each is killed. The reference Vivado numbers are in `results/REFERENCE_BUILDS.md`. The manifest digests of these four tasks changed; every other unit is unchanged.

## Course v1.3.1 (07a2 fix 7, 2026-11-09)

One development task text changed, found by `c12_nexys_pwm_audio` in 07a2 batch 2: its hidden bench connects the 16-bit `LED` output, which `spec.md` never named, so the agent's design (every gate green) failed to elaborate against the bench (0/0). `spec.md` of `c12_nexys_pwm_audio` now lists `LED` in the test-hooks port list ("the 16-bit `LED` output, which the block leaves off"). No hidden file, model, mutant, split or other task changed; the reference passes (2/2) and all 8 mutants are killed (`check_task.py`, Icarus). Only this task's digest in `MANIFEST.json` changed (public manifest edited for this unit; the private `MANIFEST_full.json` copy of the unit needs the same regeneration with `freeze.py make --private`). The C14 tiny-CNN gap (`UART_TXD_IN`) is covered by the agent's FDA-CON-9 check (#67), not by a task edit. The earlier c12 batch 2 run is a record against v1.3 and is kept as such.

## Course v1.3.2 (08a2 grader check, 2026-11-09, before any `eval-1` run)

Two development-task changes and one grader-side bench repair; no split, model, mutant or other task changed, and no held-out unit was touched.

| What | Change and reason |
|---|---|
| `c12_nexys_pwm_audio/hidden/tb_audio_bench.sv` (grader-side) | `07a2` fix 7 run: the agent's top declared `AUD_PWM` as `output logic` and released it with `1'bz`; the bench read Z on the pulled-up net although the design is legal and the reference (`output wire`) passes. Cause: Icarus drops the pull of a `tri1` net when a variable (`logic`) output port is connected straight to it (reproduced: the agent's top fails, the same top with `output wire` passes). The bench now connects each design pin to a plain `wire` and puts the pull on a net fed by a continuous assign, so both port styles resolve alike (the agent's own top now passes 2/2). A bench fault, not an agent fault, so no agent rule. Reference 2/2, 8/8 mutants killed; regression test `test_c12_open_drain_pin_logic_port` runs the reference with the port rewritten to `output logic` |
| `c14_nexys_tiny_cnn/spec.md`, `hidden/spec.yaml` | the weight encoding is stated (signed 8-bit two's complement, in the low byte of a 32-bit word of `cnn_params.hex` with the upper 24 bits zero; biases 32-bit signed; M1, S1, M2, S2 non-negative). The sign-extension error that gave every picture class 2 in the 07a2 rerun came from this gap. Reference 5/5, 7/7 mutants killed |
| scan | `benchmark/tools/pin_scan.py` (ids and yes/no flags only, safe over held-out tasks): over 93 hidden benches (v1, course, pool, and with `--private` all 19 held-out units) the only benches with a pulled net are the three I2C tasks (inout ports: a net by language rule, so not affected), the c12 task (repaired) and three unbuilt pool specs; no held-out task has a pulled net, a tri-state reference or a bench that reads Z, so no held-out bench was changed. `test_no_fragile_pulled_pin_bench` keeps it so |

The two edits and the scan were made before any `eval-1` run. Only `c12_nexys_pwm_audio` and `c14_nexys_tiny_cnn` digests change in `MANIFEST.json`; the private course manifest is regenerated.
