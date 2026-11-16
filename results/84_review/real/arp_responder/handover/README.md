# arp_responder: handover (produced by review)

> Produced by review `arp_responder` on design content `2a00846313f2`. Nothing here was measured. Read `review.json` for the findings.

## What it does

arp_responder is a single-clock ARP (RFC 826) block for one IPv4 address. It parses byte-wide Ethernet frames, replies to requests for own_ip, learns sender MACs into a small fully-associative cache with round-robin replacement, and answers next-hop lookups. On a miss it sends a rate-limited broadcast request. It flags address conflicts (RFC 5227) through ev_conflict and never caches the conflicting sender.

## Interfaces

s_axis: 8-bit AXI-Stream receive with tuser on tlast marking a bad frame, tready tied high. m_axis: 8-bit AXI-Stream transmit of 42-byte frames with tvalid/tready/tlast. Lookup: lk_valid/lk_ip in, lk_done/lk_hit/lk_mac out one clock later, plus flush. Static own_mac and own_ip inputs. Seven one-clock event pulses.

| Port | Direction | Width |
|---|---|---|
| `clk` | input | 1 |
| `s_axis_tdata` | input | [7:0] |
| `s_axis_tvalid` | input | 1 |
| `m_axis_tready` | input | 1 |
| `lk_valid` | input | 1 |
| `lk_ip` | input | [31:0] |

## Clocks and resets

One clock, clk, and one synchronous active-high reset, rst. There are no clock crossings and no asynchronous resets. Reset covers control state, the cache valid bits and the parse fields. own_mac and own_ip are static inputs treated as quasi-constant.

Clock domains found in the code: clk.

## Architecture

The receive path is a byte counter k that captures fields by index (et, htype, ptype, hlen, plen, op, sha, spa, tpa). It latches fin, fin_bad and fin_long at tlast, and the combinational arp_ok/for_me/learn terms are evaluated the following clock. The cache is a register array of valid/IP/MAC with priority-encoded known and free search and a round-robin pointer rr. Lookup is a combinational compare registered into lk_*, with a single holdoff timer and IP. Transmit is a small FSM with one reply slot and one request slot, replies first. A function arp_byte generates the frame bytes by index j, using the m_axis registers as a one-byte pipeline.

## Files

- rtl: `formal/formal_arp.sv`, `rtl/arp_responder.sv`
- tests: `tb/arp_cocotb.py`
- constraints: none
- docs: `CHANGELOG.md`, `README.md`

## Open critical and major findings

- F-e7dddd (major) `rtl/arp_responder.sv:93`: Parsed fields not cleared between frames; stale fields can validate a frame

## Known gaps and limits

- no synthesis, implementation or timing result exists in this handover
- no simulation was run by the review; the tests' coverage is the reviewer's reading
- ev_conflict is not counted in the main bench.
- Lookup concurrent with flush or learn.
- Alternating-address holdoff.
- Frames longer than 63 bytes (saturating k).
- Reset in flight during transmit or receive.
- A request arriving exactly at start_rep.

## Next steps

- fix the critical and major findings, then re-run the review and the check suite at scope synth after a build
- answer the open questions below

## Open questions

- Is own_ip/own_mac guaranteed static while frames are in flight?
- What is the intended behaviour for a lookup issued in the same clock as flush?
