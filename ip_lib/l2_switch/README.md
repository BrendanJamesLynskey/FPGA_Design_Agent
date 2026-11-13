# l2_switch 0.1.0

Learning, VLAN-aware Layer-2 switch of NP ports: per-port ingress buffers, MAC learning and ageing in match_exact, flood/forward/filter, one pkt_queue_sched per egress port.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `NP` | 4 | 2..8 |  |
| `IN_BYTES` | 4096 | 128..65536, power of two |  |
| `EG_BYTES` | 4096 | 128..65536, power of two |  |
| `IDX_W` | 9 | 2..16 |  |
| `STASH` | 4 | 0..16 |  |

Out-of-space values fail at elaboration with `$error` (tested: `IDX_W=1`).

## Interfaces

- `s_*`: axis (dir slave, tdata 8 a port, tuser 1)
- `m_*`: axis (dir master, tdata 8 a port)
- `config`: native; pvid, cfg_we/cfg_vid/cfg_mask, age_tick

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- store_and_forward: ingress stores the whole frame; core 72 clocks per 60-byte frame under backlog (measured)
- throughput: core 72 clocks per minimum frame: 4.67 ports of 100 Mb/s at minimum frames at 50 MHz (measured)

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_switch_rtl.py`.

Try it: `python3 -m pytest flow/net/tests/test_40_switch_rtl.py`.

Parameter points simulated: `NP=4, IDX_W=9`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `no_learning` | source addresses are never learnt, so everything floods | caught |
| `flood_back_to_ingress` | floods go back out of the port they came in on | caught |
| `no_ingress_vlan_filter` | a port outside the VLAN can inject into it | caught |

## Boundary and reuse

- Registered outputs: from pkt_queue_sched.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: match_exact, pkt_queue_sched.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).

## Known gaps and limits

- Limits: no egress tag push/pop (use pkt_rewrite); no STP; ingress filter only; tested at NP 4 only.
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.

## Next steps

1. Measure the out-of-context cost with python -m flow.ipchar l2_switch after adding a characterisation entry.
2. Test at port counts other than NP 4.

## History

- 0.1.0 (2026-11-11): First version (brief 40): simulated bit-exact against the Python golden model; see README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
