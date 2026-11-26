# p2_mem_test architecture

Part xck26-sfvc784-2LV-c (KR260), single 25 MHz clock domain `clk`.

## Block diagram

```text
 JTAG (BSCANE2 USER4)
        |
   +----------+  h_we/h_re/h_addr/h_wdata   +-----------------------------+
   | jtag_bus |---------------------------->| p2_mem_core                 |
   | (data/)  |<----------------------------|  regs: ID BUILD SCRATCH     |--> led[1:0]
   +----------+  h_rdata                    |  MEM_ADDR/CTRL, ROM_DATA    |
        ^ rst                               |  RAM_DATA, MARCH_* regs     |
        |                                   |  ROM 1024x32 (BRAM)         |
   +----------+                             |  RAM 1024x32 (BRAM)         |
   |por_reset |--- rst -------------------->|  march_engine (March C-)    |
   +----------+                             +-----------------------------+
 clk --> all blocks            sfp_tx_disable = 1 (constant, top)
```

## Clock plan
One clock, `clk` at 25 MHz (pin C3), period 40 ns. No MMCM, no derived clocks.
jtag_bus handles the TCK crossing internally with its own xpm_cdc primitives;
the design has no other crossings.

## Reset
Internal power-on counter holds active-high synchronous `rst` for 8 clocks.
Only control registers are reset; RAM/ROM contents come from configuration.

## Memory
ROM: $readmemh from data/rom_init.hex, RAM: init 0xC0DE0000+i, both
1 clock read latency in block RAM (2 RAMB36). The host RAM port and the March
engine share the RAM port through a mux; host accesses are ignored while BUSY.

## Pin list
- clk: C3 (25 MHz)
- led[1:0]: board user LEDs (led[0] BUSY, led[1] DONE)
- sfp_tx_disable: SFP+ tx disable, constant 1

## Resource prediction
jtag_bus ~90 LUT / 413 FF; core ~200-400 LUT, ~150-400 FF (32-bit scratch, address,
error and first-error registers, counters). Total LUT 250-700, FF 550-950, BRAM 2-3, DSP 0.

## Library entries considered
None: ip_lookup not needed; ROM/RAM/March engine are specific and small, and
the library has no memory-test block.
