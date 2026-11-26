# p5_async_fifo_soak architecture

## Block diagram

```text
 clk_c3 (25 MHz) domain                         gt_refclk0 (156.25 MHz) domain
 +----------+  h_*  +-------------------------------------------------+
 | jtag_bus |<----->| fifo_core                                       |
 +----------+       |  regs/ctrl/snapshot  writer PRBS31 --+          |
 rst_gen ---------->|                                      v          |
                    |                         xpm_fifo_async 512x32 --+--> reader PRBS31 checker
                    |  ctrl bits ----xpm_cdc_array_single-----------> |   counters
                    |  <----xpm_cdc_handshake (snapshot results)------|
                    +-------------------------------------------------+
 IBUFDS_GTE4 + BUFG_GT : gt_refclk0_p/n -> reader clock
 sfp_tx_disable = 1 ; led[0]=RUN, led[1]=any error
```

## Clock plan
- clk_c3 25 MHz: writer, register port, jtag_bus.
- gt_refclk0 156.25 MHz via IBUFDS_GTE4 and BUFG_GT: reader. Asynchronous clock groups; set_max_delay -datapath_only on CDC paths.
- Reset: active high, startup counter held >= 8 clk_c3 cycles, xpm_cdc_async_rst per domain.

## Pin list
clk_c3, gt_refclk0_p, gt_refclk0_n, sfp_tx_disable (out, const 1), led[1:0].

## Library entries considered
ip_lookup: no FIFO or clock-crossing block in the library; AMD XPM macros used. PRBS is trivial and written fresh.
