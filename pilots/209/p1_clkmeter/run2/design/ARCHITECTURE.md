# Architecture: p1_freq_meter

Measures the 25 MHz c3_clk against the 156.25 MHz SFP GT reference clock. Host access is the JTAG register bus only.

## Block diagram

```text
 ref_clk_p/n --IBUFDS_GTE4--BUFG_GT--> ref_clk (156.25 MHz)
                                         |
   JTAG --> jtag_bus (data/jtag_bus.sv) --+--h_we/h_re/h_addr/h_wdata/h_rdata--> freq_meter_core
                                                                                 |  regs ID/BUILD/SCRATCH/
                                                                                 |  GATE_LEN/CTRL/STATUS/...
                                         ref domain: gate counter, LED1 blink     |
                                              | gate_open (xpm_cdc_single)        |
                                              v                                   |
   c3_clk (pin C3, 25 MHz) -> c3 domain: edge counter, LED0 blink                 |
                                              | count (xpm_cdc_array_single) -----+
   rst (from jtag_bus reset gen, ref) -> xpm_cdc_async_rst -> c3 reset
   sfp_tx_disable = 1 (constant)
```

## Clock plan
- ref: 156.25 MHz (6.4 ns), MGTREFCLK0 of the SFP quad via IBUFDS_GTE4 (ODIV2 output) and BUFG_GT. Ruler, register bus and gate counter clock. No GT channel.
- c3: 25 MHz (40 ns), pin C3, clock under measurement, edge counter and LED0.
- The two are asynchronous; CDC paths are set false or max-delay in design.xdc.
- Crossings: gate window ref->c3 (xpm_cdc_single); count c3->ref, read only after the gate closes and a done flag has crossed (xpm_cdc_array_single); reset ref->c3 (xpm_cdc_async_rst). Resets are synchronous, active high.

## Pin list
| port | dir | board resource | pin |
|---|---|---|---|
| c3_clk | in | clk_25 | C3 (LVCMOS18) |
| ref_clk_p / ref_clk_n | in | MGTREFCLK0 SFP quad | GT dedicated pins; the board tool's resource list has no entry for them, so they are placed by the GT refclk site (to confirm at build) |
| led[0] | out | led[0] | F8 |
| led[1] | out | led[1] | E8 |
| sfp_tx_disable | out | sfp_tx_disable | Y10 (constant 1) |

## Resources
jtag_bus about 90 LUT / 413 FF; core about 250 LUT / 300 FF. Predicted total 350-900 LUT, 650-1300 FF, 0 BRAM, 0 DSP, 1 GT refclk buffer, 0 GT channels.

## Library entries considered
ip_lookup not needed: no standard function (CRC, filter, stack) is involved; counters and register file are written fresh.
