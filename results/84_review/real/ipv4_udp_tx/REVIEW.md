# Design review: ipv4_udp_tx

*Review ipv4_udp_tx, schema 1. Reviewed directory `ipv4_udp_tx`, content hash `1b322337aa42`; the reviewed files were not changed (hash checked again at the end: unchanged).*

**Statement of intent:** none given; the intent below is inferred.

## 1. Understanding

**What it does.** ipv4_udp_tx is a store-and-forward UDP/IPv4/Ethernet transmitter. It accepts one byte-wide AXI-Stream payload into a RAM (block or LUT RAM), sums the payload as 16-bit words while it arrives, and drops anything longer than MAX_PAYLOAD (ev_too_long). A single-cycle S_CALC state computes the IPv4 header checksum and the UDP checksum (an all-zero result is sent as 0xFFFF; CSUM=0 sends 0). The 42 header bytes and the payload then go out through a two-stage read pipeline. I traced the length, checksum and handshake logic by hand and found no functional defect. The findings are minor: a live-config hazard, RAM address width, documentation and testbench weaknesses, and verification gaps.

**Interfaces.** s_axis: 8-bit AXI-Stream slave, one payload per frame. s_axis_tready is high only in S_IN. s_dst_mac, s_dst_ip, s_src_port and s_dst_port are sampled with the first beat. m_axis: 8-bit AXI-Stream master carrying an Ethernet frame without FCS, 42 + n bytes, with registered tvalid, tdata and tlast. config: own_mac and own_ip are plain level inputs. events: ev_sent and ev_too_long are one-cycle pulses.

**Clocks and resets.** One clock (clk) and one synchronous active-high reset (rst). There are no clock crossings and no asynchronous resets. Control state, counters, the checksum accumulator, the captured header fields and the output registers are reset. RAM contents and rq are not, which matches the house convention. rq is only consumed after a read that follows reset.

**Architecture as built.** A three-state FSM: S_IN, S_CALC, S_OUT. In S_IN the payload is written at address n and p_acc accumulates the word sum, with the byte placed in the high or low half according to n[0]. In S_CALC the two checksums are computed in one cycle from wide adder chains. In S_OUT, j indexes frame bytes 0 to n+41. A read stage (rj, rv, rq) feeds the output register. rd_en = more && (take || !rv) keeps rq stable while the output is stalled. Bytes 0..41 come from hdr_byte and the rest from the RAM. The final output beat returns the FSM to S_IN and increments ident.

Facts made by code from the sources:

| Module | File | Clocks | Async-reset edges | Instantiates |
|---|---|---|---|---|
| `formal_udp_tx` | `formal/formal_udp_tx.sv:1` | clk | - | ipv4_udp_tx |
| `ipv4_udp_tx` | `rtl/ipv4_udp_tx.sv:1` | clk | - | - |

```
formal_udp_tx (formal/formal_udp_tx.sv:1, 53 lines; clocks clk)
  dut : ipv4_udp_tx (rtl/ipv4_udp_tx.sv:1, 173 lines; clocks clk)
```

Block diagram of the top module: [block_diagram.svg](block_diagram.svg) (made from the source hierarchy).

## 2. Findings

Counts: 0 critical, 0 major, 6 minor, 0 info.

### Minor

**F-328efe Variant table claims II=1 although only one datagram is handled at a time**
- Where: `README.md:66-67 (Variants table)`; category documentation; confidence high; found by judge
- Evidence: The table gives II = 1 for both variants, but s_axis_tready = (st == S_IN) (line 64) and the README states 'one datagram at a time'. The real interval between datagrams is about n + 42 + 3 clocks.
- Rule or reason: The documentation contradicts itself. A user could read II=1 as a new payload accepted every clock.
- Suggested fix: Describe II as per byte, or state the per-datagram interval as n + 45 clocks (payload in, calc, frame out).

