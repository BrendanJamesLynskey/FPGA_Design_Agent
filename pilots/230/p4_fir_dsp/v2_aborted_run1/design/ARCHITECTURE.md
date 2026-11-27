# fir32_sym architecture

32-tap symmetric FIR (16 DSP48E2 after pre-add), 1024-deep input and output FIFOs, JTAG register access (jtag_bus, USER4). Part xck26 (KR260).

## Block diagram

```text
 clk25 domain (25 MHz)                          clk_dp domain (250 MHz)
 +---------+  h_*  +--------------+  cmd pulses  +-----------------+
 | jtag_bus|<----->| fir_core regs|--xpm_cdc_pulse-->| run/clear FSM |
 +---------+       | ID BUILD SCR |                 |               |
   BSCANE2         | CTRL STATUS..|<--xpm_cdc_array_single/gray--| counts,busy,|
                   +------+-------+                 | sat, done     |
                          | push/pop                +--------+------+
              +-----------v-----------+  xpm_fifo_async   |
              | input FIFO 1024x16    |------------------>| 16-tap pre-add + 16 DSP
              | output FIFO 1024x16   |<------------------| round, >>>15, saturate
              +-----------------------+                   +-----------------
 clk25 -> MMCM (x40 /4) -> clk_dp ; locked -> led[1]; busy -> led[0]
 sfp_tx_disable = 1 constant
 reset: jtag_bus rst (clk25) ; datapath reset via xpm_cdc_async_rst on clk_dp, held until MMCM locked
```

Top (`fir_top`) only instantiates jtag_bus, reset generation, MMCM and `fir_core`. Reset model: reprogram (registers have initial values); the internal reset from jtag_bus is active high.

## Clock plan
- clk25: 25 MHz pin C3, MMCM input and register bus clock.
- clk_dp: MMCM, VCO 1000 MHz (x40), /4 = 250 MHz, datapath and FIFO datapath side. Timing target WNS >= 0.

## Crossings
- RUN/CLEAR command pulses clk25 -> clk_dp: xpm_cdc_pulse.
- busy, counts, SAT_COUNT, SAMPLES_DONE clk_dp -> clk25: xpm_cdc_gray / xpm_cdc_array_single (counts held stable by handshake-free sampling of gray codes).
- FIFOs: xpm_fifo_async (push/pop on clk25 side for input push and output pop; datapath side clk_dp).
- MMCM locked -> clk25 (led): xpm_cdc_single. Reset to clk_dp: xpm_cdc_async_rst.

## Library entries considered
- `fir` (ip_lib): runtime-loadable coefficients, 4-7 samples-per-II variants, II>=7 or full LUT multiply; none gives 1 sample/clk with 16 DSP symmetric pre-add; not taken, write fresh.

## Pin list
- clk25 (C3), led[1:0], sfp_tx_disable.

## Predicted resources
LUT 600-1800 (jtag_bus ~90), FF 900-3000 (jtag_bus ~413), BRAM tiles 2-4, DSP 16.
