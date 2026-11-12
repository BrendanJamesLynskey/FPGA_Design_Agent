# b58a_trigger: a mock low-latency trading path on a bench (1 Gb/s Ethernet, Kria KR260)

A packet arrives on a PL Ethernet port of the Kria KR260; its fields are parsed while it is still arriving; a rule
loaded at run time fires; hardware interlocks check the order; a response packet leaves.

**Purpose:** show that an FPGA can parse a packet as it arrives, apply a rule that can be changed while running, and
start a response within tens of nanoseconds of the deciding field, with every order passing hardware safety checks. It
is a bench loop: our own message format ([docs/bench_feed_v1.md](docs/bench_feed_v1.md)), our own traffic sources,
no market, broker or exchange, no market data.

**Status: simulation, formal checks and a Vivado 2026.1 build only. Nothing here has run on a board yet**
([docs/board_run_plan.md](docs/board_run_plan.md)). Every number below is from simulation. One clock is 8 ns (125 MHz,
one byte time at 1 Gb/s).

## Glossary

| Term | Meaning |
|---|---|
| RGMII | the 4-bit, double-data-rate link between the MAC (here, in the FPGA) and the PHY chip |
| SFD | start-of-frame delimiter: the byte that ends the preamble; the frame's first byte follows it |
| FCS | frame check sequence: the 32-bit CRC at the end of an Ethernet frame |
| IFG | inter-frame gap: the idle time between frames (at least 12 byte times) |
| cut-through | passing bytes on as they arrive, before the whole frame (and its FCS) is in |
| top-of-book | the best bid and best ask of an instrument |
| tick-to-trade | a market-data message (a "tick") arrives, an order leaves |
| tick-to-config | a tick arrives, software changes a rule and the change is in force |
| speculative / safe | speculative: act before the FCS is known and undo the order if the frame turns out bad; safe: wait for a good FCS |
| poison | invert an outgoing frame's FCS so that the far end discards it (the undo for an order already on the wire) |
| hold-off | the minimum number of clocks before the same rule may fire again |
| token bucket | a rate limit: each order takes a token; tokens come back at a fixed rate up to a maximum |
| k-induction | a formal proof that a property holds in every reachable state, not only up to a fixed depth |
| bounded check | a formal check of every behaviour up to a fixed number of clocks; it finds bugs but is not a proof |
| OOC | out-of-context synthesis: a block built on its own to measure its cost |
| luna | `openai/gpt-6-luna`, the hosted language model the project uses (through OpenRouter, provider data collection disabled) |

## The path

```
 RGMII (PHY2, J10B) -> rgmii_rx -> gmii_cdc (RX_CLK -> 125 MHz) -> mac_rx (cut-through)      ip_lib/eth_mac_rgmii
   -> feed_rx: Ethernet, IPv4 (checksum), UDP port, Bench Feed header, messages field by field  (ARP for us)
   -> book: best bid/ask per instrument in block RAM (read at the instrument field, updated at the message end)
   -> rules: 8 run-time rules, all checked at once when the price field completes
   -> interlocks: kill, halt on sequence gap, size, price band, position, token-bucket rate      (k-induction proof)
   -> order_ctl: each order bound to its own frame's verdict; speculative send, drop / poison / cancel on a bad FCS
   -> mac_tx -> rgmii_tx -> RGMII (PHY2)
 Port B (PHY3, J10A): feed_gen -> mac_tx -> RGMII; RGMII -> mac_rx -> loop timer (histogram B)
 Host: registers over the JTAG cable (rtl/jtag_bus.sv, host/jtag_regs.tcl, not yet run on a board), docs/register_map.md
```

The Ethernet blocks are the library entry [ip_lib/eth_mac_rgmii](../../ip_lib/eth_mac_rgmii/README.md) (tri-mode,
cut-through or store-and-forward). The KR260 top uses them at 1000 Mb/s only; the 10 and 100 Mb/s paths are simulated
in the library's own tests.

## Results (simulation)

