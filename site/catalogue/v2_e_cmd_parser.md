# Command packet screener (v2_e_cmd_parser)

Domain E (networking), tier T2 (L1 probe of the endpoint ladder), Nexys A7-100T. Part of the UDP command and telemetry endpoint ladder project (brief 82). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_e_cmd_parser/`.

## The problem, and where it is used

The front end of a command protocol: decide for every packet whether it is a good command and, if not, which rule refused it, and hand over the fields of the good ones.

Any small command port (UDP, UART, CAN) needs the same ordered rules: framing, length, check value, type, then sequence number. The order decides which class a damaged packet lands in, and a refused packet must leave the screener ready for the next one.

## Hero diagram

Packet bytes stream in; a row of rule lights (too long, too short, bad check, unknown type, not new) is checked left to right and the first that applies lights up; a good packet fills the field boxes (type, sequence number, payload).

## Animation plan (driven by `hidden/model.py`)

Use the Model in hidden/model.py to feed packets (good, truncated, oversize, corrupted, repeated, stale) and show the class, the counters and the last accepted number, with a button that damages a byte.

## Interface

Shell registers: the packet byte with an end flag, result, fields of the last good packet and per-class counters. LED[15:0] shows the good-packet count and a class summary.

## Acceptance criteria in plain words

Every packet lands in exactly one class and the first rule that applies decides; the check value is the Ethernet CRC-32 over every byte before it; the sequence number is new when it is 1 to 32767 ahead of the last accepted one (modulo 65536) and the first packet after reset may carry any number; a refused packet changes only its counter and the result.
