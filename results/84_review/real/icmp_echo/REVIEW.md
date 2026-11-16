# Design review: icmp_echo

*Review icmp_echo, schema 1. Reviewed directory `icmp_echo`, content hash `93ab8705e205`; the reviewed files were not changed (hash checked again at the end: unchanged).*

**Statement of intent:** none given; the intent below is inferred.

## 1. Understanding

**What it does.** icmp_echo answers ICMP echo requests for one IPv4 address on a byte-wide AXI-Stream link. It stores each received frame in a RAM (block or LUT RAM) while checking the Ethernet, IP and ICMP fields and both checksums. If the frame is a valid echo request and the buffer is free, it replays the stored frame with addresses swapped, a fixed TTL, ICMP type 0 and RFC 1624 incrementally updated checksums. Only one request is held at a time; a request arriving while a reply is pending is dropped and flagged with ev_busy. Evidence is cocotb against a Python model with scapy, SymbiYosys bounded checks and an out-of-context Artix-7 build. The design has not been run on a board.

**Interfaces.** s_axis: 8-bit AXI-Stream in, tready tied to 1, tuser marks a bad frame, frames carry no FCS. m_axis: 8-bit AXI-Stream out with tvalid/tready/tlast and registered outputs. own_mac and own_ip are static configuration inputs. Four one-clock event pulses: ev_request, ev_reply, ev_busy, ev_bad. Parameters are BUF_BYTES (power of two, 128..16384), TTL (1..255) and RAM (bram or lutram).

**Clocks and resets.** One clock, clk, and one synchronous active-high reset, rst. There are no clock crossings and no asynchronous resets. Control state and header/accumulator registers are reset. The RAM and the read data register rq are not, which is fine. The event pulses default to 0 and are cleared in reset.

**Architecture as built.** A receive side counts bytes with k (saturating) and captures header fields at fixed offsets. It accumulates the IP header sum (ip_acc) and the ICMP sum (ic_acc, limited to the IP total length). It writes the frame into mem. `fin` pulses one clock after tlast, and `ok` is then evaluated combinationally from the captured fields. `blocked` stops a frame that starts right after a request's last byte from being stored over the request. The reply side starts at fin&&ok&&f_store and sets busy. It computes the new IP and ICMP checksums incrementally and reads the RAM with an address swap for the IP source and destination (offsets 26..33). A small skid-style pipeline (rq, rv, rj, take) feeds m_axis, and out_byte substitutes the MACs, TTL, checksums and ICMP type.

Facts made by code from the sources:

| Module | File | Clocks | Async-reset edges | Instantiates |
|---|---|---|---|---|
| `formal_icmp` | `formal/formal_icmp.sv:1` | clk | - | icmp_echo |
| `icmp_echo` | `rtl/icmp_echo.sv:1` | clk | - | - |

```
formal_icmp (formal/formal_icmp.sv:1, 61 lines; clocks clk)
  dut : icmp_echo (rtl/icmp_echo.sv:1, 195 lines; clocks clk)
```

Block diagram of the top module: [block_diagram.svg](block_diagram.svg) (made from the source hierarchy).

## 2. Findings

Counts: 0 critical, 0 major, 5 minor, 0 info.

### Minor

**F-5117d0 Formal reply-content check covers one byte and one RAM variant**
- Where: `formal/formal_icmp.sv:53 (assert (m_axis_tdata == f_rq[7:0]))`; category verification; confidence high; found by judge
- Evidence: The reply content is checked only at byte index 13. The formal instance is fixed to BUF_BYTES 128 and RAM "lutram". Reset is only the initial f_past pulse (line 13). The README admits the one-byte limit.
- Rule or reason: A formal check of data integrity should cover the whole copied region, or the gap should be covered by directed tests that are known to hit it.
- Suggested fix: Use a solver-chosen byte if it can be made to converge (for example with a small BUF and k-induction), or add a second instance with RAM=bram. Add mid-stream reset in the formal bench.

**F-5f28ce Long combinational path from the checksum compare into the RAM write enable**
- Where: `rtl/icmp_echo.sv:112-115 (blocked / ok / we)`; category timing; confidence medium; found by judge
- Evidence: `blocked = busy || (fin && ok && f_store)`, and `ok` includes fold(ip_acc)==FFFF, fold(ic_acc)==FFFF and a 17-bit length compare. `blocked` feeds `we` (line 79) and `stored`. The out-of-context runs fail 125 MHz (WNS -0.59 to -3.3 ns).
- Rule or reason: Wide arithmetic compares should be registered rather than feeding memory enables and control state combinationally.
- Suggested fix: Register `ok` in a stage after fin, and block a new frame's first byte by a conservative flag (for example fin&&echo_me&&f_store) or a delayed start. Pipeline the folds, as the README's next steps already say.

**F-bd4754 Ethernet destination MAC is not checked**
- Where: `rtl/icmp_echo.sv:113 (echo_me)`; category functional; confidence medium; found by judge
- Evidence: echo_me tests EtherType, version/IHL, protocol, dst IP and ICMP type only. own_mac is used just as the reply's source address (line 183). The header comment's list of conditions has no MAC check.
- Rule or reason: A host answering ping should only answer frames addressed to its MAC, or broadcast/multicast where intended. If the MAC layer does not filter, frames for other stations are answered.
- Suggested fix: Add a check on bytes 0..5 against own_mac or broadcast. Alternatively, document that the upstream MAC must filter.

