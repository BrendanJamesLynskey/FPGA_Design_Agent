# p4_fir32 architecture

32-tap symmetric FIR, 16-bit data, with 1024-deep input and output FIFOs, on the KR260 (xck26). The host reaches it through the JTAG register bus `jtag_bus`.

## Block diagram

```text
                  clk_25 (C3, 25 MHz)
                   |        \
                   |         +--> MMCM --> clk_dp 250 MHz, locked
                   v                         |
 JTAG --> jtag_bus --h_*--> fir_core          |
 (BSCANE2)   (clk_25)       |  regs, LEDs     |
                            |                 v
                            +--> in_fifo  (xpm_fifo_async 1024x16) --> fir_datapath
                            |                                          16 pre-add, 16 DSP,
                            +<-- out_fifo (xpm_fifo_async 1024x16) <--  round/shift/sat,
                            |                                          SAT/DONE counters
                            +--> run/clear pulse, busy, counters (CDC)
 reset_gen: rst (jtag_bus) --> sync per domain; clk_dp reset also held until MMCM locked
 fir32_top: led[1:0] = {out FIFO not empty, BUSY}; sfp_tx_disable = 1
```

## Clock plan

- clk_25: board clock on C3, 25 MHz, is the bus clock for jtag_bus, fir_core, FIFO bus sides.
- clk_dp: 250 MHz from an MMCM (VCO 1000 MHz: mult 40, div 1, out divide 4) via BUFG. Datapath and FIFO datapath sides. Target WNS >= 0.
- Every crossing uses an XPM primitive (see architecture.yaml crossings). Reset is active high inside, synchronous, released synchronously by xpm_cdc_async_rst.

## Datapath

One sample per clk_dp cycle. Pipeline: delay line of 32 samples; pre-add x[n-k]+x[n-31+k] (17 bit); 16 DSP multiplies by h[k] from data/coeffs.hex; adder tree in 40-bit; add 0x4000, arithmetic shift 15, saturate. Fixed latency about 10 cycles. RUN processes min(input count, output free space) samples; CLEAR zeroes history and counters and empties FIFOs.

## Pin list

| port | dir | board resource | pin |
|---|---|---|---|
| clk_25 | in | clk_25 | C3 |
| led[0] | out | led[0] | F8 |
| led[1] | out | led[1] | E8 |
| sfp_tx_disable | out | sfp_tx_disable | Y10 |

## Library entries considered

- `fir` (ip_lib): not taken. It has runtime-loadable coefficients, valid/ready streams and a 4-DSP MAC form at II 7; the spec needs fixed symmetric coefficients, 16 DSPs and one sample per cycle.

## Resource prediction

jtag_bus about 90 LUT / 413 FF; two XPM FIFOs 1 BRAM36 each (up to 4 if split); 16 DSP.
LUT 500-1800, FF 900-2600, BRAM 2-4, DSP 16-18.
