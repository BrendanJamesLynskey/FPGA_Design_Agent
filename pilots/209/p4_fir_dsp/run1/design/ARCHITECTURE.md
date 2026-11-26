# p4_fir32 architecture

32-tap symmetric FIR (Q1.15, 16 unique coefficients from data/coeffs.hex), input and output FIFOs, JTAG register access, on xck26 (KR260).

## Block diagram

```text
 JTAG -> jtag_bus --(rst, h_we/h_re/h_addr/h_wdata/h_rdata, clk 25 MHz)--> fir_regs
                                                                   |  IN_PUSH
 clk(C3) -> MMCM x10 -> clk_dsp 250 MHz                            v
                                            in FIFO (xpm_fifo_async 1024x16)
                                                                   |  clk -> clk_dsp
 RUN/CLEAR --xpm_cdc_pulse--> fir_datapath: delay line -> 16 pre-adders -> 16 DSP48E2
                                   -> adder tree (38 bit) -> +0x4000 >>>15 -> saturate
                                                                   |  clk_dsp -> clk
                                            out FIFO (xpm_fifo_async 1024x16)
 OUT_POP / STATUS / SAT_COUNT / SAMPLES_DONE <- fir_regs (counters via xpm_cdc_array_single)
 led[0]=BUSY  led[1]=MMCM locked   sfp_tx_disable=1
```

## Clock plan
- clk 25 MHz (pin C3): register bus, FIFO write/read sides toward host.
- clk_dsp 250 MHz: MMCM (mult 10, div 1) from clk; datapath and FIFO other sides. Reset: rst from jtag_bus, synchronised into clk_dsp by xpm_cdc_async_rst; CLEAR is a pulse crossing via xpm_cdc_pulse. Active-high synchronous reset inside.
- Stalls: datapath stops while the output FIFO has no space, so no result is lost.

## Pin list
clk (C3), led[1:0], sfp_tx_disable. rst and h_* are internal. No GT channel is used.

## Library entries considered
- fir: not taken; no variant offers II 1 with a symmetric pre-adder and 16 DSPs at 250 MHz (nearest lut_mult uses LUT multipliers), so written fresh.

## Resources
jtag_bus about 90 LUT and 413 FF. Predicted: LUT 700-2400, FF 900-3200, BRAM tiles 2-4, DSP 16-20.
