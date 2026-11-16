# AGENT handover (produced by review) id=ipv4_udp_rx review=ipv4_udp_rx sha=3da95ae853c9
top=formal_udp_rx clocks=clk rtl=formal/formal_udp_rx.sv,rtl/ipv4_udp_rx.sv tests=tb/udp_rx_cocotb.py constraints=none
summary: ipv4_udp_rx is a byte-wide AXI-Stream IPv4/UDP receiver. It parses Ethernet frames without FCS and checks the IPv4 header (version, IHL, checksum, length), fragments, protocol, destination address and UDP length. It optionally verifies the UDP checksum including the pseudo-header, and picks the lowest enabled matching destination port. Payload bytes stream out with a one-byte holdback so tlast can carry the verdict as tuser, and header fields and event pulses accompany them. I found no functiona
facts: read from sources; no measurement; no build; no simulation by the review
open: 
gaps: no synthesis, implementation or timing result exists in this handover | no simulation was run by the review; the tests' coverage is the reviewer's reading | Reset during a frame or during an output stall. | s_axis_tuser asserted mid-frame, not just on the last beat. | Frames shorter than 14 bytes, and back-to-back frames with m_axis stalled at tlast. | Config changes during traffic.
next: fix the critical and major findings, then re-run the review and the check suite at scope synth after a build | answer the open questions below
