# fir32_sym architecture

32-tap symmetric FIR (Q1.15, round 0x4000, >>>15, saturate16), input/output 1024x16 FIFOs, JTAG register bus. Part xck26 (KR260). Reset model: reprogram for configuration state; the run-time reset is the jtag_bus rst, synchronised into clk_dp.

## Block diagram

```text
 JTAG -> jtag_bus --h_we/h_re/h_addr/h_wdata/h_rdata--> fir_core (clk25)
                                                    |  regs, LEDs, pulses
   clk25 -> MMCM(x10) -> clk_dp 250 MHz             |
                                      in_fifo (xpm_fifo_async, clk25->clk_dp)
                                              |
                                          fir_engine (clk_dp) -> fir_filter (16 pre-add, 16 DSP48E2, tree, round/sat)
                                              |
                                      out_fifo (xpm_fifo_async, clk_dp->clk25)
 rst (jtag_bus) -> xpm_cdc_async_rst -> clk_dp reset
 sfp_tx_disable = 1 constant
```

## Clock plan
- clk25: board 25 MHz (pin C3), register bus, FIFO host side, MMCM input, heartbeat.
- clk_dp: MMCM, VCO 250 MHz*... mult 10, div 1 (250 MHz), datapath, FIFO device side.
- Crossings: RUN/CLEAR via xpm_cdc_pulse; BUSY via xpm_cdc_single; SAT_COUNT/SAMPLES_DONE via xpm_cdc_handshake; samples via two xpm_fifo_async; reset via xpm_cdc_async_rst. FIFO counts come from the FIFO rd/wr data counts.

## Pin list
- clk25 (input, C3), led[1:0] (outputs: BUSY, heartbeat), sfp_tx_disable (output, constant 1). JTAG via BSCANE2 (no pins).

## Library entries considered
- fir (ip_lib): not taken. Runtime-loadable coefficients, valid/ready streams and II 7-19 variants do not give 1 sample/clk with 16 fixed-coefficient symmetric DSP multipliers.

## Resources
jtag_bus ~90 LUT/413 FF; filter 16 DSP, pre-adders and tree in fabric/DSP; 2 BRAM FIFOs. Predicted LUT 500-1500, FF 1000-2500, BRAM 2-4, DSP 16-20.
