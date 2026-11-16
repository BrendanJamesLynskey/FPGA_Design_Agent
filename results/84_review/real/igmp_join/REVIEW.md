# Design review: igmp_join

*Review igmp_join, schema 1. Reviewed directory `igmp_join`, content hash `8eec7222ae49`; the reviewed files were not changed (hash checked again at the end: unchanged).*

**Statement of intent:** none given; the intent below is inferred.

## 1. Understanding

**What it does.** igmp_join is an IGMPv2 host-side membership block for 1..8 configured multicast groups. It parses received Ethernet frames byte by byte, sends reports on join, answers general, group-specific and v3 queries after a random delay, honours suppression by other hosts' reports, and sends leaves. It emits fixed 46-byte frames on a byte-wide AXI-Stream master. Timing is per-tick counters driven by a TICK_CLKS divider, and the random delay comes from a 16-bit LFSR.

**Interfaces.** s_axis: 8-bit AXI-Stream slave, tready tied high, tuser used as a frame-bad flag. m_axis: 8-bit master, 46-byte frames with tlast. Config inputs: own_mac, own_ip, groups, group_en (level, edge-detected inside). Event pulses: ev_query, ev_report, ev_leave, ev_suppressed. Single clock clk, synchronous active-high rst.

**Clocks and resets.** Single clock domain with no crossings. Synchronous reset; control state, valid and timers are reset, while the checksum and data registers are mostly reset too. group_en and groups come from the same domain and are assumed synchronous. No async reset.

**Architecture as built.** A receive FSM indexed by byte counter k captures ethertype, IHL, length, protocol, IGMP type, MRT and group while accumulating two ones-complement checksums. A per-group state block (run, rep_p, lv_p, last_rep, 8-bit tmr) is updated each clock from joins, leaves, queries, reports and ticks. A transmit block picks the lowest pending group (leaves first), precomputes IP and IGMP checksums in one combinational sum, and streams the frame bytes from a case function indexed by j.

Facts made by code from the sources:

| Module | File | Clocks | Async-reset edges | Instantiates |
|---|---|---|---|---|
| `formal_igmp` | `formal/formal_igmp.sv:1` | clk | - | igmp_join |
| `igmp_join` | `rtl/igmp_join.sv:1` | clk | - | - |

```
formal_igmp (formal/formal_igmp.sv:1, 37 lines; clocks clk)
  dut : igmp_join (rtl/igmp_join.sv:1, 231 lines; clocks clk)
```

Block diagram of the top module: [block_diagram.svg](block_diagram.svg) (made from the source hierarchy).

## 2. Findings

Counts: 0 critical, 1 major, 6 minor, 1 info.

### Major

**F-5a8c6e Timing: documented 71-80 MHz Fmax, below the 125 MHz target**
- Where: `rtl/igmp_join.sv:184-186 (ip_s, ig_s, pick)`; category timing; confidence high; found by judge
- Evidence: ip_s sums nine terms combinationally behind the pick priority loop, with fold, and feeds ipcs. The README admits WNS -4.5 ns (N=4) and -6.0 ns (N=8) at 8 ns, and a fix is listed under next steps.
- Rule or reason: The design should close timing at the clock it is meant for.
- Suggested fix: Register the pick result in one stage and sum the checksum over two stages, since the frame is not started in the same cycle.

### Minor

**F-bd4e6d Formal harness uses an unavailable module and covers only the transmit side**
- Where: `formal/formal_igmp.sv:22-23 (axis_rules)`; category verification; confidence medium; found by both
- Evidence: `axis_rules #(.DATA_W(8)) u_rules (...)` is not part of the listed files (check F-34d4e2). The harness asserts only viol[3:0], and its group_en is 2 bits and drives joins and leaves at any time. Only BMC; no proof.
- Rule or reason: Formal dependencies must be listed.
- Suggested fix: Add axis_rules to the file list or vendor it; state the BMC depth.

**F-f54e02 Timer set by query can be loaded, then the group's own pending report is not cancelled/serialised; tmr compare uses q_mrt in ticks with 8-bit rnd product**
- Where: `rtl/igmp_join.sv:71-75 (rnd)`; category arithmetic; confidence low; found by judge
- Evidence: `p = r * span; rnd = p[15:8] + 1` with r from lfsr[7:0] ^ (i*37). For span=255, p[15:8] max is 254, so the result is 1..255, fine. The 8'(i*37) xor is a weak decorrelation, and the same lfsr sample is reused for all groups in one cycle, so the delays are strongly correlated across groups; this hurts RFC 2236 spreading only mildly.
- Rule or reason: Random delay should be spread uniformly.
- Suggested fix: Document the correlation, or advance the lfsr per group.

**F-18e797 Max Response Time unit not converted: IGMPv2 MRT is in tenths of a second, but a v3 query's code field is floating-point above 128**
- Where: `rtl/igmp_join.sv:122-123 (q_mrt)`; category functional; confidence medium; found by judge
- Evidence: `q_mrt = (mrt == 8'd0) ? 8'd100 : mrt;` uses the raw byte. The README says a v3 query is answered as v2, but RFC 3376 4.1.1 gives MRC >= 128 an exponent/mantissa encoding, which is treated here as a linear value up to 255 (up to 25.5 s rather than the encoded time). Responding with a longer delay than the router allows may miss the router's response window.
- Rule or reason: RFC 3376 4.1.1 MRC decoding for v3 queries.
- Suggested fix: Decode MRC>=128 as (mant|0x10)<<(exp+3), saturated to 255, when the query is longer than 8 bytes.

