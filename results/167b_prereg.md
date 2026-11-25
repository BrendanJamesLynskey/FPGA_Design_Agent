# Brief 167b pre-registration (amendment to results/167_vhdl_rerun/prereg.md), written 2026-11-22 19:55:00, before any 167b run

Why: brief 167's 5 of 6 runs ended at stage 1 on a VHDL `build.yaml` glob matching no file (agent/core/tools.py `load_build_cfg`).
Fix (this branch): `rtl_pending`: a `sources` glob over the design's own `rtl/` with an HDL suffix is accepted while the session stage is clarify or
board-and-device-planning; from rtl-design-creation on it is refused as before. SystemVerilog shares the path and gets the same treatment.
Test: agent/tests/test_167b_stage1_build_yaml.py (7 passed).

Repeat of 167, otherwise unchanged (same tasks t1_gray_stepper and t1_sync_fifo_regs, Haiku 5.5, Claude Code 2.1.321 pinned, 90 min cap, one run at a time
under a "167:" heavy slot, scoring under its own light lock, same measures and decision rules as prereg.md):
- Arm A = 33896b29 plus the stage-1 fix only (cherry-pick of the `agent/core/tools.py` change).
- Arm B = origin/b153-vhdl-parity plus the stage-1 fix (this branch).
- Alternate arms; as many complete runs per arm as usage allows (aim 2 or more per arm); stop at 99% weekly usage.
