# pkt_parser 0.1.0

Streaming header parser, one byte a clock, no store-and-forward: Ethernet, 0-2 VLAN tags, IPv4 (checksum check, options skipped by IHL, fragments), IPv6, UDP/TCP ports; a parsed-header word beside the unchanged stream.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `MAX_VLAN` | 2 | 0, 1, 2 |  |

Out-of-space values fail at elaboration with `$error` (tested: `MAX_VLAN=3`).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tuser 1)
- `m_axis`: axis (dir master, tdata 8, tuser 1)
- `m_hdr`: axis (dir master, tdata 480). one word a packet, in packet order; layout in the RTL header and flow/net/model.py HDR_FIELDS

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- data: 1 clock
- header: 1 clock after the last byte it needs (L4 destination port, end of IP header, EtherType, or tlast)
- throughput: 1 byte a clock with no per-packet gap (60 clocks per 60-byte frame measured)

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_parser_rtl.py`.

Try it: `python3 -m pytest flow/net/tests/test_40_parser_rtl.py`.

Parameter points simulated: `MAX_VLAN=0`; `MAX_VLAN=1`; `MAX_VLAN=2`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `ipv4_options_ignored` | the IPv4 header is taken as 20 bytes whatever the IHL (the brief's example) | caught |
| `csum_carry_dropped` | the ones' complement end-around carry is lost | caught |
| `one_vlan_tag_only` | the inner tag of a double-tagged frame is taken as the EtherType | caught |
| `fragment_offset_ignored` | non-first fragments report payload bytes as ports | caught |
| `truncation_not_flagged` | a frame that ends inside a header is not marked | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).

## Known gaps and limits

- IPv6 extension headers are not walked (l4 flag 0); IPv4 total length is not checked against the frame.
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.

## Next steps

1. Measure the out-of-context cost with python -m flow.ipchar pkt_parser after adding a characterisation entry.
2. Check IPv4 total length against the frame and walk IPv6 extension headers if a caller needs either.

## History

- 0.1.0 (2026-11-11): First version (brief 40): simulated bit-exact against the Python golden model; see README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
