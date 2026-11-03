# Benchmark v1: frozen 2026-11-03

Written by brief 06a before any agent tuning on these tasks, by a session that did not read the agent's prompts or
run records. Nothing in `benchmark/tasks`, `benchmark/pool`, `benchmark/lib` or the scoring tools may change after
this point without a new version and a new freeze; a change found necessary is recorded in the scoring report.

| What | Value |
|---|---|
| Tasks | 24: T1 12, T2 12. Held out 8 (T1: breathe_rgb, combo_lock, reaction_timer, stopwatch_lap; T2: adxl362_fifo, ascii_console, uart_regs, vga_800x600), development 16 |
| Split | `split.yaml`, seed 20261103, `random.Random(seed).sample(sorted(ids), round(n/3))` per tier; SHA-256 `1cf56ebdef900f5397f132ec3c7f9ea173a146b0cda6b3b0cc0eb1af01f68bcc` |
| Manifest | `MANIFEST.json` (86 units: 24 tasks, 40 pool specs, 18 probe tasks, 4 shared bench units; per unit the SHA-256 of its sorted `sha256  path` lines; held-out and probe units by digest only) |
| Private manifest | `benchmark_private/MANIFEST_full.json` in the private repository (every file of every unit) |
| Tools | Python 3.12.3, cocotb 2.0.1, Icarus 12.0, Verilator 5.048, Vivado 2025.2, PyYAML 6.0.1 |

## How to verify

```bash
python3 benchmark/tools/freeze.py verify                              # public units, from a fresh clone
python3 benchmark/tools/freeze.py verify --private <private>/benchmark_private   # every unit
python3 benchmark/tools/split.py show benchmark/split.yaml
```

`benchmark/tests/test_bench_static.py` (CI) re-runs the draw from the recorded seed and verifies the manifest.

## Rules from here

- Held-out tasks are never used while tuning the agent; scoring of the held-out set waits for the owner's sign-off
  in [OWNER_REVIEW.md](OWNER_REVIEW.md) (none signed at freeze).
- A held-out `spec.md` is published here only after scoring.
- The knowledge bank must stay free of every spec's distinctive phrases (`tools/bank_grep.py`; 0 hits at freeze).

## v1.1 (2026-11-03, after the first board run)

Two units changed after the 22/24 bring-up of the references; nothing else did. Each change is a bench or self-check
fix, recorded here and in [OWNER_REVIEW.md](OWNER_REVIEW.md):

- `t2_vga_sprite`: the self-check's bounce rule brackets the frame count (the v1 window was too narrow, a board
  measurement error), and `hidden/acceptance.py` gains three directed tests for the four recorded survivors.
- One held-out task: its on-board self-check changed (the board flow's identify step; detail in the private repository). Public: digest only.

Also in v1.1: `flow/board_check.py` reads a self-check module's `NO_SHELL` flag. Re-frozen: `MANIFEST.json` (the two
unit digests and the shared-unit digests only).
