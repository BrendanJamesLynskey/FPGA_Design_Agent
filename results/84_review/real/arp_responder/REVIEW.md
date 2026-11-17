# Design review: arp_responder

*Review arp_responder, schema 1. Reviewed directory `arp_responder`, content hash `2a00846313f2`; the reviewed files were not changed (hash checked again at the end: unchanged).*

**Statement of intent:** none given; the intent below is inferred.

## 1. Understanding

**What it does.** arp_responder is a single-clock ARP (RFC 826) block for one IPv4 address. It parses byte-wide Ethernet frames, replies to requests for own_ip, learns sender MACs into a small fully-associative cache with round-robin replacement, and answers next-hop lookups. On a miss it sends a rate-limited broadcast request. It flags address conflicts (RFC 5227) through ev_conflict and never caches the conflicting sender.

**Interfaces.** s_axis: 8-bit AXI-Stream receive with tuser on tlast marking a bad frame, tready tied high. m_axis: 8-bit AXI-Stream transmit of 42-byte frames with tvalid/tready/tlast. Lookup: lk_valid/lk_ip in, lk_done/lk_hit/lk_mac out one clock later, plus flush. Static own_mac and own_ip inputs. Seven one-clock event pulses.

**Clocks and resets.** One clock, clk, and one synchronous active-high reset, rst. There are no clock crossings and no asynchronous resets. Reset covers control state, the cache valid bits and the parse fields. own_mac and own_ip are static inputs treated as quasi-constant.

**Architecture as built.** The receive path is a byte counter k that captures fields by index (et, htype, ptype, hlen, plen, op, sha, spa, tpa). It latches fin, fin_bad and fin_long at tlast, and the combinational arp_ok/for_me/learn terms are evaluated the following clock. The cache is a register array of valid/IP/MAC with priority-encoded known and free search and a round-robin pointer rr. Lookup is a combinational compare registered into lk_*, with a single holdoff timer and IP. Transmit is a small FSM with one reply slot and one request slot, replies first. A function arp_byte generates the frame bytes by index j, using the m_axis registers as a one-byte pipeline.

Facts made by code from the sources:

| Module | File | Clocks | Async-reset edges | Instantiates |
|---|---|---|---|---|
| `arp_responder` | `rtl/arp_responder.sv:1` | clk | - | - |
| `formal_arp` | `formal/formal_arp.sv:1` | clk | - | arp_responder |

```
formal_arp (formal/formal_arp.sv:1, 42 lines; clocks clk)
  dut : arp_responder (rtl/arp_responder.sv:1, 230 lines; clocks clk)
```

Block diagram of the top module: [block_diagram.svg](block_diagram.svg) (made from the source hierarchy).

## 2. Findings

Counts: 0 critical, 1 major, 6 minor, 1 info.

### Major

**F-e7dddd Parsed fields not cleared between frames; stale fields can validate a frame**
- Where: `rtl/arp_responder.sv:93-98 (fin_long / et / htype / sha / spa / tpa)`; category functional; confidence low; found by judge
- Evidence: Field registers are only written at their byte index and are never cleared at frame end. fin_long is k >= 41 at tlast. A frame of 42 or more bytes passes, but a frame that is too short for a field cannot reach fin_long. Padded or long frames overwrite the same fields, so this is mostly benign. Frames of at least 42 bytes always overwrite all fields. Still, fin is evaluated the clock after tlast, and a new frame's first byte can arrive then, with k=0 and no field writes yet, so this is safe. The residual risk is when k saturates at 63 while the frame is longer than 63 bytes.
- Rule or reason: Frame parse state should be derived only from the current frame.
- Suggested fix: Low priority. Note it in the documentation, or clear the fields at tlast.

### Minor

**F-ac4c95 Formal wrapper uses axis_rules module that is not in the file set; checks are bounded only**
- Where: `formal/formal_arp.sv:25-36 (axis_rules)`; category verification; confidence medium; found by both
- Evidence: axis_rules is instantiated but not found (F-1e9377), so it comes from another brief. The assert on viol ignores bit 4 (viol[2:0] and !viol[3]). The wrapper makes no assumption on s_axis, which is fine. The properties are only BMC, with no induction, and CACHE_N=2 and HOLDOFF=3 are used, so the cache size is never at its limits.
- Rule or reason: State what is proved. The check tool cannot resolve the module.
- Suggested fix: Ship or reference axis_rules. Say which bit of viol is excluded and why.

**F-f0e294 Conflict detection suppresses a self-originated frame only by MAC; ev_conflict is not in the formal or fault tests**
- Where: `rtl/arp_responder.sv:120 (ev_conflict)`; category verification; confidence medium; found by both
- Evidence: ev_conflict <= !rst && fin && arp_ok && spa == own_ip && sha != own_mac. ev_conflict is not in the Events list of the main bench (the list names six events, not seven). The formal wrapper leaves the ev_conflict pin unconnected (F-0a0dd0). Only the adversarial bench, which was not provided for review, might check it.
- Rule or reason: Every documented output should be checked.
- Suggested fix: Count ev_conflict in the bench and connect it in the formal wrapper.

**F-0b8ec9 Cache lookup combinational compare limits Fmax; 16 entries miss 125 MHz**
- Where: `rtl/arp_responder.sv:140-143 (lk_h / lk_m)`; category timing; confidence high; found by judge
- Evidence: README reports WNS -0.648 ns at CACHE_N=16, 8 ns clock. The lookup compare feeds lk_hit and lk_mac, and the learn path is a priority chain over the cache. Both are one-stage combinational paths from lk_ip or spa.
- Rule or reason: The default parameter range 1..16 advertises sizes that miss the target clock.
- Suggested fix: Pipeline the compare or the known/free search, as the README next steps already note. Mention in the parameter table that 16 fails 125 MHz.

