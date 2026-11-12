# adc_histogram 0.2.0

Code-density histogram for converter tests: counts samples by their top BIN_W bits with min, max and total; DNL and INL are computed on the host (hil/instruments/models.py dnl_inl).

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against hil/instruments/models.py; not yet run on a board (needs a converter input: the XADC or the Pluto/Red Pitaya link).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `IMPL` | dist_ram | dist_ram, bram | implementation variant of the bin RAM (see variants) |
| `SAMP_W` | 12 | 4..16 | sample bits |
| `BIN_W` | 8 | 2..12 | 2**BIN_W bins (must not exceed SAMP_W) |
| `CNT_W` | 20 | 8..32 | counter bits per bin; saturates and sets overflow |

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
Parameter points simulated: `SAMP_W=12, BIN_W=6, CNT_W=16`; `SAMP_W=8, BIN_W=8, CNT_W=12`; `IMPL=bram, SAMP_W=12, BIN_W=6, CNT_W=16`; `IMPL=bram, SAMP_W=8, BIN_W=8, CNT_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `no_forwarding` | back-to-back samples in one bin lose a count | caught |
| `bin_from_low_bits` | the bin index uses the low bits of the code | caught |
| `min_wrong_way` | the minimum is tracked the wrong way | caught |
| `bram_copy_not_written` | the host's copy of the bins is never updated (bram variant, brief 63A) | caught |

## Variants

Selected by `IMPL`; every variant has the same ports, function and tests. Latency and II are in clocks.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `dist_ram` | one bin RAM in LUT RAM with two read ports (sample path and host readout) | `3` | `1` | up to a few hundred bins (BIN_W <= 8), or block RAM scarce |
| `bram` | two block RAM copies of the bins written together, one per read port | `3` | `1` | many bins (BIN_W 9 and up), or LUTs scarce |

Out-of-context cost on the xc7a100tcsg324-1 at a 4.0 ns clock ([char/xc7a100tcsg324-1.json](char/xc7a100tcsg324-1.json), `python3 -m flow.ipchar adc_histogram`):

| Variant | SAMP_W | BIN_W | CNT_W | LUT | FF | LUT RAM | BRAM tiles | DSP | WNS ns | Fmax MHz | Dynamic W | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dist_ram` | 12 | 6 | 16 | 128 | 132 | 44 | 0 | 0 | -1.503 | 181.7 | 0.003 | 3 | 1 |
| `dist_ram` | 12 | 10 | 20 | 1184 | 152 | 896 | 0 | 0 | -2.963 | 143.6 | 0.012 | 3 | 1 |
| `bram` | 12 | 6 | 16 | 81 | 100 | 0 | 1 | 0 | -2.364 | 157.1 | 0.006 | 3 | 1 |
| `bram` | 12 | 10 | 20 | 91 | 112 | 0 | 2 | 0 | -2.562 | 152.4 | 0.01 | 3 | 1 |

Tool: Vivado 2026.1 (build 6511674). Fmax is 1000 / (period - WNS) from one routed run at the target clock: an estimate, not a closure at that frequency. Power is vectorless (default toggle rates).

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (the dist_ram variant has two read ports on one LUT RAM; the bram variant keeps a second block RAM copy for the third port).
- Depends on: nothing.
- Limits: the dist_ram variant grows fast past BIN_W 8; the bram variant costs two block RAMs per 18 Kb of bins; a converter with a transfer function that is not offset binary must be converted first.

## Cost table

out-of-context, per variant: see the Variants table (char/xc7a100tcsg324-1.json); not yet in a board build.

Licence: MIT (this repository).
