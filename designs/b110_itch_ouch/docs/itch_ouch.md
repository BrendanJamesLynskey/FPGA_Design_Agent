# itch_ouch_top: datasheet

Phase 1 of a standard-protocol trading path, **simulation and out-of-context timing only**: MoldUDP64 carrying Nasdaq TotalView-ITCH 5.0 in,
a small top-of-book, a decision with pre-trade risk and a kill switch, an OUCH 5.0 Enter Order in a SoupBinTCP 3.00 packet out. Every field
layout is cited in [spec_notes.md](spec_notes.md). The data are synthetic ([model/gen.py](../model/gen.py)); nothing here ran on a board or
touched a real feed or exchange.

```
UDP payload words --> mold_rx --> itch_dec --> book_core --> risk_glue --> ouch_enter --> frame words (stub port)
 (64 bit, 6.2061 ns)   MoldUDP64    ITCH 5.0    table +        rule, risk,    OUCH 5.0 in
                       seq, gaps    decoder     ladders +      kill switch,   SoupBinTCP 3.00
                                                top of book    queue, refs
```

## 1. Interfaces and what a user could guess wrong

One clock `clk` (the 10G core's user clock, 161.1328125 MHz, period 6.2061 ns). One synchronous reset `rst` (active high; resets every register,
including the counters, and starts the table sweep). No asynchronous input, no clock crossing. All `cfg_*` inputs are **static while traffic
runs**: a change takes effect for events decoded after it, and a change while a candidate is in the pipeline may be seen by it or not.

### 1.1 Payload input (`s_*`)

| Signal | Meaning | A user could guess wrong |
|---|---|---|
| `s_v` | the word is valid | may drop inside a packet (the PCS pauses one clock in 33); state is held |
| `s_d[63:0]` | UDP payload, byte 0 in bits 7:0 | byte order is little endian across the word, big endian inside each protocol field |
| `s_sof` | first word of a payload | restarts the packet, whatever the previous one left behind (a packet cut without `s_eof` is forgotten, silently) |
| `s_eof` | last word | |
| `s_keep[7:0]` | valid bytes of the **last** word | must be low-contiguous (`01 03 07 0F 1F 3F 7F FF`); any other value is read as all eight; ignored on other words |
| `s_err` | with `s_eof`: the frame's check failed or it was cut | counts (`pkt_err`), raises `untrusted`; the packet's messages **were already delivered** (cut-through) |

The path starts at the UDP payload: no Ethernet, IP or UDP header handling and no FCS check (phase 2, [phase2_integration.md](phase2_integration.md)).
Packets need no idle gap between them (tested from 0 clocks, `results/b110/min_idle_sim.json`); real frames leave far more.
A payload shorter than 20 bytes is counted (`short`) and ignored. Payload words after the last block (trailing bytes) are ignored.

### 1.2 Order frame output (stub port, `o_*`)

| Signal | Meaning | A user could guess wrong |
|---|---|---|
| `o_v`, `o_sof`, `o_eof` | a frame of eight words, one a clock, `o_sof` on the first, `o_eof` on the last | never paused inside a frame |
| `o_d[63:0]` | byte 0 in bits 7:0 | the frame is the SoupBinTCP packet: length `0x0039`, `U`, then the 56 byte Enter Order; 59 bytes in all |
| `o_keep` | `FF` except `07` on the last word | |
| `o_abort` | one clock: **the frame in flight is cancelled** | `o_v` is low in that clock; the words already out are void and the consumer must discard them. Only a speculative frame can be aborted |

There is no TCP here: the stub port is where a TCP stack, or a fast path for pre-built segments, takes the bytes ([tcp_plan.md](tcp_plan.md)).
Order frame byte map and field values: [spec_notes.md](spec_notes.md) section 3.

### 1.3 Configuration (static)

