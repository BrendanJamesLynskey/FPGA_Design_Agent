# p5_async_fifo_soak architecture

Part xck26 (KR260). Asynchronous FIFO soak: 25 MHz PRBS-31 writer, 156.25 MHz reader/checker, host via jtag_bus.

## Block diagram

```text
 clk_25 domain                                   gt_refclk domain (156.25 MHz)
 +---------+ h_* +-----------------------------+      +----------------------------+
 |jtag_bus |---->| fifo_core regs, CTRL, LEDs  |      | reader + PRBS check, counters|
 +---------+     | PRBS writer, W-side counters|      +----------------------------+
                 +-------------+---------------+                  ^
 reset_gen -- rst --> core       |  async_fifo 512x32 (BRAM)       |
   |  xpm_cdc_async_rst ---------+--- gray wptr/rptr (xpm_cdc_gray)+
   +--------------------------------> rst_ref
 RUN/SLOW/INJECT/CLEAR: xpm_cdc_array_single ->; snapshot: xpm_cdc_handshake <-
 IBUFDS_GTE4(gt_refclk_p/n) -> BUFG_GT -> reader domain
```

## Clock plan
- clk_25: 25 MHz (C3 pin), writer, registers, jtag_bus.
- gt_refclk: 156.25 MHz from SFP+ MGTREFCLK0 via IBUFDS_GTE4 (no GT channel). Asynchronous clock groups declared between the two; Gray pointer paths get bounded max delay.
- Reset: active high internal, power-on counter in clk_25, synchronised into gt_refclk by xpm_cdc_async_rst.

## Pin list
- clk_25 (board clk_25), gt_refclk_p/n (MGTREFCLK0), led[1:0], sfp_tx_disable (constant 1).

## Library entries considered
- ip_lookup: no FIFO/CDC block in the library; XPM macros used. PRBS is a trivial 32-step LFSR, written fresh.

## Resources
jtag_bus ~90 LUT / 413 FF; remainder of core ~400-600 LUT, ~500-900 FF, 1 RAMB18 (0.5 tile), no DSP.
