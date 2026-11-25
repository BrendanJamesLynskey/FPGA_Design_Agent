# tcp_fast: datasheet

A TCP fast path for OUCH orders: option A of brief 110's [TCP plan](../../b110_itch_ouch/docs/tcp_plan.md), **simulation and out-of-context timing only**.
Software owns the TCP connection (handshake, acknowledgements, retransmission, SoupBinTCP login and heartbeats) and hands the block the connection's
addressing and sequence state over a register bus. For each order the block builds one complete Ethernet frame (without the frame check sequence):
Ethernet, IPv4 and TCP headers from a template, then the 59-byte SoupBinTCP 3.00 packet that carries the OUCH 5.0 Enter Order of brief 110, with the
sequence number, IP identification and both checksums finished in a few clocks by adding the changing fields to partial sums computed when the connection
was armed. It supports brief 110's speculative start and abort: an aborted frame ends with a poisoned frame check sequence and **consumes no sequence
space**. Each segment that really left is handed back to software for retransmission bookkeeping. The data are synthetic; nothing ran on a board and
nothing was sent to a real exchange. The software side (a user-space TCP endpoint, the owner and a software exchange) is in
[software_side.md](software_side.md).

```
order side (go, fields, commit/abort)                                          register bus (software)
        |                                                                            |
        v                                                                            v
  +-----------+   header template + partial sums    +-----------------+     +-------------+
  | tcp_fast  |<-----------------------------------| connection state |<----| owner (Python)|
  |  checksum |   seq / ack / window / id captured  | arm, valid, age  |     | handshake,    |
  |  pipeline |   at the go edge                    +-----------------+     | ACKs, RTO,    |
  |  + ouch_enter (brief 110) builds the payload words                      | login, hb     |
  +-----------+                                                             +-------------+
        | o_* words (113 bytes, 15 words), o_poison with the last word               ^
        v                                                                            | rec_* (seq, length, id, payload) for every segment that left
     to the MAC (FCS appended; poison makes it wrong)  ----------------------------->+
```

## 1. Interfaces and what a user could guess wrong

One clock `clk` (the 10G core's user clock, 161.1328125 MHz, period 6.2061 ns), one synchronous reset `rst` (active high; clears every register and
counter; no asynchronous input, no clock crossing). After reset the block is **not armed**: every order is refused until software has written the
connection and armed it (section 3).

### 1.1 Order side

The inputs are those of `ouch_enter` (brief 110), so the block replaces it in `itch_ouch_top`; `busy` is the same output and the risk logic queues behind it.

| Signal | Meaning | A user could guess wrong |
|---|---|---|
| `go` | start an order, fields on `f_*`, sampled in this clock (the **go edge**, called edge 0) | a `go` while the block is busy is **dropped**, not queued (counted, code 5 on `refuse_*`); the risk logic never does this because it waits for `busy` |
| `go_spec` | the order is started before the risk verdict | a speculative segment still without a verdict at its last word is **poisoned** (fail closed), see 2.4 |
| `f_sym`, `f_px`, `f_qty`, `f_ref` | the order's symbol, price, quantity and number | captured at the go edge; ClOrdID is built from `f_ref` as brief 110 does |
| `commit`, `abort` | the verdict, in the clock of edge k (k = 0 is the go edge) | `abort` wins over `commit`; `commit` is only honoured up to edge 14; `abort` at edge 0 cancels the go |
| `cfg_*` | order configuration (TIF, display, capacity, sweep, cross, customer type, MinQty) | **static while a segment is in flight**: a change between edge 1 and edge 13 makes the check of the payload sum fail and the segment is poisoned (counter `sumerr`) |
| `busy` | high from the clock after the go edge; low again in the clock in which the last word is visible | the next `go` is accepted 15 clocks after this one's, against 8 for the stub port of brief 110: the risk logic's order queue fills sooner at a high order rate |
| `late` | an `abort` arrived with nothing in flight (one clock) | also set for an `abort` after a refused `go`; not set when the abort cancels a `go` in its own clock |
| `refuse_v`, `refuse_code` | an order was refused or dropped (one clock after the go edge) | **the order is lost**: the risk logic has already used the order number and counted the position (section 5) |