| Input | Meaning | Legal values / default in the bench |
|---|---|---|
| `cfg_watch[N_INST*64]` | the watched symbols, instrument i in bits `64*i +: 64`, first character in the top byte, space padded | ASCII |
| `cfg_thr` | candidate rule: a new **sell** order at or below this Price(4) (and not zero) | the unit is Price(4): 1000000 is 100.0000 |
| `cfg_qty` | order quantity | 1 to 999999 and at most `cfg_max_qty`, else every candidate is refused (`rej_size`) |
| `cfg_max_qty`, `cfg_max_pos` | risk limits | position is the quantity **sent**, not filled |
| `cfg_band` | a buy price may be at most this far above the band reference (next four rows) | Price(4) units |
| `cfg_ref_sw`, `cfg_ref_px`, `cfg_ref_age`, `ref_load` | **band reference (brief 188, idea from Edwards 2026, ch 9).** `cfg_ref_sw` 0: the reference is this path's own best bid, as before (a strategy that mis-reads its own feed also mis-sets its own limit, so this is the weaker choice). 1: the reference is `cfg_ref_px`, a price software wrote from another source; it counts only while it is fresh: `ref_load` (one clock, strobed when software wrote `cfg_ref_px`) restarts an age counter, and a verdict taken when the age is above `cfg_ref_age` clocks, or before any `ref_load` since reset, is refused as `rej_band` | with `cfg_ref_sw` 1 the book's bid is not consulted at all, so a candidate is judged even when the book has no bid. The age is in core clocks and counted to within one clock; `cfg_ref_age` 0 means fresh only in the one clock after the `ref_load` strobe; the reference is a **price, not a limit**: only the upper side is checked (a buy far below it is allowed) |
| `cfg_px_off` | added to the triggering order's price to give the order price | 32 bit; **if the sum passes 2^32 - 1 the candidate is refused as `rej_band`** (it used to wrap and be judged as a small price) |
| `cfg_holdoff` | **hold-off (brief 188; b58a's rule hold-off).** After an order is accepted for an instrument, further candidates of that instrument are refused for this many clocks, counted as `rej_busy`; speculation is not started while any instrument is in hold-off | 0 = off; 16 bit, at most 65535 clocks (406.7 microseconds at 161.13 MHz); per instrument, others are unaffected; the refusal is checked last, after every other check, so a candidate that would fail another check is counted under that one; timing dependent |
| `cfg_max_notional`, `cfg_nt_shift`, `cfg_nt_tbl` | **notional check (brief 188), only when built with `NOTIONAL_MODE` 1 or 2** (section 4; ignored in mode 0). Mode 1: order price times `cfg_qty` must be at most `cfg_max_notional` (64 bit). Mode 2: `cfg_qty` must be at most `cfg_nt_tbl[i]` with bucket i = min(order price >> `cfg_nt_shift`, 15); software fills entry i with the limit divided by the **highest** price of bucket i, rounded down (the last bucket: the largest price, 2^32 - 1), so the table never admits an order the multiply would refuse but can refuse some the multiply admits (a price below the top of its bucket) | a refusal is counted as `rej_size`; both are computed on an early copy of the price three clocks before the verdict (no added clock; computed in the verdict clock the multiply missed the 6.2061 ns clock by 2.27 ns and the table by 0.63 ns, see the measurement); in mode 1 a limit of 0 refuses every order; both modes check the order price (candidate price plus `cfg_px_off`) |
| `cfg_tif`, `cfg_display`, `cfg_capacity`, `cfg_ise`, `cfg_cross`, `cfg_custtype`, `cfg_minqty` | OUCH Enter Order fields | ASCII codes; see spec_notes |
| `cfg_arm` | orders allowed | not armed: candidates are refused and counted (`rej_arm`) |
| `cfg_kill` | **kill switch**: no order starts while set | the next candidate after the change is refused (`rej_kill`); a frame already started is not recalled, except a speculative one whose verdict has not come |
| `cfg_halt_on_gap` | a sequence gap stops orders | set: orders stop at the first gap until `clr_flags`; clear: gaps are only counted |
| `cfg_spec` | speculative frame start | see section 3 |

One-clock pulses: `clr_cnt` (counters), `clr_flags` (gap, untrusted, end-of-session, the session lock and the expected sequence number: the
next packet defines the sequence again), `clr_book` (order table, ladders, locate map and inexact flags; starts the sweep), `clr_pos`
(positions sent), `clr_ref` (the next order number is 1). **The sweep takes 2^ORD_AW clocks; events decoded during it are dropped and counted
(`evdrop`)**; `flags[4]` (book ready) is low meanwhile. After `rst` the same sweep runs.

### 1.4 Observation and counters

`flags[15:0]`: 0 sequence gap seen, 1 untrusted (a bad frame was seen), 2 end of session seen, 3 session locked, 4 book ready, 5 order frame busy,
8 and up one inexact flag per instrument. `cnt` holds 45 counters of 32 bits, counter k in `cnt[32*k +: 32]`, **saturating never: they wrap**;
the index list is `rtl/itch_pkg.sv`, generated from the model's list, and every counter is defined here:

| Counter | Counts |
|---|---|
| `pkt` | packets accepted (not another session, not a duplicate), heartbeats and end-of-session packets included |
| `msg` | messages delivered to the decoder |
| `gap`, `missing` | sequence gaps (packets) and the messages they skipped (`missing` is the sum of the distances) |
| `dup` | packets dropped whole as old or duplicate (a heartbeat or end of session with a sequence below the expected one is also `dup`) |
| `ovlp` | messages skipped at the start of a packet that began before the expected number |
| `sess` | packets of another session, dropped |
| `hb`, `eos` | heartbeats, end-of-session packets (accepted ones only) |
| `short`, `trunc`, `badlen` | payloads under 20 bytes; packets that end inside a block or hold fewer blocks than their count says; blocks under 12 bytes |
| `pkt_err` | packets whose `s_err` was set |
| `m_a m_f m_e m_c m_x m_d m_u m_s m_r` | messages of that ITCH type with the right length |
| `m_skip`, `m_bad` | messages of other types; a known type with a wrong length, a bad side letter or zero shares |
| `unwatch` | order messages whose stock locate is not a watched instrument |
| `omiss` | an Execute, Cancel, Delete or Replace of a watched instrument whose order reference is not in the table |
| `odup` | an Add whose reference is already live (ignored) |
| `oovf` | an Add (or the new half of a Replace) whose table index holds a different live order: **not stored**, the instrument becomes inexact. Also (brief 188) an Add of zero shares, which would be a live entry of no size: not stored, instrument inexact (the decoder already refuses zero shares as `m_bad`, so this is a second line of defence) |
| `oover` | an execution of more shares than remain (the order is removed) |
| `lvovf` | an Add whose price has no level and the ladder is full: **the ladder is not updated, but the order is still stored in the order table** (a later removal at that price finds no level and counts `lvmiss`); the instrument becomes inexact, and a candidate Add is counted in `cand` and refused as stale |
| `lvmiss` | a removal at a price that has no level |
| (`lvovf`, continued) | **Level sizes saturate (brief 188).** An Add whose quantity would take a level past 2^32 - 1 leaves the level at 2^32 - 1 (it used to wrap to a small number), counts `lvovf` and makes the instrument inexact; a later removal from that level subtracts from the saturated value, which is no longer the true size, so the instrument stays inexact until `clr_book` |
| `evdrop` | events dropped during a sweep, or because the two-entry queue was full |
| `cand` | candidates reaching the verdict (the Add was stored in the order table; this includes an Add that the full ladder could not hold, `lvovf`) |
| `fire` | orders accepted and started or queued |
| `rej_arm rej_kill rej_gap rej_stale rej_size rej_pos rej_band` | candidates refused, the first failing check in that order |
| `rej_busy` | a passing candidate with the frame busy and the queue full, **or refused in hold-off (brief 188)**: timing dependent |
| `abort` | speculative frames cancelled (risk reject, or no book update) |
| `late_abort` | a cancel that found no frame in flight (never seen) |
| `spec` | speculative starts |

`tu_*` is the top-of-book update record: one per ladder change, **visible 7 clocks after the last byte of the message** (section 3), with the touched
side's best price and size after the change; `tob_*` are the registers of all instruments and sides (index `inst*2 + side`, side 0 bid, 1 ask).
An empty side reads price 0, size 0, `ok` 0. `sys_code` holds the last System Event code.

## 2. Behaviour in detail

**Packet level (mold_rx).** The first accepted packet locks the session. The expected sequence number is set by the first packet after reset or
`clr_flags` (no gap is reported for it) and moves to *first + count* after every accepted packet (heartbeats: *first*). A packet above the
expected number is a **gap**: counted, `gap` flag set, all its messages delivered, nothing requested. A packet entirely below it, or one with
count 0 below it, is a duplicate and dropped. A packet that starts below it and ends above it delivers only the messages from the expected
number on. The messages of a packet reach the decoder as they complete, **before the packet's frame check is known**: `s_err` marks the later
traffic `untrusted`, it cannot recall messages already applied or orders already triggered. A candidate in the very packet that carries the mark is
refused only if the mark had been set before its message was decoded, which depends on how near the packet's end the message is: the tests keep packets
with `s_err` free of candidates, and the decision there is not specified. A block shorter than 12 bytes drops the rest of
its packet. A packet may carry up to 65534 messages.

**Decoder (itch_dec).** See spec_notes section 2. A malformed message (`m_bad`) is dropped whole; it does not reach the book.

**Book (book_core).** Instruments are found through Stock Directory messages: the stock field is compared with `cfg_watch` and the locate
is remembered (the lowest instrument index wins if two entries match). A Stock Directory seen before `clr_book` is forgotten by it. Order
messages of other locates are ignored (`unwatch`). The order table has 2^ORD_AW entries addressed by the low bits of the order reference; each
holds the full reference, instrument, side, price and remaining shares. Adds are stored unless the entry is occupied. Executes and cancels
reduce the remaining shares; an order with none left is removed; a Delete removes it. A Replace removes the old order and adds the new one
with the old order's instrument and side, in that order, as two ladder changes (two `tu` records). Each instrument and side has LEVELS price
levels with an aggregate size; the best level is the highest bid or lowest ask. A level whose size reaches 0 is removed; sizes are 32 bits
and wrap. **Not a full book:** more than LEVELS distinct prices on a side, or two live orders with the same table index, cannot be tracked;
the event is counted, `inexact` is set for that instrument, orders on it are refused (`rej_stale`) and its book is not trustworthy until
`clr_book`. Priority between orders at a price is not modelled. Only the first 36 bytes of a message are used.

**Decision and risk (risk_glue).** A candidate is an Add (A or F) of a **sell** order at or below `cfg_thr` that was stored. A Replace never
triggers. The checks, in order, name the one reason counted: not armed; kill switch; untrusted frame or (halt on gap and a gap) as seen when
the message was decoded; the instrument inexact when the Add was applied; quantity zero, above `cfg_max_qty` or at least 1,000,000;
position sent plus the quantity above `cfg_max_pos`; no best bid, or the price above best bid plus `cfg_band` (the bid is the book after
this and every earlier message). A passing candidate raises the position by the quantity and the order number by one, and starts a frame
(or waits in a four entry queue behind a busy frame). The order number is assigned when the candidate passes, so refused candidates use
none. The rule is the one of `trade64` in the 96 design; trade64's input (Bench Feed v1 frames) is not used.

**Order frame (ouch_enter).** See spec_notes section 3. The order price is the triggering order's price plus `cfg_px_off`.

## 3. Latency and rate

Clock numbering: T is the clock in which the last byte of the message is presented on `s_*`; a registered output is "visible at T+n" in the
n-th clock after. Measured in simulation by `tests/b110_cocotb.py::latency`, record [results/b110/latency_sim.json](../../../results/b110/latency_sim.json):

| Event | Clocks after T |
|---|---|
| message delivered by mold_rx (`m_v`) | 1 |
| decoded event (`e_v`) | 2 |
| top-of-book update visible, for A, F, E, C, X, D and the first change of a U | 7 |
| the second change of a Replace | 8 |
| first word of the order frame, speculative start | 3 |
| first word of the order frame, started at the verdict | 8 |

The frame is eight words, so a speculative frame ends 10 clocks after T; its verdict (commit or abort) is at 7, 8 at the latest.
One clock is 6.2061 ns, so 7 clocks are 43.4 ns and 3 clocks 18.6 ns. These are clocks inside this block only; they do not include the PCS,
the MAC, the UDP/IP header (the payload starts 42 bytes into the frame), nor the TCP stack that would take the order frame.

**Speculation.** With `cfg_spec` set, the frame starts when the candidate is decoded, **if** the frame is idle, the order queue is empty and
no earlier candidate is still in flight (otherwise it starts at the verdict, as without `cfg_spec`). The verdict then arrives while the frame is
still being emitted: pass = commit, the frame continues; refuse, or the Add turned out a duplicate or an order-table overflow, or a stale book (including a ladder overflow, which makes the instrument inexact) = `o_abort`. The orders that
leave, their content and their numbers are **the same with and without speculation**; only the start time differs, and aborted frames are extra output.
A frame that is aborted cannot have already left: the verdict (clock 7) comes 3 clocks before the frame's last word (clock 10).

**Against the bench-feed path of the 96 design** (its definitions of E, L, D and tick-to-trade, and the early start of its order frame, are in [docs/latency_definitions.md](../../../docs/latency_definitions.md)). The existing mock path (`trade64` in `designs/b96_kr260_10g`, Bench Feed v1) measures, in simulation, from
the clock the price word is in the MAC register to the order's preamble in the MAC register: 3 clocks with the transmit-clock chain (RATE_MATCH = 1,
`results/b96c/core_sim.json`) and 7 clocks in the default build, which crosses clocks (`results/b96c/core_sim_default.json`). This block, from the last byte of the
price (the last byte of an Add Order) to the first word of the order frame: 3 clocks started speculatively, 8 clocks started at the verdict. The figures
are **not the same quantity**: the bench-feed price is early in a 16-byte message and its decision needs no book, while here the price is the message's last
byte and the verdict needs the book after the message (7 clocks); the starting point here is the block input, not a MAC register (the phase 2 adapter
adds clocks in front, [phase2_integration.md](phase2_integration.md)); and the end here is the first word of a frame that still has 54 bytes of TCP/IP headers to
go in front of it on the wire. What the comparison does show is the cost of a book-dependent verdict (8 against 3) and that starting the frame before the
verdict recovers it (3 against 3).

