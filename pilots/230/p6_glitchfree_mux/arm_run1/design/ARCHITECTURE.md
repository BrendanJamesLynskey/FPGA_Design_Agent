# p6_clkmux architecture

Glitch-free clock multiplexer (BUFGCTRL) between clk_c3 (25 MHz) and clk_b (SFP+ MGTREFCLK0 156.25 MHz / B_DIV=2 via IBUFDS_GTE4 + BUFG_GT), with a self-checking 64-bit counter domain and a gated frequency counter. Host access through jtag_bus (data/jtag_bus.sv, unmodified). No GT channel; sfp_tx_disable tied to 1.

## Block diagram

```text
 JTAG --> jtag_bus (clk_c3) --h_we/h_re/h_addr/h_wdata/h_rdata--> p6_clkmux_core
                                                                      |
 clk_c3 --+--> reset gen (rst, few clocks) ---------------------------+
          |                                                           |
          |   core (clk_c3): regs, SEL, STATUS, switch count, gate FSM, LEDs
          |        | SEL                               ^ ACTIVE_SEL (xpm_cdc_single)
          |        v                                   | MUX_ERRS/MUX_COUNT/FREQ_COUNT (xpm_cdc_handshake / array)
 clk_c3 --> BUFGCTRL (I0=clk_a, I1=clk_b) --> clk_mux --> muxed domain:
 gt_refclk_p/n --> IBUFDS_GTE4 --> BUFG_GT(div=B_DIV-1) --> clk_b    64-bit binary counter + Gray twin + checker,
                                                                      error counter (sat 32), edge counter for gate
 sfp_tx_disable = 1 ; led[0]=ACTIVE_SEL ; led[1]=SWITCHING
```

## Library entries considered
ip_lookup not applicable: no standard function (CRC, filter, etc.) is involved; XPM CDC macros are used for crossings.

## Clock plan
- clk_c3: 25 MHz board clock (pin from board resource clk_25), register bus, gate, status.
- gt_refclk: 156.25 MHz differential from SFP+ MGTREFCLK0; IBUFDS_GTE4 ODIV2/BUFG_GT divides to clk_b = 78.125 MHz.
- clk_mux: BUFGCTRL output (clk_c3 or clk_b); drives the muxed domain.
- All three are mutually asynchronous (clk_b and clk_mux related only by the mux); clocks declared asynchronous in constraints.

## Reset
Model reprogram: no reset input; registers carry initial values. jtag_bus rst comes from a small power-up shift generator in clk_c3. The muxed domain reset is brought into clk_mux with xpm_cdc_async_rst.

## Crossings
- SEL/ACTIVE_SEL: ACTIVE_SEL (clk_mux/BUFGCTRL state) to clk_c3 via xpm_cdc_single; SEL goes straight to the BUFGCTRL S pin (glitch-free by primitive).
- Gate enable clk_c3 -> clk_mux: xpm_cdc_single; edge count back: xpm_cdc_handshake (32 bit).
- MUX_ERRS and snapshot: xpm_cdc_handshake (snapshot request c3 -> mux, data back).
- Reset into clk_mux: xpm_cdc_async_rst.

## Pin list
- clk_c3 : board clk_25 (C3 25 MHz)
- gt_refclk_p / gt_refclk_n : SFP+ MGTREFCLK0 (GT pins, not in the board_constraints resource list; constrained by the stage that writes the XDC, with create_clock 6.4 ns)
- sfp_tx_disable : board sfp_tx_disable
- led[1:0] : board led[0:1]

## Resources
About 500-900 LUTs and 1000-1400 FFs including jtag_bus (~90 LUT, 413 FF); 0 BRAM, 0 DSP, 1 BUFGCTRL, 1 BUFG_GT.
