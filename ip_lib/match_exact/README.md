# match_exact 0.1.0

Exact-match table: two-way d-left hash (CRC-32 and CRC-32C bucket indexes) in block RAM plus a small CAM stash for collisions; INSERT/DELETE/AGE/CLEAR on a second port while lookups run every clock.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `KEY_W` | 48 | 1..256 |  |
| `ACT_W` | 16 | 1..128 |  |
| `IDX_W` | 10 | 2..16 |  |
| `STASH` | 4 | 0..16 |  |
| `TAG_W` | 8 | 1..64 |  |

Out-of-space values fail at elaboration with `$error` (tested: `IDX_W=1`, `STASH=17`, `KEY_W=0`).

## Interfaces

- `lookup`: native; lk_valid/lk_key/lk_tag -> res_valid/res_hit/res_act/res_tag
- `cmd`: native. valid/ready command port; axil_table_ctrl adds AXI4-Lite

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- lookup: 3 clocks (measured)
- insert_delete: 5 clocks at the core (measured)
- age_clear: 2 * 2**IDX_W + 2 clocks (2050 measured at IDX_W 10)
- throughput: one lookup a clock

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_tables_rtl.py`, `flow/net/tests/test_40_switch_rtl.py`.

Try it: `python3 -m pytest flow/net/tests/test_40_tables_rtl.py flow/net/tests/test_40_switch_rtl.py`.

Parameter points simulated: `IDX_W=6, STASH=4`; `IDX_W=4, STASH=0`; `IDX_W=7, STASH=16`; `KEY_W=60, ACT_W=8, IDX_W=9, STASH=4, TAG_W=1`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `stash_never_searched` | the hash-collision path (keys in the stash) is never looked up (the brief's example) | caught |
| `bank1_never_used` | a key whose bank-0 bucket is taken is reported inserted but never written | caught |
| `age_removes_used` | the AGE sweep removes recently used entries too | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (ram_style block).
- Depends on: nothing.
- Limits: placement is left-first (not least-loaded); no cuckoo moves, so the stash absorbs double collisions.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).
