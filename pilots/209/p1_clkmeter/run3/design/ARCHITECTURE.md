# Architecture: P1 clock frequency meter (kr260, xck26)

## Block diagram

```text
 clk_c3_in --BUFG--> clk_c3 --+--> power-up reset shift reg (8 clk) --> rst
                              |
   jtag_bus (BSCANE2 USER4) --h_we/h_re/h_addr/h_wdata/h_rdata--> freq_meter_core
                                                                  |  regs, LED0 divider (clk_c3)
                                                                  |  count_c3: counts clk_c3 edges in gate
                                         handshake CDC  <---------+---------> handshake CDC
                                                |                                   ^
 mgtrefclk0_p/n --IBUFDS_GTE4(ODIV2)--BUFG_GT--> clk_ref: gate_ref (gate counter, LED1 divider)
 sfp_tx_disable <= 1 constant;  led[1:0] <= LED0 (clk_c3), LED1 (clk_ref)
```

## Clock plan
- clk_c3: 25 MHz, C3 pin through BUFG; jtag_bus, register file, LED0, edge counter.
- clk_ref: 156.25 MHz, MGTREFCLK0 via IBUFDS_GTE4 ODIV2 and BUFG_GT; gate counter, LED1. No GT channel.
- The two are asynchronous; set_clock_groups -asynchronous between them; all crossings use XPM CDC primitives (see architecture.yaml). Reset: generated in clk_c3, synchronised into clk_ref with xpm_cdc_async_rst.
- START plus latched GATE_LEN cross by xpm_cdc_handshake; the gate window is a clk_ref level, synchronised to clk_c3 (xpm_cdc_single) to enable the edge counter; COUNT, GATE_ACTUAL and done cross back by handshake, stable while DONE=1.

## Pin list
- clk_c3_in: board resource clk_25
- mgtrefclk0_p / mgtrefclk0_n: SFP+ reference clock (board resource clk)
- led[1:0]: board resource led
- sfp_tx_disable: board resource sfp_tx_disable (held 1)
- JTAG: internal via BSCANE2, no pins.

## Resources
jtag_bus about 90 LUT / 413 FF; core registers and 32-bit counters add roughly 300 LUT and 400 FF. Predicted LUT 250-800, FF 600-1500, no BRAM or DSP.

## Library entries considered
ip_lookup not used: no standard function (counter and register file) needs a library block; jtag_bus is supplied.