**F-7ebe0a Report/leave bookkeeping races: sent_rep clears rep_p after a new join sets it**
- Where: `rtl/igmp_join.sv:138-141 (rep_p, last_rep)`; category functional; confidence low; found by judge
- Evidence: Line 138 `if (sent_rep[i]) begin rep_p[i] <= 1'b0; last_rep[i] <= 1'b1; end` precedes line 141 `rep_p[i] <= 1'b1` for a join, so a join in the same cycle wins on rep_p, which is correct, but last_rep is set to 1 by the earlier assignment and not cleared on a join. A leave in the same cycle as sent_rep: line 146 clears last_rep, so a report that just left is not recognised for the leave. The windows are narrow and the effect is a missed Leave.
- Rule or reason: The last-reporter state must follow the actual frame sequence.
- Suggested fix: Give sent_rep/sent_lv an explicit priority, and test a leave in the cycle a report completes.

**F-b83c47 A received query or report is dropped when it coincides with a join/leave edge for that group, and the pending flag is lost against sent_rep**
- Where: `rtl/igmp_join.sv:140-158 (per-group state)`; category functional; confidence medium; found by judge
- Evidence: The branches are an if/else-if chain: `if (group_en[i] && !en_q[i]) ... else if (!group_en[i] && en_q[i]) ... else if (group_en[i]) begin if (is_query ...) ... else if (is_report ...) ... else if (run[i] && tick && !rep_p[i])`. is_query/is_report are single-cycle pulses (fin), so a query in the same cycle as a join/leave is lost, and a tick in the same cycle as a query or report is skipped.
- Rule or reason: Events must not mask each other.
- Suggested fix: Make the tick decrement independent of the query/report branch, or note the one-tick skew as acceptable in the docs.

**F-99bc68 Verification of out-of-range interface behaviour and receive paths is thin**
- Where: `tb/igmp_cocotb.py:33-150 (igmp test)`; category verification; confidence medium; found by judge
- Evidence: The directed bench never sends frames with tuser set, IHL > 5, a runt frame, long frames (k saturates at 16'hFFFF), a query during a join, or a group_en toggle in flight. The only reset is at the start. The tests use sink ready 0.8 but never test a long stall.
- Rule or reason: Cover boundaries and error paths.
- Suggested fix: Add tests for tuser=1 frames, IHL 6 queries, group_en glitches, a reset mid-frame, and a leave-after-report race.

### Info

**F-24eba1 README/yaml table header has a mismatched column count**
- Where: `README.md:11-12 (Parameters table)`; category documentation; confidence high; found by judge
- Evidence: The header has 4 columns but the separator row has only 3 `|---|` cells, so the table may render wrongly.
- Rule or reason: Generated docs should be well-formed.
- Suggested fix: Fix the generator.

### Check findings the reviewer dismissed

- F-8f127d: The initial block only runs $error parameter guards; this is documented and tested, so it is not a defect.
- F-663ce4: No architecture.yaml is expected for this layout.
- F-c4f7a0: Prefix naming noise for the s_axis ports; the port convention is documented.
- F-bf3b28: Same as F-c4f7a0.
- F-808686: Same as F-c4f7a0.
- F-116741: Same as F-c4f7a0.
- F-a2bdf4: Same as F-c4f7a0.
- F-6bf7e3: Same as F-c4f7a0.
- F-6ec500: Same as F-c4f7a0.
- F-7c9d14: Same as F-c4f7a0.

### Looked at and found sound

- Single clock domain, no crossings
- Synchronous reset covering control state
- The AXI-Stream master holds data and valid until tready (the transmit update only changes tdata on a handshake)
- Frame length is fixed at 46 bytes, with j counting 1..45 and tlast at j==45
- Parameter guards with $error for the illegal values
- Checksum construction for the sent frame is consistent with the model, which the test compares byte for byte

## 3. Verification gap

**What the existing tests cover.**
- Directed join, general, group-specific and v3 queries, timer restart rule, bad checksum, suppression, leave
- Byte-exact frame comparison against the model with scapy decode
- Three parameter points
- Bounded formal of the 46-byte framing and AXI-Stream rules on m_axis

**What they miss.**
- tuser-marked frames, long, short or IHL>5 frames
- Events coinciding in the same cycle (join/leave with a query or sent_rep)
- Reset mid-operation
- Long sink stalls
- MRC >= 128 in v3 queries
- Version 1 queries (only in the adversarial bench, which is not shown)

**Seeded faults they would not catch.**
- A wrong MRC decode for values >= 128
- Dropping a query on the same cycle as a join
- Leave lost when it coincides with a report completing
- Ignoring tuser on received frames

No coverage run or mutation run was made by the review: the lists above are the reviewer's reasoning from the test files.

## 4. Questions for the author

- Is group_en guaranteed glitch-free and synchronous to clk?
- Should a v3 query's MRC floating-point encoding be honoured?

## 5. What was checked, and what was not

| Check | Result |
|---|---|
| lint | fail |
| standards | fail |
| resets | not_run |
| methodology | not_run |
| axi | pass |
| resets | not run:  |
| methodology | not run: no methodology report for scope rtl |

Scope: rtl. No synthesis was run, so the post-synthesis checks (CDC report, methodology, DRC, timing) did not run; a clock-domain crossing is therefore found only by the reviewer's reading. Run the suite at scope synth after a build to add them.

## 6. Handover

The design had no handover. One was written, marked produced by review: [handover/handover.yaml](handover/handover.yaml), [README](handover/README.md), [AGENT.md](handover/AGENT.md).

## Provenance

- Reviewer: claude-sonnet-5-5, effort medium, Claude Code 2.1.321 (Claude Code); tokens as the provider reported them: 28185; wall 27.8 s.
- Prompt version 2; check suite standard FDA-HDL.
