# Bring-up: P2 ROM, RAM and March C- test (kr260)

## Setup
- KR260 powered, JTAG cable connected, bitstream of this design programmed.
- The 25 MHz clock (C3) runs; the host reaches registers through the JTAG USER4 register bus.
- LEDs: led[0] = BUSY, led[1] = DONE. SFP+ tx disable is constant 1.

## Testing
1. Read 0x000: pass if 0x20920001, else fail.
2. Read 0x004: pass if it equals the bitstream USR_ACCESS word (non-zero build stamp).
3. Write 0x008 with 0x12345678 and read back: pass if equal; after reset it reads 0.
4. Set MEM_ADDR(0x10)=0, MEM_CTRL(0x1C)=1, read ROM_DATA(0x14) 16 times: pass if the words equal the first 16 lines of data/rom_init.hex and MEM_ADDR reads 16.
5. Read RAM_DATA(0x18) at addresses 0, 1, 500, 1023 with AUTOINC clear: pass if each is 0xC0DE0000 + address.
6. Write RAM_DATA at address 7, read back: pass if equal and MEM_ADDR is unchanged.
7. Set MARCH_PASSES(0x24)=2, write MARCH_CTRL(0x20)=1, poll MARCH_STATUS(0x28) until bit 0 is 0: pass if the status is 0x00020002, MARCH_ERRS(0x2C)=0, MARCH_FIRST_ERR(0x30)=0xFFFFFFFF and RAM reads 0.
8. Set MARCH_PASSES=3, write MARCH_CTRL=3 (START and INJECT_FAULT): pass if MARCH_ERRS=3 and MARCH_FIRST_ERR=0.
9. Run `python -m flow.bringup` (or the stage's bringup command); every check must print ok.

## Debug aids
- led[0] on means the march engine is running; led[1] on means a run finished.
- MARCH_STATUS bits 31:16 show passes completed.
- SCRATCH (0x008) checks that the JTAG bus itself works.

## If it fails
- ID wrong or all ones: the bitstream is not this design or JTAG chain is not reaching USER4; reprogram.
- RAM init wrong: RAM was written earlier since configuration; reprogram and retry.
- MARCH_ERRS non-zero without INJECT_FAULT: RAM fault or timing; rerun, then check the build timing report.
- BUSY never clears: read MARCH_PASSES, it must be 1..65535; reprogram.
