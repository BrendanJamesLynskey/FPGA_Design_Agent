# P3 CRC-32 engine: architecture

## Block diagram

```text
 clk25 (C3, 25 MHz) --> MMCM (x40 /10) --> BUFG --> clk 100 MHz
                          | locked
                          v
                  reset_gen (xpm_cdc_async_rst + >=4 clock hold) --> rst (active high, sync)

 JTAG --> jtag_bus (BSCANE2 USER4, data/jtag_bus.sv, unchanged)
            | h_we h_re h_addr[11:0] h_wdata[31:0] ; h_rdata[31:0]
            v
        crc_core  (the simulated toplevel)
          +- register decode: ID, BUILD (input build_word), SCRATCH, CTRL,
          |    TAIL_LEN, CRC, BYTE_COUNT, BUSY_CYCLES; PUSH4/PUSH_N write-only
          +- crc32_step (library, IMPL=word): 4 bytes per clock, crc_in = state
          +- tail logic: 1..3 byte update (bytewise, combinational, registered)
          +- BYTE_COUNT, BUSY_CYCLES counters
          +- led[0] = locked (synchronised), led[1] = 0
 top: jtag_bus + reset_gen + USR_ACCESSE2 + crc_core; sfp_tx_disable = 1
```

## Clock plan
- clk25: board 25 MHz input, only feeds the MMCM.
- clk: 100 MHz (25 x 40 / 10, VCO 1000 MHz), free running, the only clock for all logic including jtag_bus's register side.
- Crossings: MMCM locked (async) into clk through xpm_cdc_async_rst in reset_gen; jtag_bus has its own internal xpm_cdc (TCK to clk).

## Reset
One active-high synchronous `rst`, held while unlocked and at least 4 clocks after lock. Only control registers are reset (SCRATCH, TAIL_LEN, CRC state, counters, rdata); no datapath reset.

## Behaviour decisions
- Write takes effect the clock after h_we (registered push, 1 word per clock). CRC register reflects push within 2 clocks. Read data registered: valid 1 clock after h_re and held.
- INIT wins over a push in the same clock. CRC register reads state XOR 0xFFFFFFFF; empty message reads 0 because state is 0xFFFFFFFF after INIT and reset.
- BUSY_CYCLES +1 per push with N>0 (PUSH4 or PUSH_N with N 1..3).
- TAIL_LEN masked to 2 bits. WO registers read 0; unmapped read 0; RO writes ignored.

## Library entries considered
- crc32_step (variant word, latency 1, II 1; 95 LUT, 33 FF measured Artix-7 at 4 ns): taken for the 32-bit-per-clock datapath. Unverified label, so the bench checks it against zlib.
- eth_mac_rmii, match_exact: not relevant.

## Pin list
- clk25 (C3), led[1:0], sfp_tx_disable. No other pins; no GT used.

## Resources
jtag_bus ~90 LUT / 413 FF; core ~ 250 LUT / 200 FF; MMCM 1; BSCAN 1; USR_ACCESS 1; no BRAM or DSP. Fits resources_expected only in LUT; FF prediction is above spec's "under 400" because jtag_bus alone has 413 FF.
