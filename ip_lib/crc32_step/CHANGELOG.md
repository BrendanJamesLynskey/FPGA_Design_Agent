# crc32_step changelog

## 0.1.0 (2026-11-13)

- First version (brief 64A+): two implementation variants (`word`, `byte`) behind one contract, bit-exact against `model.py` and zlib, latency and II measured, seeded faults, and a `function_unit` contract that `hwsw/cfu.py` turns into a CPU custom instruction.
