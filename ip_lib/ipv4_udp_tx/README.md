# ipv4_udp_tx 0.1.0

UDP over IPv4 transmit: stores one payload, then sends Ethernet, IPv4 (header checksum, counting identification) and UDP headers (checksum over the pseudo-header, or none) followed by the payload.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated against an RFC 791/768 model with scapy recomputing both checksums; framing checked by bounded model checking; built alone out of context on an Artix-7 with Vivado 2026.1; not yet run on a board (the Nexys A7 network design carries it behind eth_mac_rmii; built, the board run waits for the owner's cabling check).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `MAX_PAYLOAD` | 1472 | 1..8972 | longest payload (1472: a 1500-byte MTU; 8972: a 9000-byte MTU) |
| `CSUM` | 1 | 0, 1 | 1 = compute the UDP checksum; 0 = send 0 |
| `TTL` | 64 | 1..255 |  |
| `RAM` | bram | bram, lutram | the payload buffer: block RAM or LUT RAM (the implementation variants) |

Out-of-space values fail at elaboration with `$error` (tested: `MAX_PAYLOAD=0`, `MAX_PAYLOAD=8973`, `CSUM=2`, `TTL=0`, `TTL=256`, `RAM=uram`).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tready True). one UDP payload per frame; s_dst_mac, s_dst_ip, s_src_port and s_dst_port are taken with the first beat
- `m_axis`: axis (dir master, tdata 8, tready True). Ethernet frames without FCS, 42 + payload bytes
- `config`: native; own_mac[47:0], own_ip[31:0]
- `events`: native; ev_sent, ev_too_long

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- frame: the first header byte on m_axis 4 clocks after the payload's last beat (store and forward; measured in the bench; the variants' declared latency)
- throughput: one datagram at a time: the payload in at a byte a clock, then the frame out at a byte a clock

## Evidence

cocotb against ip_lib/ipv4_udp_tx/model.py (RFC 791, 768, 1071) with scapy recomputing both checksums of every frame: random lengths up to and over MAX_PAYLOAD, payloads whose checksum computes to zero (sent as 0xFFFF), unicast and multicast destinations, input gaps and back-pressure; Icarus Verilog 12. Formal (bounded): every frame 42 bytes plus its payload, the AXI-Stream rules of brief 59 on m_axis, the input held while a frame is prepared or sent Tests: `flow/net/tests/test_63d_udp_tx_rtl.py`, `flow/net/tests/test_63d_formal.py`.
Parameter points simulated: `MAX_PAYLOAD=1472, CSUM=1, TTL=64, RAM=bram`; `MAX_PAYLOAD=64, CSUM=0, TTL=1, RAM=lutram`; `MAX_PAYLOAD=8972, CSUM=1, TTL=255, RAM=bram`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `udp_tx_zero_checksum_sent` | a computed checksum of 0 goes out as 0 (no checksum) instead of 0xFFFF | caught |
| `udp_tx_ident_stuck` | every datagram carries the same IP identification | caught |
| `udp_tx_length_plus_one` | the UDP length counts one byte too many | caught |
| `udp_tx_long_payload_sent` | a payload one byte over MAX_PAYLOAD is sent cut short instead of dropped | caught |

## Variants

Selected by `RAM`; every variant has the same ports, the same bit-exact result and the same tests. Latency is clocks from an accepted input to its result; II (initiation interval) is clocks between accepted inputs, 1 meaning a new input every clock.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `bram` | the payload buffer in block RAM | `4` | `1` | the default; measured: one RAMB18 at MAX_PAYLOAD 1472, 4 RAMB36 at 8972 (the depth rounds up to a power of two) |
| `lutram` | the payload buffer in LUT RAM | `4` | `1` | block RAM spoken for; measured: 276 LUTs as RAM at MAX_PAYLOAD 1472, 1692 at 8972 |

Measured at MAX_PAYLOAD 1472, CSUM 1, TTL 64: built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 8.0 ns clock (125 MHz), Vivado 2026.1 (build 6511674). Not run on a board.

| Variant | DSP | Block RAM tiles | LUT | Fmax estimate (MHz) | II | Latency |
|---|---|---|---|---|---|---|
| `bram` | 0 | 0.5 | 560 | 82 | 1 | 4 |
| `lutram` | 0 | 0 | 914 | 80 | 1 | 4 |

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); it is not a closure at that frequency. WNS (worst slack against the clock) below zero means the target was missed.

<details><summary>Every measured point (4 rows; source: <a href="char/xc7a100tcsg324-1.json">char/xc7a100tcsg324-1.json</a>)</summary>

| Variant | MAX_PAYLOAD | CSUM | TTL | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `bram` | 1472 | 1 | 64 | 560 | 251 | 0 | 0.5 | 0 | -4.265 | 81.5 | 0.006 | 4 | 1 |
| `bram` | 8972 | 1 | 64 | 532 | 269 | 0 | 4 | 0 | -4.862 | 77.7 | 0.010 | 4 | 1 |
| `lutram` | 1472 | 1 | 64 | 914 | 260 | 276 | 0 | 0 | -4.434 | 80.4 | 0.010 | 4 | 1 |
| `lutram` | 8972 | 1 | 64 | 2713 | 286 | 1692 | 0 | 0 | -5.507 | 74.0 | 0.018 | 4 | 1 |

Dynamic power is vectorless (default toggle rates, no simulation activity): use it to rank variants, not as a measurement. Regenerate with `python3 -m flow.ipchar ipv4_udp_tx` (Vivado, minutes per point).

</details>

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (memories inferred; ram_style steers the variants).
- Depends on: nothing.
- Limits: no fragmentation; no IP options; DSCP 0; one datagram buffered (the next waits); the destination MAC is the caller's (from arp_responder, or the multicast mapping); measured Fmax estimates are 74-82 MHz out of context: it closes at the 50 MHz of the RMII MAC but not at the 125 MHz of the RGMII MAC (the checksum adders are not pipelined).

## Cost table

measured costs are in the Variants section above.

Licence: MIT (this repository).