`refuse_code`: 1 not armed, 2 template not valid or the state is stale, 3 window closed, 4 MSS below one segment, 5 busy. When several apply the first in
this order is reported and counted: busy, not armed, not valid or stale, window, MSS.

### 1.2 Segment output (`o_*`)

| Signal | Meaning | A user could guess wrong |
|---|---|---|
| `o_v`, `o_sof`, `o_eof` | word valid, first word, last word | a segment is 15 words, **never paused**, so the MAC must accept a word every clock; an early abort makes it shorter |
| `o_d` | 64 bits, byte 0 in bits 7:0 | the frame has **no FCS**; the MAC appends it. The Ethernet preamble is the MAC's too |
| `o_keep` | byte enables | all ones except the last word of a complete segment, which carries one byte (`0x01`); an aborted segment ends with an all-ones word |
| `o_poison` | with the last word: the FCS must be made wrong | an aborted or unverdicted segment is **not withheld**: its words leave and the poison asks the MAC to corrupt the FCS (the `s_poison` of `mac64_tx`). Not tried on a real MAC or receiver here |

A complete segment is 113 bytes: Ethernet 14, IPv4 20, TCP 20 (no options), payload 59. The headers are the same for every segment except the fields in 2.1.

### 1.3 Hand-back to software (`rec_*`)

| Signal | Meaning | A user could guess wrong |
|---|---|---|
| `rec_v` | one clock, in the clock in which the last word (`o_eof`) of a segment that was not poisoned is visible | **not buffered**: the consumer (a FIFO in the integration) must take it in that clock or the segment cannot be retransmitted later |
| `rec_seq`, `rec_len`, `rec_id` | sequence number of the first payload byte, payload length, IP identification | `rec_len` is always 59 here |
| `rec_pay` | the 59 payload bytes, byte 0 in bits 7:0 | stable from `rec_v` until the next segment completes |

A poisoned segment produces no record and changes no state.
**Poisoned downstream (brief 176).** The block decides unpoisoned or poisoned at the last word, but the transmit side can still poison the frame (the trigger frame's bad FCS, STRICT mode without a verdict) or drop it whole (the MAC was owned). Two input pulses cover it: `tx_unsent` (one clock, in the clock the MAC takes the last word of a frame that was counted sent here and then poisoned) subtracts 59 from SND_NXT and 1 from IP_ID and counts `unsent`; `tx_drop` (one clock, in the clock of the segment's first word) makes the segment consume nothing and leave no record. A `go` in the same clock as `tx_unsent` takes the corrected numbers. The record `rec_v` of such a segment was already emitted: a consumer that retransmits from it must also watch `tx_unsent`. The flight test of that same-clock `go` still uses the uncorrected SND_NXT, so it can refuse one segment early at the very edge of the window. Tie both inputs to 0 when no transmit side poisons.

### 1.4 Register bus (`sw_*`)

Word addresses. `sw_we` with `sw_waddr` and `sw_wdata` writes in the clock; `sw_raddr` selects a register and `sw_rdata` shows its contents **as they were
before the clock edge that follows**, so a write is visible to a read issued the clock after it. Unmapped addresses read 0 and ignore writes.

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0 | CTRL | W: bit 0; R: bit 0 arm request, bit 1 valid, bit 2 busy | writing bit 0 = 1 sets the arm request and **rebuilds the template**: valid goes low and returns two clocks later. Writing bit 0 = 0 clears the arm request at once (a segment in flight completes). A write with bit 0 = 1 while busy or building is **ignored and counted** |
| 1, 2 | DMAC_HI, DMAC_LO | R/W | destination MAC, upper 16 bits and lower 32 bits |
| 3, 4 | SMAC_HI, SMAC_LO | R/W | source MAC |
| 5, 6 | SIP, DIP | R/W | IPv4 source and destination, as written in dotted order (`10.0.0.2` is `0x0A000002`) |
| 7 | PORTS | R/W | source port in bits 31:16, destination port in bits 15:0 |
| 8 | TTL_MSS | R/W | MSS in bits 31:16, TTL in bits 7:0 |
| 9 | SND_NXT | R/W | the next sequence number to send; written by software to give the sequence space back; **updated by the block** after each segment that left |
| 10 | SND_UNA | R/W | oldest unacknowledged sequence number |
| 11 | SND_WND | R/W | the peer's receive window in **bytes** (already scaled by software if window scaling was negotiated) |
| 12 | RCV_NXT | R/W | the acknowledgement number to piggyback |
| 13 | RCV_WND | R/W | the 16-bit window field to advertise (already scaled down by software if window scaling was negotiated) |
| 14 | IP_ID | R/W | the IP identification of the next segment; updated by the block |
| 15 | STALE_LIMIT | R/W | clocks; 0 disables the staleness check |
| 16 to 30 | counters | R | see 1.5 |
| 31 | CLR_CNT | W | any write clears every counter |

