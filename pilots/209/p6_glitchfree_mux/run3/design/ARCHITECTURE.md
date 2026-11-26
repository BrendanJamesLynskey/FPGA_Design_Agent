# p6_clkmux: glitch-free clock multiplexer (kr260, xck26)

## Block diagram

```text
 clk_c3 (25 MHz) ---> jtag_bus (BSCANE2 USER4) --h_we/h_re/h_addr/h_wdata/h_rdata--> p6_clkmux_core
                                                                                    |
 clk_c3 domain (core): regs, SEL, gate timer, SWITCH_COUNT, status sync, LEDs ------+--> led[1:0]
        |  SEL (S0/S1 control)                                                       +--> sfp_tx_disable = 1
        v
 gt_refclk_p/n -> IBUFDS_GTE4 (ODIV2, no GT) -> BUFG_GT (div B_DIV) --I1--> BUFGCTRL --> clk_mux
 clk_c3 -> BUFG -----------------------------------------------------I0-->  (glitch-free)
 clk_mux domain: 32-bit counter + Gray twin + checker (MUX_ERRS), edge counter (gated)
        |  ACTIVE_SEL (xpm_cdc_single), FREQ_COUNT / MUX_ERRS / MUX_COUNT (xpm_cdc_handshake) -> clk_c3
 rst (jtag_bus, clk_c3) -> xpm_cdc_async_rst -> clk_mux reset
```

Blocks: jtag_bus (supplied, data/jtag_bus.sv, unchanged); thin top (p6_clkmux_top: jtag_bus, reset, core, clock primitives);
core (register map, SEL/switch tracking, gate timer, LEDs); muxed domain (counter, Gray twin, checker, edge counter).

## Clock plan
- clk_c3 25 MHz: register bus, control, gate timer, clock A.
- gt_refclk0 156.25 MHz: clock B via IBUFDS_GTE4 + BUFG_GT (B_DIV=1).
- clk_mux: BUFGCTRL output, 25 MHz or 156.25/B_DIV. All three declared asynchronous; crossings only through XPM CDC primitives.
- Reset: active high, synchronous in clk_c3; released into clk_mux by xpm_cdc_async_rst.

## Pin list
- clk_c3 -> board resource clk_25 (C3 clock)
- led[1:0] -> led[0:1]
- sfp_tx_disable -> sfp_tx_disable
- gt_refclk_p/n: MGTREFCLK0 of the SFP+ cage; not in the board_constraints resource list, so needs checking at the constraints step (pins from the master XDC only).

## Resource prediction
jtag_bus alone is about 90 LUT / 413 FF. Core and muxed domain add about 300-400 FF (32-bit registers, counters, handshake data) and about 200-300 LUT. 0 BRAM, 0 DSP, 1 BUFGCTRL, 1 BUFG_GT.

## Library entries considered
ip_lookup not used: no standard library function (CRC, filter, FIFO) covers a clock mux; the XPM CDC macros are used for crossings.
