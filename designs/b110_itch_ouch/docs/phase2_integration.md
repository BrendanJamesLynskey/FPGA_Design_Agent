# Phase 2 integration plan: this path on the KR260 (`b96_kr260_10g`), the host bench and the board test

A plan for a later brief; **nothing here was built or measured**. Numbers about the existing design are quoted from its committed records.

## 1. What the existing design offers

`designs/b96_kr260_10g` receives 10GBASE-R on one GTH lane at 161.1328125 MHz (period 6.2058 ns in its stage file; 6.2061 ns used here), has a 64-bit
cut-through MAC (`mac64_rx`, `mac64_tx`), the mock trading decision `trade64` for Bench Feed v1 frames (one rule, a decision register one clock
after the price word) and a JTAG register bus (`jtag_bus`, reused from 58A). Its default build (RATE_MATCH = 0, brief 97C) keeps PCS, MAC and
decision in the recovered clock and crosses the order to the transmit clock; the RATE_MATCH = 1 builds (96C, 96E) bring the blocks into the
transmit clock through an elastic buffer so that MAC, decision and order logic share one clock.

Measured tick-to-trade of the existing path, simulation, from the clock the price word is in the MAC register to the order's preamble in the MAC
register: 7 clocks in the default build (`results/b96c/core_sim_default.json`: 1 to the decision register, 4 to cross to the transmit clock, 2 to the
preamble), 3 clocks with RATE_MATCH = 1 (`results/b96c/core_sim.json`: 1 + 0 + 2).

## 2. What changes in `b96_kr260_10g`

| Where | Change |
|---|---|
| New `rtl/udp_strip.sv` (adapter) | takes `mac64_rx`'s words and gives `s_*`: checks destination MAC (unicast or the multicast group's MAC), EtherType 0x0800, IPv4 version and IHL 5 (anything else is dropped and counted), protocol 17, destination address and UDP port against registers, the UDP length; removes the 42 header bytes (the payload starts at byte 2 of word 5: a 2-byte realigning shift), removes the FCS using the UDP length (not the frame length: Ethernet pads short frames), and forms `s_eof`/`s_keep` from the UDP length. IP and UDP checksums: recomputed (UNCONFIRMED whether the exchange's feed carries a UDP checksum: the Mold document does not say) |
| `mac64_rx` verdict | `mac64_rx` reports `m_end` and `m_fcs_ok` **one clock after the last word**. `s_err` of this block is defined on the last word, so either the payload is delayed two clocks (every message pays two clocks) or the verdict becomes its own late strobe `s_bad` taken up to a few clocks after `s_eof` (no added latency; the window in which an order can leave before the verdict grows by those clocks). The plan takes the strobe: a small change to `mold_rx` (`untrusted` and `pkt_err` set by it) |
| `trade64` | stays for Bench Feed (variant selected by a parameter or a register); this path replaces its **decision**, not its parsing. The order interface (`go`, instrument, price, quantity, order number) is `risk_glue`'s: its widths are 3 bit instrument, 32 bit price, 32 bit quantity, 32 bit number against trade64's 16/32/32/32, so an adapter that maps the instrument to the symbol (a table, already `cfg_watch`) is all that is needed |
| Clock domain | run the new path in the transmit clock (RATE_MATCH = 1 with 96E's own gray-pointer buffer, `RM_OWN = 1`) so the decision does not pay the 4-clock crossing; the cost is the buffer's own clocks (96E: 1.2 clocks added in simulation against 5.3 for the macro, quoted from its report) |
| `tx_path` | takes the order frame from `ouch_enter` through the TCP fast path of [tcp_plan.md](tcp_plan.md): the 54-byte header from the template, then the 59 payload bytes; `o_abort` drives `mac64_tx`'s `s_poison` |
| `regmap.py`, `docs/register_map.md`, `host/b96_regs.tcl` | the `cfg_*` inputs and the 45 counters as registers (word reads of the counters as a snapshot, like the existing counter blocks); regenerate the datasheet and the test that checks the RTL decode against the map |
| `build.yaml`, `latency_stages.yaml` | sources of this design; new stages (`udp_strip`, `mold_rx`, `itch_dec`, `book`, `risk`, `ouch`, `tcp_send`) so the latency tools reconcile the chain with the whole-core simulation |
| Constraints | none beyond the core's clock: no new I/O |

## 3. The host bench

`host/b96_bench.py` today drives Bench Feed frames. For this path: (1) a sender on the PC that turns `model/gen.py`'s packets into UDP datagrams
(multicast or unicast to the board's address) with the Mold session and sequence numbers the model assumes, at a controlled rate and with the
impairments of the generator (gap, duplicate, overlap); (2) a software exchange: a TCP server that accepts SoupBinTCP login, checks each
Unsequenced Data packet byte for byte against the model's frame, replies with Accepted, and logs the arrival time; (3) the NIC timestamps the
existing `host/nic_timestamp.py` takes, plus the board's own stage timestamps (`tx_path`), to give the wire-to-wire latency from the last byte of an
ITCH message on the wire to the first byte of the order frame on the wire. All traffic is synthetic and stays on the bench loop.

## 4. The board test (plan)

- Preconditions: the owner's rules for board use (SRAM only, wall power, at most 2.0 W predicted, junction temperature at most 85 degrees C with
  the design's own stop); one board job at a time through `_handoff/board.lock`. **Operating conditions are evidence:** die temperature and the
  VCCINT, VCCAUX and VCCBRAM rails from the SYSMON at the start and end of every run and at least once a minute in a soak, with the alarm
  thresholds set so a transient between polls is latched, and the verdict "inside ROC" or "outside ROC" in every failure report.
- Runs: (a) smoke: a short seeded session through the whole chain, every order frame compared with the model's; (b) counters: the same session
  with impairments, every counter compared with the model's; (c) latency: single messages spaced far apart, 1000 repeats, the distribution of the
  wire-to-wire latency with the speculative start off and on; (d) rate: the session at line rate, no `evdrop`; (e) risk: the kill switch and the
  limits changed from the host while traffic runs.
- Pass criteria are the simulation's: bit-exact frames, counters equal to the model's (except the counters that depend on timing), no `late_abort`.

## 5. Open points for the phase 2 brief

1. The adapter's verdict strobe against two clocks of delay (section 2): the measurement of the risk is the window in which an order can leave
   before the frame's check, to be stated in clocks and in the packets' length distribution.
2. Whether the book-dependent risk verdict (7 clocks) should be replaced by a faster partial check once speculation is on the board: decide
   after the board latency is known.
3. TCP fast path: [tcp_plan.md](tcp_plan.md).
4. In-context timing: this block closes alone ([README.md](../README.md)); inside the core the clock and placement can differ.
