# match_lpm 0.1.0

IPv4 longest-prefix match: an 8-8-8-8 multibit trie in block RAM, one lookup a clock; the control plane (flow/net/model.py lpm_compile) expands prefixes and writes raw words, deepest first, so updates never stop traffic.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `ACT_W` | 16 | 1..64 |  |
| `L1_NODES` | 64 | 1..64 |  |
| `L2_NODES` | 64 | 1..64 |  |
| `L3_NODES` | 64 | 1..64 |  |
| `TAG_W` | 8 | 1..64 |  |

Out-of-space values fail at elaboration with `$error` (tested: `L1_NODES=65`, `ACT_W=0`).

## Interfaces

- `lookup`: native
- `cmd`: native. op 1 WRITE {level, index}, op 2 CLEAR

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- lookup: 10 clocks (measured)
- word_write: 1 clock at the core (measured)
- throughput: one lookup a clock

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_tables_rtl.py`.
Parameter points simulated: `ACT_W=12, L1_NODES=16, L2_NODES=32, L3_NODES=64`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `best_match_not_kept` | a shorter prefix found higher in the trie is forgotten when a deeper level has no route | caught |
| `wrong_key_byte_level2` | level 2 is indexed by the wrong address byte | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (ram_style block).
- Depends on: nothing.
- Limits: no route delete in the compiler yet (CLEAR and reload); node indices must stay stable across incremental compiles (found in this brief).

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).
