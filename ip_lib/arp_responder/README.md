# arp_responder 0.2.0

Address Resolution Protocol (ARP, RFC 826): answers 'who has this IPv4 address?' for one address, caches other hosts' MAC addresses (round-robin replacement, flush), and looks up next-hop MAC addresses for transmit, sending a rate-limited request on a miss. A packet from another station claiming its own address is reported as a conflict (RFC 5227) and never cached.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: Meets 125 MHz out of context on xc7a100t-1 with 4 and 16 cache entries (Fmax estimates 151 and 127 MHz; 16 entries by +0.15 ns only) and with margin on xck26-2LV (228-288 MHz). Version 0.2.0 sends the first reply byte 4 clocks after the request's last byte (was 3). Simulated against an RFC 826 model, with scapy as a second decoder and an independent adversarial bench; built alone out of context with Vivado 2026.1 (single runs at 8 ns, estimates); not yet run on a board (the Nexys A7 network design carries it behind eth_mac_rmii; built, not yet run: a cable check comes first, see designs/b63d_nexys_net/host/PLAN.md).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `CACHE_N` | 4 | 1..16 | cache entries |
| `HOLDOFF` | 1000 | 1..16777215 | clocks before a second request for the same address |

Out-of-space values fail at elaboration with `$error` (tested: `CACHE_N=0`, `CACHE_N=17`, `HOLDOFF=0`, `HOLDOFF=16777216`).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tuser 1, tready always 1). received Ethernet frames without FCS; tuser on tlast marks a bad frame
- `m_axis`: axis (dir master, tdata 8, tready True). 42-byte ARP frames (replies before requests); the MAC pads them
- `lookup`: native; lk_valid, lk_ip[31:0], lk_ready, lk_done, lk_hit, lk_mac[47:0], flush. one lookup a clock, answered the next clock
- `config`: native; own_mac[47:0], own_ip[31:0]. static
- `events`: native; ev_rx_request, ev_rx_reply, ev_tx_reply, ev_tx_request, ev_learn, ev_drop, ev_conflict. one-clock pulses for counters

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- reply: the first reply byte on m_axis 4 clocks after the request's last byte when idle (measured in the bench)
- lookup: 1 clock
- throughput: one reply waiting while another is sent; requests in the receive stream at line rate are parsed without back-pressure

## Evidence

cocotb against ip_lib/arp_responder/model.py (RFC 826, plain Python) with scapy decoding every frame sent: random requests, replies, probes, malformed packets, padded frames, bad and short frames, lookups and flushes under input gaps and back-pressure, then a dropped third reply and the request holdoff; Icarus Verilog 12. Formal (bounded): every frame 42 bytes and the AXI-Stream protocol rules (valid held until ready, data steady while waiting) on m_axis; an independent adversarial bench adds gratuitous ARPs from known and unknown hosts, probes, a full cache and an address conflict. Tests: `flow/net/tests/test_63d_arp_rtl.py`, `flow/net/tests/test_63d_adversarial_rtl.py`, `flow/net/tests/test_63d_formal.py`.

Try it: `python3 -m pytest flow/net/tests/test_63d_arp_rtl.py flow/net/tests/test_63d_adversarial_rtl.py flow/net/tests/test_63d_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `CACHE_N=4, HOLDOFF=100`; `CACHE_N=1, HOLDOFF=40`; `CACHE_N=16, HOLDOFF=200`.

Terms (ARP, ICMP, IGMP, MDIO, RMII, RGMII, VLAN, pause, OOC, WNS, Fmax) are defined in [the library's terms](../README.md#terms).

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `arp_reply_wrong_opcode` | replies go out with the request opcode | caught |
| `arp_answers_any_address` | requests for other hosts' addresses are answered | caught |
| `arp_round_robin_stuck` | a full cache always replaces the same slot | caught |
| `arp_bad_frames_accepted` | frames that ended with tuser (bad FCS) are answered and learnt | caught |
| `arp_no_holdoff` | repeated misses for one address send a request each time | caught |
| `arp_learns_gratuitous_unknown` | a gratuitous ARP from an unknown host is learnt (RFC 826 merges only known senders; found by the independent review) | caught |
| `arp_learns_own_ip_claim` | another station claiming own_ip is cached (RFC 5227 address conflict; found by the independent review) | caught |

## Cost (out of context)

Built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 8.0 ns clock (125 MHz), Vivado 2026.1 (build 6511674); source: [char/xc7a100tcsg324-1.json](char/xc7a100tcsg324-1.json). Not run on a board.

| CACHE_N | HOLDOFF | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) |
|---|---|---|---|---|---|---|---|---|---|
| 4 | 1000 | 514 | 959 | 0 | 0 | 0 | 1.385 | 151.2 | 0.017 |
| 16 | 1000 | 1126 | 1939 | 0 | 0 | 0 | 0.146 | 127.3 | 0.012 |

Defaults: CACHE_N 4, HOLDOFF 1000. WNS is the worst negative slack (the timing margin at the target clock; below zero the target is missed).

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); dynamic power is vectorless (default toggle rates). Regenerate with `python3 -m flow.ipchar arp_responder` (Vivado, minutes per point).

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.

## Cost table

measured out of context: see the Cost section above.

Licence: MIT (this repository).

## Known gaps and limits

- Ethernet and IPv4 only; one own address; entries never age (flush from outside); address conflicts are reported (ev_conflict) but not resolved (no RFC 5227 probing or announcing); one reply waits while one is sent, a third request is not answered; meets 125 MHz with 4 and 16 cache entries (151 and 127 MHz estimated on xc7a100t-1; 16 entries by 0.15 ns); the added pipeline stage moves some decisions one clock later, so a same-clock race between a frame's verdict and a free-running input (a tick, a flush, a lookup, an output handshake) resolves one clock later than in 0.1.0 (no bench reaches these races; the CHANGELOG lists them); the formal checks were written for 0.1.0 and run in CI on 0.2.0.
- Board: no board run of this entry is recorded; its evidence is simulation and out-of-context builds.

## Next steps

1. Run the Nexys A7 network design (designs/b63d_nexys_net) on the board with a cable to a host and record the ARP replies.
2. Time the block in context behind eth_mac_rgmii on the KR260 (out-of-context numbers are single runs).

## History

- 0.2.0 (2026-11-16): Pipelined to meet 125 MHz out of context on xc7a100t-1 (brief 88; Vivado 2026.1, single runs). Behaviour is unchanged apart from latency: see the status line and the latency entry in ip.yaml. Same-clock races between a frame's verdict and free-running inputs (a tick, a flush, a lookup, an output handshake) resolve one clock later than in 0.1.0; no bench reaches them. Seeded faults re-expressed for the new RTL.
- 0.1.0 (2026-11-12): Initial version: simulated against a Python model, seeded faults caught, formal checks (bounded except where the README says proved), out-of-context cost on an Artix-7 (Vivado 2026.1); not run on a board. See README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
