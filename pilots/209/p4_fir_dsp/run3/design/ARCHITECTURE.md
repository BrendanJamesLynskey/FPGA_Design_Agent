# fir32_sym architecture

32-tap symmetric FIR (16 DSP48E2 multipliers, 250 MHz) with two 1024x16 dual-clock FIFOs, controlled from a JTAG register bus on clk25.

## Block diagram

```text
 C3 clk25 ---> jtag_bus (BSCANE2 USER4, supplied data/jtag_bus.sv) --h_we/h_re/h_addr/h_wdata--> fir32_core (clk25)
          |                                                          <--h_rdata--                 regs, ID/BUILD/SCRATCH,
          |                                                                                       CTRL/STATUS/SAT/DONE, LEDs
          +--> MMCM (x10) --> BUFG --> clk_dsp 250 MHz                                            |      ^
                    | locked                                                                       v      |
                    v                                                        in_fifo  (xpm_fifo_async 1024x16, clk25 -> clk_dsp)
          reset_sync (xpm_cdc_async_rst) -> rst_dsp          run/clear pulse (xpm_cdc_pulse) --> run controller (clk_dsp)
                                                                                               |
                                                  in FIFO -> history/pre-add (x[n-k]+x[n-31+k], 17 bit) -> 16 x DSP48 MAC
                                                          -> adder tree, +0x4000, >>>15, saturate16 -> out_fifo
                                                  out_fifo (xpm_fifo_async 1024x16, clk_dsp -> clk25)
                                                  busy/sat_count/samples_done -> clk25 (xpm_cdc_single / xpm_cdc_array_single)
 led[0]=BUSY, led[1]=MMCM locked, sfp_tx_disable = 1 constant
```

## Clock plan

- clk25: board clock, pin C3, 25 MHz. Drives jtag_bus, register core, FIFO bus-side ports, MMCM input.
- clk_dsp: MMCM (25 MHz x 10 / 1 = 250 MHz) through BUFG. Datapath, run controller, FIFO datapath-side ports.
- Reset: active high, synchronous. jtag_bus reset in clk25; synchronised into clk_dsp with xpm_cdc_async_rst, held while the MMCM is not locked.

## Pin list

| port | dir | board resource |
|---|---|---|
| clk25 | in | C3 25 MHz clock |
| led[1:0] | out | user LEDs |
| sfp_tx_disable | out | SFP+ tx disable, constant 1 |

h_we, h_re, h_addr, h_wdata, h_rdata are internal (core register port).

## Library entries considered

- `fir` (ip_lib): rejected. Its coefficients load at run time, it is a multi-cycle MAC (II 7 or more) or a LUT multiplier form, and it does not do 16 pre-added symmetric DSP multipliers at one sample per clock. Written fresh.

## Resource prediction

jtag_bus about 90 LUT / 413 FF. 16 DSP48 (pre-add in fabric or DSP), 2 FIFOs in block RAM, CDC and control a few hundred LUT.
