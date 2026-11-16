# icmp_echo: handover (produced by review)

> Produced by review `icmp_echo` on design content `93ab8705e205`. Nothing here was measured. Read `review.json` for the findings.

## What it does

icmp_echo answers ICMP echo requests for one IPv4 address on a byte-wide AXI-Stream link. It stores each received frame in a RAM (block or LUT RAM) while checking the Ethernet, IP and ICMP fields and both checksums. If the frame is a valid echo request and the buffer is free, it replays the stored frame with addresses swapped, a fixed TTL, ICMP type 0 and RFC 1624 incrementally updated checksums. Only one request is held at a time; a request arriving while a reply is pending is dropped and flagged with ev_busy. Evidence is cocotb against a Python model with scapy, SymbiYosys bounded checks and an out-of-context Artix-7 build. The design has not been run on a board.

## Interfaces

s_axis: 8-bit AXI-Stream in, tready tied to 1, tuser marks a bad frame, frames carry no FCS. m_axis: 8-bit AXI-Stream out with tvalid/tready/tlast and registered outputs. own_mac and own_ip are static configuration inputs. Four one-clock event pulses: ev_request, ev_reply, ev_busy, ev_bad. Parameters are BUF_BYTES (power of two, 128..16384), TTL (1..255) and RAM (bram or lutram).

| Port | Direction | Width |
|---|---|---|
| `clk` | input | 1 |
| `s_axis_tdata` | input | [7:0] |
| `s_axis_tvalid` | input | 1 |
| `m_axis_tready` | input | 1 |

## Clocks and resets

One clock, clk, and one synchronous active-high reset, rst. There are no clock crossings and no asynchronous resets. Control state and header/accumulator registers are reset. The RAM and the read data register rq are not, which is fine. The event pulses default to 0 and are cleared in reset.

Clock domains found in the code: clk.

## Architecture

A receive side counts bytes with k (saturating) and captures header fields at fixed offsets. It accumulates the IP header sum (ip_acc) and the ICMP sum (ic_acc, limited to the IP total length). It writes the frame into mem. `fin` pulses one clock after tlast, and `ok` is then evaluated combinationally from the captured fields. `blocked` stops a frame that starts right after a request's last byte from being stored over the request. The reply side starts at fin&&ok&&f_store and sets busy. It computes the new IP and ICMP checksums incrementally and reads the RAM with an address swap for the IP source and destination (offsets 26..33). A small skid-style pipeline (rq, rv, rj, take) feeds m_axis, and out_byte substitutes the MACs, TTL, checksums and ICMP type.

## Files

- rtl: `formal/formal_icmp.sv`, `rtl/icmp_echo.sv`
- tests: `tb/icmp_cocotb.py`
- constraints: none
- docs: `CHANGELOG.md`, `README.md`

## Open critical and major findings

- none

## Known gaps and limits

- no synthesis, implementation or timing result exists in this handover
- no simulation was run by the review; the tests' coverage is the reviewer's reading
- Reset in flight.
- Datagram length exactly at the buffer limit.
- TTL=1.
- Runt frames after a request (stale fields).
- Formal coverage of the bram variant and of reply bytes other than 13.
- Behaviour on frames addressed to another MAC.

## Next steps

- fix the critical and major findings, then re-run the review and the check suite at scope synth after a build
- answer the open questions below

## Open questions

- Does the upstream MAC filter frames by destination MAC, so this block need not?
- Should a ping to the broadcast address or from a broadcast/multicast source be answered or suppressed?
