| variant | change | sim clocks (tick-to-trade) | ns | WNS / WHS ns | LUT / FF | power W | worst stage slack |
|---|---|---|---|---|---|---|---|
| agent_cdc | u_p_go REG_OUTPUT 1->0 | 10 | 62.1 | 0.298 / 0.01 (met) | 5927 / 13659 | 1.045 | rx_descramble 0.855 |
| hand_ref | REG_OUTPUT 1->0; order-only early MAC start | 9 | 55.9 | 0.078 / 0.01 (met) | 6004 / 13660 | 1.048 | tx_encode 0.19 |
| agent_both | REG_OUTPUT 1->0; trade64.fire combinational | 9 | 55.9 | 0.117 / 0.01 (met) | 5966 / 13658 | 1.068 | mac_preamble 0.503 |
| all3 | all three (the early start was found by both A0 runs in round 2) | 8 | 49.6 | 0.15 / 0.01 (met) | 5978 / 13658 | 1.046 | tx_encode 0.563 |

| stage (clocks, ns at 6.2058) | baseline | agent_cdc | hand_ref | agent_both | all3 |
|---|---|---|---|---|---|
| rx_blk | 0 (0.0) | 0 (0.0) | 0 (0.0) | 0 (0.0) | 0 (0.0) |
| rx_descramble | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) |
| rx_mac | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) |
| decide | 1 (6.2) | 1 (6.2) | 1 (6.2) | 0 (0.0) | 0 (0.0) |
| cross_go | 4 (24.8) | 3 (18.6) | 3 (18.6) | 3 (18.6) | 3 (18.6) |
| fs_start | 1 (6.2) | 1 (6.2) | 0 (0.0) | 1 (6.2) | 0 (0.0) |
| mac_preamble | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) |
| tx_encode | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) |
| tx_spill | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) | 1 (6.2) |
| total | 11 (68.3) | 10 (62.1) | 9 (55.9) | 9 (55.9) | 8 (49.6) |
