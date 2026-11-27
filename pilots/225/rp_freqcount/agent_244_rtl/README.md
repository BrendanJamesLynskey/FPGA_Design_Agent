# rp_freqcount, brief 244 timing repair

`rp_freqcount.sv` here is `agent_235_r2_rtl/rp_freqcount.sv` with the end-of-gate update split over two clocks, so that the span subtraction and the edge-count comparison no longer sit behind the edge detector and the counters in one clock. `schmitt_edge.sv` is unchanged (same bytes). Register map, reset values, gate length, edge counting and every register value are unchanged.

## What changes for a user (the one-clock latency)

At the end of a gate the old block wrote EDGES, GATE_ACTUAL, SPAN, FEW_EDGES, MEAS_DONE, DONE and the final BUSY in one clock. This block captures the gate's results in that clock and writes all of them together in the next one. So:

- EDGES, GATE_ACTUAL, SPAN, STATUS.FEW_EDGES, STATUS.DONE, MEAS_DONE and the falling of STATUS.BUSY appear **one adc_clk (8 ns at 125 MHz) later** than in `agent_235_r2_rtl`, all in the same clock. A reader that sees DONE (or a new MEAS_DONE) always reads the SPAN of that same gate.
- STATUS.BUSY stays 1 for that extra clock when CONT was 0 at the end of the gate. A START written in that clock is ignored (the old block accepted it). With CONT set nothing else differs: the next gate starts in the same clock as before and counts the same edges.
- The gate length is unchanged: GATE_ACTUAL equals the GATE_LEN in force when the gate started; the extra clock is in the publishing of the result, not in the gate.
- Bus timing is unchanged: ack one clock after wen or ren.

## Tests

- `../crosscheck_tb.sv` (brief 225's independent cross-check): `XCHECK PASS`.
- `diff_tb.sv`: this block against `agent_235_r2_rtl` in lock-step on the same bus and input, 29,831 clocks and 19 gates (START gates at 61 kHz to 20 MHz, FEW_EDGES boundary, a CONT run, CONT cleared mid-gate, a flat input, thresholds in the wrong order): every result register equals the old block's one clock earlier. `hil/tests/test_244_redpitaya_freqcount.py` runs both and three mutants of the new block (each must make the lock-step fail).
