# p5_async_fifo_soak architecture

Asynchronous FIFO soak: a 25 MHz writer (clk_c3) pushes PRBS-31 words into a 512x32 FIFO, a 156.25 MHz reader (clk_gt156) checks them. Registers over the supplied JTAG bus `jtag_bus`.

## Block diagram

```text
 JTAG --> jtag_bus --h_*--> soak_core (clk_c3) -------------------+
                             regs, CTRL, PRBS writer, counters,   |
                             snapshot, LEDs                       |
                                |  wr side                        |
                                v                                 |
                          xpm_fifo_async 512x32  (Gray ptrs)      |
                                |  rd side                        |
                                v                                 |
 gt_refclk_p/n -> IBUFDS_GTE4 -> BUFG_GT -> soak_reader (clk_gt156)
                             PRBS check, INJECT, counters --handshake--> snapshot
 reset_gen (clk_c3) --xpm_cdc_async_rst--> reader reset
 sfp_tx_disable = 1 ; led[0]=RUN, led[1]=any error counter non-zero
```

## Clock plan
- clk_c3: 25 MHz, C3 oscillator; writer, registers, reset generator.
- clk_gt156: 156.25 MHz from SFP+ MGTREFCLK0 via IBUFDS_GTE4 and BUFG_GT; reader. No GT channel.
- Clocks are asynchronous: set_clock_groups -asynchronous plus max-delay on FIFO crossings.
- Crossings: FIFO (xpm_fifo_async, Gray pointers with synchroniser flops), RUN/SLOW_READ (xpm_cdc_array_single), INJECT/CLEAR (xpm_cdc_pulse), reader counters (xpm_cdc_handshake), reset (xpm_cdc_async_rst).

## Pin list
clk_c3 (C3 25 MHz), gt_refclk_p/gt_refclk_n (SFP+ MGTREFCLK0), led[1:0], sfp_tx_disable (constant 1). h_* are internal ports of the core, not pins.

## Library entries considered
ip_lookup: the library has no FIFO or clock-crossing block; AMD XPM macros are used.

## Resources
jtag_bus ~90 LUT / 413 FF; counters, snapshot registers (7x32 each), PRBS state add roughly 300-800 LUT and 500-1100 FF in total. One BRAM tile for the FIFO, 0 DSP.
