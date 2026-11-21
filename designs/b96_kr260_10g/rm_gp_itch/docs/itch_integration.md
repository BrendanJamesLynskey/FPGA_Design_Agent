# The standard-protocol trading path inside the KR260 10G design (build `rm_gp_itch`, brief 127)

Brief 110 built and measured, in simulation, a trading path that speaks the formats a venue speaks: MoldUDP64 and ITCH 5.0 in, OUCH 5.0 in a SoupBinTCP packet out ([its datasheet](../../../b110_itch_ouch/docs/itch_ouch.md)).
Its plan for the next step is [phase2_integration.md](../../../b110_itch_ouch/docs/phase2_integration.md). This build does that step: **the path runs inside the 10G design**, behind our own 10GBASE-R PCS and 64-bit MAC, in
the transmit user clock, and sends its orders back out through the same MAC. Everything is synthetic data. No board was touched for this brief: the board test is pre-registered ([board_test_plan.md](board_test_plan.md)) and its script is
written, not run.

Contents: 1 what is in the build; 2 the path, block by block; 3 latency, defined and measured; 4 the late frame check and what happens to an order on a bad frame; 5 registers and what a user could guess wrong;
6 the replay source and the capture ring (the loopback test's data path); 7 what the fibre loopback does and does not test; 8 the hook for brief 119's `tcp_fast`; 9 build results; 10 known gaps; 11 next steps.

## 1. What is in the build

`designs/b96_kr260_10g/rm_gp_itch/` is a **variant of the base design** in the same style as `rm_gp` and `rm_gp_bypass`: it lists the base's sources in its own `build.yaml` and replaces three base files by its own copies (`b96_core.sv`,
`rx_path.sv`, `tx_path.sv`); no file of the base, of brief 110 or of any open PR is edited. It is `rm_gp` (own gray-pointer elastic buffer, RATE_MATCH = 1) plus:

| File (`rtl/`) | What |
|---|---|
| `udp_strip.sv` | adapter from `mac64_rx`'s words to the Mold receiver: header checks, 42-byte strip with a 2-byte realign, FCS and padding trimmed by the UDP length, the FCS verdict as a late strobe; also the ring that captures the TCP frames that come back round a loop |
| `itch_top.sv` | brief 110's `mold_rx`, `itch_dec`, `book_core`, `risk_glue` and `ouch_enter`, **unchanged** (they are compiled from `designs/b110_itch_ouch/rtl`), wired as in 110's top but with the late verdict and the segment builder |
| `order_seg.sv` | the order frame: `ouch_enter`'s 59-byte packet inside a 113-byte Ethernet/IPv4/TCP frame, as a 15-word stream. **A stand-in for brief 119's `tcp_fast`** (section 8) |
| `tx_mux.sv` | the transmit multiplexer in front of `mac64_tx`: the 96 design's frame source, the replay memory, and the order stream |
| `itch_path.sv`, `itch_pkg2.sv` | the wrapper in the core clock: host vectors, the poison policy, counters, latency statistics, stamps |
| `rx_path.sv`, `tx_path.sv`, `b96_core.sv` | the base files with the MAC's outputs brought out, the multiplexer in front of the MAC, and the registers. This build has **RATE_MATCH = 1 only** (the ITCH path needs the MAC in the transmit clock), no eye scan and no GT bypass |

