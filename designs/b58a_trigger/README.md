# b58a_trigger: a mock trading path on a bench (brief 58A, 1 Gb/s copper, KR260)

A packet arrives on a PL Ethernet port of the Kria KR260; its fields are parsed while it is still arriving; a rule
loaded at run time fires; interlocks check the order; a response packet leaves. **Everything is a mock**: our own
message format ([docs/bench_feed_v1.md](docs/bench_feed_v1.md)), our own traffic sources, no market, broker or
exchange, no market data. Orders are packets on a bench loop.

**Status (2026-11-12): simulation, formal and a Vivado 2026.1 build only. Nothing here has run on a board yet**
([docs/board_run_plan.md](docs/board_run_plan.md)). Every number below is from simulation, in 8 ns clocks.

## The path

```
 RGMII (PHY2, J10B) -> rgmii_rx -> gmii_cdc (RX_CLK -> 125 MHz) -> mac_rx (cut-through)      ip_lib/eth_mac_rgmii
   -> feed_rx: Ethernet, IPv4 (checksum), UDP port, Bench Feed header, messages field by field  (ARP for us)
   -> book: best bid/ask per instrument in block RAM (read at the instrument field, updated at the message end)
   -> rules: 8 run-time rules, all checked at once when the price field completes
   -> interlocks: kill, halt on sequence gap, size, price band, position, token-bucket rate      (formally proved)
   -> order_ctl: pre-built response headers, speculative send, poison or cancel on a bad FCS
   -> mac_tx -> rgmii_tx -> RGMII (PHY2)
 Port B (PHY3, J10A): feed_gen -> mac_tx -> RGMII; RGMII -> mac_rx -> loop timer (histogram B)
 Host: registers over the JTAG cable (jtag_bus, BSCANE2), docs/register_map.md
```

The Ethernet blocks are the library entry [ip_lib/eth_mac_rgmii](../../ip_lib/eth_mac_rgmii/README.md) (tri-mode,
cut-through or store-and-forward), used here at 1000 Mb/s.

## Results so far (simulation)

| What | Clocks (8 ns) | Source |
|---|---|---|
| Last price byte in to first preamble byte out, speculative, response headers pre-built | 8 | `results/b58a/latency_sim.json` |
| The same, safe mode (waits for the FCS), one-message frame | 19 | same |
| The same, assemble-then-send (frame built after the decision) | 75 | `results/b58a/latency_sim_assemble.json` |
| Receive SFD to first preamble byte out, speculative (58 of these are the bytes before the price field) | 66 | `results/b58a/latency_sim.json` |

Per stage (speculative): mac_rx + parser 2, rules 1, interlocks 1, order control 2, mac_tx 2. Pin-side stages
(RGMII and the clock-crossing FIFO's simulation model) in `results/b58a/pins_sim.json`. The silicon numbers come
from the board run's timestamps; the simulation of the XPM FIFO is a model, not the macro.

## How it is checked

- **cocotb against a Python reference model** ([model/ref_model.py](model/ref_model.py), written from the docs, not
  the RTL): random mock-venue streams with hostile frames (wrong MAC, IPv6, VLAN, IPv4 options and fragments, TCP,
  wrong IP or port, bad IP checksum, bad magic, version and counts, ARP for us and not, runts, giants, bad FCS,
  RX_ER, truncated frames), in speculative and safe mode; every order, undo, cancel, ARP reply, counter, log entry
  and book entry must match. Minimum gaps with clock-crossing bubbles; 1518-byte frames; the interlocks under attack;
  a 4-token rate burst; kill while an order waits; the port B loop; MDIO against a model PHY; the RGMII pin loop of
  kr260_top. `tests/test_b58a_rtl.py`, `tests/test_b58a_model.py`.
- **Formal** (SymbiYosys, `verif/formal`): the interlocks proved by k-induction (no grant while killed or halted, size
  and band respected, the position within its limit, no more than a bucket of grants between refills); the MAC
  frame FSMs bounded (20 to 40 clocks) and covered.
- **Natural language to rules**: `host/nl_rule.py` asks luna (OpenRouter, data collection denied) for a rule from a
  sentence; `model/rules.py` validates it; ten recorded sentences in `rules/fixtures`, checked offline in CI against
  meanings written by hand.
- **Tick-to-config**: `host/strategy.py`, a toy slow-path loop that rewrites a rule from the book; the stale-parameter
  case is shown in simulation (`results/b58a/stale_parameters_sim.json`); its software time is assumed there, not
  measured.
- **Mock venue**: `host/mock_venue.py` makes the stimulus in simulation and is the PC side of the bench run.

## Build (Vivado 2026.1, xck26-sfvc784-2LV-c)

`flow/run_vivado.sh designs/b58a_trigger`; records in `results/b58a/build` (`summary.json`).

| | |
|---|---|
| Timing after routing | all constraints met: WNS +0.803 ns, WHS +0.010 ns, at 125 MHz with the RGMII I/O constrained |
| Resources | 6,980 LUTs (5.96 %), 10,191 registers, 6.5 block RAM tiles, 1 MMCM, 7 global buffers |
| Power estimate | 0.495 W on chip, junction 43.7 C in still air with no heat sink (the pessimistic bound; the SOM's fansink is not modelled) |
| Gates | all pass except `exceptions_clean`: Vivado flags (TIMING-47) the false paths that pair each RGMII DDR edge with its capture edge, the standard pattern for centre-aligned DDR I/O |
| Build | 1,321 s, peak 4.3 GB (one 6 GB-capped Vivado, 2 threads) |

The RGMII receive timing assumes the PHY's internal RX delay is on and RGMII v2.0's 1.2 ns set-up and hold; both
are owner questions for the board run. After placement the hold slack was negative on the RGMII inputs in the
second build and the router repaired it; in this build placement and routing both met hold.
