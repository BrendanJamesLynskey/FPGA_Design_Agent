# dds_awg 0.2.0

DDS/AWG stimulus source: phase accumulator, sine table, triangle, saw and square, amplitude shift. f_out = f_tick * step / 2**PHASE_W.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against hil/instruments/models.py; measured on the Nexys A7-100T inside b30_hil_audio (the 1 kHz sine read at the audio jack at 999.99 Hz, THD 1.32 %).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `IMPL` | bram | bram, lut | implementation variant of the sine table (see variants) |
| `PHASE_W` | 32 | 8..48 | accumulator width |
| `LUT_W` | 8 | 4..12 | sine table address bits (must not exceed PHASE_W) |
| `OUT_W` | 16 | 4..24 | output sample bits |

Out-of-space values fail at elaboration with `$error` (tested: `LUT_W=2`, `IMPL=rom`).

## Interfaces

- `sample`: native; tick, step, wave, amp_shift -> sample (signed), phase_o

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- tick_to_sample: 1 clock
- throughput: one sample per tick

## Evidence

Bit-exact against the Python models in `hil/instruments/models.py` (plain Python written from the definitions, not from the RTL); cocotb with Icarus Verilog 12. Tests: `hil/tests/test_30_ip_rtl.py`, `designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.
Parameter points simulated: `PHASE_W=32, LUT_W=8, OUT_W=16`; `PHASE_W=24, LUT_W=6, OUT_W=12`; `IMPL=lut, PHASE_W=32, LUT_W=8, OUT_W=16`; `IMPL=lut, PHASE_W=24, LUT_W=6, OUT_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `sine_wrong_slice` | the table address skips the top phase bit, so the sine runs at twice the frequency (bram variant) | caught |
| `lut_sine_wrong_slice` | the same fault in the lut variant's table address (brief 63A) | caught |
| `bram_next_entry` | the registered table read is one entry ahead of the phase (bram variant) | caught |
| `triangle_no_fold` | the triangle is a saw at twice the rate | caught |
| `shift_logical` | amplitude scaling shifts zeros into negative samples | caught |

## Variants

Selected by `IMPL`; every variant has the same ports, function and tests. Latency and II are in clocks.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `bram` | sine table in block RAM, read one clock early at the next phase (phase + step) into the RAM's own register | `1` | `1` | large tables (LUT_W 10 and up) or LUTs scarce; a block RAM free |
| `lut` | sine table as an asynchronous ROM in LUTs, read from the phase register | `1` | `1` | small tables, or no block RAM to spare |

Out-of-context cost on the xc7a100tcsg324-1 at a 4.0 ns clock ([char/xc7a100tcsg324-1.json](char/xc7a100tcsg324-1.json), `python3 -m flow.ipchar dds_awg`):

| Variant | PHASE_W | LUT_W | OUT_W | LUT | FF | LUT RAM | BRAM tiles | DSP | WNS ns | Fmax MHz | Dynamic W | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `bram` | 32 | 8 | 16 | 113 | 48 | 0 | 0.5 | 0 | -1.452 | 183.4 | 0.01 | 1 | 1 |
| `bram` | 32 | 12 | 16 | 113 | 48 | 0 | 2 | 0 | -1.354 | 186.8 | 0.018 | 1 | 1 |
| `lut` | 32 | 8 | 16 | 171 | 56 | 0 | 0 | 0 | -0.912 | 203.6 | 0.013 | 1 | 1 |
| `lut` | 32 | 12 | 16 | 871 | 100 | 0 | 0 | 0 | -2.742 | 148.3 | 0.08 | 1 | 1 |

Tool: Vivado 2026.1 (build 6511674). Fmax is 1000 / (period - WNS) from one routed run at the target clock: an estimate, not a closure at that frequency. Power is vectorless (default toggle rates).

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (the sine table is built in an initial block with $sin; Vivado 2026.1 synthesises it; rom_style attributes steer the variants).
- Depends on: nothing.
- Limits: no table interpolation: the sine's spurs are set by LUT_W (about -6 dB per bit below the carrier, 8 bits: SFDR near 48 dB for the table alone); no phase offset input.

## Cost table

out-of-context, per variant: see the Variants table (char/xc7a100tcsg324-1.json); in context inside b30_hil_audio the 0.1.0 design measured 115 LUT, 48 FF, 1 RAMB18 at PHASE_W 32, LUT_W 8, OUT_W 16 (Vivado 2026.1, xc7a100t -1, timing met at 100 MHz; results/vivado_2026_1_remeasure/b30_hil_audio.json).

Licence: MIT (this repository).
