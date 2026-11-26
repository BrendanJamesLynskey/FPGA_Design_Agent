# p5_async_fifo_soak architecture

A 25 MHz writer fills an asynchronous 512 x 32 FIFO with PRBS-31 words. A 156.25 MHz reader (from the SFP+ MGTREFCLK0 buffer, no GT channel) checks them against its own PRBS copy. The host reads counters through jtag_bus.

## Block diagram

```text
 JTAG -> jtag_bus (clk) --rst,h_*--> p5_async_fifo_core (clk 25 MHz)
                                       |  regs, CTRL, snapshot, writer PRBS-31, W counters
                                       |-- xpm_cdc_array_single (RUN/SLOW/CLEAR/INJECT) --> reader_checker
                                       |-- xpm_fifo_async 512x32 (wr clk) ==> (rd gt_refclk)
 MGTREFCLK0 p/n -> IBUFDS_GTE4 -> BUFG_GT -> reader_checker (gt_refclk 156.25 MHz)
                                       |  slow-read divider, PRBS-31 check, INJECT, R counters
 reader_checker --xpm_cdc_handshake (counter set)--> snapshot regs in clk domain
 reset_gen: rst (clk) --xpm_cdc_async_rst--> rst_gt (gt_refclk)
 core -> led[1:0] (RUN, error nonzero), sfp_tx_disable = 1
```

## Clock plan

- clk: 25 MHz board clock, writer and register port.
- gt_refclk: 156.25 MHz from SFP+ MGTREFCLK0 via IBUFDS_GTE4 and BUFG_GT; reader domain.
- Unrelated: set_clock_groups -asynchronous, set_max_delay -datapath_only on each CDC path.
- Reset: rst from jtag_bus (active high), synchronised into gt_refclk with xpm_cdc_async_rst.
- CDC: XPM async FIFO (Gray pointers), xpm_cdc_array_single for static controls, xpm_cdc_handshake for the coherent snapshot.

## Pin list

- clk: board clock (resource clk_25 on the board master XDC).
- gt_refclk_p / gt_refclk_n: MGTREFCLK0. The board constraint tool lists no resource for it. This is an open point to resolve at constraint time.
- led[1:0]: board LEDs.
- sfp_tx_disable: constant 1.
- Unused SFP signals are not declared.

## Library entries considered

ip_lookup was not used. The library has no FIFO or CDC block, and XPM macros cover both. The PRBS-31 generator is a small LFSR written fresh.

## Resources

LUT 450 to 900 (jtag_bus about 90), FF 800 to 1400 (jtag_bus about 413), 1 RAMB36 (up to 2 tiles), 0 DSP.
