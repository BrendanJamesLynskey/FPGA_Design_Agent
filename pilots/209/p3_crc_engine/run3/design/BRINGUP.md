# Bring-up: p3_crc32 (Ethernet CRC-32 engine, JTAG register access)

## Setup
1. Connect the KR260 JTAG (USB) to the host; power the board.
2. Program build/base/crc32_top.bit with Vivado hardware manager.
3. Check that led[1] is on (MMCM locked) and led[0] blinks at about 1 Hz.
4. Registers are read and written over the BSCANE2 USER4 JTAG register bus (bus.rd / bus.wr). No UART exists.

## Testing
1. Read 0x000 (ID). Pass: 0x20930001. Fail: anything else.
2. Read 0x004 (BUILD). Pass: a non-zero USR_ACCESS stamp that is stable on re-read.
3. Write 0x008 (SCRATCH) with 0xA5A55A5A and read back. Pass: same value; a second pattern also matches.
4. Write 1 to CTRL (0x010), read CRC (0x020). Pass: 0x00000000; CTRL reads 0.
5. For messages of 0..65 bytes (including 1,2,3,4,5,7,8,63,64,65): INIT, PUSH4 (0x014) full words, set TAIL_LEN (0x01C) and PUSH_N (0x018) for the rest. Pass: CRC equals zlib.crc32 and BYTE_COUNT (0x024) equals the length.
6. INIT, 10 PUSH4 writes. Pass: BUSY_CYCLES (0x028) reads 10.
7. Write 7 to TAIL_LEN. Pass: the previous value is kept.
8. Read an unmapped address (0x100). Pass: 0. Writing to RO registers changes nothing.
The script hw_checks.py does all of this and leaves the design at INIT, TAIL_LEN 0.

## Debug aids
- led[1] = MMCM locked, led[0] = heartbeat (about 1 Hz).
- sfp_tx_disable is always 1.
- Reading 0x004 shows whether the bitstream is the expected build.

## If it fails
- ID wrong or reads all ones/zeros: JTAG chain or USER4 access problem, or the wrong bitstream; reprogram.
- led[1] off: MMCM not locked; check the 25 MHz clock and the reset.
- CRC mismatch on tail lengths only: check TAIL_LEN is set before PUSH_N.
- CRC mismatch everywhere: check byte order (bits 7:0 first) in the host script.
