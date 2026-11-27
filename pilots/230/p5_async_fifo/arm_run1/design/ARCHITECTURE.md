# p5_async_fifo_soak architecture

Asynchronous FIFO soak: PRBS-31 writer at 25 MHz (clk_wr), reader/checker at 156.25 MHz (clk_rd), JTAG register port in clk_wr.
Reset model: reprogram (no reset input); a reset generator inside the top releases `rst` after a few clocks from initial values and is synchronised per domain.

## Block diagram

```text
 clk_c3 (25MHz)--BUFG--> clk_wr domain                         clk_rd domain <--IBUFDS_GTE2/BUFG-- gt_refclk_p/n
 +---------+  h_*  +-----------------------+  xpm_fifo_async   +------------------------+
 | jtag_bus|<----->| reg core (regs, CTRL, |  512x32, gray     | reader: FIFO pop, PRBS |
 | (USER4) |       | PRBS writer, counters,|=================> | check, slow-read gate, |
 +---------+       | OCC_MAX, snapshot)    |                   | WORDS_R/ERRS/UNDERFLOWS|
   reset gen       +-----------------------+                   +------------------------+
   (rst, xpm_cdc_async_rst per domain)   ^  xpm_cdc_array_single: RUN, SLOW, INJECT, CLEAR
                                         |  xpm_cdc_handshake: reader counters (snapshot)
 led[1:0] = {error seen, RUN}; sfp_tx_disable = 1
```

## Clock plan
- clk_wr: clk_c3, 25 MHz, writer, jtag_bus, registers, snapshot.
- clk_rd: gt_refclk_p/n through the GT reference buffer, 156.25 MHz, reader and checker.
- Asynchronous groups; set_max_delay -datapath_only on CDC paths.

## Pin list
clk_c3 (in), gt_refclk_p/n (in), led[1:0] (out), sfp_tx_disable (out, constant 1).

## Library entries considered
No library entry for FIFO or clock crossing (library has none); AMD XPM macros used.
