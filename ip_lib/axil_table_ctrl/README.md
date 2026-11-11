# axil_table_ctrl 0.1.0

AXI4-Lite front end for the match tables: 512-bit staging DATA, CMD and STATUS registers; one command at a time.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| (none) | | | |

Out-of-space values fail at elaboration with `$error` (tested: no parameters).

## Interfaces

- `s_axil`: axi4-lite (dir slave, addr 7, data 32)
- `cmd`: native (dir master)

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- command: about 37 clocks a table command including the AXI4-Lite writes and the STATUS poll (median, exact table)
- throughput: software-bound

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_tables_rtl.py`.
Parameter points simulated: `defaults`.

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.
- Limits: no write strobes; one outstanding read and write.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).