**F-d00469 Holdoff misses a different address: single holdoff slot, and an ask is suppressed while a request is pending**
- Where: `rtl/arp_responder.sv:151-158 (ask / ho_ip / req_pend)`; category functional; confidence medium; found by judge
- Evidence: ho_ip holds one address. Alternating misses for A and B send a request every time, so the rate limit does not hold per address. Lookups of a different address while req_pend is set are silently not requested (!req_pend). The caller is told to ask again, which is documented in the header, but not that the holdoff is per last-requested address only.
- Rule or reason: Document the interface contract.
- Suggested fix: Document that the holdoff covers only the most recent address, or add a small holdoff table.

**F-5b0c2d Lookup during a learn or flush is not coherent; a hit can be reported for a just-flushed entry**
- Where: `rtl/arp_responder.sv:154-158 (lk_hit / flush)`; category functional; confidence medium; found by judge
- Evidence: The lk_* outputs are registered from lk_h, which reads c_v the same clock that flush clears it. A hit is reported for the clock in which flush asserts. The test never overlaps lookup with flush or learn (the lookup helper runs serially).
- Rule or reason: Document ordering between concurrent flush and lookup.
- Suggested fix: State in the README that a lookup in the flush clock may hit. Optionally mask lk_h with flush.

**F-4a7bcc ev_drop and a reply collision: request arriving at the same clock as start_rep**
- Where: `rtl/arp_responder.sv:220-224 (rep_pend / start_rep)`; category verification; confidence low; found by judge
- Evidence: The code `if (!rep_pend || start_rep)` sets rep_pend; it also assigns rep_pend <= 0 in the start branch earlier. The later nonblocking assignment wins, which is correct. The directed test sends frames 10 clocks apart, so a request arriving exactly at start_rep is never exercised by directed or targeted stimulus. Random traffic with a Sink at 0.7 readiness covers it only by chance, and the bench asserts ev_drop == 0 there, so a drop under the random load would fail rather than be checked.
- Rule or reason: The corner needs a directed test.
- Suggested fix: Add a directed test of back-to-back requests where the second arrives at the clock of start_rep.

### Info

**F-f177d5 initial block with $error used for parameter guard**
- Where: `rtl/arp_responder.sv:57-60 (initial)`; category style; confidence high; found by both
- Evidence: The initial block holds only $error checks on parameters.
- Rule or reason: STD-INIT-01 allows only ROM initialisation, but this is an elaboration-time guard with no synthesised state.
- Suggested fix: Optionally use a generate-if with $error, which is the cleaner elaboration-time form.

### Check findings the reviewer dismissed

- F-663ce4: No architecture.yaml is expected here; documentation lives in ip.yaml.
- F-d44441: Prefix naming noise; the ports are a correct AXI-Stream naming.
- F-82ca7c: Same prefix-naming noise.
- F-2d2cf5: Same prefix-naming noise.
- F-bc4b2a: Same prefix-naming noise.
- F-9a4649: Same prefix-naming noise.
- F-a0b93d: Same prefix-naming noise.
- F-aa1242: Same prefix-naming noise.
- F-ed238c: Same prefix-naming noise.

### Looked at and found sound

- Single clock with synchronous reset and no asynchronous resets; no clock crossings.
- The m_axis hold rules are structurally satisfied: tdata and tvalid change only after tvalid && tready, or at the start of a frame.
- Parameter guards for CACHE_N and HOLDOFF are present, and the tests cover the corners CACHE_N=1 and CACHE_N=16.
- The round-robin pointer wraps correctly, and the known entry is updated in place without moving rr.
- The cache clear-on-flush and reset cover the valid bits, which is what matters for behaviour.
- Transmit byte indexing is consistent: the first byte comes at start, j runs 1..41, and tlast is set when j==41 is loaded.
- The conflict path never caches: learn requires spa != own_ip.

## 3. Verification gap

**What the existing tests cover.**
- Random requests, replies, probes, malformed, padded, bad and short frames against a Python model, with scapy as a second decoder.
- The dropped third reply and the request holdoff, with parameter points CACHE_N 4, 1 and 16.
- Reply latency of 3 clocks.
- Bounded formal checks on m_axis: 42-byte frames and the AXI-Stream hold rules.
- Seven seeded faults.

**What they miss.**
- ev_conflict is not counted in the main bench.
- Lookup concurrent with flush or learn.
- Alternating-address holdoff.
- Frames longer than 63 bytes (saturating k).
- Reset in flight during transmit or receive.
- A request arriving exactly at start_rep.
- Two requests where the sender is unknown, with a full cache and a simultaneous lookup hit.

**Seeded faults they would not catch.**
- Dropping the ev_conflict condition `sha != own_mac`.
- Wrong saturation of k at 63.
- A holdoff counter width or HOLDOFF boundary error (off by one) with long holdoffs.
- Wrong flush clearing of rr.
- A lookup hit based on an invalid entry's stale IP, since flush also zeroes the IP.

No coverage run or mutation run was made by the review: the lists above are the reviewer's reasoning from the test files.

## 4. Questions for the author

- Is own_ip/own_mac guaranteed static while frames are in flight?
- What is the intended behaviour for a lookup issued in the same clock as flush?

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

- Reviewer: claude-sonnet-5-5, effort medium, Claude Code 2.1.321 (Claude Code); tokens as the provider reported them: 28855; wall 33.6 s.
- Prompt version 2; check suite standard FDA-HDL.
