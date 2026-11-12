# adc_histogram changelog

## 0.2.0 (2026-11-12)

- Implementation variants (brief 63A): `IMPL = "dist_ram"` (default; the 0.1.0 design) and `IMPL = "bram"` (two block RAM copies, one per read port). Same ports, function and latency; both bit-exact against the model; characterised out of context on the xc7a100t. The bin RAM's write port is now one combinational write enable, address and data.

## 0.1.0 (2026-11-11)

- First version (brief 30): simulated against the Python models, seeded faults caught, measured on the Nexys A7-100T inside designs/b30_hil_audio where noted in README.md.
