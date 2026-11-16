# AGENT handover (produced by review) id=arp_responder review=arp_responder sha=2a00846313f2
top=formal_arp clocks=clk rtl=formal/formal_arp.sv,rtl/arp_responder.sv tests=tb/arp_cocotb.py constraints=none
summary: arp_responder is a single-clock ARP (RFC 826) block for one IPv4 address. It parses byte-wide Ethernet frames, replies to requests for own_ip, learns sender MACs into a small fully-associative cache with round-robin replacement, and answers next-hop lookups. On a miss it sends a rate-limited broadcast request. It flags address conflicts (RFC 5227) through ev_conflict and never caches the conflicting sender.
facts: read from sources; no measurement; no build; no simulation by the review
open: F-e7dddd/major/rtl/arp_responder.sv:93
gaps: no synthesis, implementation or timing result exists in this handover | no simulation was run by the review; the tests' coverage is the reviewer's reading | ev_conflict is not counted in the main bench. | Lookup concurrent with flush or learn. | Alternating-address holdoff. | Frames longer than 63 bytes (saturating k).
next: fix the critical and major findings, then re-run the review and the check suite at scope synth after a build | answer the open questions below
