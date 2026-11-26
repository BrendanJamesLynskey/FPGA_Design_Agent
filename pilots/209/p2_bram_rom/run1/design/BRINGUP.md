# Bring-up: p2_rom_ram_march (KR260)

## Setup
- KR260 powered, JTAG cable connected, bitstream `build/base/p2_top.bit` programmed (25 MHz clock, pin C3).
- The host talks to the design over the JTAG register bus (BSCANE2 USER4); there is no UART.
- Run the flow's bring-up (flow/bringup.py), which runs `hw_checks.py` on the real bus.
- SFP+ laser stays off (sfp_tx_disable = 1).

## Testing
1. Read 0x000 (ID). Pass: 0x20920001. Fail: anything else (wrong bitstream or bus).
2. Read 0x004 (BUILD). Pass: equals the bitstream USR_ACCESS stamp (non-zero for a stamped build).
3. Write 0x008 SCRATCH with a pattern, read back. Pass: same value; after reset reads 0.
4. Set MEM_CTRL=1 (AUTOINC), MEM_ADDR=0, read ROM_DATA (0x014) 16 times. Pass: words equal the first 16 lines of data/rom_init.hex and MEM_ADDR is 16.
5. Read ROM_DATA at 1020..1025. Pass: address wraps to 0 after 1023.
6. With AUTOINC clear, read ROM_DATA. Pass: MEM_ADDR unchanged.
7. Read RAM_DATA (0x018) from address 0. Pass: word i is 0xC0DE0000 + i.
8. Write two words to RAM_DATA at 100, read back. Pass: both match.
9. Set MARCH_PASSES=2, write MARCH_CTRL=1, poll MARCH_STATUS (0x028). Pass: DONE (bit 1) set, BUSY clear, bits 31:16 = 2, MARCH_ERRS (0x02C)=0, MARCH_FIRST_ERR (0x030)=0xFFFFFFFF; RAM reads 0.
10. Write MARCH_CTRL=3 (START + INJECT_FAULT). Pass: DONE, MARCH_ERRS=2 (one per pass), MARCH_FIRST_ERR=0x155.
11. LEDs: led[0] lit while BUSY, led[1] lit after DONE.

## Debug aids
- SCRATCH and ID tell whether the bus works at all.
- MARCH_STATUS shows BUSY/DONE and completed passes; MARCH_FIRST_ERR gives the failing address.
- The hw_checks run leaves registers at reset values (MARCH_PASSES=1).

## If it fails
- ID wrong or reads all ones/zeros: check the programmed bitstream and JTAG chain (USER4).
- ROM mismatch: confirm data/rom_init.hex is the file used at build.
- March never finishes: check the clock (LEDs) and that reset released.
- Errors without INJECT_FAULT: genuine RAM problem; rebuild and retry.
