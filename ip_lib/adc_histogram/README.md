# adc_histogram 0.2.0

Code-density histogram for converter tests: counts samples by their top BIN_W bits with min, max and total; DNL and INL are computed on the host (hil/instruments/models.py dnl_inl).

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against hil/instruments/models.py in both variants and measured out of context on an Artix-7 (xc7a100t, Vivado 2026.1); not yet run on a board (needs an on-chip or external converter input).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `IMPL` | dist_ram | dist_ram, bram | implementation variant of the bin RAM (see variants) |
| `SAMP_W` | 12 | 4..16 | sample bits |
| `BIN_W` | 8 | 2..12 | 2**BIN_W bins (must not exceed SAMP_W) |
| `CNT_W` | 20 | 8..32 | counter bits per bin; saturates and sets overflow |

Constraints: `BIN_W <= SAMP_W`.

Out-of-space values fail at elaboration with `$error` (tested: `BIN_W=1`, `IMPL=lutram`).

## Interfaces

- `samples`: native; s_valid, s_data
- `readout`: native; rd_bin -> rd_count (one clock later), min_code, max_code, total, overflow, busy

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- sample_to_count: 3 clocks (read, add, write; back-to-back hits on one bin are forwarded)
- clear: 2**BIN_W clocks
- throughput: one sample per clock

## Evidence

Bit-exact against the Python models in `hil/instruments/models.py` (plain Python written from the definitions, not from the RTL); cocotb with Icarus Verilog 12. Tests: `hil/tests/test_30_ip_rtl.py`.

Try it: `python3 -m pytest hil/tests/test_30_ip_rtl.py`.

Parameter points simulated: `SAMP_W=12, BIN_W=6, CNT_W=16`; `SAMP_W=8, BIN_W=8, CNT_W=12`; `IMPL=bram, SAMP_W=12, BIN_W=6, CNT_W=16`; `IMPL=bram, SAMP_W=8, BIN_W=8, CNT_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `no_forwarding` | back-to-back samples in one bin lose a count | caught |
| `bin_from_low_bits` | the bin index uses the low bits of the code | caught |
| `min_wrong_way` | the minimum is tracked the wrong way | caught |
| `bram_copy_not_written` | the host's copy of the bins is never updated (bram variant, added with the variants) | caught |

## Variants

Selected by `IMPL`; every variant has the same ports, the same bit-exact result and the same tests. Latency is clocks from an accepted input to its result; II (initiation interval) is clocks between accepted inputs, 1 meaning a new input every clock.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `dist_ram` | one bin RAM in LUT RAM with two read ports (sample path and host readout) | `3` | `1` | measured: at BIN_W 6, 128 LUTs and 182 MHz against 81 LUTs plus one block RAM tile at 157 MHz; guidance: up to about BIN_W 8, or block RAM scarce |
| `bram` | two block RAM copies of the bins written together, one per read port | `3` | `1` | measured: at BIN_W 10, 91 LUTs and 2 block RAM tiles against 1184 LUTs for dist_ram; guidance: from about BIN_W 9, or LUTs scarce |

Measured at SAMP_W 12, BIN_W 6, CNT_W 16: built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 4.0 ns clock (250 MHz), Vivado 2026.1 (build 6511674). Not run on a board.

| Variant | DSP | Block RAM tiles | LUT | Fmax estimate (MHz) | II | Latency |
|---|---|---|---|---|---|---|
| `dist_ram` | 0 | 0 | 128 | 182 | 1 | 3 |
| `bram` | 0 | 1 | 81 | 157 | 1 | 3 |

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); it is not a closure at that frequency. WNS (worst slack against the clock) below zero means the target was missed.

<details><summary>Every measured point (4 rows; source: <a href="char/xc7a100tcsg324-1.json">char/xc7a100tcsg324-1.json</a>)</summary>

| Variant | SAMP_W | BIN_W | CNT_W | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dist_ram` | 12 | 6 | 16 | 128 | 132 | 44 | 0 | 0 | -1.503 | 181.7 | 0.003 | 3 | 1 |
| `dist_ram` | 12 | 10 | 20 | 1184 | 152 | 896 | 0 | 0 | -2.963 | 143.6 | 0.012 | 3 | 1 |
| `bram` | 12 | 6 | 16 | 81 | 100 | 0 | 1 | 0 | -2.364 | 157.1 | 0.006 | 3 | 1 |
| `bram` | 12 | 10 | 20 | 91 | 112 | 0 | 2 | 0 | -2.562 | 152.4 | 0.010 | 3 | 1 |

Dynamic power is vectorless (default toggle rates, no simulation activity): use it to rank variants, not as a measurement. Regenerate with `python3 -m flow.ipchar adc_histogram` (Vivado, minutes per point).

</details>

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (the dist_ram variant has two read ports on one LUT RAM; the bram variant keeps a second block RAM copy for the third port).
- Depends on: nothing.

## Cost table

measured costs are in the Variants section above.

Licence: MIT (this repository).

## Known gaps and limits

- Limits: the dist_ram variant grows fast with BIN_W (measured at BIN_W 10: 1184 LUTs, 896 of them LUT RAM); the bram variant keeps two block RAM copies, so twice the block RAM of the bin storage; a converter with a transfer function that is not offset binary must be converted first.
- Board: no board run of this entry is recorded; its evidence is simulation and out-of-context builds.

## Next steps

1. Run it on a board with a real converter input (the XADC or an external ADC) and compare the histogram with the model.

## History

- 0.2.0 (2026-11-12): Implementation variants: `IMPL = "dist_ram"` (default; the 0.1.0 design) and `IMPL = "bram"` (two block RAM copies, one per read port). Same ports, function and latency; both bit-exact against the model; measured out of context (built alone, no I/O constraints) on the xc7a100t. The bin RAM's write port is now one combinational write enable, address and data, so both variants share it.
- 0.1.0 (2026-11-11): First version: simulated against the Python models, seeded faults caught, measured on the Nexys A7-100T inside designs/b30_hil_audio where noted in README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