What a write does:
- **Static fields (1 to 8):** a write marks the template **not valid** (orders are then refused with code 2 until CTRL bit 0 = 1 is written again) and is ignored and counted while a segment is in flight or the template is building.
- **SND_NXT and IP_ID:** ignored and counted while a segment is in flight or the template is building; otherwise they take effect for the next segment and leave the template valid.
- **Live fields (SND_UNA, SND_WND, RCV_NXT, RCV_WND):** accepted at any time and restart the staleness age. A segment in flight keeps the ACK number and window it captured at its go edge; the next segment uses the new ones.
- **STALE_LIMIT:** takes effect at once and does not restart the age.
- Writing CTRL bit 0 = 1 also restarts the age.

### 1.5 Counters

32 bits, wrap, never saturate; reset and CLR_CNT zero them. Addresses 16 to 30, in this order.

| Addr | Name | Counts |
|---|---|---|
| 16 | sent | segments that left unpoisoned |
| 17 | poison | segments that ended poisoned (abort, no verdict, or payload sum mismatch) |
| 18 | ref_arm | orders refused, not armed |
| 19 | ref_stale | orders refused, template not valid or state stale |
| 20 | ref_win | orders refused, window closed |
| 21 | ref_mss | orders refused, MSS below one segment |
| 22 | busy | orders dropped because the block was busy |
| 23 | late | aborts with nothing in flight |
| 24 | nov | speculative segments poisoned for want of a verdict |
| 25 | wrign | register writes ignored (static, SND_NXT, IP_ID or arm while busy or building) |
| 26 | sumerr | segments poisoned because the payload sum of the bytes sent differed from the sum the checksum used |
| 27 | cancel0 | orders cancelled by an abort in their go clock |
| 28 | build | template builds completed |
| 29 | abort | segments aborted in flight (also counted in `poison`) |
| 30 | unsent | segments given back by the transmit side (`tx_unsent`, brief 176): they ended unpoisoned here (so they are also in `sent`) but the multiplexer poisoned them downstream |

## 2. Behaviour in detail

### 2.1 The segment

Wire offsets (byte 0 is the first byte of the destination MAC); the fields marked * change from segment to segment.

| Bytes | Field | Value |
|---|---|---|
| 0 to 5, 6 to 11 | destination MAC, source MAC | from DMAC, SMAC |
| 12 to 13 | EtherType | `0x0800` |
| 14 to 15 | IPv4 version, header length, DSCP/ECN | `0x45`, `0x00` |
| 16 to 17 | total length | 99 (always) |
| 18 to 19 | identification * | IP_ID, then incremented |
| 20 to 21 | flags, fragment offset | `0x4000` (don't fragment) |
| 22, 23 | TTL, protocol | TTL, 6 |
| 24 to 25 | header checksum * | RFC 1071, includes the identification |
| 26 to 33 | source, destination address | SIP, DIP |
| 34 to 37 | source, destination port | PORTS |
| 38 to 41 | sequence number * | SND_NXT at the go edge |
| 42 to 45 | acknowledgement number * | RCV_NXT at the go edge |
| 46, 47 | data offset, flags | `0x50` (no options), `0x18` (PSH and ACK) |
| 48 to 49 | window * | RCV_WND at the go edge |
| 50 to 51 | checksum * | RFC 1071 over the pseudo-header, header and payload |
| 52 to 53 | urgent pointer | 0 |
| 54 to 112 | payload * | the SoupBinTCP Unsequenced Data packet of brief 110 (length `0x0039`, `U`, the 56-byte Enter Order) |

**Options.** The block sends no TCP options, so the connection must not use any that has to be present on every segment: **disable timestamps** (RFC 7323
requires them on every segment once negotiated; a segment without one may be dropped by the peer). SACK-permitted and window scaling need nothing on a data
segment, but the scaled values are software's business (1.4). A TCP checksum that comes out 0 is sent as 0 (the UDP rule does not apply to TCP).

### 2.2 Checksums: incremental, not recomputed

When software writes CTRL bit 0 = 1 the block builds the template: two clocks later it holds the folded sum of the IPv4 header's fixed words (version and
length, total length, flags, TTL and protocol, the two addresses) and the folded sum of the TCP pseudo-header's and header's fixed words (addresses,
protocol, TCP length 79, ports, data offset and flags). For each order:
- the IPv4 checksum is the complement of the template sum plus the identification (final at edge 2);
- the TCP checksum is the complement of the folded total of the template sum, the sequence number (two words), the acknowledgement number (two words), the window and the **payload sum** (final at edge 5). The payload sum is formed from the order's fields by a two-stage adder tree (30 sixteen-bit words, the last padded with a zero byte), not from the words as they stream out, because the checksum field is sent before the payload;
- as an independent check the block sums the payload words that `ouch_enter` actually emits and compares the total with the early one at the last word; a difference poisons the segment and counts `sumerr`. This guards against the two copies of the frame layout drifting apart and against a change of `cfg_*` in flight.

