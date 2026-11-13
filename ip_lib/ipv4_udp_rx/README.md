# ipv4_udp_rx 0.1.0

IPv4 and UDP receive: header checksum and length checks, options skipped, fragments refused, destination by own address, broadcast or multicast, UDP checksum with the pseudo-header, demultiplexed by destination port; the payload streams out with its header fields.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: Misses 125 MHz out of context (75-81 MHz estimated: needs pipelining before it sits behind the RGMII MAC); closes at 50 MHz. Simulated against an RFC 791/768 model with scapy checking the bench's frames; output protocol checked by bounded model checking; built alone out of context on an Artix-7 with Vivado 2026.1; not yet run on a board (the Nexys A7 network design carries it behind eth_mac_rmii; built, not yet run: a cable check comes first, see designs/b63d_nexys_net/host/PLAN.md).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `N_PORTS` | 4 | 1..8 | destination ports in the table (the lowest matching index wins) |
| `CHECK_UDP` | 1 | 0, 1 | 1 = verify a non-zero UDP checksum |
| `ACCEPT_BCAST` | 1 | 0, 1 | 1 = accept 255.255.255.255 |
| `ACCEPT_MCAST` | 1 | 0, 1 | 1 = accept 224.0.0.0/4 (the MAC filter and igmp_join choose the groups) |

Out-of-space values fail at elaboration with `$error` (tested: `N_PORTS=0`, `N_PORTS=9`, `CHECK_UDP=2`, `ACCEPT_BCAST=2`, `ACCEPT_MCAST=2`).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tuser 1, tready True). received Ethernet frames without FCS; tready falls only while m_axis is stalled and for one clock after each frame
- `m_axis`: axis (dir master, tdata 8, tuser 1, tdest 3, tready True). UDP payloads; tuser on tlast = discard (bad frame, short frame or wrong UDP checksum); m_src_ip, m_dst_ip, m_src_port, m_dst_port and m_len beside every byte
- `config`: native; own_ip[31:0], ports[N_PORTS*16-1:0], port_en[N_PORTS-1:0]
- `events`: native; ev_ok, ev_bad_ip, ev_bad_udp, ev_no_port, ev_frag, ev_empty

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- payload: each payload byte leaves one input byte later (one byte held back to place tlast); the last one 1 clock after the frame's last byte
- throughput: a byte a clock, less one clock per frame

## Evidence

cocotb against ip_lib/ipv4_udp_rx/model.py (RFC 791, 768, 1071), frames built in plain Python with scapy recomputing the bench's own UDP checksums: unicast, broadcast, multicast and foreign destinations; enabled, disabled, duplicated and unknown ports; right, wrong and absent UDP checksums; IP options, fragments, other protocols, bad header checksums, short and long UDP lengths, zero and non-zero Ethernet padding, bad and truncated frames, empty payloads; input gaps and back-pressure; every event counter compared; Icarus Verilog 12. Formal (bounded): the AXI-Stream protocol rules (valid held until ready, data steady while waiting) on m_axis with tuser, tdest and the header fields, and a cover of a whole datagram; an independent adversarial bench adds last fragments, IHL 15, odd checksums and short UDP lengths. Tests: `flow/net/tests/test_63d_udp_rx_rtl.py`, `flow/net/tests/test_63d_adversarial_rtl.py`, `flow/net/tests/test_63d_formal.py`.

Try it: `python3 -m pytest flow/net/tests/test_63d_udp_rx_rtl.py flow/net/tests/test_63d_adversarial_rtl.py flow/net/tests/test_63d_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `N_PORTS=4, CHECK_UDP=1, ACCEPT_BCAST=1, ACCEPT_MCAST=1`; `N_PORTS=1, CHECK_UDP=0, ACCEPT_BCAST=0, ACCEPT_MCAST=0`; `N_PORTS=8, CHECK_UDP=1, ACCEPT_BCAST=0, ACCEPT_MCAST=1`.

Terms (ARP, ICMP, IGMP, MDIO, RMII, RGMII, VLAN, pause, OOC, WNS, Fmax) are defined in [the library's terms](../README.md#terms).

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `udp_rx_highest_port_wins` | when two port entries match, the highest index wins instead of the lowest | caught |
| `udp_rx_no_pseudo_header_source` | the UDP checksum leaves half of the source address out of the pseudo-header | caught |
| `udp_rx_padding_passed` | bytes after the datagram (Ethernet padding) are passed on as payload | caught |
| `udp_rx_fragments_passed` | fragments are taken as whole datagrams | caught |
| `udp_rx_options_not_skipped` | IP options are read as the UDP header | caught |
| `udp_rx_last_fragment_passed` | a last fragment (MF 0, offset not 0) is taken as a whole datagram (found by the independent review) | caught |

## Cost (out of context)

Built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 8.0 ns clock (125 MHz), Vivado 2026.1 (build 6511674); source: [char/xc7a100tcsg324-1.json](char/xc7a100tcsg324-1.json). Not run on a board.

| N_PORTS | CHECK_UDP | ACCEPT_BCAST | ACCEPT_MCAST | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 1 | 1 | 1 | 491 | 416 | 0 | 0 | 0 | -5.412 | 74.6 | 0.006 |
| 8 | 1 | 1 | 1 | 527 | 418 | 0 | 0 | 0 | -4.336 | 81.1 | 0.006 |

Defaults: N_PORTS 4, CHECK_UDP 1, ACCEPT_BCAST 1, ACCEPT_MCAST 1. WNS is the worst negative slack (the timing margin at the target clock; below zero the target is missed).

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); dynamic power is vectorless (default toggle rates). Regenerate with `python3 -m flow.ipchar ipv4_udp_rx` (Vivado, minutes per point).

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.
- Limits: no reassembly (fragments are counted and dropped); no VLAN tags (strip them in the MAC); a datagram with no payload produces no output; the UDP checksum verdict comes on tlast, so a consumer acting on the bytes early must undo on tuser; measured Fmax estimates 75-81 MHz out of context: it closes at the RMII MAC's 50 MHz but not at the RGMII MAC's 125 MHz (header index compares and checksum folds are not pipelined).

## Cost table

measured out of context: see the Cost section above.

Licence: MIT (this repository).
