# p5_async_fifo_soak architecture

Asynchronous FIFO soak: PRBS-31 writer at 25 MHz, checker at 156.25 MHz, host access through jtag_bus.

## Block diagram

```text
 clk_25 --> [jtag_bus (BSCANE2 USER4)] -- h_we/h_re/h_addr/h_wdata/h_rdata --> [soak_core]
                                                                               |
 clk_wr domain (25 MHz):  regs, CTRL, snapshot, PRBS writer --> [fifo_mem 512x32 BRAM] --+
                              ^ gray rd ptr (xpm_cdc_gray)          gray wr ptr (xpm_cdc_gray) v
 clk_rd domain (156.25 MHz): reader, PRBS check, counters  <----------------------------------+
 mgtrefclk0_p/n --> IBUFDS_GTE4 --> clk_rd (top)
 CTRL bits: xpm_cdc_array_single / xpm_cdc_pulse (INJECT, CLEAR) to clk_rd
 reader counters: xpm_cdc_handshake to clk_wr on snapshot
 led[0]=RUN, led[1]=sticky error ; sfp_tx_disable = 1
```

## Clock plan

- clk_wr = clk_25 (25 MHz board clock): register port, writer, control.
- clk_rd = SFP+ MGTREFCLK0 156.25 MHz via IBUFDS_GTE4 (no GT channel), reader.
- Domains are asynchronous; all crossings use XPM CDC primitives (see architecture.yaml).
- Reset model: reprogram; no reset input, registers use initial values. jtag_bus rst driven internally for a few clocks.

## Pin list

clk_25, mgtrefclk0_p, mgtrefclk0_n, led[1:0], sfp_tx_disable (pins from the board master XDC).

## Library entries considered

ip_lookup: none needed; the library has no FIFO or clock-crossing block, XPM macros used for CDC; PRBS is a trivial LFSR written fresh.

## Resources

jtag_bus ~90 LUT / 413 FF; core about 7 live + 7 snapshot 32-bit counters; 1 BRAM (18K half tile), 0 DSP.
