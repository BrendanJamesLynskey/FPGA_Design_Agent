# fir32_sym architecture (KR260, xck26-sfvc784-2LV-c)

## Block diagram

```text
 clk_25 (C3) --> reset_gen --rst--> jtag_bus <--> JTAG USER4
     |                                  | h_we/h_re/h_addr/h_wdata/h_rdata
     +--> MMCM (x10) --> clk_dp 250MHz  v
     |           locked -> reset_gen   fir32_core (clk_25) --> led[1:0]
     |                                  |  in_fifo (xpm async, 1024x16)  --+
     |                                  |  run/clear handshake CDC         |
     |                                  |  out_fifo (xpm async, 1024x16) <-+
     |                                  v                                  
     +-- clk_dp domain: reset_sync -> fir_datapath (pre-add + 16 DSP48E2, round, >>>15, saturate)
 sfp_tx_disable = 1 (constant)
```

## Clock plan
- clk_25: 25 MHz board clock on C3, drives jtag_bus, register block, FIFO write/read sides.
- clk_dp: 250 MHz from one MMCM (VCO 1000 MHz, x40 / div 4 from 25 MHz, via BUFG), datapath and FIFO opposite sides.
- Reset: active-high rst on clk_25 (16 cycles and until MMCM locked); xpm_cdc_async_rst gives clk_dp reset. Reset model per spec: reprogram, control state also has initial values.
- All crossings use XPM primitives (see architecture.yaml).

## Behaviour summary
RUN snapshots the input FIFO count (limited to free output space), the datapath processes that many samples one per clk_dp cycle, BUSY clears when the last result is in the output FIFO. CLEAR aborts, empties FIFOs, zeroes history and counters. Coefficients from data/coeffs.hex via $readmemh (symmetric, 16 unique).

## Library entries considered
FIR/filter library lookup to be done at RTL stage; none assumed taken. Async FIFOs use AMD XPM since the library has none.

## Resource prediction
jtag_bus ~90 LUT / 413 FF; DSP 16-20; RAMB 2-4 tiles; LUT 700-2500; FF 900-3500; 1 MMCM; 0 GT.

## Pin list
| Port | Dir | Board resource | Note |
|---|---|---|---|
| clk_25 | in | C3 | 25 MHz board clock |
| led[1:0] | out | user LEDs | led0 BUSY, led1 sticky saturation |
| sfp_tx_disable | out | SFP+ tx disable | constant 1 |
