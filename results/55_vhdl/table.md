| Task | Area | Arm A | Arm B | Vivado 2026.1, SystemVerilog reference | Vivado 2026.1, VHDL |
|---|---|---|---|---|---|
| `t1_gray_stepper` | T1 | FAIL (does not build) | PASS 9/9 | pass; 448 LUT / 386 FF; WNS +3.544 ns | pass; 442 LUT / 386 FF; WNS +3.191 ns |
| `t1_elevator_fsm` | FSM | FAIL (does not build) | PASS 9/9 | pass; 393 LUT / 343 FF; WNS +3.768 ns | pass; 379 LUT / 343 FF; WNS +3.893 ns |
| `d24_registered_outputs` | FSM drill (registered outputs) | FAIL (does not build) | PASS 3/3 | pass; 387 LUT / 312 FF; WNS +4.268 ns | pass; 380 LUT / 312 FF; WNS +4.018 ns |
| `t1_sync_fifo_regs` | memory (FIFO) | FAIL (does not build) | PASS 9/9 | pass; 379 LUT / 294 FF; WNS +3.953 ns | pass; 372 LUT / 294 FF; WNS +4.117 ns |
| `t1_debounce_bank` | T1, asynchronous inputs | FAIL (does not build) | PASS 9/9 | pass; 678 LUT / 872 FF; WNS +4.131 ns | pass; 682 LUT / 872 FF; WNS +2.931 ns |
| `cdcfx_c10` | CDC (async FIFO), block | PASS | not run | 34 LUT / 56 FF; WNS -0.81; CDC gate pass | 34 LUT / 56 FF; WNS -0.81; CDC gate pass |
| `cdcfx_c8` | CDC (handshake), block | FAIL | FAIL | 4 LUT / 40 FF; WNS -0.101; CDC gate pass | 4 LUT / 40 FF; WNS -0.101; CDC gate pass |
| `axil_regs` | AXI4-Lite slave, block | PASS | not run | 57 LUT / 174 FF; WNS 1.012 | 85 LUT / 174 FF; WNS 1.012 |