**F-809e1d Runt frames after a ping raise a spurious ev_bad (stale header registers)**
- Where: `rtl/icmp_echo.sv:170-171 (echo_me / ev_bad)`; category functional; confidence medium; found by judge
- Evidence: The header registers (et, vi, proto, dst, typ) are only reset by rst and are not cleared at the start of a frame (line 87 clears only ip_acc and ic_acc). A frame shorter than 35 bytes that follows a request keeps the old values, so echo_me stays true. ic_acc is 0, so ok is false and `if (!ok) ev_bad <= 1'b1` fires.
- Rule or reason: An event flag should depend only on the current frame's data.
- Suggested fix: Clear the captured fields, or a per-frame 'seen typ/dst' flag, when first is true. Alternatively gate echo_me with f_len > 37.

**F-a6996d Testbench corners not exercised**
- Where: `tb/icmp_cocotb.py:97 (echo)`; category verification; confidence medium; found by judge
- Evidence: The random tests do not hit tl14 == BUF_BYTES exactly, since lengths are random below min(buf, 9000). TTL is 64, 255 and 128 only. There is no reset while a frame or reply is in flight, no runt frame after a request, and no test with the sink stalled during the reply tail.
- Rule or reason: Boundary and reset-in-flight cases are where counter and handshake bugs hide.
- Suggested fix: Add directed cases for datagram length exactly BUF_BYTES-14 and BUF_BYTES-13, TTL=1, runt frames after a request, and a reset during a reply. Also check that ev_bad stays 0 for frames not meant for us.

### Check findings the reviewer dismissed

- F-a29de9: axis_rules is an external AXI checker module from the library, not part of this block's files. It is a layout complaint for a formal-only wrapper.
- F-fadf62: The initial block holds only $error elaboration guards for parameters. It is simulation and elaboration checking, not synthesised state, and is documented and tested.
- F-663ce4: The architecture.yaml file belongs to the agent's own layout; not applicable to this block.
- F-be3956: Naming-prefix complaint (s_axis/m_axis); not applicable.
- F-a67be0: Naming-prefix complaint (s_axis/m_axis); not applicable.
- F-0a658d: Naming-prefix complaint (s_axis/m_axis); not applicable.
- F-af5a80: Naming-prefix complaint (s_axis/m_axis); not applicable.
- F-e00242: Naming-prefix complaint (s_axis/m_axis); not applicable.
- F-26b534: Naming-prefix complaint (s_axis/m_axis); not applicable.
- F-c4f568: Naming-prefix complaint (s_axis/m_axis); not applicable.
- F-ba5502: Naming-prefix complaint (s_axis/m_axis); not applicable.

### Looked at and found sound

- Incremental checksum updates match RFC 1624 eqn 3: the IP checksum for the TTL change, and the ICMP checksum for type 8 to 0. The IP address swap leaves the IP sum unchanged.
- The read-address swap for bytes 26..33 and the out_byte substitutions at 0..11, 22, 24/25, 34 and 36/37 are consistent with the header layout.
- The output pipeline (take, rv, rd_en) holds tdata and tvalid stable while m_axis_tready is low and loses no byte.
- `blocked` protects the stored request against a frame starting on the clock after the last byte and against frames during a reply. The tail-overwrite fault is caught by the adversarial bench.
- The ICMP sum is limited to the IP total length, so Ethernet padding is excluded. The length checks (tl>=28, f_len>=tl+14, tl+14<=BUF_BYTES) and the saturating k prevent overflow.
- Parameter guards exist and are tested. Reset policy follows the house convention.

## 3. Verification gap

**What the existing tests cover.**
- Random request lengths with padding, wrong addresses, bad checksums, fragments, options, other types and codes, bad and truncated frames, and oversize frames, checked against the model and scapy under random gaps and back-pressure.
- A request arriving while a reply is held (ev_busy), and the declared 4-clock latency.
- AXI-Stream protocol rules on m_axis, no reply without a request, and byte 13 of the reply, all by bounded model checking.
- Seven seeded faults, all caught.

**What they miss.**
- Reset in flight.
- Datagram length exactly at the buffer limit.
- TTL=1.
- Runt frames after a request (stale fields).
- Formal coverage of the bram variant and of reply bytes other than 13.
- Behaviour on frames addressed to another MAC.

**Seeded faults they would not catch.**
- The ev_bad stale-field behaviour (spurious ev_bad on a runt frame) would pass the tests, which check only ev_busy==0 and the request/reply counts.
- A fault in the tl14 <= BUF_BYTES boundary (off by one at exactly BUF_BYTES) is probably not caught.
- An error in a copied byte other than 13 that appears only for particular lengths (for example stale data past the current frame) is checked only by random simulation.

No coverage run or mutation run was made by the review: the lists above are the reviewer's reasoning from the test files.

## 4. Questions for the author

- Does the upstream MAC filter frames by destination MAC, so this block need not?
- Should a ping to the broadcast address or from a broadcast/multicast source be answered or suppressed?

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

- Reviewer: claude-sonnet-5-5, effort medium, Claude Code 2.1.321 (Claude Code); tokens as the provider reported them: 33628; wall 66.1 s.
- Prompt version 2; check suite standard FDA-HDL.
