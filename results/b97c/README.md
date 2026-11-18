# results/b97c: order sequence resync and order-content check (brief 97C)

Records of brief 97C on `designs/b96_kr260_10g` and its variants `lat_agent_both` and `lat_all3`.

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
