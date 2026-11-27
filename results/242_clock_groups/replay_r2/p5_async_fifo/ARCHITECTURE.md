# p5_async_fifo_soak architecture

## Block diagram

```text
 JTAG --> jtag_bus (clk_c3) --h_we/h_re/h_addr/h_wdata/h_rdata--> p5_core
 clk_c3 (25 MHz) -------------------------------+
   rst_gen (8-clk power-up counter) --rst--> jtag_bus, p5_core
                                             |
 +------------------- p5_core ---------------------------------------------+
 | clk_c3 domain                         | gt_refclk domain (156.25 MHz)    |
 | regfile + CTRL + snapshot regs        |                                  |
 | wr_side: PRBS31 -> xpm_fifo_async 512x32 -> rd_side: PRBS31 check        |
 |   STALL_W WORDS_W OVERFLOWS OCC_MAX  |   WORDS_R DATA_ERRS UNDERFLOWS   |
 | RUN,SLOW_READ: xpm_cdc_array_single ->|                                  |
 | INJECT,CLEAR: xpm_cdc_pulse ->        |                                  |
 | snapshot req: xpm_cdc_handshake ->    | <- xpm_cdc_handshake counters    |
 | rst -> xpm_cdc_async_rst -----------> | rst_sync_rd                      |
 +--------------------------------------------------------------------------+
 gt_refclk_p/n -> IBUFDS_GTE4 -> BUFG -> gt_refclk domain
 led[0]=RUN, led[1]=DATA_ERRS!=0 (xpm_cdc_single); sfp_tx_disable=1
```

## Clock plan
- clk_c3: 25 MHz, writer, jtag_bus, register file. BUFG.
- gt_refclk: 156.25 MHz from SFP+ MGTREFCLK0 via IBUFDS_GTE4 (ODIV2 output) and BUFG; reader.
- The two clocks are asynchronous; set_clock_groups -asynchronous in design.xdc, every crossing through an XPM primitive.
- Reset: model reprogram, no reset port; internal rst from a power-up counter in clk_c3, synchronised into gt_refclk by xpm_cdc_async_rst.

## Pin list
- clk_c3 (in, C3 25 MHz), gt_refclk_p / gt_refclk_n (in, SFP+ MGTREFCLK0)
- led[1:0] (out), sfp_tx_disable (out, constant 1), no other ports.

## Library entries considered
- FIFO / clock crossing: the library has none; AMD xpm_fifo_async taken (1 RAMB36).
- PRBS-31: written fresh (small XOR/shift); no fitting entry assumed.

## Resource prediction
jtag_bus ~90 LUT / 413 FF; counters, snapshot registers (7 x 32), PRBS state 2 x 31, FIFO control: about 350-800 LUT, 800-1400 FF, 1 BRAM, 0 DSP.
