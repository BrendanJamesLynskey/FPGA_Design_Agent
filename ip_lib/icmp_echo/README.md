# icmp_echo 0.1.0

Answers ping (ICMP echo, RFC 792) for one IPv4 address: stores the frame, checks both checksums, and sends the echo reply with addresses swapped, a fresh TTL and incrementally updated checksums (RFC 1624).

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: Misses 125 MHz out of context (89-116 MHz estimated); closes at 50 MHz. Simulated against a model that computes the reply's checksums from scratch, scapy as a second decoder; reply protocol checked by bounded model checking; built alone out of context on an Artix-7 with Vivado 2026.1; not yet run on a board (the Nexys A7 network design carries it behind eth_mac_rmii; built, not yet run: a cable check comes first, see designs/b63d_nexys_net/host/PLAN.md).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `BUF_BYTES` | 2048 | 128..16384, power of two | the longest frame answered (without FCS) |
| `TTL` | 64 | 1..255 | TTL of the replies |
| `RAM` | bram | bram, lutram | the frame buffer: block RAM or LUT RAM (the implementation variants) |

Out-of-space values fail at elaboration with `$error` (tested: `BUF_BYTES=100`, `BUF_BYTES=64`, `BUF_BYTES=32768`, `TTL=0`, `TTL=256`, `RAM=uram`).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tuser 1, tready always 1). received Ethernet frames without FCS
- `m_axis`: axis (dir master, tdata 8, tready True). echo replies, 14 + IP total length bytes
- `config`: native; own_mac[47:0], own_ip[31:0]
- `events`: native; ev_request, ev_reply, ev_busy, ev_bad

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- reply: the first reply byte on m_axis 4 clocks after the request's last byte (measured in the bench; the variants' declared latency)
- throughput: one request at a time: a request arriving while a reply waits or is sent is not answered (ev_busy)

## Evidence

cocotb against ip_lib/icmp_echo/model.py (RFC 792 and 791; the model recomputes both checksums from scratch while the RTL updates them incrementally, RFC 1624) with scapy re-deriving the checksums of every reply: random request lengths with zero and non-zero Ethernet padding, other addresses, bad checksums, fragments, options, other types and codes, bad and truncated frames, frames too long for the buffer, then a request arriving while a reply is held; Icarus Verilog 12. Formal (bounded): the AXI-Stream protocol rules (valid held until ready, data steady while waiting) on m_axis, no reply without a request, the reply carrying the request it answers whatever frame follows it (fails with the back-to-back bug restored), and a cover of a whole reply; an independent adversarial bench adds odd lengths, last and first fragments, DF and a frame arriving on the clock after a request. Tests: `flow/net/tests/test_63d_icmp_rtl.py`, `flow/net/tests/test_63d_adversarial_rtl.py`, `flow/net/tests/test_63d_formal.py`.

Try it: `python3 -m pytest flow/net/tests/test_63d_icmp_rtl.py flow/net/tests/test_63d_adversarial_rtl.py flow/net/tests/test_63d_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `BUF_BYTES=2048, TTL=64, RAM=bram`; `BUF_BYTES=128, TTL=255, RAM=lutram`; `BUF_BYTES=16384, TTL=128, RAM=bram`.

Terms (ARP, ICMP, IGMP, MDIO, RMII, RGMII, VLAN, pause, OOC, WNS, Fmax) are defined in [the library's terms](../README.md#terms).

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `icmp_ttl_kept` | the reply keeps the request's TTL while its checksum assumes the new one | caught |
| `icmp_checksum_not_updated` | the ICMP checksum is not updated for the type change | caught |
| `icmp_answers_fragments` | a first fragment (MF set) is answered as if it were the whole request | caught |
| `icmp_sum_over_padding` | the ICMP checksum is checked over the Ethernet padding too | caught |
| `icmp_addresses_not_swapped` | the reply's IP source stays the requester's address | caught |
| `icmp_back_to_back_overwrite` | a frame starting on the clock after a request's last byte is stored over the request (found by the independent review) | caught |
| `icmp_tail_bytes_overwritten` | bytes after 13 of a frame arriving during a reply overwrite the stored request (the formal check watches byte 13 only; found by the independent review) | caught |

## Variants

Selected by `RAM`; every variant has the same ports, the same bit-exact result and the same tests. Latency is clocks from an accepted input to its result; II (initiation interval) is clocks between accepted inputs, 1 meaning a new input every clock.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `bram` | the frame buffer in block RAM | `4` | `1` | the default; measured: one RAMB18 at BUF_BYTES 2048, 4 RAMB36 at 16384, about 114-116 MHz |
| `lutram` | the frame buffer in LUT RAM | `4` | `1` | block RAM spoken for; measured: 384 LUTs as RAM at BUF_BYTES 2048 (3072 at 16384) and slower (106 and 89 MHz) |

Measured at BUF_BYTES 2048, TTL 64: built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 8.0 ns clock (125 MHz), Vivado 2026.1 (build 6511674). Not run on a board.

| Variant | DSP | Block RAM tiles | LUT | Fmax estimate (MHz) | II | Latency |
|---|---|---|---|---|---|---|
| `bram` | 0 | 0.5 | 391 | 116 | 1 | 4 |
| `lutram` | 0 | 0 | 897 | 106 | 1 | 4 |

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); it is not a closure at that frequency. WNS (worst slack against the clock) below zero means the target was missed.

<details><summary>Every measured point (4 rows; source: <a href="char/xc7a100tcsg324-1.json">char/xc7a100tcsg324-1.json</a>)</summary>

| Variant | BUF_BYTES | TTL | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `bram` | 2048 | 64 | 391 | 443 | 0 | 0.5 | 0 | -0.590 | 116.4 | 0.007 | 4 | 1 |
| `bram` | 16384 | 64 | 398 | 443 | 0 | 4 | 0 | -0.742 | 114.4 | 0.010 | 4 | 1 |
| `lutram` | 2048 | 64 | 897 | 455 | 384 | 0 | 0 | -1.437 | 106.0 | 0.020 | 4 | 1 |
| `lutram` | 16384 | 64 | 4557 | 513 | 3072 | 0 | 0 | -3.285 | 88.6 | 0.065 | 4 | 1 |

Dynamic power is vectorless (default toggle rates, no simulation activity): use it to rank variants, not as a measurement. Regenerate with `python3 -m flow.ipchar icmp_echo` (Vivado, minutes per point).

</details>

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (memories inferred; ram_style steers the variants).
- Depends on: nothing.

## Cost table

measured costs are in the Variants section above.

Licence: MIT (this repository).

## Known gaps and limits

- Limits: requests with IP options are not answered; one request held at a time; no other ICMP messages (no destination unreachable, no timestamp); measured Fmax estimates 89-116 MHz out of context: below the RGMII MAC's 125 MHz; the formal reply check follows one byte (13): a version that lets the solver choose the byte did not finish its passing run in reasonable time, so the other copied bytes are checked in simulation only.
- Board: no board run of this entry is recorded; its evidence is simulation and out-of-context builds.

## Next steps

1. Pipeline the checksum path so the block meets 125 MHz behind the RGMII MAC.
2. Run designs/b63d_nexys_net on the board with a cable to a host and record ping replies.

## History

- 0.1.0 (2026-11-12): Initial version: simulated against a Python model, seeded faults caught, formal checks (bounded except where the README says proved), out-of-context cost on an Artix-7 (Vivado 2026.1); not run on a board. See README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
