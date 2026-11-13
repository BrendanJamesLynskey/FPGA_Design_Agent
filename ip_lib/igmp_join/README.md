# igmp_join 0.1.0

Multicast group membership for a host (IGMPv2, RFC 2236) for up to 8 configured groups: unsolicited reports on joining, reports in answer to general, group-specific and version 3 queries after a random delay, suppression by other hosts' reports, leaves. IGMPv2 only: IGMPv3 reports are not implemented (a version 3 query is answered as version 2).

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: Misses 125 MHz out of context (71-80 MHz estimated: needs pipelining before it sits behind the RGMII MAC); closes at 50 MHz. Simulated against RFC 2236 (directed sequence, every frame compared with the model, scapy decoding); transmit framing checked by bounded model checking; built alone out of context on an Artix-7 with Vivado 2026.1; not yet run on a board (the Nexys A7 network design carries it behind eth_mac_rmii; built, not yet run: a cable check comes first, see designs/b63d_nexys_net/host/PLAN.md).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `N_GROUPS` | 4 | 1..8 |  |
| `TICK_CLKS` | 12500000 | 1..16777215 | clocks per tick; RFC 2236 counts tenths of a second (12_500_000 at 125 MHz) |
| `UNSOL_TICKS` | 100 | 1..255 | the repeat of a join's report comes within this many ticks |

Out-of-space values fail at elaboration with `$error` (tested: `N_GROUPS=0`, `N_GROUPS=9`, `TICK_CLKS=0`, `UNSOL_TICKS=0`, `UNSOL_TICKS=256`).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tuser 1, tready always 1). received Ethernet frames without FCS
- `m_axis`: axis (dir master, tdata 8, tready True). 46-byte reports and leaves (TTL 1, Router Alert); the MAC pads them
- `config`: native; own_mac[47:0], own_ip[31:0], groups[N_GROUPS*32-1:0], group_en[N_GROUPS-1:0]. a group joins when its group_en rises and leaves when it falls; the MAC filter must accept the groups (01-00-5E plus the low 23 bits)
- `events`: native; ev_query, ev_report, ev_leave, ev_suppressed

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- report: a join's first report follows at once (no tick wait); query answers after a random 1..Max Response Time ticks, checked against that window in the bench
- throughput: one frame at a time, lowest group first

## Evidence

cocotb, a directed sequence written from RFC 2236 with short ticks: joins (a report at once and one repeat), general, group-specific and version 3 queries answered within the Max Response Time, the timer-restart rule, a query with a bad checksum ignored, suppression by another host's report, leaves only after being the last reporter; every frame compared byte for byte with ip_lib/igmp_join/model.py and decoded by scapy; Icarus Verilog 12. Formal (bounded): every frame 46 bytes and the AXI-Stream protocol rules (valid held until ready, data steady while waiting) on m_axis; an independent adversarial bench adds report timing in ticks, version 1 queries and scapy-built frames. Tests: `flow/net/tests/test_63d_igmp_rtl.py`, `flow/net/tests/test_63d_adversarial_rtl.py`, `flow/net/tests/test_63d_formal.py`.

Try it: `python3 -m pytest flow/net/tests/test_63d_igmp_rtl.py flow/net/tests/test_63d_adversarial_rtl.py flow/net/tests/test_63d_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `N_GROUPS=4, TICK_CLKS=40, UNSOL_TICKS=10`; `N_GROUPS=1, TICK_CLKS=25, UNSOL_TICKS=1`; `N_GROUPS=8, TICK_CLKS=60, UNSOL_TICKS=20`.

Terms (ARP, ICMP, IGMP, MDIO, RMII, RGMII, VLAN, pause, OOC, WNS, Fmax) are defined in [the library's terms](../README.md#terms).

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `igmp_no_router_alert` | the Router Alert option is missing from reports and leaves | caught |
| `igmp_no_suppression` | another host's report does not cancel our pending report | caught |
| `igmp_leave_always` | a leave is sent even when another host sent the last report | caught |
| `igmp_timer_never_restarted` | a query with a shorter Max Response Time does not shorten a running timer | caught |
| `igmp_ttl_two` | reports leave with TTL 2 instead of 1 | caught |
| `igmp_timer_always_restarted` | a query with a longer Max Response Time restarts a running timer (found by the independent review) | caught |

## Cost (out of context)

Built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 8.0 ns clock (125 MHz), Vivado 2026.1 (build 6511674); source: [char/xc7a100tcsg324-1.json](char/xc7a100tcsg324-1.json). Not run on a board.

| N_GROUPS | TICK_CLKS | UNSOL_TICKS | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 12500000 | 100 | 1075 | 430 | 0 | 0 | 0 | -4.529 | 79.8 | 0.020 |
| 8 | 12500000 | 100 | 1628 | 491 | 0 | 0 | 0 | -6.033 | 71.3 | 0.033 |

Defaults: N_GROUPS 4, TICK_CLKS 12500000, UNSOL_TICKS 100. WNS is the worst negative slack (the timing margin at the target clock; below zero the target is missed).

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); dynamic power is vectorless (default toggle rates). Regenerate with `python3 -m flow.ipchar igmp_join` (Vivado, minutes per point).

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.

## Cost table

measured out of context: see the Cost section above.

Licence: MIT (this repository).

## Known gaps and limits

- IGMPv2 host side only: no IGMPv3 reports or source filtering (a version 3 query is answered as a version 2 query, RFC 3376 7.2.1); no version 1 router compatibility timer; the random delay comes from a 16-bit LFSR; measured Fmax estimates 71-80 MHz out of context: below the RGMII MAC's 125 MHz (the frame's checksums are summed in one clock).
- Board: no board run of this entry is recorded; its evidence is simulation and out-of-context builds.

## Next steps

1. Pipeline the block before it sits behind the RGMII MAC (it closes at 50 MHz, not 125 MHz).
2. Run designs/b63d_nexys_net on the board and record the joins on a switch.

## History

- 0.1.0 (2026-11-12): Initial version: simulated against a Python model, seeded faults caught, formal checks (bounded except where the README says proved), out-of-context cost on an Artix-7 (Vivado 2026.1); not run on a board. See README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
