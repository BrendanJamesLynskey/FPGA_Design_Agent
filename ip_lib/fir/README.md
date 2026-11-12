# fir 0.1.0

FIR filter with runtime-loadable coefficients, full-precision output and valid/ready streams, in four implementations that trade multipliers for speed: multiply-accumulate (MAC) engines on DSP slices with block RAM or with LUT RAM, one time-shared DSP MAC, and a fully parallel form with one LUT-built multiplier per tap.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against ip_lib/fir/model.py: every variant at four parameter points, a differential test across the variants, and an adversarial bench (coefficient beats between samples, reloads with results in flight, resets mid-stream); measured out of context on an Artix-7 (xc7a100t, Vivado 2026.1); not yet run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `IMPL` | dsp_bram | dsp_bram, dist_ram, serial, lut_mult | implementation variant (see variants) |
| `TAPS` | 16 | 2..256 | number of taps (lut_mult up to 64) |
| `DATA_W` | 16 | 4..24 | sample bits, signed |
| `COEF_W` | 16 | 4..18 | coefficient bits, signed |
| `FOLD` | 4 | 2..256 | taps per multiply-accumulate engine for dsp_bram and dist_ram (at most TAPS); serial and lut_mult ignore it |

Constraints: `DATA_W + COEF_W + clog2(TAPS) <= 48`.

Out-of-space values fail at elaboration with `$error` (tested: `IMPL=fast`, `TAPS=1, FOLD=1`, `FOLD=32`, `DATA_W=25`, `COEF_W=19`, `DATA_W=24, COEF_W=18, TAPS=256, FOLD=8`, `IMPL=lut_mult, TAPS=65`).

## Interfaces

- `coefficients`: valid/ready stream; c_valid, c_ready, c_data (signed COEF_W), c_last. h[0] first; c_last (or the TAPS-th beat) ends a load; no sample is taken while c_valid is high
- `samples`: valid/ready stream; s_valid, s_ready, s_data (signed DATA_W)
- `results`: valid/ready stream; m_valid, m_ready, m_data (signed ACC_W = DATA_W + COEF_W + clog2(TAPS))
- `status`: native; busy (high while the memories are cleared after reset)

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- sample_to_result: the LATENCY localparam of fir (clocks from the accepting clock to m_valid, with m_ready high); per variant below
- after_reset: busy for FOLD clocks (folded variants) or one clock (lut_mult)
- throughput: one sample every II clocks (the II localparam; per variant below); results wait for m_ready without loss

## Evidence

