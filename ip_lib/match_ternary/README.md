# match_ternary 0.1.0

Ternary match (TCAM emulation) in LUT RAM: one 2**CHUNK_W x 1 RAM per (rule, key chunk), AND of the chunk vectors, lowest index wins.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `KEY_W` | 40 | 1..128 |  |
| `ACT_W` | 16 | 1..128 |  |
| `ENTRIES` | 32 | 1..256 |  |
| `CHUNK_W` | 5 | 2..8 |  |
| `TAG_W` | 8 | 1..64 |  |

Constraints: `KEY_W % CHUNK_W == 0`.

Out-of-space values fail at elaboration with `$error` (tested: `KEY_W=41, CHUNK_W=5`, `ENTRIES=300`, `CHUNK_W=9, KEY_W=45`).

## Interfaces

- `lookup`: native
- `cmd`: native. op 1 WRITE entry (value, care mask, action), op 2 DELETE

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- lookup: 4 clocks (measured)
- write: 2**CHUNK_W + 2 clocks at the core (34 measured at CHUNK_W 5)
- delete: 1 clock
- throughput: one lookup a clock

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_tables_rtl.py`.

Try it: `python3 -m pytest flow/net/tests/test_40_tables_rtl.py`.

Parameter points simulated: `KEY_W=40, ENTRIES=32, CHUNK_W=5`; `KEY_W=24, ENTRIES=8, CHUNK_W=4`; `KEY_W=48, ENTRIES=64, CHUNK_W=6`; `KEY_W=8, ENTRIES=1, CHUNK_W=8`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `highest_index_wins` | overlapping rules resolve to the wrong one | caught |
| `care_mask_ignored` | every bit is compared (no wildcards) | caught |
| `action_written_early` | the new action is visible while a lookup that matched the old rule is still in flight (a race found and fixed in this brief) | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none; CHUNK_W 5 suits 32-deep and 6 suits 64-deep LUT RAM (7-series and UltraScale+ both have 64x1 LUT RAM).
- Depends on: nothing.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).

## Known gaps and limits

- A rule being rewritten is absent for 2**CHUNK_W + 2 clocks; for make-before-break write a free entry, then delete.
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.

## Next steps

1. Measure the out-of-context cost with python -m flow.ipchar match_ternary after adding a characterisation entry.

## History

- 0.1.0 (2026-11-11): First version (brief 40): simulated bit-exact against the Python golden model; see README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
