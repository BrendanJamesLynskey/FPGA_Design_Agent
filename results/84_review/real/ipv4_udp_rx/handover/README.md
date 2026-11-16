# ipv4_udp_rx: handover (produced by review)

> Produced by review `ipv4_udp_rx` on design content `3da95ae853c9`. Nothing here was measured. Read `review.json` for the findings.

## What it does

ipv4_udp_rx is a byte-wide AXI-Stream IPv4/UDP receiver. It parses Ethernet frames without FCS and checks the IPv4 header (version, IHL, checksum, length), fragments, protocol, destination address and UDP length. It optionally verifies the UDP checksum including the pseudo-header, and picks the lowest enabled matching destination port. Payload bytes stream out with a one-byte holdback so tlast can carry the verdict as tuser, and header fields and event pulses accompany them. I found no functional bug in the RTL by reading. The main weaknesses are timing (it misses 125 MHz, which the docs state), documentation mismatches, and the limited reach of the formal and seeded-fault evidence.

## Interfaces

Slave AXI-Stream s_axis (8-bit data, tuser = bad frame). Master AXI-Stream m_axis (8-bit data, tuser = discard on tlast, 3-bit tdest = port index) with sideband m_src_ip, m_dst_ip, m_src_port, m_dst_port and m_len. Native config inputs own_ip, ports[N_PORTS*16] and port_en. Six one-clock event pulses. s_axis_tready = !fin && (!m_axis_tvalid || m_axis_tready), so it is combinational from m_axis_tready.

| Port | Direction | Width |
|---|---|---|
| `clk` | input | 1 |
| `s_axis_tdata` | input | [7:0] |
| `s_axis_tvalid` | input | 1 |
| `m_axis_tready` | input | 1 |

## Clocks and resets

Single clock `clk`, synchronous active-high `rst`, no crossings. The reset also clears many data registers (header fields, accumulators and so on), which is more than needed but harmless. Config inputs are used directly with no synchronisation, which is fine in one domain but they must be static during a frame.

Clock domains found in the code: clk.

## Architecture

A byte counter k, saturating at 0xFFFF, indexes the frame. Header fields are captured by case on k. Two 32-bit one's-complement accumulators run, one over the IP header and one over the UDP datagram. The header verdict (mine && len_ok && port_hit) is taken when the first payload byte arrives at k = u0+8, which sets fwd and f_dest. A single holding register h_d/h_v delays each payload byte by one so the last byte can be emitted with tlast and tuser = u_bad once the `fin` cycle follows tlast. In that cycle, if nothing was held, the reason is classified into an ev_* pulse. Large combinational cones (index compares, the fold and the 7-term u_tot add) are unpipelined.

## Files

- rtl: `formal/formal_udp_rx.sv`, `rtl/ipv4_udp_rx.sv`
- tests: `tb/udp_rx_cocotb.py`
- constraints: none
- docs: `CHANGELOG.md`, `README.md`

## Open critical and major findings

- none

## Known gaps and limits

- no synthesis, implementation or timing result exists in this handover
- no simulation was run by the review; the tests' coverage is the reviewer's reading
- Reset during a frame or during an output stall.
- s_axis_tuser asserted mid-frame, not just on the last beat.
- Frames shorter than 14 bytes, and back-to-back frames with m_axis stalled at tlast.
- Config changes during traffic.
- Full parameter cross product (CHECK_UDP=0 with ACCEPT_BCAST=1, BCAST/MCAST independence).
- Frames above Ethernet size, with k saturation.

## Next steps

- fix the critical and major findings, then re-run the review and the check suite at scope synth after a build
- answer the open questions below

## Open questions

- Is ev_* intended to pulse for frames dropped with s_axis_tuser set when the datagram is not for us? The code and model both stay silent there; confirm this is intended.
- What BMC depth was used for the formal runs? The result files are not provided.