Software never computes a checksum: it writes addresses and ports, and the block derives the partial sums itself, so a wrong partial sum cannot reach the wire.

### 2.3 Timing of a segment

Edge 0 is the clock edge that samples `go`. Word k of the segment is loaded into the output registers at edge k, so it is visible in the clock after edge k.

| Edge | What happens |
|---|---|
| 0 | word 0 out (`o_sof`); the refusal is decided; sequence number, acknowledgement number, window and identification captured |
| 1 to 2 | IPv4 checksum formed, final at edge 2 (word 3 carries it) |
| 1 to 5 | TCP checksum formed, final at edge 5 |
| 5 | the embedded `ouch_enter` is started with the captured fields; its eight words stream at edges 5 to 12 |
| 6 | word 6: window, TCP checksum, urgent pointer and the first two payload bytes |
| 14 | word 14 (the last payload byte, `o_eof`); state advanced, record emitted, or the segment poisoned |

The payload arrives from `ouch_enter` six bytes behind the header's end (54 mod 8 = 6), so each payload word is built from two builder words.

### 2.4 Speculative start, abort, verdict

The segment can start before the risk verdict. The verdict is `commit` or `abort` in the clock of any edge from 0 to 14 (edge 0 is the go edge).
- `abort` at edge 0 cancels the `go`: nothing leaves, nothing is counted except `cancel0`.
- `abort` at edge 1 to 14 ends the segment at once: the word that would have gone out at that edge is the last, with `o_eof` and `o_poison`. **Nothing is consumed**: SND_NXT and IP_ID are as before, so the next segment has the same sequence number and identification. The embedded frame builder is stopped with it, so a `go` in the very next clock is accepted.
- `abort` from edge 15 (nothing in flight) is a late abort: counted, ignored. The segment, if it was complete, had already left and is real: it was recorded and SND_NXT advanced.
- A speculative segment (`go_spec`) with no `commit` by edge 14 is poisoned and counted in `nov`. A non-speculative segment needs no verdict.
- `commit` before an `abort` does not protect the segment: an abort up to edge 14 always wins.
- A poisoned segment leaves the peer's TCP state unchanged by construction, because the peer's MAC drops it; the end-to-end test shows the software exchange sees no gap and no duplicate.

In brief 110's pipeline the verdict arrives before the end of its 8-word frame; the segment is longer (15 words), so the verdict has more margin here.

### 2.5 Refusals

An order is refused (nothing leaves, `refuse_v` for one clock, the matching counter) when, checked in this order at the go edge:
1. the block is busy (code 5);
2. the arm request is clear (1);
3. the template is not valid, or the state is stale (2): **stale** means `STALE_LIMIT` is non-zero and more than that many clocks have passed since the last refresh write (SND_UNA, SND_WND, RCV_NXT, RCV_WND or an arm write); the age as the block sees it at the go edge is the number of clocks since the refresh write's edge less one;
4. the window is closed (3): the block needs `SND_NXT - SND_UNA + 59 <= SND_WND`, with the difference taken modulo 2^32, so a window of exactly 59 bytes admits one segment and one byte less admits none; a SND_UNA ahead of SND_NXT gives a huge difference and is refused;
5. the MSS register is below 59 (4).

