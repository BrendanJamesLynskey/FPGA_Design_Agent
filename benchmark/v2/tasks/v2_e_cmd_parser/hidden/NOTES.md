# Open points of v2_e_cmd_parser

The request does not settle these; the oracle's `spec.yaml` does.

- Order of the classes: framing, then check, then type, then length, then sequence (spec.md lists it; the interview should confirm).
- 'Oversize' includes trailing bytes after a complete packet and length bytes above 8, decided when the fourth byte arrives.
- A packet that fails type or length does not move the sequence state; a replayed or stale one neither.
- Half-span rule: delta 0x8000 is out of order; delta 1..0x7FFF is new; the first packet after reset has no previous number.
- Both type and length errors share one counter and have different result codes.
- A one-byte packet is possible (the end flag on the first byte): short.
- Register offsets, widths and zero fill of the payload fields.
