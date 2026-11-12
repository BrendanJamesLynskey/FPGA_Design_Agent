# frame_crc 0.1.0

Frame CRC and statistics for video: CRC-32 (IEEE 802.3), pixel count and pixel sum of every frame, compared with the model's CRC at each frame end; counts mismatches.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against zlib.crc32; measured on the Nexys A7-100T inside b30_hil_audio (the model's CRC read back, a seeded one-bit pixel fault counted).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `PIX_W` | 24 | 8, 16, 24, 32 | pixel word width in bits |

Out-of-space values fail at elaboration with `$error` (tested: `PIX_W=12`).

## Interfaces

- `pixels`: native; frame_start, pix_valid, pix_data -> crc_last, pix_last, sum_last, frames, mismatches, frame_done

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- result: the clock after the next frame_start (the frame ends there)
- throughput: one pixel word per clock

## Evidence

Bit-exact against the Python models in `hil/instruments/models.py` (plain Python written from the definitions, not from the RTL); cocotb with Icarus Verilog 12. Tests: `hil/tests/test_30_ip_rtl.py`, `designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.
Parameter points simulated: `PIX_W=24`; `PIX_W=8`; `PIX_W=32`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `compare_unfinalised` | the compare uses the CRC before the final inversion, so every good frame is flagged | caught |
| `wrong_polynomial` | one bit of the polynomial wrong | caught |
| `sum_misses_first_pixel` | the first pixel of a frame is left out of the sum | caught |
| `mismatch_not_counted` | a bad frame is never counted | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none (one clock; the pixel clock is the caller's).
- Part, board or pin: none.
- Depends on: nothing.
- Limits: the CRC is bitwise per word (a combinational loop of PIX_W steps), fine to about 150 MHz at PIX_W 24 on a -1 part; frame_start must precede the first pixel by at least zero clocks.

## Cost table

in-context cost (not an OOC sweep): 275 LUT, 257 FF at PIX_W 24 inside b30_hil_audio (Vivado 2026.1, xc7a100t -1, 100 MHz met; results/vivado_2026_1_remeasure/b30_hil_audio.json); the OOC sweep is still to do.

Licence: MIT (this repository).
