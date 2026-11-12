# adc_histogram changelog

## 0.2.0 (2026-11-12)

- Implementation variants: `IMPL = "dist_ram"` (default; the 0.1.0 design) and `IMPL = "bram"` (two block RAM copies, one per read port). Same ports, function and latency; both bit-exact against the model; measured out of context (built alone, no I/O constraints) on the xc7a100t. The bin RAM's write port is now one combinational write enable, address and data, so both variants share it.
- Simulation-only behaviour change: the write enable now depends combinationally on `clear`. A bench that leaves `clear` undriven (X) in the first clock after reset leaves bin 0 unknown in simulation; drive `clear` low before reset ends. Hardware is unaffected (a real input is never X).

## 0.1.0 (2026-11-11)

- First version: simulated against the Python models, seeded faults caught, measured on the Nexys A7-100T inside designs/b30_hil_audio where noted in README.md.
