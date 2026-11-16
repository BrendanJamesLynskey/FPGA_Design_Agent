# Design review: ipv4_udp_rx

*Review ipv4_udp_rx, schema 1. Reviewed directory `ipv4_udp_rx`, content hash `3da95ae853c9`; the reviewed files were not changed (hash checked again at the end: unchanged).*

**Statement of intent:** none given; the intent below is inferred.

## 1. Understanding

**What it does.** ipv4_udp_rx is a byte-wide AXI-Stream IPv4/UDP receiver. It parses Ethernet frames without FCS and checks the IPv4 header (version, IHL, checksum, length), fragments, protocol, destination address and UDP length. It optionally verifies the UDP checksum including the pseudo-header, and picks the lowest enabled matching destination port. Payload bytes stream out with a one-byte holdback so tlast can carry the verdict as tuser, and header fields and event pulses accompany them. I found no functional bug in the RTL by reading. The main weaknesses are timing (it misses 125 MHz, which the docs state), documentation mismatches, and the limited reach of the formal and seeded-fault evidence.

**Interfaces.** Slave AXI-Stream s_axis (8-bit data, tuser = bad frame). Master AXI-Stream m_axis (8-bit data, tuser = discard on tlast, 3-bit tdest = port index) with sideband m_src_ip, m_dst_ip, m_src_port, m_dst_port and m_len. Native config inputs own_ip, ports[N_PORTS*16] and port_en. Six one-clock event pulses. s_axis_tready = !fin && (!m_axis_tvalid || m_axis_tready), so it is combinational from m_axis_tready.

**Clocks and resets.** Single clock `clk`, synchronous active-high `rst`, no crossings. The reset also clears many data registers (header fields, accumulators and so on), which is more than needed but harmless. Config inputs are used directly with no synchronisation, which is fine in one domain but they must be static during a frame.

**Architecture as built.** A byte counter k, saturating at 0xFFFF, indexes the frame. Header fields are captured by case on k. Two 32-bit one's-complement accumulators run, one over the IP header and one over the UDP datagram. The header verdict (mine && len_ok && port_hit) is taken when the first payload byte arrives at k = u0+8, which sets fwd and f_dest. A single holding register h_d/h_v delays each payload byte by one so the last byte can be emitted with tlast and tuser = u_bad once the `fin` cycle follows tlast. In that cycle, if nothing was held, the reason is classified into an ev_* pulse. Large combinational cones (index compares, the fold and the 7-term u_tot add) are unpipelined.

Facts made by code from the sources:

| Module | File | Clocks | Async-reset edges | Instantiates |
|---|---|---|---|---|
| `formal_udp_rx` | `formal/formal_udp_rx.sv:1` | clk | - | ipv4_udp_rx |
| `ipv4_udp_rx` | `rtl/ipv4_udp_rx.sv:1` | clk | - | - |

```
formal_udp_rx (formal/formal_udp_rx.sv:1, 38 lines; clocks clk)
  dut : ipv4_udp_rx (rtl/ipv4_udp_rx.sv:1, 184 lines; clocks clk)
```

Block diagram of the top module: [block_diagram.svg](block_diagram.svg) (made from the source hierarchy).

## 2. Findings

Counts: 0 critical, 0 major, 7 minor, 0 info.

### Minor

**F-3d044d Seeded-fault set misses key checks**
- Where: `faults.yaml:4-46 (faults)`; category verification; confidence medium; found by judge
- Evidence: Six faults are seeded: port priority, pseudo-header source, padding, fragments, options and last fragment. None touches the IP header checksum compare, the broadcast/multicast acceptance, len_ok, u_bad's truncation term, f_bad/tuser propagation, ucs==0 handling, or the event classification.
- Rule or reason: Mutation evidence only shows that the tests detect those specific classes.
- Suggested fix: Add faults such as fold(ip_acc) compare removed, `ulen <= tl-hl` loosened, `k+1 < u_end` off by one, f_bad ignored, `ucs != 0` removed, and ev_empty/ev_no_port order swapped.