Measurement points, all on the core side (the 125 MHz byte interface after the receive clock crossing and before the
transmit pins): **SFD in** is the clock mac_rx takes the SFD (the board's histogram A starts at the same point); **price
in** is the clock the last byte of the price field enters mac_rx; **first byte out** is the clock mac_tx's first
preamble byte is on its registered output. Resolution one clock (8 ns). The receive clock crossing, the RGMII registers,
the pins, the PHY chips and the cable are outside these numbers.

| What (`results/b58a/latency_sim*.json`) | Clocks | ns |
|---|---|---|
| Decision latency, speculative: price in to first byte out | 8 | 64 |
| The same, safe mode, one-message frame (waits for the 12 bytes after the price field: the rest of the message and the FCS) | 18 | 144 |
| Frame-start latency, speculative: SFD in to first byte out (57 of these clocks are the header bytes before the price field) | 65 | 520 |

Per stage (speculative, clocks): mac_rx and parser 2, rules 1, interlocks 1, order control 2, mac_tx 2.
At the pins add 2 clocks on transmit and about 7 on receive (17 clocks around a simulated pin loop, less the 8 of the
preamble and SFD and the 2 of transmit: the RGMII registers and the clock-crossing FIFO, whose simulation model stands
in for the Xilinx XPM macro, so its real latency is unmeasured; `results/b58a/pins_sim.json`).

**What pre-building the response headers saves.** The response's IPv4 header checksum can be computed before any
decision (BUILD_MODE 0) or after it, one word a clock while the preamble goes out (BUILD_MODE 1). Both give 8 clocks:
at 1 Gb/s the MAC needs no header byte for 8 clocks (the preamble) and the checksum for 32, so computing headers after
the decision costs nothing when the frame is streamed as the MAC asks for it. Building the whole frame in a buffer after
the decision and only then sending it (BUILD_MODE 2, store and assemble) costs 75 clocks. Pre-building matters at
higher line rates, where the header leaves in a few clocks.

**Tick-to-config** (`results/b58a/stale_parameters_sim.json`): a toy strategy loop (`host/strategy.py`) reads the book
after a market-data packet and commits a new rule threshold. A trigger that arrives before the commit is judged on the
old table and does not fire; the next one fires on the new. The 2,125-clock figure in the file is 2,000 clocks (16 us)
of software time that is **assumed**, plus 125 simulated clocks of register traffic: it is the mechanism, not a
measurement.

## How it is checked

- **cocotb against a Python reference model** ([model/ref_model.py](model/ref_model.py), written from the docs, not
  the RTL): random streams from the mock venue with hostile frames (wrong MAC, IPv6, VLAN, IPv4 options and
  fragments, TCP, wrong IP or port, bad IP checksum, bad magic, version and counts, ARP for us and not, runts, giants,
  bad FCS, RX_ER, truncated frames), in speculative and safe mode; every order, undo, cancel, ARP reply, counter, log
  entry and book entry must match. Also: minimum gaps with clock-crossing bubbles; 1518-byte frames; the interlocks
  under attack; a rate burst; kill while an order waits; the port B loop; MDIO against a model PHY; the RGMII pin loop
  of kr260_top.
- **Adversarial regression tests** from the independent review (`tests/rev_adv_cocotb.py`): frames cut 0 to 9 bytes
  after the price field with a wrong FCS, 74 to 76-byte frames with a wrong FCS whose second message triggers, and
  orders waiting behind an ARP reply. Each order from a bad frame must be dropped, poisoned or cancelled, and the order
  slot must drain. A second round (`tests/rev2_cocotb.py`): a soft reset while a speculative order from a bad frame
  is on the wire (it must still be poisoned or cancelled), and a trigger 253 to 256 frames after the last request (it
  must fire whatever the frame counter's value).
- **Formal** (SymbiYosys, `verif/formal`, `results/b58a/formal.json`):
  - `interlocks.sv`: **k-induction proof** that no order is granted while killed or halted, above the size limit,
    outside the price band or without a band reference, beyond the position limit, or beyond a bucketful of tokens
    between refills. Assumptions: the limits do not change after reset; bucket at most 4 and refill 3 to 6 clocks
    (small values keep the proof short; the logic does not depend on them); the bucket-refill write is not exercised.
    The proof covers `interlocks.sv` alone. If the host lowers the position limit at run time, the position can sit
    above the new limit; orders that would reduce it are then refused too. The position counts every order granted
    since reset (a cancelled or poisoned order still counts).
  - `order_ctl.sv`: **bounded check (30 clocks), not a proof**, with every input free (soft resets included), an
    abstract MAC (3-clock frames), a watchdog of 8 clocks and a 2-bit frame counter (so its wrap is within reach): an
    order whose frame turns out bad is never started once that is known, and if it left with a good FCS a cancel for
    it follows within 12 clocks, across soft resets too; a cancel only follows a bad frame (or the watchdog); safe mode
    never sends before a good verdict; one request per frame, and a trigger in a frame that has not asked always makes
    one when the slot is free; the order slot is never busy for more than 24 clocks. Outside the bound: backlogs of
    several orders, and the 16-bit age counter's saturation.
  - mac_rx and mac_tx frame state machines: **bounded checks (20 and 40 clocks), not proofs**, with reachability covers.
- **The price band** is checked against the book **before** the triggering message (a buy against the best ask, a
  sell against the best bid, else the last trade), never against the message itself; with no price in the book the
  order is refused.
- **Natural language to rules**: `host/nl_rule.py` asks luna for a rule from a sentence; `model/rules.py` validates
  it; ten recorded sentences in `rules/fixtures`, checked offline in CI against meanings written by hand.
- **Mock venue**: `host/mock_venue.py` makes the stimulus in simulation and is the PC side of the bench run.

## Build (Vivado 2026.1, xck26-sfvc784-2LV-c)

Routed and written to a bitstream (`results/b58a/build/`, `summary.json`): 7,225 LUTs (6.2 %), 10,318 flip-flops
(4.4 %), 6.5 block RAM tiles, 0.50 W estimated on chip. **Every gate passes** (`summary.json`, generated from
`gates.json`): worst setup slack +0.102 ns, worst hold slack +0.010 ns.

| RGMII worst slack (ns) | Port A setup | Port A hold | Port B setup | Port B hold |
|---|---|---|---|---|
| Receive (centre-aligned, PHY RX delay on, 1000 ps IDELAY on each input) | +0.360 | +0.697 | +0.642 | +0.238 |
| Transmit (TXC edge-aligned, PHY TX delay on, the PHY's own window less 0.1 ns assumed board skew) | +0.102 | +0.533 | +0.137 | +0.516 |

The constraints and their derivation are in `design.xdc`: no false paths or other exceptions on the RGMII ports, and
no methodology warning about them. Both directions use the PHY's own timing from its datasheet (Marvell 88E1111,
MV-S100649-00 Rev. M, section 4.12.2), with its internal delays on (register 20 bits 7 and 1). On transmit that
window lets a data change come up to 0.9 ns after its TXC edge and no earlier than 1.3 ns before the next; RGMII
v2.0's generic +/-0.5 ns, used by an earlier build, missed by up to 0.2 ns. The KR260's TXC-to-TXD trace skew is not
in our notes: the constraints take an **assumed** 0.1 ns off both sides of the window. A centred TXC from a 90-degree
MMCM output (PHY TX delay off) was also built and did not close (`results/b58a/build_tx_centred_trial/`).

## Limits

- No board run; the JTAG register script has not run on a board; no KR260 programming path in the flow yet.
- The transmit constraints assume at most 0.1 ns of TXC-to-TXD skew on the KR260 (not in our notes; the schematic or
  the board's layout report would confirm it).
- One order slot: at most one order request per received frame, none while the slot is busy. A soft reset (PULSE
  bit 7) forgets which frame last made a request, so that frame may make one more; it never removes an undo.
- A bad frame's book updates are not rolled back: a bad frame becomes a sequence gap at the next packet, and with
  halt-on-gap set trading stops until the host clears it.
- Rule hold-off counters restart when a rule table is committed; interlock limits are separate registers, not part of
  the atomic rule commit.
- The kill is a register only: the KR260 has no PL push button.
- UDP checksums are not checked or generated; no IPv4 options, VLAN tags or fragments.
