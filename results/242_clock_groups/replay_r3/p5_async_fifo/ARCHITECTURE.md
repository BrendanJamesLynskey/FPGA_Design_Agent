# p5_async_fifo_soak architecture

Asynchronous FIFO soak test: 25 MHz writer (PRBS-31) to 156.25 MHz reader (checker), host access over JTAG (`jtag_bus`, USER4).

## Block diagram

```text
 clk_25mhz --> [rst_gen: power-on counter, 16 clk] --rst--> jtag_bus (BSCANE2, tck) --h_*--> [p5_core]
                                                                                              |
  clk_wr (25 MHz) domain                          p5_core                    clk_rd (156.25 MHz) domain
  +-------------------------------+   +-----------------+   +---------------------------------+
  | CTRL, SCRATCH, ID, BUILD      |   |   xpm_fifo_async|   | pop gate (SLOW_READ /8)         |
  | prbs_wr -> write gate (!full) |-->| 512x32, Gray ptr|-->| prbs_rd checker, inject         |
  | WORDS_W STALL_W OVFL OCC_MAX  |   +-----------------+   | WORDS_R DATA_ERRS UNDERFLOWS    |
  | snapshot holding regs (7x32)  |<== xpm_cdc_handshake ===| (96-bit coherent transfer)      |
  +-------------------------------+==> RUN/SLOW (array_single), INJECT/CLEAR (handshake) ==>   |
 gt_refclk_p/n --> IBUFDS_GTE4 --> BUFG_GT --> clk_rd
 led[0]=RUN, led[1]=sticky error; sfp_tx_disable = 1
```

## Clock plan

- clk_wr = clk_25mhz (25 MHz, C3 pin): bus clock, writer, registers, snapshot.
- clk_rd = SFP MGTREFCLK0 via IBUFDS_GTE4 and BUFG_GT (156.25 MHz): reader. No GT channel.
- tck: inside jtag_bus, asynchronous to both. Constraints: set_clock_groups -asynchronous between clk_wr, clk_rd, tck; max_delay -datapath_only on FIFO Gray pointers.
- Reset model reprogram: no reset input; initial values; power-on counter (RESET_HOLD_CYCLES=16) drives jtag_bus rst; xpm_cdc_async_rst per domain releases the FIFO reset in both domains before RUN is honoured.

## Crossings
All through XPM primitives: jtag_bus internals (xpm_cdc_single/array_single), xpm_fifo_async, xpm_cdc_array_single (RUN, SLOW_READ), xpm_cdc_handshake (INJECT/CLEAR, reader counters), xpm_cdc_async_rst.

## Pin list
| port | dir | note |
|---|---|---|
| clk_25mhz | in | C3, 25 MHz |
| gt_refclk_p / gt_refclk_n | in | SFP+ MGTREFCLK0, 156.25 MHz |
| led[1:0] | out | led[0] RUN, led[1] sticky error |
| sfp_tx_disable | out | constant 1 |

## Library entries considered
ip_lookup: the library has no FIFO or clock-crossing block; the FIFO is xpm_fifo_async. PRBS is a 31-bit LFSR written fresh (small).

## Resource prediction
jtag_bus ~90 LUT / 413 FF; counters 7x32, snapshot 7x32, PRBS 2x31, handshake registers. LUT 300-800, FF 800-1500, 1 BRAM tile (RAMB36 or 2 RAMB18), 0 DSP. Note spec's "FF under 800" is tight given the 413 FF bus.
