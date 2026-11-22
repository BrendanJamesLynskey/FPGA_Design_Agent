# Brief 127 board test: pre-registered re-run after run B (brief 172)

Written 2026-11-22 before any re-run, from the records of run B (`hw/20261122_150408/rm_gp_itch/stage1.json`) and the RTL. No board command was run for this brief.

## Why run B's `rate` stage failed (cause found, harness side)

Run B: smoke, counters, latency (both arms) and risk passed; `rate` failed with "frames played 4634 of 1900", `itch.evdrop` 0, `itch.dup` 1881. The reasons list had no `us.fwd` entry, so the receiver forwarded exactly 1900 frames in the stage (the check
`us.fwd == 1900` held), and `itch.dup` 1881 = 99 x 19 is what the Mold layer counts for 100 passes of the same 19 packets: the receive side saw 1900.

`rp.frames` is the replay player's frame counter. In `rtl/tx_mux.sv` it is cleared only by `rst` (`rp_frames <= '0` in the reset branch), never by CLR_CNT, so it counts every frame played since the build was loaded. The stages before `rate` had played
69 (smoke) + 165 (counters) + 2 x 125 passes x 10 frames (latency, two arms) = 2734 frames; 2734 + 1900 = 4634, exactly the number the stage read. The stage compared that absolute counter with its own 1900. Every other counter the stage reads
(`us.fwd`, `us.bad_fcs`, `us.cut`, `us.orphan`, `itch.evdrop`, `itch.pkt_err`) is cleared by the stage's configure step (CLR_CNT), which is why only this check failed.
The dry run had missed it because each stage was simulated on its own from reset, where the counter is 0. So the player did send exactly 1900 frames in its own stage and the receive side is right: **the fault was in the harness, not the RTL; no RTL change, no
rebuild, same stamp `1d8ac802`.**

## The fix (host/b127_stages.py)

`rp_baseline` reads `rp.frames` after the configure step and before the replay starts; the stages that check "frames played" (smoke and rate) compare the rise over their own replay (`frames_played`) with the number they sent. **The pass criterion is unchanged:**
"every frame sent and forwarded (`rp.frames` = `us.fwd` = 1900)" is read, as it always meant, over the stage's own replay. The rate stage's numbers now also record `rp_frames_before` and `rp_frames_after`.
Tests: `tests/test_b127_stages_order.py` (no simulator: a stand-in register file with the cumulative counter; fails on the old stage, passes on the new) and `test_full_session_in_board_order` in `tests/test_b127_stages_sim.py` (the five stages in the board's
order on one continuous simulation from reset).

## The re-run

Same build (`rm_gp_itch`, stamp `1d8ac802`, already in the 127 worktree's `build/base`), same set-up and hardware rules as run B. Commands: given by the planner at the board, not here. The script is unchanged in default behaviour; two optional variables were added: `STAGES=` and `DRIVER_ROOT=`.

| Run | What | Stages | Pass/fail (written now) |
|---|---|---|---|
| **R1** (primary) | the whole session in the board's order, the driver from the b172 tree (`DRIVER_ROOT`) | smoke, counters, latency (off, on), rate, risk | all six stage entries pass with the same criteria as run B (board_test_plan.md section 2). **Predictions:** `rate.numbers.rp_frames_before` = 2734, `rp_frames_after` = 4634, `frames` = 1900, `evdrop` 0, `dup` 1881; latency bins inside {10, 11} and {5, 6} again (same build, so a different bin is a finding, not noise) |
| **R2** (optional, about 5 minutes) | rate alone on a freshly programmed and reset board (`STAGES=rate`) | rate | passes; `rp_frames_before` = 0 (run B's smoke read 69 after 69 frames from a fresh reset, so reset clears the counter), `rp_frames_after` = 1900. R2 shows the stage on its own; R1 is the run that shows the stage in the order that failed |

**Stopping rules and nulls:** as in `preregistration.md`. A failure of `rate` in R1 or R2 for a reason other than the frame count (any of `us.fwd`, `us.bad_fcs`, `us.cut`, `us.orphan`, `itch.evdrop`, `itch.pkt_err`) is a finding about the design and is reported as such; nothing is retuned.
A rise of `rp.frames` different from 1900 with `us.fwd` = 1900 would mean the counter, not the harness, is wrong (it would then be an RTL question for a new brief). A result outside the recommended operating conditions voids the run. Run B's records stay as found:
5 of 6 stage entries passed, `rate` failed (`hw/README.md`).
