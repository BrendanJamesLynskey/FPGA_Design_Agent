# igmp_join: handover (produced by review)

> Produced by review `igmp_join` on design content `8eec7222ae49`. Nothing here was measured. Read `review.json` for the findings.

## What it does

igmp_join is an IGMPv2 host-side membership block for 1..8 configured multicast groups. It parses received Ethernet frames byte by byte, sends reports on join, answers general, group-specific and v3 queries after a random delay, honours suppression by other hosts' reports, and sends leaves. It emits fixed 46-byte frames on a byte-wide AXI-Stream master. Timing is per-tick counters driven by a TICK_CLKS divider, and the random delay comes from a 16-bit LFSR.

## Interfaces

s_axis: 8-bit AXI-Stream slave, tready tied high, tuser used as a frame-bad flag. m_axis: 8-bit master, 46-byte frames with tlast. Config inputs: own_mac, own_ip, groups, group_en (level, edge-detected inside). Event pulses: ev_query, ev_report, ev_leave, ev_suppressed. Single clock clk, synchronous active-high rst.

| Port | Direction | Width |
|---|---|---|
| `clk` | input | 1 |
| `s_axis_tdata` | input | [7:0] |
| `s_axis_tvalid` | input | 1 |
| `m_axis_tready` | input | 1 |
| `group_en` | input | [1:0] |

## Clocks and resets

Single clock domain with no crossings. Synchronous reset; control state, valid and timers are reset, while the checksum and data registers are mostly reset too. group_en and groups come from the same domain and are assumed synchronous. No async reset.

Clock domains found in the code: clk.

## Architecture

A receive FSM indexed by byte counter k captures ethertype, IHL, length, protocol, IGMP type, MRT and group while accumulating two ones-complement checksums. A per-group state block (run, rep_p, lv_p, last_rep, 8-bit tmr) is updated each clock from joins, leaves, queries, reports and ticks. A transmit block picks the lowest pending group (leaves first), precomputes IP and IGMP checksums in one combinational sum, and streams the frame bytes from a case function indexed by j.

## Files

- rtl: `formal/formal_igmp.sv`, `rtl/igmp_join.sv`
- tests: `tb/igmp_cocotb.py`
- constraints: none
- docs: `CHANGELOG.md`, `README.md`

## Open critical and major findings

- F-5a8c6e (major) `rtl/igmp_join.sv:184`: Timing: documented 71-80 MHz Fmax, below the 125 MHz target

## Known gaps and limits

- no synthesis, implementation or timing result exists in this handover
- no simulation was run by the review; the tests' coverage is the reviewer's reading
- tuser-marked frames, long, short or IHL>5 frames
- Events coinciding in the same cycle (join/leave with a query or sent_rep)
- Reset mid-operation
- Long sink stalls
- MRC >= 128 in v3 queries
- Version 1 queries (only in the adversarial bench, which is not shown)

## Next steps

- fix the critical and major findings, then re-run the review and the check suite at scope synth after a build
- answer the open questions below

## Open questions

- Is group_en guaranteed glitch-free and synchronous to clk?
- Should a v3 query's MRC floating-point encoding be honoured?