**F-c8022f Verification gaps: formal covers only lutram at depth 4; edge cases not exercised**
- Where: `formal/formal_udp_tx.sv:19 (dut instance)`; category verification; confidence medium; found by judge
- Evidence: The formal wrapper instantiates MAX_PAYLOAD=4 with .RAM("lutram") only and asserts length and AXI rules, not content or checksums. The bench (N=40) takes most lengths below 600 and has no MAX_PAYLOAD=1 point, no reset in mid-frame, no ident wrap and no change of own_ip or own_mac mid-frame. The bench runs MAX_PAYLOAD=1472 for its first point (the `-k bram_1472` fault tests).
- Rule or reason: Fault-tests only watch the 1472/bram point. The depth-is-power-of-two case (MAX=4) in the formal run is the one the lint complains about. Reset in flight and MAX_PAYLOAD=1 are boundary cases of the contract.
- Suggested fix: Add MAX_PAYLOAD=1 and a power-of-two depth point to the bench. Add a reset-mid-frame test. Run the formal wrapper for both RAM values and add a checksum assertion for small lengths.

**F-36788b RAM address width exceeds memory depth; header-phase reads are out of range**
- Where: `rtl/ipv4_udp_tx.sv:41-110 (AW / mem / ra)`; category functional; confidence medium; found by both
- Evidence: AW = $clog2(MAX_PAYLOAD+1) while mem has MAX_PAYLOAD entries. ra = AW'(j - 16'd42) wraps to large indices during the header phase, and rd_en is asserted then. Lint reports WIDTHTRUNC on lines 109 and 110 (F-c097fa, F-7ad15e), which fits MAX_PAYLOAD=4 in the formal wrapper (a 3-bit index into a 4-entry array).
- Rule or reason: Indexing past the declared array depth gives X in simulation (rq is overwritten with X). It is harmless only because rq is ignored while rj<42, which depends on that mux staying as it is. Synthesis behaviour for out-of-range reads is tool-defined.
- Suggested fix: Use a depth of 2**AW, or gate rd_en with j >= 42 so no out-of-range read occurs. Size AW as $clog2(MAX_PAYLOAD) with a minimum of 1.

**F-cd020d own_mac / own_ip are used live, not captured per datagram**
- Where: `rtl/ipv4_udp_tx.sv:128 (hdr_byte / ip_sum / u_sum)`; category functional; confidence medium; found by judge
- Evidence: d_mac, d_ip, sp and dp are latched with the first beat (line 140), but own_ip enters ip_sum and u_sum (lines 74-77) in S_CALC, and own_mac and own_ip are passed to hdr_byte (line 128) throughout S_OUT.
- Rule or reason: A config input that changes between S_CALC and the end of S_OUT yields a frame whose checksums do not match its header bytes. The contract does not say the config must be static.
- Suggested fix: Either latch own_mac and own_ip at the same time as the other header fields, or document that they must be static while the block is busy.

**F-951980 Checksum and critical path: both sums are computed in one cycle (documented limit)**
- Where: `rtl/ipv4_udp_tx.sv:153-157 (S_CALC)`; category timing; confidence high; found by judge
- Evidence: ipcs and ucs are each computed from a chain of 8 to 10 operands plus two folds in one cycle (lines 154-155). The characterisation shows WNS of -4.3 to -5.5 ns at 8 ns (74-82 MHz).
- Rule or reason: The README already states that the block misses 125 MHz. Because S_CALC is a state of its own, the fix is simple: spread the calculation over several cycles at a cost of a few clocks of latency.
- Suggested fix: Split the sum into two or three registered stages inside S_CALC, then update the latency figure and the bench's LATENCY constant.

**F-8dc109 Bench silently skips the independent scapy check when scapy is absent**
- Where: `tb/udp_tx_cocotb.py:31-33 (scapy_check)`; category tb-defect; confidence medium; found by judge
- Evidence: `if not HAVE_SCAPY: return`. The test then passes against the in-repo model only (inet.udp, inet.ipv4), which the README presents as independently cross-checked.
- Rule or reason: The only independent checksum recomputation disappears without a failure or even a warning.
- Suggested fix: Fail, or at least log a prominent warning and mark the test as degraded, when scapy is missing in CI.

