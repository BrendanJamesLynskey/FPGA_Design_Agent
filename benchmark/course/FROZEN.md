# Benchmark course tier: frozen 2026-11-06

Written by brief 07a1 before any agent run on these tasks. The tier ports the course projects of Parts 13-16 to the benchmark v1 layout; v1 itself (`benchmark/tasks`, `pool`, `lib`, the scoring tools) is unchanged.
Nothing in `benchmark/course/tasks`, `benchmark/lib` or the scoring tools may change after this point without a new version and a new freeze; a change found necessary is recorded here.

| What | Value |
|---|---|
| Split | `split.yaml`, seed 20261106, `random.Random(seed).sample(sorted(ids), round(n/3))` per course part (tier C13..C16), 19 ids; SHA-256 `9d4262ae11cdc67a11a78e227f0606cddb793dbf182b23305a1fbf41951a96f7`. Drawn and committed before any agent run (and before the tasks were checked). Held out 7 of 19 (C13 2, C14 1, C15 2, C16 2), development 12 |
| Tasks built | 15: development 10 (in this repository), held out 5 (private repository, by digest here). Four split ids have no task yet: [PENDING.yaml](PENDING.yaml) |
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