**F-81b523 Formal proof covers only protocol rules, one parameter point, and depends on an external module**
- Where: `formal/formal_udp_rx.sv:21-35 (formal_udp_rx)`; category verification; confidence medium; found by both
- Evidence: The DUT is instantiated with N_PORTS(2), CHECK_UDP(1) and a fixed own_ip. Only viol[2:0] is asserted, though viol is 5 bits wide. The properties are AXI stability, the post-tlast stall and 'nothing leaves without input'. axis_rules is not in this directory (lint F-aecef7).
- Rule or reason: Bounded protocol checks do not show datagram correctness. Unused viol bits and a single parameter point leave gaps.
- Suggested fix: State the BMC depth in the README. Assert, or document why you ignore, viol[4:3]. Add formal properties for tlast and tuser, for example that tlast appears exactly once per forwarded payload, and run N_PORTS=1/8 and CHECK_UDP=0.

**F-167a7b Parameter guards are in an initial block, so synthesis may not enforce them**
- Where: `rtl/ipv4_udp_rx.sv:50-55 (initial $error)`; category other; confidence medium; found by both
- Evidence: The checks are `initial begin if (N_PORTS < 1 || ...) $error(...)`. README says out-of-space values 'fail at elaboration', tested only in simulation.
- Rule or reason: An initial block runs at simulation time. Vivado synthesis may ignore it, so N_PORTS=9 could synthesise silently. For N_PORTS>8, tdest 3'(i) would truncate.
- Suggested fix: Use `generate if (...) $error(...)` elaboration-time checks, which both tools evaluate at elaboration.

**F-b75054 README/ip.yaml claim 'Registered outputs: yes' but s_axis_tready is combinational from m_axis_tready**
- Where: `rtl/ipv4_udp_rx.sv:64-65 (s_axis_tready)`; category documentation; confidence high; found by judge
- Evidence: `assign take = !m_axis_tvalid || m_axis_tready; assign s_axis_tready = !fin && take;` while README line 70 says 'Registered outputs: yes'.
- Rule or reason: The documented boundary contract should match the code. A combinational ready path through the block matters for timing closure with neighbours.
- Suggested fix: Document the combinational tready path, or add a skid register on the output to break it.

**F-c898d8 Header comment says total length >= header+8 is checked as a bad-IP condition; code differs**
- Where: `rtl/ipv4_udp_rx.sv:87-97 (hdr_ok / len_ok)`; category documentation; confidence medium; found by judge
- Evidence: The header comment (line 5) says 'total length at least the header plus 8'. hdr_ok only checks `tl >= IHL*4`, and the +8 is enforced indirectly via len_ok (`ulen >= 8 && ulen <= tl - hl`).
- Rule or reason: The comment and the event classification should agree. A datagram with tl = hl+4 gives ev_bad_udp, not ev_bad_ip.
- Suggested fix: Reword the comment, and state in the README which event each length error raises.

**F-7d8ff7 Timing fails at 125 MHz; verdict path is a long combinational cone**
- Where: `rtl/ipv4_udp_rx.sv:111-114 (u_tot / u_bad / hdr_ok)`; category timing; confidence high; found by judge
- Evidence: u_tot is a 7-operand 32-bit add, then fold(), then a compare, then it feeds m_axis_tuser through u_bad at line 168. hdr_ok folds ip_acc and compares. char JSON shows WNS -5.412 ns (74.6 MHz) and -4.336 ns (81.1 MHz) at 8 ns.
- Rule or reason: The block is intended to sit behind an RGMII MAC at 125 MHz; README and ip.yaml state it does not close.
- Suggested fix: Register the folded IP and UDP checksum results, and the hdr_ok, len_ok and port_hit flags, in extra cycles. Use the one-clock `fin` gap, or add a verdict stage. Compute the pseudo-header sum incrementally while src/dst arrive instead of adding it at the end.

**F-e3bf46 Tests never exercise reset in flight, mid-frame tuser, or all parameter combinations**
- Where: `tb/udp_rx_cocotb.py:68-121 (udp_rx)`; category verification; confidence medium; found by judge
- Evidence: The bench resets once via axis_tb.start. s_axis_tuser is only driven with the final-beat 'bad' kind. Only three parameter points run (ACCEPT_BCAST=1/ACCEPT_MCAST=0 and CHECK_UDP=0 with BCAST=1 are never reached). own_ip and port_en are static. Frames of 1 to 33 bytes and sustained back-to-back traffic with the output stalled across tlast are only incidentally covered. I could not see the adversarial bench or the formal harness test.
- Rule or reason: Control state must recover cleanly from reset mid-frame, and each parameter must be exercised independently.
- Suggested fix: Add a reset-mid-frame test (check the next frame is clean, no spurious tvalid). Add runt frames and a mid-frame tuser. Sweep BCAST and MCAST independently.

