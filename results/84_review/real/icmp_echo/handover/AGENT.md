# AGENT handover (produced by review) id=icmp_echo review=icmp_echo sha=93ab8705e205
top=formal_icmp clocks=clk rtl=formal/formal_icmp.sv,rtl/icmp_echo.sv tests=tb/icmp_cocotb.py constraints=none
summary: icmp_echo answers ICMP echo requests for one IPv4 address on a byte-wide AXI-Stream link. It stores each received frame in a RAM (block or LUT RAM) while checking the Ethernet, IP and ICMP fields and both checksums. If the frame is a valid echo request and the buffer is free, it replays the stored frame with addresses swapped, a fixed TTL, ICMP type 0 and RFC 1624 incrementally updated checksums. Only one request is held at a time; a request arriving while a reply is pending is dropped and flagg
facts: read from sources; no measurement; no build; no simulation by the review
open: 
gaps: no synthesis, implementation or timing result exists in this handover | no simulation was run by the review; the tests' coverage is the reviewer's reading | Reset in flight. | Datagram length exactly at the buffer limit. | TTL=1. | Runt frames after a request (stale fields).
next: fix the critical and major findings, then re-run the review and the check suite at scope synth after a build | answer the open questions below
