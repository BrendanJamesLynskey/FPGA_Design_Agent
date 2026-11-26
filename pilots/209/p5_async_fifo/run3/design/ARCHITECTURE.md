# P5 asynchronous FIFO soak: architecture

## Block diagram

```text
 clk25 (C3) ──┬────────────────────────────────────────────┐
              │ clk25 domain                               │
  BSCANE2 ─ jtag_bus ─h_*─► soak_core ──► led[1:0]         │
              │            │  regs, CTRL, snapshot         │
 reset_gen ─rst            ├─ prbs_writer ─► async_fifo ───┼─► (Gray ptrs, xpm_cdc_gray)
              │            │                 512x32 BRAM   │
              │            │ handshake (xpm_cdc_handshake) │
 gt_refclk_p/n ─IBUFDS_GTE4─BUFG_GT─ gt_refclk 156.25 MHz  │
              │            └─ prbs_checker (reader, compare, counters)
 sfp_tx_disable = 1 (constant)
```

## Clock plan
- clk25: 25 MHz, board pin C3; writer, register port, jtag_bus, reset generator.
- gt_refclk: 156.25 MHz, SFP+ MGTREFCLK0 via IBUFDS_GTE4 and BUFG_GT; reader domain. No GT channel.
- The two are unrelated: asynchronous clock groups, every crossing set_max_delay -datapath_only (Gray pointers also set_bus_skew).
- Reset: active high `rst` from a 16-clock power-on counter in clk25, released into gt_refclk through xpm_cdc_async_rst. Synchronous resets elsewhere.

## Crossings
Gray pointers (xpm_cdc_gray, both directions), control and snapshot data by xpm_cdc_handshake, reset by xpm_cdc_async_rst.

## Pin list
- clk25 (in, C3), gt_refclk_p / gt_refclk_n (in, MGTREFCLK0)
- led[1:0] (out): led[0] RUN, led[1] sticky error
- sfp_tx_disable (out): constant 1

## Resources
jtag_bus is about 90 LUT and 413 FF; the rest about 400-1000 LUT, 400-1400 FF, one BRAM (512x32 = 0.5 tile as RAMB18 pair/RAMB36), 0 DSP.

## Library entries considered
ip_lookup not used: the library has no FIFO or clock-crossing block; XPM macros are used for crossings. PRBS is a short LFSR written fresh.
