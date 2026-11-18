# results/b97c: order sequence resync and order-content check (brief 97C)

This folder holds the simulation logs, the rebuild queue and the board results of brief 97C, which fixes the order-sequence resync after a link restart and adds an order-content check to `designs/b96_kr260_10g` and its variants `lat_agent_both` and `lat_all3`.

## Records
- `sim_before.log`, `core_sim_before.json`, `pytest_before.txt`: the core cocotb bench (15 tests, the 97C tests added) on the RTL of main 3db08151. 7 pass, 8 fail: every sequence scenario except an RX-only restart shows all orders stale, late and poisoned.
- `sim_control.log`, `sim_agent_both.log`, `sim_all3.log` (and `core_sim_*.json`, `pytest_*.txt`): the same bench on the fixed base and the two variants; all 15 pass.
- `run_sims.sh`: how each was run (Icarus, simulation only).
- `builds/<name>/`: digest.json (timing, utilisation, power, gates), run.json, wall time of the rebuilds of control, agent_both and all3 (the `.bit` files are local and git-ignored, in `designs/b96_kr260_10g/build/base` and `lat_*/build/base` of the worktree `_worktrees/97c-seq`).
- `build_one.sh`, `queue.sh`: the heavy-slot Vivado jobs.

## Measured
Cause (simulation, before): CMD bit 0 zeroed the receive side's order number but not the transmit side's go count; a TX-datapath or whole-GT reset zeroed the go count but not the order number. An RX-datapath restart alone was clean. After: every scenario clean (counter clear, RX, TX and whole-GT restarts, the bench's restart-then-clear sequence, a clear in the middle of a stream of orders at seven offsets), a forced offset poisons exactly one order and then heals, a wrong-quantity order with a good FCS is counted `order_bad`. Tick-to-trade in simulation is unchanged: 11, 9 and 8 clocks (control, agent_both, all3).

## Reproduce
`results/b97c/run_sims.sh before|control|agent_both|all3` (about 8 minutes each); `python3 -m pytest designs/b96_kr260_10g/tests`.

## Known gaps and limits
No board result: the board run is the owner's (`_handoff/fpga_agent/run_97c_stage3.sh`). The content check covers the order's fields, length and FCS, not the MAC, IP and UDP header bytes beyond classification, and holds one order in flight. The re-synchronisation is verified in simulation with both user clocks equal; on the board the two restart pulses can differ by a few clocks (the self-heal covers that case).

## Board run, 2026-11-18 19:42 (`hw/20261118_194221/`)

The owner ran `_handoff/fpga_agent/run_97c_stage3.sh` on the KR260 (10G-LR module in J24, 0.17 m OS2 loopback lead), 100 link restarts per variant, 5 orders per restart. `program.json` holds the programming record (build ID read back over JTAG, XADC supplies inside the DS925 limits); `stage3.json` holds the per-restart counters and the safety verdict.

| Variant | safety_ok | Orders sent / fired / order_ok | order_bad, stale, late, poisoned, bad | E min (median, range) | L min (median, range) | L−E | Tick-to-trade ≈ (L−E)×6.206 − 0.83 ns |
|---|---|---|---|---|---|---|---|
| control | true | 500 / 500 / 500 | all 0 | 20 (19–21) | 50 (48–51) | 30 | ≈185 ns |
| agent_both | true | 500 / 500 / 500 | all 0 | 20 (19–21) | 48 (47–49) | 28 | ≈173 ns |
| all3 | true | 500 / 500 / 500 | all 0 | 20 (19–20) | 46 (45–47) | 26 | ≈161 ns |

Every restart locked. The 97 predictions were L 50, 48 and 47; all3 came in one clock better than predicted. With the sequence fix, every order of every restart is clean and its content checked in hardware, so agent_both and all3 are accepted.
