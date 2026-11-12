# Build-ID guard on the board

Before arming, the capture reads the build ID that the bitstream carries in its USR_ACCESS register (over JTAG) and
arms only if it equals the debug build's own ID, so a capture never runs against a bitstream that its probe map does not
describe (for example after `capture --no-program`). Checked on the board on 2026-11-12 (Nexys A7-100T, Vivado 2026.1,
board memory only, one board job at a time). Summary: [guard.json](guard.json).

- [pass/](pass/): the reuse request replayed with the recorded parser reply. The board held build d2b75378, the
  expected one; the capture armed and passed its known-answer check again (count 0x0000 to 0x0042, read back 0x42).
  Supply and temperature at programming, arming and after upload are in `pass/capture.json` (inside the recommended
  operating conditions, no alarm).
- [refused/](refused/): `capture --no-program` with the PWM plan (build ff89fe4c) while the board held d2b75378.
  Nothing was armed: "the board holds build d2b75378, not the expected ff89fe4c; program the matching debug build first.
  Not arming anything."

The Vivado and hw_server logs are not kept, because they name the programming cable.
