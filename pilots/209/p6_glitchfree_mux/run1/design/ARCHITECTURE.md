# P6 glitch-free clock mux

## Block diagram
```text
 JTAG --> jtag_bus (clk 25MHz) --h_*--> p6_clkmux_core --led[1:0]
                                          |  sel_req (xpm_cdc_single)
 gt_refclk_p/n -> IBUFDS_GTE4 -> BUFG_GT(/2) = clk_b ---+
 clk (25MHz, BUFG) = clk_a -----------------------------+--> BUFGCTRL --> clk_mux
                                                                 |
                                       p6_muxed_domain: bin cnt + gray twin + checker
                                       (snapshot, errs, edge count -> clk via xpm_cdc_gray/pulse)
 sfp_tx_disable = 1
```

## Clock plan
- clk 25 MHz: register bus, gate timer, SEL FSM.
- clk_b 78.125 MHz: gt_refclk 156.25 MHz via IBUFDS_GTE4 + BUFG_GT divide 2.
- clk_mux: BUFGCTRL output (A or B); reset synchronised with xpm_cdc_async_rst (3 stages).
- clk_mux <-> clk paths constrained asynchronous; all crossings use XPM CDC primitives.

## Pin list
clk (C3 25 MHz), gt_refclk_p/n (SFP+ MGTREFCLK0), led[1:0], sfp_tx_disable. Pins from board master XDC via board_constraints.

## Library entries considered
None: no standard IP-library function covers a clock mux or this checker; written fresh.

## Resources
jtag_bus ~90 LUT / 413 FF; remainder register map and 32-bit counters: total 350-800 LUT, 600-1100 FF, no BRAM/DSP.
