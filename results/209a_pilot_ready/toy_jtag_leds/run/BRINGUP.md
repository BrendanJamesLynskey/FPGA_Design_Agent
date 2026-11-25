# jtag_blink bring-up

## Setup
- KR260 powered, JTAG cable connected, the bitstream `build/base/jtag_blink_top.bit` programmed (owner approves programming).
- The host talks to the design over the JTAG register bus (BSCANE2 USER4). The clock is 25 MHz; LEDs are led[1:0].
- The design resets itself 16 clocks after configuration; there is no reset pin.

## Testing
1. Read 0x000. Pass: 0x20920001. Fail: any other value (wrong bitstream or bus problem).
2. Read 0x004 (BUILD). Pass: a nonzero USR_ACCESS word that is the same on each read.
3. Write 0xA5A5A5A5 to 0x008 and read it back. Pass: same value. Write 0 afterwards.
4. Read 0x010. Pass: 0x00BEBC20 (12,500,000). Read 0x014. Pass: 0.
5. Write 0 to 0x010, read it. Pass: 1. Write 0x12345678, read it. Pass: same. Restore 0x00BEBC20.
6. Write 0xFFFFFFFF to 0x014, read it. Pass: 1 (led[1] on). Write 0, read it. Pass: 0 (both LEDs off).
7. Read 0x00C and 0x018. Pass: 0; a write to 0x018 changes nothing.
8. Optional visual check: with BLINK_DIV at the default write 1 to 0x014. Pass: led[1] on and led[0] toggles every 0.5 s. Write 0 afterwards.

`python -m flow.bringup` runs steps 1-7 automatically through `hw_checks.py`.

## Debug aids
- Scratch register 0x008 tests the bus path alone.
- Set BLINK_DIV small (e.g. 1) to see led[0] change state fast; led[1] shows BLINK_EN directly.
- Post-route reports are under build/base/ (timing_summary.rpt).

## If it fails
- ID reads 0 or all ones: the bitstream is not loaded or the JTAG chain/USER4 is wrong; reprogram.
- ID right but BLINK registers wrong: compare with spec.yaml register map.
- LEDs never change with BLINK_EN set: check BLINK_DIV was not left at a huge value.
- BUILD reads 0: the USR_ACCESS word was not set in the bitstream.
