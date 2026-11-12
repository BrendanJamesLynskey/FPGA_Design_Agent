# fir changelog

## 0.1.0 (2026-11-12)

- First version (brief 63A): four implementation variants (`dsp_bram`, `dist_ram`, `serial`, `lut_mult`) behind one contract, bit-exact against `model.py` at four parameter points, a differential test across the variants, seeded faults, and an out-of-context characterisation on the xc7a100t.
