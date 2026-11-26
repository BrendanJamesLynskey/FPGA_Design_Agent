# P2: ROM, RAM and March C- memory test (kr260, xck26)

## Block diagram

```text
 CLK(25 MHz, C3) --+--> rst_gen --rst--> jtag_bus <== JTAG (BSCANE2 USER4)
                   |                      | h_we h_re h_addr[11:0] h_wdata[31:0]  ^ h_rdata[31:0]
                   |                      v                                       |
                   +------------------> p2_core
                                          |- register map (ID, BUILD, SCRATCH, MEM_*, MARCH_*)
                                          |- ROM 1024x32 (BRAM, $readmemh data/rom_init.hex)
                                          |- RAM 1024x32 (BRAM, init 0xC0DE0000+i), one port muxed host / march engine
                                          |- March C- FSM, error counter, first-error latch
                                          +-- led[1:0] = {DONE, BUSY}
 p2_top: sfp_tx_disable = 1 (constant)
```

## Clock plan
Single clock `clk`, 25 MHz (40 ns), board pin C3, no MMCM. The JTAG TCK domain exists only inside jtag_bus and is crossed by its own xpm_cdc_single / xpm_cdc_array_single primitives. Reset is internal: a counter holds `rst` (active high, synchronous) for 8 clocks after configuration; no memory content is affected by it.

## Pin list
- clk: 25 MHz board clock, C3
- led[1:0]: user LEDs (led[0] BUSY, led[1] DONE)
- sfp_tx_disable: SFP+ tx disable, constant 1
- JTAG via the dedicated configuration TAP (BSCANE2), no user pins.

## Design notes
- Memories are read with registered output (BRAM); host reads show data within 2 clocks and are held in h_rdata until the next h_re.
- While BUSY the march engine owns the RAM port; host RAM reads return 0 and writes are ignored.
- March engine: 2 backgrounds x 6 elements per pass, at most 4 clk per word per element, well under 1 s for 200 passes.
- INJECT_FAULT flips bit 0 of one read per pass at FAULT_ADDR (0).

## Predicted resources
jtag_bus about 90 LUT / 413 FF; core about 200-400 LUT, 150-300 FF; 2 BRAM36 (ROM and RAM; up to 4 tiles if split as RAMB18); 0 DSP.

## Library entries considered
ip_lookup not applicable: a ROM/RAM with a March FSM and a register map is not a standard-library function (CRC, filter, crossbar ...); written fresh.
