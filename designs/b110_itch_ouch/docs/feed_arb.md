# feed_arb: A/B feed arbiter (brief 191): datasheet

An idea from Edwards 2026 (ch 4), built from scratch. Exchanges send every MoldUDP64 packet on two multicast feeds, A and B. `feed_arb` takes both UDP payload streams and gives **one**
stream with the interface of `mold_rx`, so the parser sees one sequence: the first copy of each packet wins, the other is dropped as a duplicate, and when one feed lost a packet the
other feed's copy is the first copy and fills the gap. It sits in front of `mold_rx`; `itch_ouch_top` instantiates it with `DUAL_FEED = 1`. Simulation and out-of-context timing only.

```
 A: s_*  ----> feed_arb_in (FIFO, header) --\
                                              >-- decision on the header's third word --> one packet at a time --> mold_rx
 B: sb_* ----> feed_arb_in (FIFO, header) --/        (nxt: the next expected sequence number)
```

## 1. Interface (what a user could guess wrong)

- **Inputs**: two streams, each exactly the `s_*` interface of `mold_rx` (64-bit words, byte 0 in bits 7:0, `s_sof` first word, `s_eof` last word, `s_keep` the valid bytes of the last word, `s_err` on
  the last word of a bad or cut frame). Each feed must keep at least 4 idle clocks between its own packets, as `mold_rx` requires. The feeds are in **one clock domain** (the same `clk`) and need no
  alignment: any skew is allowed (the fill window below says how much matters). The two streams are never merged word by word: a packet leaves whole from one feed.
- **Output**: the `mold_rx` input interface; at least `MIN_IDLE` (4) idle clocks between packets, so the output is always legal for `mold_rx` even when packets from the two feeds arrive back to back.
- **Counters** (`cnt_ab` of `itch_ouch_top`, 7 counters of 32 bits, `clr_cnt` clears them, wrapping not saturating): `fwd_a`, `fwd_b` (packets forwarded from each feed), `old_a`, `old_b` (dropped as old),
  `gap` (a forwarded packet started beyond the next expected number: a gap passed on to the parser), `sess` (forwarded packets of another session than the first one seen), `ovf` (words or packets lost to FIFO overflow).
- **The parser's own counters are unchanged**: with a perfect arbiter the parser's counters equal those of a single clean feed (the bench checks every counter against the model).

## 2. The rules (what is decided on the header's third word)

`nxt` is the end of the last packet forwarded (its sequence number plus its message count). For a packet with sequence number `s` and message count `n`:

