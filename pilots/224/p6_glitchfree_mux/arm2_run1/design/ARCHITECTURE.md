# p6_clkmux architecture

Glitch-free clock mux on KR260 (xck26): BUFGCTRL selects clk_c3 (25 MHz) or the
SFP+ MGTREFCLK0 (156.25 MHz via IBUFDS_GTE4 and BUFG_GT, divide B_DIV=1). No GT channel.

## Block diagram

```text
clk_c3 --> rst_gen --> rst
JTAG --> jtag_bus --h_we/h_re/h_addr/h_wdata--> p6_clkmux_core --> led[1:0]
                      <--h_rdata--------------      |  \--> sfp_tx_disable = 1
gtref_p/n -> IBUFDS_GTE4 -> BUFG_GT(div) -> BUFGCTRL <- clk_c3, SEL
                                               |
                                            mux_clk -> bin counter + gray twin + checker
                                               | (xpm_cdc) active_sel, errs, snapshot, freq count
                                            clk_c3: registers, switch count, gate timer
```

## Clock plan
- clk_c3 25 MHz: registers, jtag_bus, gate timebase, reset.
- gtref 156.25 MHz: only through IBUFDS_GTE4/BUFG_GT into BUFGCTRL.
- mux_clk: BUFGCTRL output; checker and edge counter. Clock groups async. Crossings by XPM
  (single, array_single, handshake, gray, async_rst for reset into mux_clk).

## Pin list
clk_c3 (C3 25 MHz), gtref_p/gtref_n (MGTREFCLK0), led[1:0], sfp_tx_disable (const 1).

## Library entries considered
None fits (clock mux, CDC checker are bespoke; XPM used for crossings).

## Resources
About 250-700 LUT, 600-1100 FF (jtag_bus alone ~90 LUT/413 FF), 1 BUFGCTRL, 1 BUFG_GT, 0 BRAM/DSP.
