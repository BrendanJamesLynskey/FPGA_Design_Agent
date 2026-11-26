# Architecture: p2_rom_ram_march (kr260, xck26)

## Block diagram

```text
 clk (C3, 25 MHz) --> por_reset --rst--> jtag_bus <--BSCANE2 USER4 (JTAG)
                          |                 | h_we h_re h_addr h_wdata / h_rdata
                          +-----rst-----> p2_core
                                           |- register map (ID, BUILD, SCRATCH, MEM_*, MARCH_*)
                                           |- ROM 1024x32 (readmemh data/rom_init.hex) BRAM
                                           |- RAM 1024x32 (init 0xC0DE0000+i) BRAM, shared host/march port
                                           |- March C- engine (1 op/clock)
                                           +-> led[1:0] (BUSY, DONE)
 p2_top: sfp_tx_disable = 1
```

## Clock plan
One domain, clk 25 MHz (40 ns), board pin C3, BUFG inferred. jtag_bus crosses TCK to clk internally with xpm_cdc primitives. Reset is a synchronous active-high power-on counter, 8 clocks.

## Pin list
- clk: C3 (25 MHz)
- led[1:0]: board user LEDs
- sfp_tx_disable: SFP+ tx disable, constant 1
- h_* are internal (no pins)

## Resources
jtag_bus ~90 LUT / 413 FF; core ~200 LUT / ~150 FF; 2 RAMB36 (ROM and RAM); 0 DSP; 0 GT.

## Library entries considered
ROM/RAM/march test are not covered by a library function; written fresh.
