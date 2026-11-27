# p4_fir32 architecture

32-tap symmetric FIR (Q1.15, 16 DSP multipliers) on a 250 MHz MMCM clock, driven by the JTAG register bus on clk25.

## Block diagram

```text
 JTAG -> jtag_bus (clk25) --h_we/h_re/h_addr/h_wdata--> fir32_core --h_rdata--> jtag_bus
                                                        |
 clk25 domain:  regs, CTRL, STATUS, LEDs                |
   IN_PUSH -> in_fifo (xpm_fifo_async) ==============> fir_dsp (clk_dsp 250 MHz)
   OUT_POP <- out_fifo (xpm_fifo_async) <============== (pre-add, 16 DSP mult, adder tree, round, saturate)
   CLEAR/RUN pulses (xpm_cdc_pulse) -> clk_dsp ; BUSY (xpm_cdc_single) <- clk_dsp
   SAT_COUNT/SAMPLES_DONE (xpm_cdc_handshake) <- clk_dsp
 clk25 -> MMCM (x10) -> BUFG clk_dsp ; locked -> xpm_cdc_single -> clk25 (led[1], rst hold)
 rst (clk25) -> xpm_cdc_async_rst -> clk_dsp reset
 sfp_tx_disable = 1 constant
```

## Clock plan

- clk25: 25 MHz board clock (C3), register bus, FIFO write/read ports on the host side, LEDs.
- clk_dsp: 250 MHz from one MMCM (25 x 40 VCO 1000 MHz / 4... exact: VCO 1000 MHz, divide 4), via BUFG. Reset is held while unlocked.
- All crossings use XPM primitives listed in architecture.yaml; the filter runs one sample per clk_dsp cycle, with run stalled when the output FIFO lacks room.

## Pin list

- clk25: C3 (25 MHz); led[1:0]: board user LEDs (led[0] BUSY, led[1] MMCM locked); sfp_tx_disable: SFP+ TX disable, constant 1.
- h_* signals are internal, no pins.

## Library entries considered

- fir (ip_lib): not taken: runtime-loadable coefficients, valid/ready streams, 4 DSPs and II 7; this design needs fixed symmetric coefficients, II 1 and 16 multipliers.

## Resources

LUT 500-1500, FF 900-2200 (jtag_bus alone is about 90 LUT and 413 FF), BRAM tiles 2-4, DSP 16-20, MMCM 1, GT 0.
