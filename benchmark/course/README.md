# benchmark/course/: the course-tier tasks (Parts 13-16)

Natural-language FPGA design tasks taken from the 19 project specs of course Parts 13 (computer vision), 14 (machine learning), 15 (AI kernels) and 16 (crypto),
in the layout of benchmark v1 ([../README.md](../README.md)) and scored by the same `run_task.py` through the same test shell. The tier is separate from v1: its own task
list, split, manifest and freeze ([FROZEN.md](FROZEN.md)); v1 itself is unchanged. The purpose is to run the agent on the projects and use the results to improve it (brief 07a).

## What is the same as v1

Layout of one task (`spec.md`, `hidden/{spec.yaml, model.py, acceptance.py, bench.yaml, mutants.yaml, selfcheck.py}`, `ref/rtl/`), board top `<id>_top` with the master-XDC port
names, the test shell on the USB-UART with a DESIGN_ID, the "Test hooks" paragraph, one acceptance bench per task against an independent `model.py`, at least three mutants
per task that the bench must kill. `check_task.py` and `run_task.py` are the v1 tools, entered through [tools/](tools/) (see below).

## What is different

- **Register window on blocks.** The course projects are mostly stand-alone blocks with valid/ready or start/done ports. The task asks for the block behind the test shell: operands
  are written to registers, a "go"/"burst" command presents them for one clock (or on consecutive clocks), results are read back. The register map is in `hidden/spec.yaml`
  (the interview oracle answers from it). What the shell cannot see is stated in each `spec.yaml` and in the report: a latency of a few clocks is observed only where the task
  adds a measuring register (the matrix multiplier, the Montgomery multiplier, the NTT, the top-8 tracker).
- **`no_shell: true`** (bench.yaml) for tasks whose subject is the USB-UART itself (the AES, SHA-256 and vector-search servers and the tiny-CNN board): they are compiled without
  the shell, because a design with its own `uart_rx`/`uart_tx` would clash with the shell's modules. [tools/no_shell.py](tools/no_shell.py) does this for the course tier only.
- **`data/`** (optional): files the user hands over together with `spec.md` (weights, databases, pictures); the agent may see them. Everything else stays under `hidden/`.
- **Package files first.** The harness compiles sources in file-name order, so a SystemVerilog package must sort before its users (a reference file is named `_*_pkg.sv`). An agent
  design that names its package file otherwise fails to build.
- **Re-scoped tasks (course v1.1).** `c13_nexys_blob_tracker` and `c13_nexys_harris_vga` keep the course project ids, but the task is only what the course reference implements: a block behind the shell that is fed a picture
  (a 40 x 30 bit picture and the biggest-object report; an 80 x 60 grey picture and the corner list), with no VGA output, overlay, seven-segment display or switches. Each `hidden/spec.yaml` has a `scope:` section that
  says what was dropped and what glue was added; the course project specs were re-scoped the same way.
- **`hidden/reference_qor.md`**: the course's recorded numbers for the reference, marked "OOC" (out of context, 200 MHz target), "placed only" or "not run". Difficulty 3 tasks keep
  the course's OOC numbers only.

## Tools

| Tool | What |
|---|---|
| `tools/run_task.py <task> [--rtl DIR]` | v1 `run_task.py` with `no_shell` support; scoring uses exactly this |
| `tools/check_task.py <task>` | v1 `check_task.py` with `no_shell`; writes `results/<id>__icarus.json` here |
| `tools/freeze.py make\|verify` | the course manifest (see [FROZEN.md](FROZEN.md)) |
| `tools/bank_grep.py` | the knowledge bank must not contain any course task's distinctive phrases (public and, when present, private tasks) |
| `../tools/split.py` | the seeded draw (seed 20261106, per course part, `round(n/3)` held out) |

## Tasks

Development tasks in this repository; held-out tasks live in the private repository and are listed by id and digest only ([split.yaml](split.yaml), [MANIFEST.json](MANIFEST.json)).
All 19 split ids have a task since course v1.1 (the two Part 13 held-out tasks and the two re-scoped development tasks were added on 2026-11-06, see [FROZEN.md](FROZEN.md)).

| Part | Development tasks |
|---|---|
| 13 | `c13_hough_lines`, `c13_nexys_blob_tracker`, `c13_nexys_harris_vga` |
| 14 | `c14_int8_dot_requant`, `c14_nexys_tiny_cnn`, `c14_systolic_matmul` |
| 15 | `c15_pq_search`, `c15_rmsnorm_unit`, `c15_softmax_unit` |
| 16 | `c16_montgomery_mult`, `c16_nexys_aes_uart`, `c16_ntt_engine` |

Reference check results (reference passes, every mutant killed) are in [results/](results/); the reference Vivado builds are in [results/REFERENCE_BUILDS.md](results/REFERENCE_BUILDS.md).