The staleness check exists so that a hung or crashed owner stops the fast path: if software stops refreshing, orders stop. It is a software watchdog, not a protocol feature.

## 3. What software must do and when

1. **Open the connection and log in** with its own TCP: handshake, then the SoupBinTCP Login Request (`L`) and wait for Login Accepted (`A`).
2. **Hand over:** write the static fields (1 to 8), SND_NXT (the stack's next sequence number), IP_ID, STALE_LIMIT, the live fields from the stack's state, then write CTRL = 1 and **wait for the valid bit** (two clocks).
3. **Keep the live fields current:** after each segment from the peer, write SND_UNA, SND_WND, RCV_NXT and RCV_WND if they changed; with a stale limit set, rewrite one of them at least every half limit.
4. **Record every `rec_*` pulse** as sent bytes (sequence number, payload), in order. A record whose sequence number is not the stack's SND_NXT means the sequence space was corrupted: stop.
5. **Retransmit from the records**: when the retransmission timer expires, resend the oldest unacknowledged segment's bytes from the record with software's own headers (the fast path never retransmits). A retransmission does not move SND_NXT, so it needs no hand-over.
6. **To send its own bytes** (login, client heartbeat after one second of silence, logout): write CTRL = 0, wait for `busy` (CTRL bit 2) to clear, absorb the last record, read SND_NXT and check it equals the stack's, send, then **give the sequence space back**: write SND_NXT with the stack's new value, refresh the live fields, write CTRL = 1 and wait for valid. Orders arriving meanwhile are refused (code 1).
7. **Pure ACKs** carry the sequence number read from the block's SND_NXT when it is idle: a sequence number behind the peer's expected one makes the peer discard the segment (RFC 793 acceptability).
8. **Use a separate IP identification range** for software segments (the model uses 0x8000 and up); with don't-fragment set the value only needs to be harmless.
9. **Do not change `cfg_*` while a segment may be in flight.**
10. **Disarm before closing**, and never write SND_NXT or the static fields while armed and busy: the write is ignored and counted.

## 4. Latency and rate

All figures are clocks of 6.2061 ns in simulation (`results/b119/bench_sim.json`, `results/b119/top_sim.json`), counted from the clock in which `go` is presented.

| Quantity | Value |
|---|---|
| first byte of the frame (destination MAC) after `go` | 1 clock |
| last byte of the IPv4 checksum field after `go` | 4 clocks |
| last byte of the TCP checksum field after `go` | 7 clocks |
| last byte of the segment after `go` | 15 clocks |
| segment starts, back to back | every 15 clocks |

The headers add nothing to the first byte: the destination MAC leaves in the same clock the stub port of brief 110 shows its first word. Behind brief 110's
risk logic (`rtl/itch_ouch_tcp_top.sv`, simulation) the first byte of the Ethernet frame is **8 clocks** after the last byte of the triggering ITCH message when the frame
starts at the verdict and **3 clocks** when it starts speculatively, the same as the stub port. The checksum fields are complete 6 clocks after the first byte, inside the
header's own transmission time, as the TCP plan claimed.

Throughput: one segment per 15 clocks (the block is busy that long and drops a `go` meanwhile).

## 5. Integration notes (phase 2)

[phase2_integration.md](phase2_integration.md) lists what changes in the 96 design and what is open. The points a user could guess wrong:
- **A refused order is lost, and the risk logic does not know.** `risk_glue` of brief 110 has already assigned the order number and counted the position when `go` is refused. A feedback of `refuse_v` to `risk_glue` (give the number back, subtract the position) is not built.
- **`busy` lasts 15 clocks.** The four-entry order queue of `risk_glue` absorbs bursts of candidates; the count `rej_busy` of brief 110 will be higher than with the stub port at the same input.
- **The MAC must accept a word every clock** and honour `o_poison`; the `mac64_tx` of the 96 design has a poison input of the same kind, but the pair was not simulated together.
- **Receive side:** the block parses nothing. Software (or the PS) must see every segment of the connection to keep SND_UNA, SND_WND and RCV_NXT current.

## 6. Parameters and resources

There are no parameters. The out-of-context cost and timing are in the [README](../README.md) and `results/b119/ooc/tcp_fast.json`.
