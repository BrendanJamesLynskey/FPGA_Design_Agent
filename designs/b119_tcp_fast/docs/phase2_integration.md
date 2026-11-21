# Phase 2 integration notes: the TCP fast path behind brief 110's path and the 96 design's MAC

These are plans and observations, not a build. The block is simulated alone and behind brief 110's risk logic (`rtl/itch_ouch_tcp_top.sv`); nothing here ran on a board.
It extends [brief 110's phase 2 plan](../../b110_itch_ouch/docs/phase2_integration.md).

## Where it sits

```
10G MAC rx -> UDP adapter -> itch_ouch (mold_rx .. risk_glue) --go/fields/verdict--> tcp_fast --o_*--> mac64_tx (s_poison) -> PCS
                                                                                         ^  | rec_*  
                                              AXI-Lite register bus <---- PS software -----+  v   (FIFO to a PS-readable ring)
10G MAC rx -> frames of the order connection ---------------------------------------> PS (ACKs, replies, heartbeats)
```

- `tcp_fast` replaces `ouch_enter` with the same order-side ports and `busy`; brief 110's top needed no other change in simulation.
- The output goes to a transmit multiplexer in front of `mac64_tx`: the fast path's words, the PS's own frames (handshake, ACKs, retransmissions, heartbeats), the feed bench frames of the 96 design. The fast path's words cannot be paused, so the multiplexer must give it priority from the first word and finish a frame in progress before it starts one of its own; a PS frame that is in flight when an order arrives delays the order (the cost of one frame at 10G is about 1.2 microseconds for 1500 bytes: UNCONFIRMED figure from the line rate, not measured here).
- `o_poison` connects to `s_poison` of `mac64_tx`. An early abort leaves a runt frame with a bad frame check sequence: whether the 96 design's MAC pads or truncates a frame shorter than the minimum was not checked.
- The register bus needs a bridge to AXI-Lite (the 96 design's `regmap` is the model); the record needs a FIFO (the pulse is one clock).
- The receive side needs the order connection's frames copied to the PS (a filter on the four-tuple), since the block parses nothing.

## Open points

1. **Refusals feed back to nobody.** When `refuse_v` fires the risk logic has already used an order number and counted a position. Needed: a pulse from `tcp_fast` into `risk_glue` to release them (a change to brief 110's block, not made here).
2. **`busy` is 15 clocks long.** Re-measure `rej_busy` of the risk logic's four-entry queue on the real feed rate before accepting the longer busy time; the speculative start's advantage (3 clocks from the last ITCH byte) is kept.
3. **Frame check sequence.** The segment excludes it; the MAC adds it, and the pair `tcp_fast` plus `mac64_tx` was not simulated together.
4. **ARP and the destination MAC.** Software resolves it and writes DMAC; a change of next hop is a static write, which invalidates the template until the next arm.
5. **Time.** The staleness age is in clocks; the PS's refresh cadence at half the limit is a design choice to tune (a PS pause of a few milliseconds is a million clocks).
6. **Congestion and loss.** The fast path obeys only the peer's window. The PS's TCP decides everything else, and a loss shows up as a retransmission by the PS from the records; the exchange's behaviour under loss is not modelled beyond a single dropped segment.
7. **Timestamps must be off** on the connection (no options are sent).
8. **Heartbeat timing.** The one-second client heartbeat rule of SoupBinTCP 3.00 is software's; the takeover (disarm, idle, give back) means orders arriving during it are refused as not armed: a heartbeat takes a few register accesses.
9. **In-context timing.** Out-of-context closure at 6.2061 ns is not closure inside the 10G core; the host bus and the multiplexer add paths.

## Board test (when it comes)

A bench host sends ITCH-over-UDP at a known rate; the board sends orders; a second host (or the same one with a capture card) runs the exchange model of this brief on its
own TCP stack or the Python endpoint; the check is the one of the bench: the exchange's byte stream equals the orders sent, every checksum verifies on the wire, an aborted
frame never reaches the exchange, and the sequence number after a long run equals the PS's. Timestamps from the board's own counter give tick-to-trade as in brief 96.
