# dds_awg changelog

## 0.2.0 (2026-11-12; reset change 2026-11-14)

- 2026-11-14 (brief 70): the `bram` variant's table register has no reset or enable pin: the reset and the tick choose the read address instead (AMD DRC REQP-1840), and the table is a constant computed by a function (the old `$rtoi` in an initial block is not read by the reset check's front end). Same values and behaviour; the sine table entries are bit-identical (checked against the old expression for four table sizes).

- Implementation variants: `IMPL = "bram"` (default; the sine table read one clock early at the next phase into a block RAM register) and `IMPL = "lut"` (asynchronous LUT ROM). Same ports, function and latency; both bit-exact against the model; measured out of context (built alone, no I/O constraints) on the xc7a100t. Seeded faults for both variants.

## 0.1.0 (2026-11-11)

- First version: simulated against the Python models, seeded faults caught, measured on the Nexys A7-100T inside designs/b30_hil_audio where noted in README.md.
