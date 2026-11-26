# p3_crc32 architecture

CRC-32 (Ethernet, reflected) engine, 4 bytes per clock, registers over JTAG (jtag_bus, USER4). No GT used.

## Block diagram

```text
 clk_25 (C3) --> MMCM (x40/8) --> clk 125 MHz (BUFG)
                    | locked
                    v
              crc32_rst_gen (xpm_cdc_async_rst) --> rst (active high, sync)

 JTAG --> jtag_bus (data/jtag_bus.sv, unchanged, TCK->clk via xpm_cdc)
            | h_we h_re h_addr h_wdata   ^ h_rdata
            v                            |
        crc32_core: register decode (ID, BUILD, SCRATCH, CTRL, PUSH4, PUSH_N,
        TAIL_LEN, CRC, BYTE_COUNT, BUSY_CYCLES) + 32-bit CRC datapath
        (one 4-byte or 1..3-byte update per clock) + counters + heartbeat
            |--> led[0] = MMCM lock, led[1] = heartbeat
 sfp_tx_disable = 1 constant
```

## Clock plan

clk_25 (25 MHz board input) feeds an MMCM (VCO 1000 MHz, divide 8) giving clk = 125 MHz, the only
design clock; everything including jtag_bus runs on it. The JTAG TCK domain is inside jtag_bus,
crossed with xpm_cdc primitives there. Reset: rst is active high, asserted while the MMCM is not
locked, released synchronously through xpm_cdc_async_rst.

## Pin list

- clk_25: C3 (LVCMOS18), 25 MHz input
- led[0]: F8, led[1]: E8 (LVCMOS18)
- sfp_tx_disable: Y10 (LVCMOS33), constant 1

## Library entries considered

- crc32_step (variant word, latency 1, II 1, 95 LUT / 33 FF on Artix-7): not taken. The core needs
  the state register inside the datapath with 1..4 byte updates (PUSH_N tails) and INIT; the entry is
  a 4-byte stateless step only, so a small purpose-written CRC function is simpler.
- eth_mac_rmii, match_exact: not relevant.

## Resources

jtag_bus about 90 LUT / 413 FF; core about 250 LUT / 200 FF; MMCM 1; no BRAM, no DSP.
