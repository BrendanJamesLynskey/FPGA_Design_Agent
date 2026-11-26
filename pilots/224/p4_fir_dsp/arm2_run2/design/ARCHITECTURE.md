# fir32_sym architecture

Part xck26-sfvc784-2LV-c (KR260). 32-tap symmetric FIR, 16 DSP48E2 multipliers, JTAG register access.

## Block diagram

```text
 JTAG --> jtag_bus --h_we/h_re/h_addr/h_wdata/h_rdata--> fir32_core (clk_25)
                                                       |  regs, CTRL, STATUS, LEDs
                                                       |  in FIFO (xpm_fifo_async 1024x16)
 clk_25 -> rst_gen -> rst  -----------------------------+--> pulses run/clear (xpm_cdc_pulse)
 clk_25 -> MMCM -> clk_dsp (250 MHz) --> fir_dsp: pre-add -> 16 x DSP48E2 -> round/sat
                                          -> out FIFO (xpm_fifo_async 1024x16) -> core
 sat_count/samples_done: xpm_cdc_gray; busy: xpm_cdc_single
 sfp_tx_disable = 1 constant; led[0]=BUSY, led[1]=0
```

## Clock plan

- clk_25 (pin C3, 25 MHz): register bus, control, FIFO host sides, reset generator.
- clk_dsp: 250 MHz from an MMCM (VCO 1000 MHz, M=40, D=1, O=4) driven by clk_25; datapath and FIFO DSP sides.
- Reset: active-high rst from a 16-cycle power-on counter on clk_25; into clk_dsp through xpm_cdc_async_rst. The datapath registers in DSP slices use synchronous or no reset.

## Pin list

| port | dir | pin | standard |
|---|---|---|---|
| clk_25 | in | C3 | LVCMOS18 |
| led[0] | out | F8 | LVCMOS18 |
| led[1] | out | E8 | LVCMOS18 |
| sfp_tx_disable | out | Y10 | LVCMOS33 |

## Library entries considered

- fir (ip_lib): rejected; coefficient-loadable MAC engines with II 7 or more, no symmetric pre-add, cannot accept one sample per clock.

## Resources

LUT 600-2000, FF 1200-3000 (jtag_bus alone ~90 LUT/413 FF), BRAM tiles 2-6, DSP 16-20.
Pipeline depth about 8-12 clk_dsp cycles, documented in RTL.
