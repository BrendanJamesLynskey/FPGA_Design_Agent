# adc_histogram 0.1.0

Code-density histogram for converter tests: counts samples by their top BIN_W bits with min, max and total; DNL and INL are computed on the host (hil/instruments/models.py dnl_inl).

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against hil/instruments/models.py; not yet run on a board (needs a converter input: the XADC or the Pluto/Red Pitaya link).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `SAMP_W` | 12 | 4..16 | sample bits |
| `BIN_W` | 8 | 2..12 | 2**BIN_W bins (must not exceed SAMP_W) |
| `CNT_W` | 20 | 8..32 | counter bits per bin; saturates and sets overflow |

Out-of-space values fail at elaboration with `$error` (tested: `BIN_W=1`).

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
Parameter points simulated: `SAMP_W=12, BIN_W=6, CNT_W=16`; `SAMP_W=8, BIN_W=8, CNT_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `no_forwarding` | back-to-back samples in one bin lose a count | caught |
| `bin_from_low_bits` | the bin index uses the low bits of the code | caught |
| `min_wrong_way` | the minimum is tracked the wrong way | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (three read ports, so it maps to distributed RAM, not block RAM).
- Depends on: nothing.
- Limits: bin RAM is distributed RAM: use BIN_W <= 8 for a small cost; a converter with a transfer function that is not offset binary must be converted first.

## Cost table

pending: no OOC synthesis sweep yet, and the block is not in the b30_hil_audio build, so no Vivado cost is recorded.

Licence: MIT (this repository).
