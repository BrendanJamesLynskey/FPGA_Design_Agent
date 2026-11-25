# results/b127/hw: board runs of build `rm_gp_itch` (brief 127)

Records as the owner's run left them, not edited (copied unchanged from the 127 worktree). Operating conditions inside ROC at start and end (`roc_ok: true`).

## 20261122_150408/rm_gp_itch: run B, 2026-11-22 15:04, build stamp `1d8ac802`, fibre loop 0.17 m

Files: `stage1.json` (the session record), `session.json` (the driver's summary), `program.json` (the SRAM programming step), `git_heads.txt` (the tree and main it ran from). The driver's log is `_handoff/fpga_agent/board_127_runB.log` (not in this repository).

Result as found: **5 of the 6 stage entries passed; `rate` failed; `all_pass` false.**

| Stage | Result | Numbers |
|---|---|---|
| smoke | PASS | 69 packets, 7 orders, all 7 captured frames equal the model's |
| counters | PASS | 153 packets, 165 frames played, 12 orders |
| latency, speculation off (at verdict) | PASS | 1000 orders, 10 clocks 956, 11 clocks 44 (predicted 10 to 11) |
| latency, speculation on | PASS | 1000 orders, 5 clocks 996, 6 clocks 4 (predicted 5 to 6) |
| **rate** | **FAIL** | "frames played 4634 of 1900"; `evdrop` 0, `dup` 1881; no other reason listed |
| risk | PASS | 4 orders before the kill, 0 with it, 1 with the position limit |

## Why `rate` failed (brief 172)

Not the design. `rp.frames` is cleared only by reset; the stage compared the absolute counter, 2734 frames of the three earlier stages plus its own 1900 = 4634, with 1900. The receiver's `us.fwd` check (also 1900) did not fail. Details, the fix and
the pre-registered re-run: [../preregistration_rerun_172.md](../preregistration_rerun_172.md). This record is not re-labelled: the verdict above is the harness's verdict at the time; a new run goes in its own directory beside it.
