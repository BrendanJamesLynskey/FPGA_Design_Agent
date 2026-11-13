# pkt_queue_sched 0.1.0

Packet buffer with a ring region and descriptor FIFO per queue, whole-packet tail drop with counters, and a round-robin / strict-priority / deficit-round-robin scheduler.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `NQ` | 4 | 2, 4, 8 |  |
| `QBYTES` | 2048 | 64..65536, power of two |  |
| `DESC` | 16 | 2..256, power of two |  |
| `MAX_LEN` | 1522 | 1..65536 |  |

Constraints: `MAX_LEN <= QBYTES`.

Out-of-space values fail at elaboration with `$error` (tested: `NQ=3`, `QBYTES=1000`, `DESC=1`, `MAX_LEN=5000, QBYTES=2048`).

## Interfaces

- `s_axis`: axis (dir slave, tdata 8, tuser 1, tdest 3). tready always 1
- `m_axis`: axis (dir master, tdata 8, tuser 1, tdest 3)

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- store_and_forward: first byte out = packet length + 3 clocks after the first byte in (63 for 60 bytes, measured)
- throughput: output 62 clocks per 60-byte packet (2 clocks a packet overhead, measured)

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_queues_rtl.py`, `flow/net/tests/test_40_switch_rtl.py`.

Try it: `python3 -m pytest flow/net/tests/test_40_queues_rtl.py flow/net/tests/test_40_switch_rtl.py`.

Parameter points simulated: `NQ=4, QBYTES=8192, DESC=32`; `NQ=2, QBYTES=256, DESC=4, MAX_LEN=200`; `NQ=4, QBYTES=512, DESC=2, MAX_LEN=512`; `NQ=8, QBYTES=1024, DESC=8, MAX_LEN=1000`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `overflow_not_counted` | packets dropped on a full queue are not counted (the brief's example) | caught |
| `drr_no_subtract` | DRR never charges a queue for what it sent | caught |
| `strict_priority_inverted` | the highest-numbered queue is served first | caught |
| `space_freed_early` | a full region is overwritten instead of dropping the packet | caught |

## Boundary and reuse

- Registered outputs: m_axis from a 2-entry skid buffer.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).

## Known gaps and limits

- Static per-queue regions (no shared buffer); no cut-through.
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.

## Next steps

1. Measure the out-of-context cost with python -m flow.ipchar pkt_queue_sched after adding a characterisation entry.

## History

- 0.1.0 (2026-11-11): First version (brief 40): simulated bit-exact against the Python golden model; see README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
