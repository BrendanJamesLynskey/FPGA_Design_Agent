# Frame check unit (v2_e_crc32_unit)

Domain E (networking), tier T1, Nexys A7-100T. Part of the UDP command and telemetry endpoint ladder project (brief 82). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_e_crc32_unit/`.

## The problem, and where it is used

A byte-serial Ethernet CRC-32 with a flag that says when a packet ends in its own check value.

Every network receiver checks frames this way: Ethernet, many serial links and storage formats append a CRC and the receiver recomputes it. Running the register through the check bytes leaves a fixed constant when the packet is intact, so no separate comparison is needed.

## Hero diagram

A packet's bytes arrive one by one; below them, the 32-bit register shifts and folds in the polynomial. When the four check bytes (low byte first) go through, the register lands on the same constant for any intact packet; flip one bit and it misses.

## Animation plan (driven by `hidden/model.py`)

Use Model in hidden/model.py (zlib.crc32 of the bytes so far) to step one byte at a time: show the running check, the count and the intact flag, with a bit flip button.

## Interface

Shell registers: DATA (next byte), CLEAR, CHECK, INTACT, COUNT. LED[15:0] shows the low half of the check.

## Acceptance criteria in plain words

CHECK equals the standard CRC-32 of the bytes since the last clear (zero for none); INTACT is true exactly when the bytes are a message followed by its own check, low byte first; COUNT is a 16-bit byte count; clear and reset restart; register masks and unmapped offsets as listed.
