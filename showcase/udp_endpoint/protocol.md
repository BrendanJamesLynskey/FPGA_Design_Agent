# UDP endpoint protocol (generated from showcase/udp_endpoint/model/udp_ref.py; do not edit by hand)

Command: `TYPE LEN SEQ(2) PAYLOAD CRC32(4)`. Response: `TYPE|0x80 STATUS SEQ(2) LEN PAYLOAD CRC32(4)`. Numbers are big-endian;
the CRC (IEEE 802.3, over every byte before it) is little-endian. `LEN` is at most 8 in a command.

| Type | Meaning |
|---|---|
| 1 | READ: payload ADDR(2); reply payload DATA(4) |
| 2 | WRITE: payload ADDR(2) DATA(4) |
| 3 | STATUS: no payload; reply 16 counter bytes + TLM_ON |
| 4 | TLM_START: payload PERIOD(2) ticks, 0 keeps the current one; minimum 4 |
| 5 | TLM_STOP: no payload |

| Status | Name |
|---|---|
| 0 | OK |
| 1 | BAD_TYPE |
| 2 | BAD_LEN |
| 3 | BAD_ADDR |
| 4 | BAD_SEQ |
| 5 | READ_ONLY |

## Order of checks (the first that fails decides)

1. Framing. A packet whose `LEN` is above 8, or that runs past `4 + LEN + 4` bytes, is oversize: dropped, counted, no reply. A packet
   that ends early (including an empty one) is truncated: dropped, counted, no reply.
2. CRC. A wrong CRC is dropped, counted, no reply (the sequence number cannot be trusted).
3. Type unknown: reply BAD_TYPE. `LEN` not the one the type needs: reply BAD_LEN. Both count as `protocol`.
4. Sequence. A number is newer when `(seq - last) mod 65536` is 1 to 0x7FFF; The first command after reset may carry any number.
   Equal is a replay and older is out of order: both are refused with reply BAD_SEQ, counted separately, and change nothing. A newer number may skip
   ahead (a lost command is not an error).
5. Address and access. An address above 7 replies BAD_ADDR; a write to a read-only register replies READ_ONLY (both count as `protocol`).
   An accepted command consumes its sequence number even when step 5 then fails.

A command that passes every check is executed once and counted in `ok` (STATUS, and a READ of CMDS or ERRS, show the counts as they were before it). Rejected packets change no register, no sequence state and no telemetry state.

## Registers (ADDR)

| Addr | Name | Access |
|---|---|---|
| 0 | ID (0x55445031) | read only |
| 1 | SCRATCH0 | read/write |
| 2 | SCRATCH1 | read/write |
| 3 | SCRATCH2 | read/write |
| 4 | CMDS (accepted commands) | read only |
| 5 | ERRS (all rejected packets) | read only |
| 6 | PERIOD (ticks) | read only |
| 7 | UPTIME (ticks) | read only |

## Counters (STATUS reply, 16 bits each, wrapping, then the telemetry frame count and a TLM_ON byte)

ok, bad_crc, truncated, oversize, replay, out_of_order, protocol.

## Telemetry

While on, one frame is due every PERIOD ticks, counted from the TLM_START command (a period below 4 is raised to 4; the new period
applies from the next start). The pacer holds at most one frame: a frame that falls due while the previous one has not been taken by the transmitter is
dropped and counted as an overrun, never queued, so the rate cannot exceed 1 per PERIOD ticks. Frame: type 0x40|0x80, status 0, its own sequence
number from 0, payload UPTIME(4) OK(2) ERRORS(2), CRC.
