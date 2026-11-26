# p6_clkmux architecture

Glitch-free BUFGCTRL clock mux (clk_a 25 MHz / GT reference 156.25 MHz via BUFG_GT), with a self-checking 64-bit binary + Gray counter in the muxed domain and a gated frequency counter. Host access through jtag_bus (data/jtag_bus.sv, unchanged).

## Block diagram

```text
 clk_c3 (25MHz) ----------------------------+--> jtag_bus --h_*--> p6_clkmux_core --> led[1:0]
 mgtrefclk0_p/n -> IBUFDS_GTE4 -> BUFG_GT -+                         |  SEL, gate, regs
                                            v                        v
                  clk_a --------------> BUFGCTRL (S0/S1) -> clk_mux -> mux_domain
                                                                  (cnt64 + gray64 twin, checker, MUX_ERRS, freq edge count)
 rst (clk_a) -> xpm_cdc_async_rst -> rst_mux (clk_mux)
 clk_mux->clk_a: active_sel (xpm_cdc_single), snapshot/errs/freq count (xpm_cdc_handshake)
 clk_a->clk_mux: gate_open (xpm_cdc_single)
 sfp_tx_disable = 1
```

## Clock plan
- clk_a: clk_c3, 25 MHz, register bus, gate, BUFGCTRL input 0.
- clk_b_ref: MGTREFCLK0 156.25 MHz, IBUFDS_GTE4 -> BUFG_GT (divide B_DIV=1) -> BUFGCTRL input 1; no GT channel.
- clk_mux: BUFGCTRL output; muxed domain. All crossings use XPM CDC primitives; reset is synchronised by xpm_cdc_async_rst.

## Pin list
clk_c3, mgtrefclk0_p, mgtrefclk0_n, led[1:0], sfp_tx_disable (from board master XDC; h_* are internal core ports).

## Library entries considered
ip_lookup not needed: no standard IP function (CRC, filter, etc.) applies; XPM macros used for CDC.

## Resources
jtag_bus ~90 LUT / 413 FF; plus two 64-bit counters, 32-bit error/freq/gate/snapshot registers: LUT 350-900, FF 800-1500, no BRAM/DSP.
