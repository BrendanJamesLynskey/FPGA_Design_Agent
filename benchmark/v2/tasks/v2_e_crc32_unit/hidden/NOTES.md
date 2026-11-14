# v2_e_crc32_unit: points the request leaves open on purpose

A good interview asks about each; the oracle replies from `spec.yaml`.

- Which CRC: Ethernet CRC-32, not CRC-16 or CRC-32C. spec.md names zlib and the polynomial.
- The intact test is the constant residue (spec.md says only 'ends in its own check value, low byte first').
- The check of no bytes is zero (final inversion of the start value), and the flag is 0 for no bytes.
- DATA reads back the last byte; COUNT is 16-bit wrapping; offsets and masks (only bit 0 of CLEAR).
