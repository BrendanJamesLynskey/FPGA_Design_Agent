# Board self-checks (brief 04c)

Each design was built with `flow/run_vivado.sh` and run 3 times with `python3 flow/board_check.py designs/<name> --runs 3` (power gate, discover, program SRAM by cable serial, identify, self-check, still alive). The pass rules are in each design's `selfcheck.py` docstring, written before any board run. `<name>.json` holds the final invocation's 3 runs, from a clean committed tree. `runs/` holds all 30 runs, every one PASS: 12 from the uncommitted tree on `ac271b0` (the first runs; the per-rail limits were added to the gate after the temperature, accelerometer and flash runs), 6 on `95dcbe8` with an uncommitted documentation edit (flash, microphone), and the 12 clean final runs. The build stamps (a hash of the RTL and XDC) are the same in all of them.

| Design | Runs | Commit | Build stamp | Power gate (source, total, Tj) | Result |
|---|---|---|---|---|---|
| [b2_tmp_adt7420](../../designs/b2_tmp_adt7420) | 3/3 PASS | 95dcbe8 | `a576bb81` | wall, 0.116 W, 42.1 C | ID 0xCB; 18.88 C, 18.88 C, 18.81 C |
| [b2_acl_adxl362](../../designs/b2_acl_adxl362) | 3/3 PASS | 95dcbe8 | `026c264a` | wall, 0.116 W, 42.1 C | IDs ad 1d f2, REVID 0x02; magnitude 1.018 g, 1.0156 g, 1.0181 g; X/Y/Z [992, 17, -228]; [988, 22, -234]; [991, 24, -232] mg |
| [b2_qspi_jedec](../../designs/b2_qspi_jedec) | 3/3 PASS | a2e31a0 | `48ff26c6` | wall, 0.117 W, 42.1 C | RDID 01 20 18 4d 01 80 30 30 (model "00") |
| [b2_mic_pdm](../../designs/b2_mic_pdm) | 3/3 PASS | a2e31a0 | `2c661a6c` | wall, 0.117 W, 42.1 C | ones 0.5157-0.5167, changes 0.7377-0.7391 over 9 windows of 1,048,576 bits |

Times per run (s): b2_tmp_adt7420: 40.4, 37.5, 34.3; b2_acl_adxl362: 35.2, 35.1, 35.2; b2_qspi_jedec: 34.9, 34.6, 34.7; b2_mic_pdm: 36.3, 36.3, 42.5

The cable serial appears only as its last 4 characters; no `/dev` path is written.

## Records

- `b2_*.json` (the four designs in the table): the final invocation's 3 board runs of that design, with the steps, the power gate and the self-check measurements.
- `t1_*.json`, `t2_*.json` (sixteen development-task reference designs built under `build/bench/`, from the brief 06a benchmark bring-up): one passing board run each, in the same format.
- `runs/`: all 30 runs, written by the same command. It is git-ignored (private runs) and is not in the repository; only the final-invocation JSON files are committed.

## Reproduce

Needs the Nexys A7-100T, the board lock and the design's Vivado build (`flow/run_vivado.sh designs/<name>` under a heavy slot):
`python3 flow/board_check.py designs/<name> --runs 3` (the `t1_*`/`t2_*` records name `build/bench/<id>` designs). The records cannot be regenerated without the board.

## Known gaps and limits

- The table above covers only the four `b2_*` designs; the sixteen `t1_*` and `t2_*` records are a single run each, and their pass rules live in each task's own checks, not in this README.
- SRAM programming only, over JTAG; no flash was written.
- The bitstreams of the earlier runs were built with an earlier Vivado release; the build stamp is the same in every run of a design.
- Each design's pass rule is its `selfcheck.py` docstring, written before the board runs; the checks are known-answer checks of one sensor or interface, not a sweep of conditions.
- 12 of the 30 runs came from an uncommitted tree and 6 had an uncommitted documentation edit (see above); those runs are not committed.
