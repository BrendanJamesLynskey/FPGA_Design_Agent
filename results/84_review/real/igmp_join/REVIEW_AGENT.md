# REVIEW (agent) igmp_join id=igmp_join schema=1 design_sha=8eec7222ae49 mode=review (read-only)
top: formal_igmp; clocks: clk; scope: rtl
checks: lint=fail, standards=fail, resets=not_run, methodology=not_run, axi=pass | not run: resets, methodology
summary: igmp_join is an IGMPv2 host-side membership block for 1..8 configured multicast groups. It parses received Ethernet frames byte by byte, sends reports on join, answers general, group-specific and v3 queries after a random delay, honours suppression by other hosts' reports, and sends leaves. It emits fixed 46-byte frames on a byte-wide AXI-Stream master. Timing is per-tick counters driven by a TICK

FINDINGS id | sev | cat | where | conf | src | title | fix
F-5a8c6e | major | timing | rtl/igmp_join.sv:184 | high | judge | Timing: documented 71-80 MHz Fmax, below the 125 MHz target | Register the pick result in one stage and sum the checksum over two stages, since the frame is not started in the same cycle.
F-bd4e6d | minor | verification | formal/formal_igmp.sv:22 | medium | both | Formal harness uses an unavailable module and covers only the transmit side | Add axis_rules to the file list or vendor it; state the BMC depth.
F-f54e02 | minor | arithmetic | rtl/igmp_join.sv:71 | low | judge | Timer set by query can be loaded, then the group's own pending report is not cancelled/serialised; t | Document the correlation, or advance the lfsr per group.
F-18e797 | minor | functional | rtl/igmp_join.sv:122 | medium | judge | Max Response Time unit not converted: IGMPv2 MRT is in tenths of a second, but a v3 query's code fie | Decode MRC>=128 as (mant|0x10)<<(exp+3), saturated to 255, when the query is longer than 8 bytes.
F-7ebe0a | minor | functional | rtl/igmp_join.sv:138 | low | judge | Report/leave bookkeeping races: sent_rep clears rep_p after a new join sets it | Give sent_rep/sent_lv an explicit priority, and test a leave in the cycle a report completes.
F-b83c47 | minor | functional | rtl/igmp_join.sv:140 | medium | judge | A received query or report is dropped when it coincides with a join/leave edge for that group, and t | Make the tick decrement independent of the query/report branch, or note the one-tick skew as acceptable in the docs.
F-99bc68 | minor | verification | tb/igmp_cocotb.py:33 | medium | judge | Verification of out-of-range interface behaviour and receive paths is thin | Add tests for tuser=1 frames, IHL 6 queries, group_en glitches, a reset mid-frame, and a leave-after-report race.
F-24eba1 | info | documentation | README.md:11 | high | judge | README/yaml table header has a mismatched column count | Fix the generator.

QUESTIONS
- Is group_en guaranteed glitch-free and synchronous to clk?
- Should a v3 query's MRC floating-point encoding be honoured?

TEST GAPS
- tuser-marked frames, long, short or IHL>5 frames
- Events coinciding in the same cycle (join/leave with a query or sent_rep)
- Reset mid-operation
- Long sink stalls
- MRC >= 128 in v3 queries
- Version 1 queries (only in the adversarial bench, which is not shown)

RULES: this review did not edit the design; fixes are separate, opt-in work. Re-run the checks after any change.