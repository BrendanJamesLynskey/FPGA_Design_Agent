# Architecture: p5_async_fifo_soak

Asynchronous FIFO soak: a 25 MHz writer pushes PRBS-31 words into a 512x32 asynchronous FIFO; a 156.25 MHz reader pops and checks them. Host access is through jtag_bus (BSCANE2 USER4), unchanged, in clk_25.

## Block diagram

```text
 clk_c3 (25MHz) --> por_reset --rst--> [clk_25 domain]                     [clk_gt156 domain] <-- IBUFDS_GTE4 <-- gt_refclk0_p/n
                         |                                                       ^ BUFG_GT
                         +--xpm_cdc_async_rst--------------------------------> rst_gt
 JTAG --> jtag_bus --h_we/h_re/h_addr/h_wdata/h_rdata--> soak_core
   soak_core clk_25 : regs, PRBS writer, counters, snapshot --> xpm_fifo_async (512x32) --> reader PRBS check, counters (clk_gt156)
   CTRL levels/pulses : xpm_cdc_array_single / xpm_cdc_pulse (25 -> 156)
   snapshot of reader counters : xpm_cdc_handshake (156 -> 25); error flag : xpm_cdc_single -> led[1]
 sfp_tx_disable = 1 (constant); led[0]=RUN, led[1]=sticky error
```

## Clock plan
- clk_25: clk_c3 25 MHz, free-running; writer, register port, POR counter.
- clk_gt156: SFP MGTREFCLK0 156.25 MHz via IBUFDS_GTE4 (ODIV2 output) and BUFG_GT; reader. No GT channel used.
- The two are unrelated: set_clock_groups -asynchronous in design.xdc; all crossings use XPM primitives (CDC report lists them).
- Reset: active high, 16-clock POR in clk_25, synchronised into clk_gt156 by xpm_cdc_async_rst (async assert, sync release).

## Pin list
- clk_c3 (25 MHz C3), gt_refclk0_p / gt_refclk0_n (MGTREFCLK0), led[1:0], sfp_tx_disable (constant 1).

## Library entries considered
- FIFO / clock crossing: ip_lib has none; AMD XPM macros (xpm_fifo_async, xpm_cdc_*) used.
- PRBS: simple 32-bit-per-clock LFSR step written fresh (small).

## Resources
jtag_bus ~90 LUT / 413 FF; core ~14 x 32 counter/snapshot flops, handshake, PRBS x2; 1 BRAM36 FIFO (512x32 = 16 Kb, may map as 1 tile). Predicted LUT 450-1400, FF 900-2000, BRAM 1-2, DSP 0.
