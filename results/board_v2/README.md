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
