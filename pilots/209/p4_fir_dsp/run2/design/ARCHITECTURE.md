# p4_fir32: 32-tap symmetric FIR with FIFOs, JTAG register bus (KR260, xck26)

## Block diagram

```text
 clk_25 (C3) --+--> MMCM (x10) --> clk_dsp 250 MHz, locked
               |
               v  clk_bus 25 MHz                              clk_dsp 250 MHz
 JTAG -> jtag_bus -> fir_core regs/CTRL/STATUS
                       | IN_PUSH --> xpm_fifo_async in (1024x16) --> fir_engine (16 DSP48E2, pre-add, 1 sample/clk)
                       | OUT_POP <-- xpm_fifo_async out (1024x16) <-- fir_engine results, SAT/DONE counters
                       | CLEAR/RUN --> xpm_cdc_pulse --> dsp-side control FSM
                       | BUSY, SAT_COUNT, SAMPLES_DONE <-- xpm_cdc_array_single / handshake
 reset generator: power-up counter (clk_25), released after MMCM lock; per-domain xpm_cdc_async_rst
 led[0]=BUSY, led[1]=locked, sfp_tx_disable = 1 constant
```

## Clock plan
- clk_25: board clock, pin C3, bus domain (jtag_bus, register core), MMCM input.
- clk_dsp: 250 MHz from MMCM (VCO 1000 MHz, CLKOUT0 divide 4) through BUFG; datapath and FIFO read/write sides.
- Crossings: FIFOs use xpm_fifo_async; CLEAR/RUN use xpm_cdc_pulse; status/counters use xpm_cdc_array_single (quasi-static, read when not BUSY, or sampled via handshake); reset via xpm_cdc_async_rst.

## Pin list
clk_25 (C3, LVCMOS18), led[0] F8, led[1] E8 (LVCMOS18), sfp_tx_disable Y10 (LVCMOS33). No GT used.

## Library entries considered
- fir (ip_lib): variants serial/dist_ram/dsp_bram have II 7 to 19, lut_mult is II 1 but 117 MHz and no symmetry; none gives II 1 at 250 MHz with 16 DSPs. Not taken; written fresh.

## Resources
jtag_bus about 90 LUT / 413 FF; engine 16 DSP, pipeline registers; 2 FIFOs in BRAM.