**Rate.** One 64-bit word a clock is accepted; messages of at least 14 bytes on the wire (block header included) arrive at most two in
consecutive clocks and never three. A Replace takes two slots in the book's first stage and the two-entry queue absorbs the cost (`evdrop` stays 0
in the stress tests). The sustained rate with back-to-back D messages is in [results/b110/throughput_sim.json](../../../results/b110/throughput_sim.json).
`rej_busy` is the only counter that depends on the timing of the stream: orders more than 8 clocks apart never hit it.

## 4. Parameters

| Parameter | Default | Legal | Effect |
|---|---|---|---|
| `N_INST` | 4 | 2 to 8 | instruments watched |
| `LEVELS` | 8 | 4 or 8 | price levels per side and instrument (the best-level tree reduces them in two steps) |
| `ORD_AW` | 8 | 4 to 16 (tested at 5, 6, 8 and 10) | order table index bits: 2^ORD_AW live orders |
| `NOTIONAL_MODE` | 0 | 0, 1, 2 | brief 188: pre-trade notional check: 0 none, 1 price times quantity, 2 price-band table written by software (section 1.3; measured cost in [results/188_trading_safety/notional_measurement.md](../../../results/188_trading_safety/notional_measurement.md)) |

The bench also runs 2/4/5, 3/8/6 and 8/8/10 (N_INST/LEVELS/ORD_AW) and lints clean at several points (`tests/test_b110_rtl.py`, `tests/test_b110_lint.py`).
Resources and timing are in [README.md](../README.md) (measured, out of context).
