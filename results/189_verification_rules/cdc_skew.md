# Per-bit skew injection on a torn-pointer FIFO (brief 189 item 8)

Advisory. Icarus 12.0, cocotb 2.0.1, fixtures in `flow/tests/fixtures/cdc_pointer` and `cdc_mutants`.

| fixture | skew (max cycles a bit is held) | seeds run | seeds whose own test failed |
|---|---|---|---|
| cdcfx_m12 | 1 | 8 | 0  |
| cdcfx_m12 | 2 | 8 | 2 [2, 6] |
| cdcfx_m12 | 4 | 8 | 8 [1, 2, 3, 4, 5, 6, 7, 8] |
| cdcfx_m12 | none (plain) | 1 | 0  |
| cdcfx_c10 | 1 | 8 | 0  |
| cdcfx_c10 | 2 | 8 | 0  |
| cdcfx_c10 | 4 | 8 | 0  |
| cdcfx_c10 | none (plain) | 1 | 0  |
