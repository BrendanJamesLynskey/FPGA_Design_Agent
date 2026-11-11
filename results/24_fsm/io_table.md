# Controller on pins: routed (Vivado 2025.2, xc7a100tcsg324-1, 10 ns clock, output delay 4 ns max / -1 min)

| variant | IOB property | output drivers | in an OLOGIC flop | clock-to-pad data path (ns, min..max) | levels | worst setup slack | worst hold slack |
|---|---|---|---|---|---|---|---|
| io_in1 | unset | FDRE, FDSE | 0 of 8 | 5.51..6.45 | 1 | -5.815 | 0.237 |
| io_in1_iob | TRUE | FDRE, FDSE | 8 of 8 | 3.99..4.03 | 1 | -3.392 | 0.185 |
| io_out0 | unset | LUT3, LUT4, LUT5 | 0 of 8 | 6.71..7.50 | 2 | -6.854 | 0.241 |
| io_out0_iob | TRUE | LUT3, LUT4, LUT5 | 0 of 8 | 6.71..7.50 | 2 | -6.854 | 0.241 |
| io_out1 | unset | FDRE, FDSE | 0 of 8 | 5.51..6.20 | 1 | -5.550 | 0.111 |
| io_out1_iob | TRUE | FDRE, FDSE | 8 of 8 | 3.99..4.03 | 1 | -3.392 | 0.225 |
| io_out2 | unset | FDRE, FDSE | 0 of 8 | 5.51..5.54 | 1 | -4.899 | 0.186 |
| io_out2_iob | TRUE | FDRE, FDSE | 8 of 8 | 3.99..4.03 | 1 | -3.392 | 0.077 |

## Input pins: first cell of each path and routed delay (ns)

| variant | cmd_valid | gnt | ack | nack | rsp_ready |
|---|---|---|---|---|---|
| io_in1 | g_one.q_reg: 2.728 | g_one.q_reg: 2.634 | g_one.q_reg: 7.274 | g_one.q_reg: 2.443 | g_one.q_reg: 2.46 |
| io_in1_iob | g_one.q_reg: 8.795 | g_one.q_reg: 8.797 | g_one.q_reg: 8.802 | g_one.q_reg: 8.794 | g_one.q_reg: 8.81 |
| io_out0 | cmd_ack: 8.17 | FSM_sequential_g_st_sync.st_reg[2]: 6.65 | cnt_reg[0]: 6.814 | cnt_reg[0]: 6.832 | cnt_reg[0]: 6.46 |
| io_out0_iob | cmd_ack: 8.17 | FSM_sequential_g_st_sync.st_reg[2]: 6.65 | cnt_reg[0]: 6.814 | cnt_reg[0]: 6.832 | cnt_reg[0]: 6.46 |
| io_out1 | FSM_sequential_g_st_sync.st_reg[3]: 6.623 | FSM_sequential_g_st_sync.st_reg[3]: 5.996 | FSM_sequential_g_st_sync.st_reg[0]: 6.754 | FSM_sequential_g_st_sync.st_reg[1]: 6.965 | cnt_reg[0]: 7.056 |
| io_out1_iob | g_sync.q_reg[0]: 6.255 | FSM_sequential_g_st_sync.st_reg[1]: 7.044 | FSM_sequential_g_st_sync.st_reg[1]: 6.729 | FSM_sequential_g_st_sync.st_reg[1]: 7.339 | FSM_sequential_g_st_sync.st_reg[1]: 6.412 |
| io_out2 | FSM_onehot_g_st_sync.st_reg[2]: 7.726 | FSM_onehot_g_st_sync.st_reg[7]: 7.916 | FSM_onehot_g_st_sync.st_reg[2]: 7.768 | FSM_onehot_g_st_sync.st_reg[2]: 8.104 | FSM_onehot_g_st_sync.st_reg[1]: 7.18 |
| io_out2_iob | g_sync.q_reg[6]: 7.19 | FSM_onehot_g_st_sync.st_reg[7]: 7.755 | g_sync.q_reg[1]: 8.727 | g_sync.q_reg[1]: 7.805 | FSM_onehot_g_st_sync.st_reg[6]: 7.578 |
