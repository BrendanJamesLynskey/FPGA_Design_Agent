# Bring-up: P3 CRC-32 engine (KR260)

## Setup
- KR260 powered, JTAG (USB) connected to the host; no UART is used.
- Program the bitstream for `top` (MMCM 25 MHz -> 100 MHz). The host talks to the
  design through the JTAG register bus (BSCANE2 USER4, `jtag_bus`).
- No SFP module is needed; `sfp_tx_disable` is held at 1 (laser off).

## Testing
1. Check LED0 is on (MMCM locked) and LED1 is off. Fail if LED0 is off.
2. Read 0x000 (ID). Pass if it equals 0x20930001.
3. Read 0x004 (BUILD). Pass if it is the bitstream's USR_ACCESS word (non-constant
   per build, matches the build stamp).
4. Write 0x008 (SCRATCH) with 0xA5A55A5A and read back. Pass if equal; after a reset
   it reads 0.
5. Write 1 to CTRL (0x010), read CRC (0x020). Pass if 0x00000000 and CTRL reads 0.
6. Write PUSH4 (0x014) 0x34333231 then 0x38373635, read CRC. Pass if it equals
   zlib.crc32(b"12345678") = 0x9AE0DAAF; BYTE_COUNT (0x024) = 8; BUSY_CYCLES (0x028) = 2.
7. Random messages of lengths 0..200 (PUSH4 for words, TAIL_LEN 0x01C plus PUSH_N
   0x018 for the tail): CRC equals zlib.crc32 and BYTE_COUNT equals length for each.
8. Write TAIL_LEN = 7. Pass if it reads 3.
Run all of these with the bring-up tool; every check line must show ok.

## Debug aids
- Scratch register for bus round-trip tests; BUILD register to identify the bitstream.
- BYTE_COUNT and BUSY_CYCLES show whether pushes arrive.
- LED0 shows MMCM lock.

## If it fails
- ID reads 0 or all ones: JTAG chain or wrong bitstream; reprogram.
- BUILD reads 0: bitstream written without a USR_ACCESS value; not a logic fault.
- LED0 off: MMCM not locked; check the 25 MHz oscillator and reprogram.
- CRC wrong but counts right: check TAIL_LEN was set before PUSH_N and that INIT
  was written before the message.
