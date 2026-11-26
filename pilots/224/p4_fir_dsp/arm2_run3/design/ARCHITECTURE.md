# fir32_sym architecture (xck26, KR260)

## Block diagram

```text
 JTAG --> jtag_bus --h_we/h_re/h_addr/h_wdata/h_rdata--> fir32_core (clk25) --> led[0]=BUSY, led[1]=heartbeat
                                                          |   ^
                                           IN_PUSH        v   | OUT_POP
                                          in_fifo (xpm_fifo_async 1024x16)       out_fifo (xpm_fifo_async 1024x16)
                                              clk25 -> clk_dsp                      clk_dsp -> clk25
                                                   \                               ^
                                                    v                              |
 clk25 --> MMCM (x40 /4) --> clk_dsp 250 MHz --> fir_dsp: pre-add -> 16 x DSP48 mult -> adder tree -> round/saturate
 rst, MMCM locked --> xpm_cdc_async_rst --> clk_dsp reset          sfp_tx_disable = 1 constant
```

## Clock plan

- clk25: 25 MHz board clock (pin C3). Drives the MMCM, jtag_bus, register core, FIFO host sides and heartbeat.
- clk_dsp: 250 MHz from the MMCM (VCO 1000 MHz), through BUFG. Datapath, FIFO DSP sides. Must close at 250 MHz.
- Crossings: two xpm_fifo_async; xpm_cdc_pulse for RUN/CLEAR; xpm_cdc_array_single for quasi-static BUSY, SAT_COUNT, SAMPLES_DONE; xpm_cdc_async_rst for the reset into clk_dsp; jtag_bus's own TCK crossing.
- Reset: active high inside, synchronous; datapath reset held while MMCM is not locked.

## Behaviour summary

Registers at 0x000 ID, 0x004 BUILD, 0x008 SCRATCH, 0x010 CTRL, 0x014 IN_PUSH, 0x018 OUT_POP, 0x01C STATUS, 0x020 SAT_COUNT, 0x024 SAMPLES_DONE. RUN reads the input FIFO count at RUN time and streams that many samples through the filter, one per clk_dsp. Coefficients from data/coeffs.hex (symmetric, 16 unique).

## Pin list

| port | board resource | dir |
|---|---|---|
| clk25 | clk_25 | in |
| led[1:0] | led[0:1] | out |
| sfp_tx_disable | sfp_tx_disable | out |

## Library entries considered

- fir (ip_lib): runtime-loadable coefficients, II 7 for dsp_bram; does not give one sample per clock with 16 DSPs and fixed symmetric coefficients. Not taken; written fresh.

## Resource prediction

jtag_bus about 90 LUT / 413 FF; 16 DSP48; FIFOs 2 to 4 RAMB tiles; total LUT 350-1500, FF 900-2500.
