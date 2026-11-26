# p2_mem_test bring-up

## Setup
- KR260 powered, JTAG (USB) connected, bitstream `p2_mem_test` programmed. Clock is 25 MHz on C3.
- The host reads and writes registers through the JTAG register bus (BSCANE2 USER4, `jtag_bus`).
- Registers are 32 bits at byte addresses: 0x000 ID, 0x004 BUILD, 0x008 SCRATCH, 0x010 MEM_ADDR,
  0x014 ROM_DATA, 0x018 RAM_DATA, 0x01C MEM_CTRL, 0x020 MARCH_CTRL, 0x024 MARCH_PASSES,
  0x028 MARCH_STATUS, 0x02C MARCH_ERRS, 0x030 MARCH_FIRST_ERR.
- No SFP module is needed; sfp_tx_disable is held 1.

## Testing
1. Read 0x000. Pass: 0x20920001. Fail: any other value (wrong bitstream or bus).
2. Read 0x004. Pass: non-zero build stamp equal to the bitstream's USR_ACCESS word.
3. Write 0x12345678 to SCRATCH, read back. Pass: same value; after reset it is 0.
4. ROM: set MEM_ADDR, read ROM_DATA at 0, 1, 2, 511, 1023. Pass: equals data/rom_init.hex words.
5. AUTOINC: set MEM_CTRL=1, MEM_ADDR=100, read ROM_DATA 8 times. Pass: words 100..107 and MEM_ADDR=108.
6. RAM init: read RAM_DATA at 0, 1, 1023. Pass: 0xC0DE0000 + address.
7. RAM write 0xA5A55A5A at address 5, read back. Pass: same value.
8. March: MARCH_PASSES=2, MARCH_CTRL=1, poll MARCH_STATUS. Pass: BUSY (bit 0) clears, DONE (bit 1) sets, passes completed (31:16) = 2, MARCH_ERRS = 0, MARCH_FIRST_ERR = 0xFFFFFFFF, any RAM word reads 0. LED0 lights while busy, LED1 when done.
9. Fault injection: MARCH_PASSES=3, MARCH_CTRL=3 (START + INJECT). Pass: finishes DONE, MARCH_ERRS > 0, MARCH_FIRST_ERR = 0.
10. Leave: MARCH_CTRL=0, MARCH_PASSES=1, MEM_ADDR=0, MEM_CTRL=0.

## Debug aids
- LED0 = BUSY, LED1 = DONE.
- MARCH_STATUS, MARCH_ERRS and MARCH_FIRST_ERR show the engine state at any time.
- A March pass takes about 0.82 ms at 25 MHz.

## If it fails
- ID wrong or reads time out: JTAG chain or bitstream not loaded; reprogram.
- ROM mismatch: data/rom_init.hex was not the file used at build.
- RAM accesses return 0 or are ignored: the March engine is BUSY; wait for DONE.
- March errors without injection: memory or timing fault; rerun, check timing report.
- Never ends: check MARCH_PASSES (0 counts as 1) and that the clock runs.
