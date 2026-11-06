# Benchmark course tier: course v1 frozen 2026-11-06, course v1.1 frozen 2026-11-06 (see the end)

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
