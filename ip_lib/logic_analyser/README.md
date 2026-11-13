# logic_analyser 0.1.0

Register-mapped logic analyser: captures WIDTH internal signals into RAM at the sample rate, with a level or edge trigger and a pre-trigger depth, and reads the buffer back through the test shell window.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated; measured on the Nexys A7-100T inside b30_hil_audio (256 tone samples read back, matched to the DDS model; pre-trigger edge test).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `WIDTH` | 16 | 1..32 | probed bits |
| `ADDR_W` | 10 | 2..14 | DEPTH = 2**ADDR_W samples |

Out-of-space values fail at elaboration with `$error` (tested: `ADDR_W=1`).

## Interfaces

- `probe`: native; sample, sample_en
- `window`: native. the test shell window (win_addr, win_wr, win_rd, win_wdata, win_rdata); read data is combinational on win_addr

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- trigger_to_capture_end: DEPTH - 1 - PRE samples after the trigger sample
- throughput: one sample per clock when sample_en is 1

## Evidence

Bit-exact against the Python models in `hil/instruments/models.py` (plain Python written from the definitions, not from the RTL); cocotb with Icarus Verilog 12. Tests: `hil/tests/test_30_ip_rtl.py`, `designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.

Try it: `python3 -m pytest hil/tests/test_30_ip_rtl.py designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.

Parameter points simulated: `WIDTH=16, ADDR_W=6`; `WIDTH=8, ADDR_W=4`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `pretrigger_off_by_one` | capture sample 0 is one sample late | caught |
| `edge_mode_both_edges` | edge mode also triggers on falling edges | caught |
| `post_trigger_short` | capture ends one sample early, so the last sample is stale | caught |

## Boundary and reuse

- Registered outputs: no (read data is combinational from the RAM and registers).
- Clock crossings: none (the probes must be in the capture clock domain).
- Part, board or pin: none (inferred RAM).
- Depends on: nothing.

## Cost table

in-context cost (not an OOC sweep): 132 LUT plus 88 LUTRAM, 142 FF, no block RAM at WIDTH 16, ADDR_W 8 inside b30_hil_audio (Vivado 2026.1, xc7a100t -1; results/vivado_2026_1_remeasure/b30_hil_audio.json); the OOC sweep is still to do. For comparison the AMD ILA on T1 on Vivado 2026.1 (one ILA IP, 13 probes packed into 2 ports, 1024 deep) cost 1181 LUT, 2074 FF and 2 block RAM tiles (results/f0a_2026_1).

Licence: MIT (this repository).

## Known gaps and limits

- Limits: one trigger stage (no sequencer); depth is fixed at build time; compare with the ILA in ip.yaml limits of ila-in-batch for the full-rate, multi-probe case.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.

## Next steps

1. Add a trigger sequencer stage if captures need more than one trigger condition.

## History

- 0.1.0 (2026-11-11): First version (brief 30): simulated against the Python models, seeded faults caught, measured on the Nexys A7-100T inside designs/b30_hil_audio where noted in README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
