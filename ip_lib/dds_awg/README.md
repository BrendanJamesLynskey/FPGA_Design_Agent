# dds_awg 0.1.0

DDS/AWG stimulus source: phase accumulator, sine table, triangle, saw and square, amplitude shift. f_out = f_tick * step / 2**PHASE_W.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against hil/instruments/models.py; measured on the Nexys A7-100T inside b30_hil_audio (the 1 kHz sine read at the audio jack at 999.99 Hz, THD 1.32 %).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `PHASE_W` | 32 | 8..48 | accumulator width |
| `LUT_W` | 8 | 4..12 | sine table address bits (must not exceed PHASE_W) |
| `OUT_W` | 16 | 4..24 | output sample bits |

Out-of-space values fail at elaboration with `$error` (tested: `LUT_W=2`).

## Interfaces

- `sample`: native; tick, step, wave, amp_shift -> sample (signed), phase_o

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- tick_to_sample: 1 clock
- throughput: one sample per tick

## Evidence

Bit-exact against the Python models in `hil/instruments/models.py` (plain Python written from the definitions, not from the RTL); cocotb with Icarus Verilog 12. Tests: `hil/tests/test_30_ip_rtl.py`, `designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.
Parameter points simulated: `PHASE_W=32, LUT_W=8, OUT_W=16`; `PHASE_W=24, LUT_W=6, OUT_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `sine_wrong_slice` | the table address skips the top phase bit, so the sine runs at twice the frequency | caught |
| `triangle_no_fold` | the triangle is a saw at twice the rate | caught |
| `shift_logical` | amplitude scaling shifts zeros into negative samples | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none (the sine table is built in an initial block with $sin; Vivado 2026.1 synthesises it).
- Depends on: nothing.
- Limits: no table interpolation: the sine's spurs are set by LUT_W (about -6 dB per bit below the carrier, 8 bits: SFDR near 48 dB for the table alone); no phase offset input.

## Cost table

in-context cost (not an OOC sweep): 115 LUT, 48 FF, 1 RAMB18 at PHASE_W 32, LUT_W 8, OUT_W 16, inside b30_hil_audio (Vivado 2026.1, xc7a100t -1, timing met at 100 MHz; results/49_vivado_2026_1/b30_hil_audio.json); the OOC sweep over the parameter space is still to do.

Licence: MIT (this repository).
