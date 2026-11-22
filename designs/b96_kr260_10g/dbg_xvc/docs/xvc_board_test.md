# Build dbg_xvc: the pre-registered board test (brief 131; written before any board time, not run)

No commands here (owner rule); `dbg_xvc/board/xvc_board_session.sh` runs it, `dbg_xvc/model/xvc_verdict.py` judges it, and `tests/test_b131_xvc.py` checks that the judge fails on each broken criterion.
Rules: SRAM only (the PL is loaded through Linux), reads and captures only, never flash or eFUSE, laser off throughout (the default after load; the test never writes a register), board lock text starts `131:`.

**Question.** Can Vivado reach an ILA in the PL over the network while the board's Linux keeps running, with the JTAG cable not in use?

**Not claimed.** That JTAG access disturbs Linux on this board: the article this build follows (Adam Taylor, Hackster, https://www.hackster.io/adam-taylor/debugging-hw-ilas-with-petalinux-over-ethernet-be6218) makes that argument and the run plan notes a Linux check after a JTAG load, but this test does not
run a JTAG comparison. It measures whether the network path works and whether Linux stays healthy while it does.

| # | Criterion (all must hold) | Source of the number |
|---|---|---|
| T0 | The JTAG cable is not connected to the board during the test | the operator's set-up, recorded; nothing measures it |
| T1 | The board's 1 Hz heartbeat has no gap longer than 3.0 s over the whole test, and no new kernel-log line matches error, fail, timeout, unhandled, serror, oops or bug | heartbeat file and `dmesg` from the board |
| T2 | Vivado connects over XVC and finds exactly 1 ILA with a 38-bit probe within 60 s of the connection command | the Vivado record |
| T3 | A trigger on `pcs_lock = 1` stays armed for 30 s (no light, so no block lock), then 20 immediate-trigger captures each upload 1024 samples | the Vivado record |
| T4 | In the captured samples `rx_los` = 1, `mod_abs` = 0, `tx_fault` = 0, `pgood` = 1 (the values the 2026-11-17 run measured with the laser off, results/b96/hw/20261117_101326/stage3.json; `pgood` is 1 whenever the GT has power) | the first capture's CSV |

**Verdict.** PASS only if every row holds; a missing record entry is a FAIL. Any FAIL is reported with its reason and nothing is retuned; a failure of T2 stops the session before T3.

**Left out on purpose and why.** Link-up capture (trigger on the rising edge of `pcs_lock` with the laser on) needs the laser enabled, which is a register write over the JTAG register bus; that bus is not reachable over this path (docs/dbg_xvc.md, item 5).
It can be added as a second test once the planner approves a write over JTAG, with the cable in use for that one write only.

**Expected duration.** About 10 minutes once the overlay is loaded (the capture loop is short; the 30 s held trigger is the longest single wait).
