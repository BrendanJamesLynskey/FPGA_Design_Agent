# dds_awg 0.2.0

DDS/AWG stimulus source: phase accumulator, sine table, triangle, saw and square, amplitude shift. f_out = f_tick * step / 2**PHASE_W.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against hil/instruments/models.py in both variants and measured out of context on an Artix-7 (xc7a100t, Vivado 2026.1); the 0.1.0 design (one table, before the variants) was measured on the Nexys A7-100T inside b30_hil_audio (1 kHz sine at the audio jack, 999.99 Hz, THD 1.32 %); the 0.2.0 variants have not been run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `IMPL` | bram | bram, lut | implementation variant of the sine table (see variants) |
| `PHASE_W` | 32 | 8..48 | accumulator width |
| `LUT_W` | 8 | 4..12 | sine table address bits (must not exceed PHASE_W) |
| `OUT_W` | 16 | 4..24 | output sample bits |

Constraints: `LUT_W <= PHASE_W`.

Out-of-space values fail at elaboration with `$error` (tested: `LUT_W=2`, `IMPL=rom`).

## Interfaces

- `sample`: native; tick, step, wave, amp_shift -> sample (signed), phase_o

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- tick_to_sample: 1 clock
- throughput: one sample per tick

## Evidence

Bit-exact against the Python models in `hil/instruments/models.py` (plain Python written from the definitions, not from the RTL); cocotb with Icarus Verilog 12. Tests: `hil/tests/test_30_ip_rtl.py`, `designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.

Try it: `python3 -m pytest hil/tests/test_30_ip_rtl.py designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.

Parameter points simulated: `PHASE_W=32, LUT_W=8, OUT_W=16`; `PHASE_W=24, LUT_W=6, OUT_W=12`; `IMPL=lut, PHASE_W=32, LUT_W=8, OUT_W=16`; `IMPL=lut, PHASE_W=24, LUT_W=6, OUT_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `sine_wrong_slice` | the table address skips the top phase bit, so the sine runs at twice the frequency (bram variant) | caught |
| `lut_sine_wrong_slice` | the same fault in the lut variant's table address (added with the variants) | caught |
| `bram_next_entry` | the registered table read is one entry ahead of the phase (bram variant) | caught |
| `triangle_no_fold` | the triangle is a saw at twice the rate | caught |
| `shift_logical` | amplitude scaling shifts zeros into negative samples | caught |

## Variants

Selected by `IMPL`; every variant has the same ports, the same bit-exact result and the same tests. Latency is clocks from an accepted input to its result; II (initiation interval) is clocks between accepted inputs, 1 meaning a new input every clock.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `bram` | sine table in block RAM, addressed one clock early so the RAM's output register delivers the sample on time | `1` | `1` | measured: at LUT_W 12, 113 LUTs against 871 and faster (187 against 148 MHz); at LUT_W 8 still the fewer LUTs (113 against 171) but slower (183 against 204 MHz) |
| `lut` | sine table as an asynchronous ROM in LUTs, read from the phase register | `1` | `1` | measured: the faster choice at LUT_W 8 (204 against 183 MHz) for 58 more LUTs; the crossover between LUT_W 8 and 12 was not measured |

Measured at PHASE_W 32, LUT_W 8, OUT_W 16: built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 4.0 ns clock (250 MHz), Vivado 2026.1 (build 6511674). Not run on a board.

| Variant | DSP | Block RAM tiles | LUT | Fmax estimate (MHz) | II | Latency |
|---|---|---|---|---|---|---|
| `bram` | 0 | 0.5 | 113 | 183 | 1 | 1 |
| `lut` | 0 | 0 | 171 | 204 | 1 | 1 |

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); it is not a closure at that frequency. WNS (worst slack against the clock) below zero means the target was missed.

<details><summary>Every measured point (4 rows; source: <a href="char/xc7a100tcsg324-1.json">char/xc7a100tcsg324-1.json</a>)</summary>

| Variant | PHASE_W | LUT_W | OUT_W | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `bram` | 32 | 8 | 16 | 113 | 48 | 0 | 0.5 | 0 | -1.452 | 183.4 | 0.010 | 1 | 1 |
| `bram` | 32 | 12 | 16 | 113 | 48 | 0 | 2 | 0 | -1.354 | 186.8 | 0.018 | 1 | 1 |
| `lut` | 32 | 8 | 16 | 171 | 56 | 0 | 0 | 0 | -0.912 | 203.6 | 0.013 | 1 | 1 |
| `lut` | 32 | 12 | 16 | 871 | 100 | 0 | 0 | 0 | -2.742 | 148.3 | 0.080 | 1 | 1 |

Dynamic power is vectorless (default toggle rates, no simulation activity): use it to rank variants, not as a measurement. Regenerate with `python3 -m flow.ipchar dds_awg` (Vivado, minutes per point).

</details>

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (the sine table is built in an initial block with $sin; Vivado 2026.1 synthesises it; rom_style attributes steer the variants).
- Depends on: nothing.

## Cost table

measured costs are in the Variants section above; in context inside b30_hil_audio the 0.1.0 design measured 115 LUT, 48 FF, 1 RAMB18 at PHASE_W 32, LUT_W 8, OUT_W 16 (Vivado 2026.1, xc7a100t -1, timing met at 100 MHz; results/vivado_2026_1_remeasure/b30_hil_audio.json).

Licence: MIT (this repository).

## Known gaps and limits

- No table interpolation: the sine's spurs are set by LUT_W (about -6 dB per bit below the carrier, 8 bits: SFDR near 48 dB for the table alone); no phase offset input.
- The 0.2.0 variants have not been run on a board; the board measurement is of the 0.1.0 single-table design.

## Next steps

1. Run the 0.2.0 variants on the Nexys A7 inside b30_hil_audio and repeat the audio-jack tone measurement.

## History

- 0.2.0 (2026-11-12): Implementation variants: `IMPL = "bram"` (default; the sine table read one clock early at the next phase into a block RAM register) and `IMPL = "lut"` (asynchronous LUT ROM). Same ports, function and latency; both bit-exact against the model; measured out of context (built alone, no I/O constraints) on the xc7a100t. Seeded faults for both variants.
- 0.1.0 (2026-11-11): First version: simulated against the Python models, seeded faults caught, measured on the Nexys A7-100T inside designs/b30_hil_audio where noted in README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