### Check findings the reviewer dismissed

- F-aecef7: axis_rules is a library module outside this directory, used only by the formal harness. It is noted in the formal finding but is not an RTL defect.
- F-663ce4: The missing architecture.yaml is a layout expectation of the checker. It does not apply to this design from outside the agent's own layout.
- F-4fdde2: The initial block only carries parameter guards, not initialisation. The substance (it may not be enforced in synthesis) is reported in my own finding.
- F-fa1663: Naming prefix complaint only. The s_axis/m_axis ports follow the standard AXI-Stream naming and signals; noise.
- F-780329: Same as F-fa1663; naming noise.
- F-94187c: Same as F-fa1663; naming noise.
- F-75ba7b: Same as F-fa1663; naming noise.
- F-c820bd: Same as F-fa1663; naming noise.
- F-592a06: Same as F-fa1663; naming noise.
- F-9b7f7d: Same as F-fa1663; naming noise.
- F-5e8790: Same as F-fa1663; naming noise.

### Looked at and found sound

- m_axis data, tdest, tuser and the sideband fields change only when `take` is true (idle or accepted), so they stay stable while stalled; this is consistent with the AXI-Stream rules.
- Odd-length UDP checksum: wv places the last odd byte in the high half via k[0], and u0 is always even, so parity tracks the UDP word alignment.
- Truncation is detected correctly: at fin, k is the last byte index, and `k+1 < u_end` flags a frame that ends inside the datagram.
- Ethernet padding is dropped by in_pay's `k < u_end` bound.
- The one-byte holdback with the fin cycle always emits the final byte with tlast, and h_v is cleared per frame, so no stale byte leaks across frames.
- Event classification order matches model.py (bad_ip, frag, no_port, empty, bad_udp), and stale header registers are only read after k has passed their capture index.
- Reset is synchronous and covers all control state (fin, h_v, m_axis_tvalid, k, fwd, decided); no CDC exists.
- The lowest-index port wins because the loop runs downward and the last assignment is the lowest index.
- An IHL up to 15 is handled (u0 up to 74); k saturation at 0xFFFF is harmless for Ethernet frame sizes.

## 3. Verification gap

**What the existing tests cover.**
- Random frames: unicast, broadcast, multicast and foreign destinations.
- Enabled, disabled, duplicate and unknown ports.
- Good, bad and absent UDP checksums.
- IP options, fragments, other protocols, bad IP checksum, UDP length errors, padding, truncation, empty payloads.
- Input gaps and 75% output ready; per-frame payload, tuser, sideband and all event counters compared against the model.
- Formal AXI-Stream stability and 'nothing leaves without input' on one parameter point.

**What they miss.**
- Reset during a frame or during an output stall.
- s_axis_tuser asserted mid-frame, not just on the last beat.
- Frames shorter than 14 bytes, and back-to-back frames with m_axis stalled at tlast.
- Config changes during traffic.
- Full parameter cross product (CHECK_UDP=0 with ACCEPT_BCAST=1, BCAST/MCAST independence).
- Frames above Ethernet size, with k saturation.
- Timing at 125 MHz; no board run.

**Seeded faults they would not catch.**
- IP header checksum compare removed or weakened (only the 'ipcs' kind catches it, via the random generator; not verified as mutation-tested).
- Broadcast acceptance accepting subnet broadcasts or a wrong mask.
- len_ok upper bound off by one.
- u_bad truncation term off by one.
- f_bad dropped from u_bad.
- ucs==0 no-checksum handling inverted.
- Event priority swaps between ev_empty and ev_bad_udp.
- The `k != 16'hFFFF` saturation removed.

No coverage run or mutation run was made by the review: the lists above are the reviewer's reasoning from the test files.

## 4. Questions for the author

- Is ev_* intended to pulse for frames dropped with s_axis_tuser set when the datagram is not for us? The code and model both stay silent there; confirm this is intended.
- What BMC depth was used for the formal runs? The result files are not provided.

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

- Reviewer: claude-sonnet-5-5, effort medium, Claude Code 2.1.321 (Claude Code); tokens as the provider reported them: 35116; wall 85.0 s.
- Prompt version 2; check suite standard FDA-HDL.