Host side (`host/`): `itch_host.py` (synthetic frames, replay image, expected order frame, order check), `itch_bench.py` (a *plan* of register operations that runs unchanged in simulation and on the board, and the checks against brief 110's model),
`b127_stages.py` and `b127_board.py` (the pre-registered board stages and the board driver). Registers: [register_map.md](register_map.md), generated from `regmap_itch.py` and tested against the RTL.

## 2. The path, block by block

```
 GT RX --> pcs_rx --(rx clock)--> rate_match_gp --(core clock)--> mac64_rx --+--> trade64 (Bench Feed rule: unchanged, off at reset)
                                                                              |
                                                                              +--> udp_strip --payload words--> mold_rx --> itch_dec --> book_core --> risk_glue --go--> order_seg --stream--+
                                                                                       |   `--late FCS verdict (v_v, v_bad)--> untrusted, pkt_err, order poison                              |
                                                                                       `--capture ring (TCP frames that come back)                                                          v
 GT TX <-- pcs_tx <-- mac64_tx <-- tx_mux <-- frame_src (probe, feed, test and Bench Feed order frames)   replay memory (host-loaded frames)   order FIFO and head register -------------------+
```
Everything from `mac64_rx` on is in one clock, the transmit user clock (161.1328125 MHz, 6.2058 ns): the elastic buffer is the only receive-to-transmit crossing, as in `rm_gp`.

**`udp_strip`** (one clock after the frame word that carries a payload word's last byte). Checks, in the order the words arrive: destination MAC (our `MY_MAC`, always; and also the group's multicast MAC `01:00:5E:xx:xx:xx` when `IT_FEED_IP` is in
224.0.0.0/4), EtherType 0x0800, IPv4 version 4 **and header length 5** (anything else, IPv6 and VLAN included, is dropped and counted `drop_type`), no fragment, protocol 17, destination address, destination UDP port, UDP length of at least 9
and equal to the IP total length minus 20, and the IPv4 header checksum (the ten 16-bit words are summed as they pass and folded in the two clocks before the first payload word is made). The first failing check is counted; the frame is
not forwarded and its verdict is swallowed. **The UDP checksum is not checked** (the frame check sequence protects the frame on this link; whether a feed carries one is UNCONFIRMED, see `spec_notes.md`). The payload starts at byte 2 of frame word 5, so
payload word k is `{frame word 6+k [15:0], frame word 5+k [63:16]}`; the last word is trimmed to the UDP length (`s_keep` is the low-contiguous mask of its valid bytes), not to the frame length, because Ethernet pads short frames.
`mac64_rx` can leave a one-clock bubble inside a frame (the elastic buffer's cadence); the adapter follows it.

**Mold, ITCH, book, risk** are brief 110's blocks, unmodified. One thing differs: the frame check verdict. `mold_rx`'s `s_err` is tied low and the flag `untrusted` and the counter `pkt_err` are kept in `itch_top` from the late strobe (section 4).

**`order_seg`** builds the order frame: word 0 is in its output register the clock after `go` (G+1), word i in G+1+i, word 14 (one byte) in G+15. The first six words are the template (destination = `VENUE_MAC`, source = `MY_MAC`, IPv4 with ID 0, DF, TTL 64,
protocol 6, total length 99, header checksum computed from the addresses; TCP ports `PORTS_A[31:16]` and `PORTS_B[15:0]`, sequence `IT_TCP_SEQ`, acknowledgement `IT_TCP_ACK`, PSH+ACK, window 0xFFFF), the rest is `ouch_enter`'s output, realigned by 6 bytes.
**The TCP checksum field is 0: the stand-in's frame is not a valid TCP segment** (section 8).

`ouch_enter`'s own `o_abort` pulse (it stops a frame of 8 words) is not used here: a 15-word frame cannot be stopped half way (the MAC needs every word), so the abort input is latched and becomes the poison on the last word.

**`tx_mux`** has one owner at a time. The order stream wins the clock its first word arrives if the MAC is free; the frame source and the replay wait by holding their `valid`. An order frame that finds the MAC owned is **dropped whole and counted
(`ord.drop`)**: the risk logic has already used its number and position. The stream cannot be paused (as tcp_fast's cannot), so it goes through an 8-entry FIFO and a head register; the MAC's one-clock-in-33 pause (`adv`) is absorbed there.

## 3. Latency, defined and measured

Owner rule: say what the start event, the end event and the path are. There are several latencies in this design; each is named and none is mixed with another.

**Start events** (a message's last byte is the byte that completes the price; for an Add Order it is the last byte of the message):

- **X**: the clock `mac64_rx`'s output register holds the 64-bit word that carries the message's last byte.
- **T**: the clock `udp_strip`'s output holds the payload word that carries it (what brief 110's text calls T; its table starts there). T = X + 1 when the byte is in byte 0 or 1 of its MAC word, X + 2 otherwise.
- **PCS word**: the clock the receive PCS output register loads the word (96E's measurement point; `results/b96e`).

**End event:** the clock `mac64_tx`'s output register holds the **first word of the frame, the preamble** (`sop`). The first byte of the frame is the start character in it; the destination MAC follows in the next word, and the first byte of the OUCH packet itself (its SoupBinTCP length field) is 54 bytes after the frame's first data byte: about 7 clocks later at 8 bytes a clock. The PCS and the GT add
two more clocks before the start block is on the GT port (the same two the 96 measurements add).

**Measured, in two benches** (every number is in a committed record; clocks of 6.2058 ns; the transceiver is a behavioural stand-in in both, so the GT's own delays are not in any figure):

1. *The new blocks with the real MACs* (Icarus, `tests/b127_unit_cocotb.py::latency_by_alignment`, [`results/b127/latency_sim.json`](../../../../results/b127/latency_sim.json), rows in `latency_unit_sim.json`): 24 single-candidate packets in each mode, the message end taking all 8 byte positions in its MAC word.

| Quantity (clocks) | speculative start | start at the verdict |
|---|---|---|
| X to T (MAC word with the last byte to the adapter's output word) | 1 to 2 | 1 to 2 |
| T to `go` | 2 | 7 |
| T to the start strobe (end event) | 5 to 6 | 10 to 11 |
| X to the start strobe | 6 to 8 | 11 to 13 |

   X to T is 1 when the message's last byte is in byte 0 or 1 of its MAC word and 2 for the other six bytes (the payload starts at byte 2 of frame word 5, so most messages end in the word before the one that completes their payload word). The `adv` pause
   of the transmit gearbox (one clock in 33) adds one clock to the last stage when it falls on the MAC's start: the upper end of the ranges.

2. *The whole core* (xsim 2026.1, real XPM macros, `tests/measure_xsim.py`, [`results/b127/core_sim.json`](../../../../results/b127/core_sim.json), per phase in `core_lat_sim.json`): the frames come from the replay memory, round the closed loop, through the PCS and the
   elastic buffer to the MAC; 8 candidates in each mode (one for each alignment) at each of four phases between the receive and transmit user clocks (0, 1550, 3100 and 4650 ps: 32 orders per mode).

| Mode | **Tick-to-trade, GT port to GT port** (min / mean / max, clocks) | mean in ns | MAC word X to the start strobe | PCS output word to MAC output word (the elastic buffer and the MAC register) |
|---|---|---|---|---|
| speculative start | 15.25 / 16.78 / 18 | 104 ns | 6 / 6.78 / 8 | 6.25 / 7 / 8 |
| start at the risk verdict | 20.25 / 21.63 / 23 | 134 ns | 11 / 11.75 / 12 | 6.25 / 6.88 / 8 |

   *GT port to GT port* is 96E's definition, so the figure can be set beside `results/b96e`: the clock the receive PCS's output register is loaded with the word that carries the message's last byte, minus one clock, to the start block of the order frame on the
   transmit GT port (the start strobe plus the PCS's two clocks). By phase:

| Phase between the clocks (ps) | speculative (min / mean / max) | at the verdict (min / mean / max) |
|---|---|---|
| 0 | 16 / 17.25 / 18 | 21 / 22 / 23 |
| 1550 | 15.75 / 16.88 / 17.75 | 20.75 / 21.75 / 22.75 |
| 3100 | 15.5 / 16.63 / 17.5 | 20.5 / 21.5 / 22.5 |
| 4650 | 15.25 / 16.38 / 17.25 | 20.25 / 21.25 / 22.25 |

   Each later phase is a quarter of a clock earlier in the mean, the same effect 96E found for the elastic buffer.

**The chain, clock by clock (speculative start; T = the clock the adapter's output holds the last byte):** X = T - 1 or T - 2 (the MAC word) | T the adapter's word | T + 1 `mold_rx` delivers the message | T + 2 `itch_dec` has the event, the book sees
the candidate and the risk logic starts the frame (`go`) | T + 3 `order_seg`'s word 0 is in its output register | T + 4 the multiplexer's head register holds it | **T + 5 `mac64_tx`'s output register holds the preamble (the end event)** | T + 7 the book update is visible and
the risk verdict (commit or abort) arrives | the frame's last word is taken by the MAC about 14 clocks after the start. Without the speculative start `go` comes with the verdict, at T + 7, and the start strobe at T + 10. Which register each clock
is, and what removing it would cost, is in [`latency_stages.yaml`](../latency_stages.yaml) (reconciled by `tests/test_b127_latency.py`).

**What this is not:** not a wire-to-wire time (the GT, the optics and the fibre are not in it; the board's loopback figures for the base design are in `results/b96e/hw`); not comparable one for one with the base design's Bench Feed path, whose rule fires on a price word early in a
frame with no book (12.9 clocks GT port to GT port in 96E's record, `rm_gp`): here the start event is the last byte of the message, the verdict needs the book after it (5 more clocks when the frame waits for it: 21.6 against 16.8), and the order frame is 15 words
long behind a 54-byte header. **Throughput:** two orders in a row (the second waits in the risk logic's queue) have start strobes 18 to 19 clocks apart (`results/b127/back_to_back_unit_sim.json`: the 15-word frame plus the MAC's start); orders further apart never wait.

## 4. The late frame check, and what happens to an order on a bad frame

`mac64_rx` forwards every byte of a frame as it arrives and reports the frame check (m_end, m_fcs_ok, m_len) a few clocks **after** the last word. Brief 110 put the verdict on the last payload word (`s_err`); here each payload word would
have to wait two clocks for it, so the verdict is its own strobe (`v_v` once per forwarded frame, `v_bad` = bad FCS, cut by an error character or a lost block lock, or shorter than its IP length says), 3 to 4 clocks after the frame's last word at `mac64_rx`'s output and 1 to 2 clocks after the adapter's last payload word (`results/b127/verdict_lag_unit_sim.json`), never before it. No word is delayed for it. Consequences, measured in simulation with the real MACs (`tests/b127_unit_cocotb.py`: `poison_policy`, `fcs_window_sweep`):

1. **The flag `untrusted` and the counter `pkt_err` are set by the strobe**, a few clocks after the frame's last word instead of on it. A candidate decoded in those few clocks (a candidate in the last message of the bad packet) is not blocked by its own packet's
   flag. Brief 110 left that case "not specified"; here it is **specified by the order's poison, below**.
2. **An order frame is poisoned when, at its last word,** (a) risk refused it or the book did not confirm it (an abort), or a speculative frame still had no verdict; (b) the frame that carried its trigger message had a bad verdict that is known by then, or any bad
   verdict arrived while the order was in flight (this also covers an order that waited in risk_glue's queue, whose trigger frame cannot be told); (c) in **STRICT** mode (`IT_CTRL` bit 5), also when the trigger frame's verdict was not yet known and good.
   A poisoned frame goes out with a **wrong frame check sequence**, the receiver's MAC drops it, and a TCP stack never sees it; its sequence number is not consumed (the next segment reuses it).
   The packets are tagged by a count of started packets and the verdicts by a count of verdicts (one per forwarded packet, in order), with an 8-deep history of results indexed by their difference.
3. **The window.** The order frame's last word leaves 15 clocks after `go`; when the trigger message is far enough before its packet's end, the packet's verdict comes after that and the order has already left. In the default **cut-through** mode that order leaves
   unpoisoned and is counted `ord.unverified`: this is the risk the speculative start accepts, now with a number. Measured with a bad frame and one candidate message followed by `n` bytes of other messages in the same packet:

| | speculative start | start at the verdict |
|---|---|---|
| largest tail that is still poisoned (bytes) | 126 | 166 |
| smallest tail that escapes (bytes) | 128 | 168 |

   (`results/b127/fcs_window_unit_sim.json`, `tests/b127_unit_cocotb.py::fcs_window_sweep`; 2-byte steps near each edge. A packet's tail after the message is 8 bytes a clock on the wire: 126 bytes are
   16 clocks.) So **a candidate whose message ends more than 126 bytes (speculative start) or 166 bytes (start at the verdict) before its packet's end can leave
   before the packet's check is known.** Whether that is rare depends on the real feed's packet lengths, which are not known here (synthetic data only). For the seeded generator (20 seeds of 400 messages, `results/b127/fcs_window_share.json`) with 1, 3 and 6 messages a packet, **0 %, 0 % and 8.5 %** of the candidates are outside the speculative window and 0 %, 0 % and 1.0 % outside the verdict window.

   STRICT mode closes the window: nothing leaves on an unverified frame, at the price that every order whose trigger message is more than that far from its packet's end is poisoned (`ord.pz_strict`). Which mode a trading
   system wants is a policy decision the owner makes; the default is cut-through because that is brief 110's behaviour.
4. **What cannot be recalled:** an order already on the wire (its last word accepted by the MAC) when the verdict arrives. That is why the window above is measured to the order's **last** word, not its first.
5. The adapter counts a bad verdict as `us.bad_fcs` (FCS wrong, or the frame shorter than its IP length) or `us.cut` (error character, lost lock). Frames that are not forwarded produce no verdict and no counter beyond their drop reason.

## 5. Registers, and what a user could guess wrong

The full datasheet is [register_map.md](register_map.md) (generated, tested). The points a user could get wrong:

- **Configuration registers cross as one vector.** The 32 words of `0x300` to `0x37C` cross to the core clock as one coherent 1024-bit vector a few dozen clocks after a write, so a write takes effect together with every earlier write, never half of one. Commands
  (`IT_CMD`), replay writes (`RP_WHI`) and tcp_fast bus writes (`TCPF_WDATA`) carry a sequence byte that the register block increments by itself; **two of the same kind written closer than about a microsecond can lose one** (the host's JTAG transactions are
  far slower; the simulation bench spaces them by 400 ns). `RP_STAT` bits 7:0 and `ISTAT` `cmd.echo` say how many the core has executed.
- **`IT_CMD` is write-only; a read returns the number of commands written** (bits 23:16), not the last value. `RP_WHI` reads back the last value written, but the memory word is committed on the **write**, once. The replay address does **not** auto-increment.
- **Counters are read from a snapshot** (`CMD` bit 2 of the base map takes it, as for the base counters), in three parts of 32 words (`ISTAT0` to `ISTAT31`, `ISTAT32` to `ISTAT63`, `ISTAT64` to `ISTAT95`). Each part is one coherent copy; **the three parts can be a few clocks apart**,
  so a counter in the first part and one in the third are not mutually exact while traffic runs. The capture window word (`cap.lo`, `cap.hi`) follows `CAP_ADDR` after the next snapshot: compare `cap.echo` with what you wrote.
- **Reads have no side effects; unmapped addresses read 0 and ignore writes; reserved bits read 0 and are ignored on write** (base rules; the generated datasheet repeats them).
- **Reset values** are listed per register; the configuration survives a transmit-datapath restart (it is in the register clock), the book, position, counters, flags and the replay engine do not. After `IT_CMD` CLR_BOOK the book needs about 300 core clocks before it is ready again.
- **`IT_CTRL` EN = 0 drops every frame** (counted `us.drop_off`), and the receive MAC and the Bench Feed rule keep working. ARM is separate from the Bench Feed rule's ARM (`TRADE_CTRL`); this build resets `TRADE_CTRL.TRADE_EN` to 0.
- **Prices are Price(4)** (four implied decimals: 1000000 is 100.0000), unlike the base map's hundredths for the Bench Feed rule.
- **Order numbers** (OUCH UserRefNum, the ClOrdID digits) are assigned when a candidate passes the risk checks; refused candidates use none; they restart at 1 with CLR_REF.
- **TCP sequence number:** `IT_TCP_SEQ` takes effect on `IT_CMD` TCP_LOAD; it advances by 59 for every segment that left unpoisoned. Nothing reads acknowledgements.

## 6. The replay source and the capture ring

**Replay memory** (256 words of 64 bits, written through `RP_WADDR`, `RP_WLO`, `RP_WHI`; format, per frame): a header word `{31'd0, poison, gap[15:0], length[15:0]}` then `ceil(length / 8)` data words, byte 0 of the frame in bits 7:0 of the first; the list ends with a zero header whose `gap` field is the
pause between passes. `length` is the frame **without** its FCS (the MAC adds it), 60 to 1514 bytes (the MAC does not pad: a shorter frame is skipped and counted, `rp.stat` bits 31:16). `gap` is the number of idle clocks after the previous frame's last word was taken by the MAC.
`poison` = 1 makes that frame's FCS wrong, for the receiver's bad-frame path. `RP_CFG` gives the number of passes per `IT_CMD` RP_START. The replay source sends a frame only when the MAC is free; it holds its words until the MAC takes them. `host/itch_host.py` builds the image.

**Capture ring.** The receiver keeps, for each frame of IPv4 protocol 6 (our own order frames coming back round the loop), words 3 to 14 of the frame (bytes 24 to 119: IP checksum, addresses, TCP header, the OUCH payload and the FCS) in one of 8 slots, and a meta word
`{valid, fcs_good, frame length with FCS}` that is written when the verdict arrives. The first 24 bytes (Ethernet and the start of IP) are classified, not kept. Reading is through `CAP_ADDR` (slot and entry) and the counter window. A poisoned order frame (aborted
speculation) is captured with `fcs_good` = 0: it came back, the receiver's MAC saw its FCS was wrong.

## 7. What the fibre loopback does and does not test

With the fibre looped back, **the board receives what it transmits**. The replay source transmits the synthetic feed frames; they come back, drive the ITCH path; the path transmits order frames; those come back too and are captured and read back by the host.
- **Tested:** the whole digital chain on real frames from the transmitter's MAC through the receiver's MAC (frame layout, FCS, the poison path: a poisoned order comes back with a bad FCS and the receiver sees it), the adapter's checks (frames for another MAC, port,
  address and protocol are sent and counted), the counters against the model, the order frames byte for byte, the latency statistics in the real clock.
- **Not tested:** a second implementation of the MAC or PCS (both ends are ours: a mistake they share, such as the FCS byte order, is accepted); an exchange's or NIC's acceptance of the order frame (the stand-in's TCP checksum is 0, so no real TCP stack would take it);
  rate matching under a frequency offset (a loopback has none); wire-to-wire time (it needs a NIC's timestamps); real multicast feeds (the adapter accepts the group's MAC, but nothing here sends one).
- **Frames go to the venue MAC**: our order frames carry `VENUE_MAC` as destination, so on the loop they come back as frames **for another MAC** and are counted `us.drop_mac`, not forwarded; the capture ring classifies them by protocol, not by address.

## 8. The hook for brief 119's `tcp_fast`

Brief 119 (PR #245) built `tcp_fast`: software owns the TCP connection, the fabric sends each OUCH order as one complete Ethernet/IPv4/TCP frame from a template, finishing both checksums per order, with the same order-side ports as `ouch_enter` and a poison output.
`order_seg.sv` is the **stand-in** with the same job and the same ports; `rtl/order_seg_tcpfast.sv` is the same module name instantiating `tcp_fast`. **When #245 is merged:**

1. in `build.yaml`, replace `rm_gp_itch/rtl/order_seg.sv` by `rm_gp_itch/rtl/order_seg_tcpfast.sv` and add `designs/b119_tcp_fast/rtl/tcp_fast.sv` (the same in the unit bench's file list and in `sim/xsim_core.sh`);
2. the template registers of the stand-in (`IT_TCP_SEQ`, `IT_TCP_ACK`, `IT_CMD` TCP_LOAD, the addresses and ports from the base map) stop being used; the connection state is written by software through `TCPF_ADDR` and `TCPF_WDATA`, which already reach tcp_fast's `sw_*` bus
   (the stand-in ignores them and `TCPF_RDATA` reads 0). Software must hand the connection over and arm it (docs of brief 119, `software_side.md`);
3. the frame becomes a **valid TCP segment** (checksums finished per order), 15 words as now, the same one clock from `go` to its first word, the same stream interface, so `tx_mux`, the poison policy, the latency and the counters need no change. tcp_fast poisons an
   aborted or unresolved speculative frame itself; the FCS-verdict poison of `itch_path` is still ORed in. A refused order (not armed, stale state, closed window, MSS) makes no words: it is counted `ord.refused`, but **risk_glue has already used its order number and
   position** (brief 119's open point 1; releasing them needs a change to brief 110's block);
4. the frame is 15 clocks long as before, so `busy` and the busy-order drop are unchanged; brief 119 measured 1546 LUTs and 2907 flip-flops for the block, to be added to this build's figures;
5. the stand-in's frame bytes (a zero TCP checksum, sequence from `IT_TCP_SEQ`) are what the byte-for-byte checks in this brief's tests expect: they need the `tcp_frame_valid` variant of `host/itch_host.py` and tcp_fast's sequence rules.

**Simulated with the hook** (`tests/b127_hook_cocotb.py`, Icarus, the real MACs, brief 119's `tcp_fast.sv` from its branch; [`results/b127/hook_tcp_fast_sim.json`](../../../../results/b127/hook_tcp_fast_sim.json)): the connection is handed over
through `TCPF_ADDR` and `TCPF_WDATA` as software would (addresses, ports, sequence, acknowledgement, window, then arm), a seeded session plays, and the order frames on the wire are checked: **both the IPv4 and the TCP checksums verify**, the payload equals brief 110's
frame byte for byte, the sequence numbers run 1000, 1059, 1118 with the acknowledgement 777, a refused speculative candidate comes out as one **poisoned frame that consumes no sequence number**, and `go` to the start strobe is 3 clocks, the same as the stand-in. With speculation off the
same session sends the same three orders and no poisoned frame. `tests/test_b127_hook.py` also compiles the hook and checks that its ports equal the stand-in's. Both skip unless tcp_fast's source is present (B119_RTL, or `designs/b119_tcp_fast/rtl/tcp_fast.sv` after the merge).

## 9. Build results

Build `designs/b96_kr260_10g/rm_gp_itch` through the flow on Vivado 2026.1 (one thread, heavy slot, `results/b127/build_one.sh`; records in [`results/b127/builds/rm_gp_itch/`](../../../../results/b127/builds/rm_gp_itch/)), part `xck26-sfvc784-2LV-c`, user clocks 161.133 MHz and 100 MHz. **Build stamp `1d8ac802`**
(the hash of the sources, recomputed from the tree with `flow/prepare.py sources_sha256`: it matches), BUILD ID `266acfe8`. Nothing was loaded on a board.

| | `rm_gp` (96E, the base this builds on) | `rm_gp_itch` |
|---|---|---|
| LUTs | 6,730 | 17,258 |
| registers | 18,938 | 46,116 |
| block RAM tiles, DSP | 0, 0 | 0, 0 |
| worst setup slack | +0.164 ns | **+0.153 ns** (met, 0 failing endpoints) |
| worst hold slack | +0.01 ns | **+0.01 ns** (met) |
| power (report_power after routing, vectorless, confidence Medium) | 1.105 W, 48.2 C | 1.253 W, 49.3 C |
| flow gates | all 29 true | **all 29 true** (`digest.json` `gates`) |
| `report_cdc` | no CDC-1, 0 critical | **no CDC-1, 0 critical**: 1,202 CDC-3 info, 4 CDC-9 info, 6 CDC-6 warnings and 5,792 CDC-15 warnings (the handshake vectors' enabled crossings), see `cdc_summary.txt` |
| wall time, Vivado resident peak | 1384 s, 4,398 MiB | 5574 s, 4,875 MiB (6 GiB scope cap hit 832 times; the base hit it 35 times) |

**Timing is met with 0.153 ns of setup slack on the transmit clock: thin, as in the base builds (rm_gp 0.164 ns).** The worst path is in the base design's receive MAC (`mac64_rx`, the late CRC term), not in the new blocks.
**CDC: no new waiver.** The only entry of `architecture.yaml`'s `cdc_waivers` is the GT Wizard's own reset synchroniser, inherited from the base. The new crossings are two coherent handshakes of whole vectors (CFG2 once, STAT2 three times, `hs_vec`), the same primitive the base uses
for its configuration and counters; every other path of the new blocks is in the transmit clock. `xpm_cdc_handshake` carries at most 1024 bits, hence the three STAT2 parts.

Resources by block (post-route, `utilization_hier.rpt`; LUTs include the LUT RAM; brief 110's out-of-context figures are in its README):

| Block | LUTs | of which LUT RAM | Flip-flops |
|---|---|---|---|
| whole core | 16,558 | 2,212 | 45,653 |
| `itch_path` (the whole ITCH path with `udp_strip` and `order_seg`) | 7,444 | 1,876 | 7,624 |
| `book_core` (110: 4,397 out of context) | 4,232 | 1,728 | 1,703 |
| `mold_rx` (110: 1,394) | 1,289 | 0 | 1,650 |
| `risk_glue` (110: 490) | 450 | 0 | 971 |
| `itch_dec` (110: 140) | 60 | 0 | 629 |
| `order_seg` (the stand-in segment builder) | 582 | 0 | 903 |
| `udp_strip` (with the capture ring) | 713 | 148 | 918 |
| `tx_mux` (with the replay memory) | 1,670 | 336 | 303 |
| CFG2 handshake, 1024 bits | 332 | 0 | 3,112 |
| one STAT2 handshake part, 1024 bits | 4 | 0 | 4,109 |

The FF count is dominated by the host vectors (about 12,000 flip-flops for STAT2's 96 words in three coherent copies and its snapshot, 3,100 for CFG2): the cost of word-coherent reads of 96 counters over a slow bus, and the reason the flow's post-synthesis CDC dump took 55 minutes.

**In-context timing of brief 110's critical paths** (`results/b127/builds/rm_gp_itch/ctx_timing.txt`, `results/b127/ctx_timing.tcl`, worst setup path ending in each group, required 6.206 ns; brief 110 out of context at 6.2061 ns: risk verdict into the position register +0.109 ns, the price ladder update the worst path at 5.0 ns):

| Register group | Worst setup slack | Logic levels | Path |
|---|---|---|---|
| risk_glue position registers (pos) | +0.790 ns | 14 | `u_ip/u_it/u_book/tu_inst_reg[0]/C` to `u_ip/u_it/u_risk/pos_reg[2][11]/CE` |
| risk_glue verdict counters and queue (the rest of the risk verdict) | +0.903 ns | 0 | `u_gt/inst/gen_gtwizard_gthe4_top.gth_wiz_gtwizard_gthe4_inst` to `u_ip/u_it/u_risk/dq_cnt_reg[0]/R` |
| book_core price ladder (lv_*) | no path or no cells matched | | |
| book_core top of book and update record | +0.919 ns | 0 | `u_gt/inst/gen_gtwizard_gthe4_top.gth_wiz_gtwizard_gthe4_inst` to `u_ip/u_it/u_book/tu_cand_reg/R` |
| mold_rx | +0.528 ns | 11 | `u_ip/u_us/s_eof_reg/C` to `u_ip/u_it/u_mold/c_trunc_reg[20]/CE` |
| itch_dec | +0.626 ns | 0 | `u_gt/inst/gen_gtwizard_gthe4_top.gth_wiz_gtwizard_gthe4_inst` to `u_ip/u_it/u_dec/e_sell_reg/R` |
| udp_strip | +0.556 ns | 0 | `u_gt/inst/gen_gtwizard_gthe4_top.gth_wiz_gtwizard_gthe4_inst` to `u_ip/u_us/lp_reg/R` |
| order_seg | +0.317 ns | 15 | `u_ip/u_it/u_book/tu_inst_reg[0]/C` to `u_ip/u_it/u_seg/o_d_reg[0]/CE` |
| tx_mux | +0.538 ns | 14 | `u_tx/u_mt/FSM_sequential_st_reg[0]/C` to `u_tx/u_mx/rp_err_reg[4]/CE` |
| mac64_tx (the CRC path with the multiplexer in front) | +0.214 ns | 11 | `u_tx/u_mt/crc_reg[5]/C` to `u_tx/u_mt/crc_reg[30]/D` |
| itch_path (poison policy, counters, statistics) | +0.193 ns | 11 | `u_ip/u_it/u_book/t1_inst_reg[0]/C` to `u_ip/u_it/u_book/t2b_px_reg[31]/D` |

Rows with 0 logic levels and a start in the transceiver's reset synchroniser are the reset pins of the block's registers (the first selection did not exclude them), not its logic: only the rows with logic levels measure the block. The price-ladder row matched no cells; the corrected selection is in `results/b127/ctx_timing.tcl` and `results/b127/ctx_only.sh` re-runs it (no heavy slot was free to do it before hand-back).

In context the risk verdict into the position register has about +0.79 ns where brief 110 had +0.109 ns out of context; the two are not the same measurement (placement and the clock's uncertainty differ), and the worst paths of the whole design are the base's receive MAC (0.153 ns) and the CRC cone of the transmit MAC (0.214 ns, with the multiplexer in front of it).

## 10. Known gaps

- **No board run.** Everything above is simulation (xsim with the real XPM macros and a behavioural transceiver; Icarus with the real MACs) and a Vivado build. The board test is pre-registered ([board_test_plan.md](board_test_plan.md)); the script is written and checked only with `bash -n`.
- **The order frame is not a valid TCP segment** (checksum 0, nothing reads acknowledgements): section 8 says what brief 119 changes. No exchange, no NIC, no second MAC: interoperability of the frames and of the PCS is not shown (the loopback accepts a mistake both ends share).
- **UDP checksum not checked**; IPv4 options, VLAN tags, IPv6 and fragments are dropped and counted; no IGMP join, ARP or ICMP; MoldUDP64 retransmission requests are not sent (brief 110).
- **The cut-through window** (section 4): an order whose trigger message is far from its packet's end can leave before the packet's FCS is known; STRICT mode closes it by poisoning those orders. The policy choice is the owner's.
- **A dropped order is still counted fired.** An order frame that finds the MAC owned by the generator or the replay is dropped, but risk has used its number and position (`ord.drop`). The same holds for a refused order with tcp_fast (`ord.refused`). The risk block would need a release input (brief 119 open point 1).
- **Order spacing:** the frame is 15 words, so two orders in a row start 18 to 19 clocks apart and the risk logic's queue (4 entries) holds later ones; `rej_busy` appears when more than four are pending.
- **Capture and replay are small:** 256 replay words (about 14 feed frames), a ring of the last 8 TCP frames keeping bytes 24 to 119. The counter window's three 1024-bit parts can be a few clocks apart.
- **This build is RATE_MATCH = 1 only,** no eye scan, no GT buffer bypass; combining it with 96F1's bypass or 126's cuts was not built. The Bench Feed rule (`trade64`) is kept, off at reset, for the base design's loop measurements.
- **Latency is simulated only.** The GT and the optics are not in any figure; 96E found 1.25 clocks of the board's loop latency that simulation does not reproduce (`design.md` section 11), which applies here too. The per-phase table is four phases of the receive clock, not a real offset.
- **Synthetic data only;** the packet-length distribution behind the FCS window is the generator's, not a real feed's.

## 11. Next steps

1. Owner runs `_handoff/fpga_agent/run_127_stage1.sh` (pre-registered); the planner records the result and the stamp in `results/b127/hw/`.
2. Merge brief 119's PR #245, swap `order_seg.sv` for the hook (section 8), re-run the unit bench, the whole-core latency record and the build, and run the board test with real checksums; then a NIC and a software exchange (brief 110's plan section 3) for a wire-to-wire figure.
3. Decide the cut-through policy (default or STRICT) from the owner's tolerance of the window, and give risk a release input for dropped and refused orders.
4. Consider the multicast feed (a second board or NIC sending the group) and the real-offset test of the elastic buffer with this path under load.
