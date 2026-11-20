# `agent/tests/fixtures/run4_c14`: the three local failures (brief 102F)

`agent/tests/fixtures/run4_c14/tests/test_c14_int8_dot_requant_rtl.py` (seeds 1, 2, 3) is a model-written design from run 4 (2026-11-07) kept as a
fixture for `test_07a2_fix4.py`. CI does not run it (the main job has `--ignore-glob='*_rtl.py'` and no cocotb job lists it), and a plain
`python3 -m pytest agent/tests` on a box without the cocotb extras collects it. 82P4 saw three failures there. On main at ddc62aa5 (2026-11-20):

| Run | Result | Cause |
|---|---|---|
| as found, `cocotb 2.0.1`, no `cocotb_coverage` | 3 failed in 1.6 s | `ModuleNotFoundError: No module named 'cocotb_coverage'` (the bench imports it; CI's cocotb jobs install it; the cocotb 2.0.1 regression manager then aborts with `no attribute '_running_test'`, which hides the cause) |
| a stand-in `cocotb_coverage` module (empty cover points) on `PYTHONPATH`, bench unchanged | 3 failed in 358 s, each seed `TESTS=12 PASS=10 FAIL=2` | **real, and not the design's fault**: `test_smoke` reads register 0x01 and expects `0x00010000`, the shell now returns `0x00010001`; `test_shell_protocol` writes register 0x05 and expects status 3 (unmapped), the shell now returns 4 (read-only). Both are the shell protocol 1.1 change of 2026-11-12 (commit 8e971392: version word `0x00010001`, read-only BUILD_ID at 0x05); the fixture was written on 2026-11-07 against 1.0 |
| the same, bench expectations updated to 1.1 (two lines in `tests/c14_bench.py`) | 3 passed in 431 s | |

Changes: the two assertions in the fixture's bench now state the 1.1 values with the reason in a comment, and the fixture's pytest entry skips with a
message when `cocotb_coverage` is missing (instead of the misleading cocotb abort). Nothing in the agent or the flow was wrong. The stand-in
`cocotb_coverage` was a six-line module outside the repo (the real package could not be installed here: package installs were refused by the
permission system); it replaces `CoverPoint` with a pass-through and `coverage_db.export_to_yaml` with a no-op, so coverage was not measured. Run
with the real package for a full check; CI does not run this fixture.
