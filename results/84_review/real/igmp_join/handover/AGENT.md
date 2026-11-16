# AGENT handover (produced by review) id=igmp_join review=igmp_join sha=8eec7222ae49
top=formal_igmp clocks=clk rtl=formal/formal_igmp.sv,rtl/igmp_join.sv tests=tb/igmp_cocotb.py constraints=none
summary: igmp_join is an IGMPv2 host-side membership block for 1..8 configured multicast groups. It parses received Ethernet frames byte by byte, sends reports on join, answers general, group-specific and v3 queries after a random delay, honours suppression by other hosts' reports, and sends leaves. It emits fixed 46-byte frames on a byte-wide AXI-Stream master. Timing is per-tick counters driven by a TICK_CLKS divider, and the random delay comes from a 16-bit LFSR.
facts: read from sources; no measurement; no build; no simulation by the review
open: F-5a8c6e/major/rtl/igmp_join.sv:184
gaps: no synthesis, implementation or timing result exists in this handover | no simulation was run by the review; the tests' coverage is the reviewer's reading | tuser-marked frames, long, short or IHL>5 frames | Events coinciding in the same cycle (join/leave with a query or sent_rep) | Reset mid-operation | Long sink stalls
next: fix the critical and major findings, then re-run the review and the check suite at scope synth after a build | answer the open questions below