Bit-exact against `ip_lib/fir/model.py` (plain Python written from the definition, not from the RTL); cocotb with Icarus Verilog 12. Every variant at four parameter points with random input gaps and output back-pressure, a coefficient reload mid-stream and the full-precision corner; the measured latency and II equal the declared ones; a differential test feeds every variant the same values and compares their outputs; an adversarial bench (written by an independent reviewer) interleaves coefficient beats with samples, reloads with results in flight and resets mid-stream, rebuilding the expected outputs from the handshakes. Tests: `ip_lib/fir/tb/test_fir_rtl.py`.
Parameter points simulated: `IMPL=['dsp_bram', 'dist_ram', 'serial', 'lut_mult'], TAPS=16, DATA_W=16, COEF_W=16, FOLD=4`; `IMPL=['dsp_bram', 'dist_ram', 'serial', 'lut_mult'], TAPS=7, DATA_W=12, COEF_W=10, FOLD=3`; `IMPL=['dsp_bram', 'dist_ram', 'serial', 'lut_mult'], TAPS=33, DATA_W=18, COEF_W=18, FOLD=8`; `IMPL=['dsp_bram', 'dist_ram', 'serial', 'lut_mult'], TAPS=2, DATA_W=4, COEF_W=4, FOLD=2`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py --blocks fir`):

| Fault | What it breaks | Result |
|---|---|---|
| `delay_no_shift` | the sample leaving one engine's segment does not reach the next engine (folded variants with more than one MAC) | caught |
| `acc_not_cleared` | each output adds onto the last one's partial sums | caught |
| `sweep_wrong_way` | the delay line is read forwards, so the taps meet the wrong samples | caught |
| `coef_wrong_field` | a coefficient is written into the field of the wrong MAC engine | caught |
| `sample_with_coef` | a sample offered beside a coefficient beat is acknowledged and then dropped | caught |
| `ram_one_read_register` | the RAM's read latency drops to one clock, so data and the MAC pipeline flags are a clock apart | caught |
| `product_unsigned` | the LUT multipliers treat negative samples as large positive ones | caught |
| `delay_line_broadcast` | every tap sees the previous sample instead of its own delay | caught |
| `latency_declared_short` | the declared LATENCY no longer matches the clocks the folded variants take, so a caller reading it would be wrong | caught |
| `coef_while_products_form` | a coefficient can land while a sample's products are being formed, so that sample mixes old and new coefficients | not run |

## Variants

Selected by `IMPL`; every variant has the same ports, the same bit-exact result and the same tests. Latency is clocks from an accepted input to its result; II (initiation interval) is clocks between accepted inputs, 1 meaning a new input every clock.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `dsp_bram` | ceil(TAPS/FOLD) MAC engines on DSP slices, each taking FOLD taps in turn; samples and coefficients in block RAM | `FOLD + 8 + clog2(ceil(TAPS / FOLD))` | `FOLD + 3` | guidance: longer filters at sample rates well below the clock, with DSP slices and block RAM to spare |
| `dist_ram` | the same engines with the samples and coefficients in LUT RAM | `FOLD + 8 + clog2(ceil(TAPS / FOLD))` | `FOLD + 3` | guidance: short coefficient sets, or block RAM already spoken for |
| `serial` | one DSP MAC engine time-shared over every tap; memory type left to synthesis | `TAPS + 8` | `TAPS + 3` | the fewest DSP slices, when a new sample every TAPS + 3 clocks is fast enough |
| `lut_mult` | fully parallel: one multiplier per tap built from LUTs, all taps summed every clock (direct form) | `2 + clog2(TAPS)` | `1` | a sample every clock with no DSP slices to spare; measured: 15 to 42 times the LUTs of dsp_bram and under half its Fmax |

Measured at TAPS 16, DATA_W 16, COEF_W 16, FOLD 4: built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 4.0 ns clock (250 MHz), Vivado 2026.1 (build 6511674). Not run on a board.

| Variant | DSP | Block RAM tiles | LUT | Fmax estimate (MHz) | II | Latency |
|---|---|---|---|---|---|---|
| `dsp_bram` | 4 | 2 | 363 | 267 | 7 | 14 |
| `dist_ram` | 4 | 0 | 448 | 275 | 7 | 14 |
| `serial` | 1 | 0 | 181 | 284 | 19 | 24 |
| `lut_mult` | 0 | 0 | 5377 | 117 | 1 | 6 |

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); it is not a closure at that frequency. WNS (worst slack against the clock) below zero means the target was missed.

<details><summary>Every measured point (12 rows; source: <a href="char/xc7a100tcsg324-1.json">char/xc7a100tcsg324-1.json</a>)</summary>

| Variant | TAPS | DATA_W | COEF_W | FOLD | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dsp_bram` | 16 | 16 | 16 | 4 | 363 | 563 | 0 | 2 | 4 | 0.256 | 267.1 | 0.060 | 14 | 7 |
| `dsp_bram` | 32 | 16 | 16 | 8 | 375 | 576 | 0 | 2 | 4 | 0.204 | 263.4 | 0.061 | 18 | 11 |
| `dsp_bram` | 64 | 12 | 12 | 16 | 285 | 464 | 0 | 2 | 4 | 0.326 | 272.2 | 0.053 | 26 | 19 |
| `dist_ram` | 16 | 16 | 16 | 4 | 448 | 563 | 88 | 0 | 4 | 0.368 | 275.3 | 0.041 | 14 | 7 |
| `dist_ram` | 32 | 16 | 16 | 8 | 468 | 576 | 88 | 0 | 4 | 0.289 | 269.5 | 0.043 | 18 | 11 |
| `dist_ram` | 64 | 12 | 12 | 16 | 349 | 464 | 64 | 0 | 4 | 0.287 | 269.3 | 0.033 | 26 | 19 |
| `serial` | 16 | 16 | 16 | 4 | 181 | 269 | 24 | 0 | 1 | 0.482 | 284.3 | 0.012 | 24 | 19 |
| `serial` | 32 | 16 | 16 | 8 | 190 | 279 | 24 | 0 | 1 | 0.575 | 292.0 | 0.013 | 40 | 35 |
| `serial` | 64 | 12 | 12 | 16 | 193 | 237 | 32 | 0 | 1 | 0.748 | 307.5 | 0.011 | 72 | 67 |
| `lut_mult` | 16 | 16 | 16 | 4 | 5377 | 1552 | 0 | 0 | 0 | -4.532 | 117.2 | 0.067 | 6 | 1 |
| `lut_mult` | 32 | 16 | 16 | 8 | 10126 | 3145 | 0 | 0 | 0 | -5.490 | 105.4 | 0.123 | 7 | 1 |
| `lut_mult` | 64 | 12 | 12 | 16 | 12037 | 4818 | 0 | 0 | 0 | -3.905 | 126.5 | 0.143 | 8 | 1 |

Dynamic power is vectorless (default toggle rates, no simulation activity): use it to rank variants, not as a measurement. Regenerate with `python3 -m flow.ipchar fir` (Vivado, minutes per point).

</details>

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (memories and multipliers are inferred; use_dsp and ram_style attributes steer the variants; no primitive is instantiated).
- Depends on: nothing.
- Limits: no rounding or saturation: the output carries every bit; no symmetric-coefficient or polyphase (decimating, interpolating) forms yet; coefficients are loaded one at a time (the folded variants take three clocks per coefficient).

## Cost table

measured costs are in the Variants section above.

Licence: MIT (this repository).
