# results/b93: deciding before the last byte, measured

Recorded results for [designs/b93_precompute](../../designs/b93_precompute/README.md): simulation of the 58A trigger core with the
decision model behind the rules (baseline, early features, table block), the table blocks against their integer models, and
out-of-context, post-route builds on the K26 (`xck26-sfvc784-2LV-c`) and the Artix-7 100T (`xc7a100tcsg324-1`), Vivado 2026.1.
Synthetic data only (brief 87's splits). No board run.

## Records

| File | What | Made by |
|---|---|---|
| `stage0.json` | when each model input becomes known, which input is last, the ITCH 5.0 Add Order offsets | `python -m designs.b93_precompute.model.stage0` |
| `block_equivalence.json` | each table block against the 87 or 89 integer model: test split, 20,000 random vectors, every late value | `B93_RECORD=results/b93 pytest designs/b93_precompute/tests/test_b93_pe.py` |
| `integration_<gbt\|lgs>_pre<0-3>_latency.json` | the 58A stage clocks with the model off and on, speculative and safe, and when the class is valid | `B93_ML_ARM=<1\|4> B93_ML_PRE=<0-3> B93_RECORD=results/b93 pytest designs/b93_precompute/tests/test_b93_integ_rtl.py` |
| `integration_*_twin*.json` | features and classes equal the twin: generator stream, 300 edge cases, bad-FCS frames, other instruments between tracked ones | same command |
| `speculation.json` | how often a send on the table's most likely class would be undone (counted, not built) | `python -m designs.b93_precompute.model.speculation` |
| `ooc/<k26\|a7>/<block>.json`, `ooc/*/reports/` | post-route LUT, FF, slack at the closed clock, early and late path delay of the table blocks, every pass of the clock search, and the closed pass's reports | `python -m designs.b93_precompute.ooc.ooc --part <part> --arms ...` |
| `timing_baseline.svg`, `timing_early.svg`, `timing_table.svg` | timing diagrams of the three arms from the measured clocks | `python -m designs.b93_precompute.model.figures` |
| `summary.json` | the numbers the write-up quotes, from the files above only | `python3 results/b93/summary.py` (`--check` in CI) |

## Reproduce

- Python 3.12 with numpy and cocotb 2.0.1; Icarus Verilog 12; Verilator 5 for the lint test; Vivado 2026.1 for the `ooc` runs
  (about 3 hours a part on the shared workstation, one thread each, in a heavy slot).
- Latency of a block = clocks x max(closed period, 2.0 ns). The early and late path delays are the clock period minus the slack
  of the worst path from the early or the late input registers.

## Known gaps and limits

- Out of context only: no clock buffer or jitter, so no clock is quoted faster than 2.0 ns; closed clocks are closed points of a
  search (routing noise is about 0.1 ns), not bounds. The gate's bypass path is not in the block builds.
- `ML_PRE` 1 to 3 are simulation only: no full-design build and no board run.
- The late feature is not really late in this design, and no model here takes the message's own price.
- The speculation counts use one synthetic data set; the SVG diagrams were checked as generated text, not rendered.
