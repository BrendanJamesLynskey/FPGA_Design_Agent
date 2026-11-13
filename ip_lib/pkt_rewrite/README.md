# pkt_rewrite 0.1.0

Applies a match-action result as the packet streams: drop, MAC rewrite, VLAN push/pop/VID, TTL/hop-limit decrement, IPv4 destination rewrite, with IPv4 and TCP/UDP checksums updated incrementally (RFC 1624 eqn 3).

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| (none) | | | |

Out-of-space values fail at elaboration with `$error` (tested: no parameters).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tuser 1)
- `s_meta`: axis (dir slave, tdata 640). {parsed header, action}, one a packet
- `m_axis`: axis (dir master, tdata 8, tuser 1, tdest 7)

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- data: 3 clocks (measured; a two-byte window lets a checksum's high byte be patched)
- throughput: 1 byte a clock; a VLAN push costs 4 clocks of input stall

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_rewrite_rtl.py`.

Try it: `python3 -m pytest flow/net/tests/test_40_rewrite_rtl.py`.

Parameter points simulated: `defaults`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `rfc1624_without_complement` | the incremental update adds the deltas to the checksum itself rather than to its complement | caught |
| `udp_zero_checksum_rewritten` | a UDP datagram sent without a checksum gets one (RFC 768 says leave zero) | caught |
| `pop_loses_tlast` | a frame that ends inside the popped tag loses its end (a bug found and fixed in this brief) | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).

## Known gaps and limits

- Limits: no IPv6 address rewrite; the action word is 160 bits (tables usually store an index into an action RAM).
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.

## Next steps

1. Measure the out-of-context cost with python -m flow.ipchar pkt_rewrite after adding a characterisation entry.

## History

- 0.1.0 (2026-11-11): First version (brief 40): simulated bit-exact against the Python golden model; see README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