| Packet | Decision |
|---|---|
| `s + n <= nxt` (every message already forwarded) | **old**: dropped, counted `old_a` or `old_b` |
| any other data packet | **forwarded** whole: in order (`s = nxt`), an overlap (`s < nxt < s + n`, `mold_rx` trims it) or ahead (`s > nxt`: a gap on this feed, counted `gap`); `nxt` becomes `s + n` |
| heartbeat (`n = 0`) or end of session (`n = 0xFFFF`) below `nxt` | old |
| heartbeat or end of session at or above `nxt` | forwarded unless a heartbeat **of the same kind and sequence number** was forwarded within `HB_WIN` (4096) clocks (it is then the other feed's copy); `nxt` becomes `s` |
| another session than the first one seen | forwarded unchanged and **not** deduplicated (the parser counts and drops it; `sess` counts it here), `nxt` unchanged |
| a runt (it ends before its third word) or a packet whose first words were lost to overflow | forwarded unchanged, not deduplicated (no sequence number to judge) |

Both feeds deciding in the same clock: A first, B on the state A leaves. The first packet seen fixes the session and `nxt`.

**Things a user could guess wrong.**
- **Fill window.** A packet missing on feed A is filled from feed B only if B's copy has its header's third word in **before** A's next packet has its own (a tie goes to A). The arbiter holds no packet back to wait for a late copy: that
  would need a whole-packet buffer and would delay every packet behind it. Measured in simulation (`fill_window`, [results/191_trading_variants/sim/feed_arb_fill_window.json](../../../results/191_trading_variants/sim/feed_arb_fill_window.json)):
  with packets 40 clocks apart the gap is filled for a B skew of 0 to 39 clocks and not for 40 or more. A copy that comes too late is dropped as old, and the parser sees the gap it would have seen without B.
- **A bad frame on the first copy is not repaired.** Words go out as they come (cut-through), so a copy that ends with `s_err` is forwarded and flagged exactly as without the arbiter (`pkt_err`, `untrusted`),
  and the other feed's good copy is dropped as old.
- **Overflow is loud.** A feed that runs far ahead of the packet being forwarded (its next real packet waits in its FIFO) can overflow the `2^ARB_AW` word FIFO (default 32 words). Words are dropped, `ovf` counts them
  and the packet's last word carries `s_err`, so the parser marks the path untrusted: a packet that lost words is never passed as good (`deep_skew`, with `ARB_AW = 8` the same case is clean).
- **Heartbeats**: a heartbeat repeated by one feed within `HB_WIN` clocks with an unchanged sequence number is taken as the other feed's copy and dropped. Real heartbeats are about a second apart (161 million clocks), far beyond 4096.
- **Another session is not deduplicated.** Both feeds' packets of an unexpected session reach the parser, which counts and drops them (`sess` in `mold_rx` counts both).
- Packets leave in the order of their decisions. A forwarded packet from the other feed that has to wait for the one being sent waits in its FIFO.

## 3. Latency and cost

A forwarded packet's words leave **4 clocks after they entered**, all of them (a registered decision, then the FIFO read and the output register). So every latency of [itch_ouch.md](itch_ouch.md) section 3 grows by 4 clocks when
`DUAL_FEED = 1`: book update 11 clocks after the last byte (against 7), first order word 12 (against 8). Measured in simulation (`ab_latency`, [feed_arb_latency.json](../../../results/191_trading_variants/sim/feed_arb_latency.json)), the same
from either feed, the other idle. This is the price of deciding on the header (the third word) before anything is forwarded; the benefit is that a lost packet on one feed no longer halts trading.
Cost, out of context on the K26 at 6.2061 ns (Vivado 2026.1, [ooc/top_dual.json](../../../results/191_trading_variants/ooc/top_dual.json)): the arbiter is 1526 LUTs (feed A's input stage 976, B's 377; the FIFOs are distributed RAM) and the whole path 8182 LUTs against 6836 without it, 6889 flip-flops against 6024, no DSP, no block RAM; the build closes (WNS +0.112 ns, WHS +0.044 ns).

## 4. Parameters

| Parameter (of `itch_ouch_top`) | Default | Effect |
|---|---|---|
| `DUAL_FEED` | 0 | 1 puts `feed_arb` in front of `mold_rx` and uses the `sb_*` inputs (the B feed); with 0 the `sb_*` inputs are ignored and `cnt_ab` is 0 |
| `ARB_AW` | 5 | FIFO depth per feed, 2^ARB_AW words (a skew of that many words between the feeds, with the later feed's next packet new, is held); 8 for up to 256 |
| (`feed_arb` only) `MIN_IDLE`, `HB_WIN` | 4, 4096 | idle clocks between output packets; heartbeat window in clocks |

## 5. Verification

`tests/b110_ab_cocotb.py` (run with `DUAL_FEED = 1`; `test_b110_rtl.py::test_dual_feed`): both feeds complete with skews of either sign and jitter; each feed dropping packets (not the same one) and the other filling every gap with no gap at the parser;
a packet lost on both feeds (a real gap: counted, halts as before); the fill window; heartbeats and end of session; a bad frame on the first copy; another session and an overlapping copy; runts; packets back to back with the feeds up to three packets
apart and alternating (the arbiter inserts the idle clocks); FIFO overflow and the deep FIFO; seeded random sessions with random skews and losses; and the latency. Every test compares the whole path against the single-feed model of
[model/ref.py](../model/ref.py) (messages, events, book updates, order frames, counters, flags). Seeded faults in `feed_arb.sv`: [verif/mutants.yaml](../verif/mutants.yaml) (`arb_*`).
