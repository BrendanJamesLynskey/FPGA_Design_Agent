# AGENT handover (produced by review) id=ipv4_udp_tx review=ipv4_udp_tx sha=1b322337aa42
top=formal_udp_tx clocks=clk rtl=formal/formal_udp_tx.sv,rtl/ipv4_udp_tx.sv tests=tb/udp_tx_cocotb.py constraints=none
summary: ipv4_udp_tx is a store-and-forward UDP/IPv4/Ethernet transmitter. It accepts one byte-wide AXI-Stream payload into a RAM (block or LUT RAM), sums the payload as 16-bit words while it arrives, and drops anything longer than MAX_PAYLOAD (ev_too_long). A single-cycle S_CALC state computes the IPv4 header checksum and the UDP checksum (an all-zero result is sent as 0xFFFF; CSUM=0 sends 0). The 42 header bytes and the payload then go out through a two-stage read pipeline. I traced the length, checksu
facts: read from sources; no measurement; no build; no simulation by the review
open: 
gaps: no synthesis, implementation or timing result exists in this handover | no simulation was run by the review; the tests' coverage is the reviewer's reading | MAX_PAYLOAD=1 and power-of-two depths in the bench | Reset during a frame or during S_CALC | Identification wrap at 65536 datagrams | Config (own_ip/own_mac) changing mid-frame
next: fix the critical and major findings, then re-run the review and the check suite at scope synth after a build | answer the open questions below