### Check findings the reviewer dismissed

- F-f343c0: axis_rules is a library module that is not in this entry's file list; layout noise for the formal wrapper.
- F-270952: The initial block only calls $error to check parameters at elaboration, which is the documented guard approach; it is not state initialisation.
- F-663ce4: No architecture.yaml is needed for this single-module IP; not applicable.
- F-7234fb: STD-AXI-02: the s_axis/m_axis naming is a conventional layout complaint, not applicable.
- F-b5e367: Duplicate of the STD-AXI-02 naming note.
- F-5902c7: Duplicate of the STD-AXI-02 naming note.
- F-44fb9c: Duplicate of the STD-AXI-02 naming note.
- F-9c6888: Duplicate of the STD-AXI-02 naming note.
- F-9387b7: Duplicate of the STD-AXI-02 naming note.
- F-0d5bf6: Duplicate of the STD-AXI-02 naming note.
- F-71cc2f: Duplicate of the STD-AXI-02 naming note.

### Looked at and found sound

- Over-length handling: the first byte past MAX_PAYLOAD sets over, the frame is dropped at tlast with ev_too_long, and n and p_acc are cleared. A payload of exactly MAX_PAYLOAD is accepted.
- UDP and IP lengths (n+8, n+28) and the frame length n+42 are consistent in the 16-bit counters for every legal MAX_PAYLOAD. The tlast condition rj == tlen+13 is correct.
- Checksum arithmetic: ulen is counted twice (pseudo-header and UDP header) and TTL/protocol are packed as {TTL,17}. The single fold, including the 0 to 0xFFFF substitution, is correct and cannot overflow.
- Odd-length payloads are padded on the right via the n[0] placement in p_acc.
- Output pipeline: rd_en = more && (take || !rv) keeps rq and rj stable under back-pressure. tvalid and tdata hold while tready is low, and the next frame is not taken until tlast is accepted.
- Parameter guards use $error at elaboration, and the guard tests are listed. Resets are synchronous and the control, valid and counter registers are all reset.

## 3. Verification gap

**What the existing tests cover.**
- Random lengths up to and over MAX_PAYLOAD, frames compared byte-for-byte with the Python model and recomputed by scapy
- Zero-sum payloads sent as 0xFFFF; unicast and multicast destinations
- Input gaps and output back-pressure
- Frame length, AXI-Stream rules on m_axis and 'input not taken while sending' (bounded formal at depth 4, lutram only)
- Latency of 4 clocks
- Four seeded faults, all caught

**What they miss.**
- MAX_PAYLOAD=1 and power-of-two depths in the bench
- Reset during a frame or during S_CALC
- Identification wrap at 65536 datagrams
- Config (own_ip/own_mac) changing mid-frame
- Formal for the bram variant; no formal on checksum values
- Sustained long runs; scapy check silently skipped if scapy is missing

**Seeded faults they would not catch.**
- A fault in the ident wrap or width (the bench sends only 40 datagrams)
- A fault in own_mac/own_ip capture timing
- A fault in the bram-only read path at MAX_PAYLOAD=8972 (the fault tests run at bram_1472)
- An off-by-one in the RAM address range at a power-of-two depth

No coverage run or mutation run was made by the review: the lists above are the reviewer's reasoning from the test files.

## 4. Questions for the author

- Is own_mac/own_ip guaranteed static while the block is busy (the ARP/MAC integration)?
- Is s_dst_* guaranteed valid on the first beat only, or does the caller hold it for the whole payload?

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

- Reviewer: claude-sonnet-5-5, effort medium, Claude Code 2.1.321 (Claude Code); tokens as the provider reported them: 31727; wall 64.2 s.
- Prompt version 2; check suite standard FDA-HDL.
