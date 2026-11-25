# Architecture: p3_crc32 (Ethernet CRC-32, 4 bytes/clk, JTAG register access)

## Block diagram

```text
 clk_25 (C3, 25 MHz) --> BUFG --> MMCM (x4 -> 100 MHz) --> BUFG --> clk
                                   | locked
                                   v
                          reset_gen (xpm_cdc_async_rst, hold 8 clk) --> rst (active high)

 JTAG (BSCANE2 USER4) --> jtag_bus (data/jtag_bus.sv, unmodified)
        TCK -> clk crossings inside jtag_bus (xpm_cdc_single, xpm_cdc_array_single)
        h_we h_re h_addr[11:0] h_wdata[31:0]  -->  crc32_core  --> h_rdata[31:0] (back to jtag_bus)
 crc32_core: register file (ID, BUILD, SCRATCH, CTRL, PUSH4, PUSH_N, TAIL_LEN, CRC,
             BYTE_COUNT, BUSY_CYCLES) + 32-bit-parallel CRC update (4 bytes/clk)
             + heartbeat (led[0]) ; led[1] = MMCM locked
 BUILD word: USR_ACCESSE2 in the top, passed to the core as a port
 sfp_tx_disable = 1 constant
```

## Clock plan
- clk_25: board clock, 25 MHz, constrained at 40 ns. Used only by the MMCM.
- clk: 100 MHz from MMCM (VCO 1000 MHz, CLK_MULT_NUM_X1000=40000), through BUFG. All logic runs in clk.
- The MMCM locked signal (async to clk) enters the reset generator, xpm_cdc_async_rst: assert asynchronously, release synchronously, held RST_HOLD_CYCLES=8 clk. led[1] shows locked through a 2-FF synchroniser.
- JTAG TCK to clk crossing is inside jtag_bus (xpm CDC macros).

## Pin list (board resources)
- clk_25: 25 MHz clock, C3
- led[1:0]: user LEDs
- sfp_tx_disable: constant 1
- h_* ports: internal, no pins (jtag_bus <-> core)

## Library entries considered
- crc32_step (variant word, latency 1, II 1, 95 LUT / 33 FF measured on Artix-7): fits the update function, but it is stateless and handles only a 32-bit word; PUSH_N needs 1 to 3 byte updates and the INIT/same-cycle-drop control. Not taken: the core writes its own small combinational update (word and tail-length variants) for one-cycle PUSH.
- eth_mac_rmii, match_exact: not relevant.

## Resources
jtag_bus about 90 LUT / 413 FF; core about 150-250 LUT and about 200 FF; reset and MMCM small.
