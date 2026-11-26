# Brief 231, item 8: does a Yosys logic-depth estimate rank designs like Vivado's synthesis-stage logic levels?

Method: `compare.py` takes the 55 UltraScale+ (xck26) cases of brief 142 that have a recorded Vivado synthesis-stage worst path (`results/b142/vivado/k26/viv_default/*/timing_worst_synth.rpt`, line "Logic Levels"), synthesises each with
`synth_xilinx -family xcup -flatten` through `flow/yosys_depth.py` (LUT and wide-mux cells count 1, CARRY4 0.5, CARRY8 1; registers, DSPs and RAMs end a path), and writes `depth.csv` and `summary.json`.
Yosys 0.70+385 (OSS CAD Suite, slang front end), Vivado 2026.1 records of brief 142. One run each; no place and route.

Result (`summary.json`): rank correlation (Spearman) 0.749 over 55 cases; 43 of 55 within 2 levels; the top quarter by Vivado levels (13 cases) and by Yosys depth share 8 cases.
Yosys is higher than Vivado in 22 cases and lower in 10 (mean +1.3 levels). The large overestimates are the cases brief 142 already explained: a DSP accumulate, pattern detect or pre-adder that Vivado absorbs and
Yosys leaves as a CARRY4 chain (`m14_mac`, `m15_patdet`, `m16_fir4`, `r05_mult_dsp35`), a LUT-array multiplier (`r07_mult_booth18`: 23.5 against 10) and the wide LUT networks `k01_crc64_rx` and `k02_pcs_tx` (cause not investigated).

## Known gaps and limits

* One part (xck26, UltraScale+) and one Yosys flow (`synth_xilinx -flatten`, the default abc9 mapper); 7-series (`xc7`) was not measured here, and the Vivado side is the unplaced synthesis-stage worst path, not the post-route path.
* Vivado's worst path and Yosys's longest chain may be different paths of one design; the comparison is of the maximum per design only.
* 38 of the 55 cases are one-feature micro cases from brief 142's list; 4 are K26 blocks and 11 arithmetic, so the sample is not a population of user designs.
* The estimate is advisory. Vivado's `report_design_analysis` and `report_timing` stay the sign-off; nothing in the flow or the agent calls `flow/yosys_depth.py` yet (a proposal in `reports/231_edwards_appendix_d_report.md`).

## Records

`depth.csv` (one row per case: Vivado levels, Yosys depth, the last 12 cells of the Yosys path), `summary.json`, `compare.py`; the inputs are the records of brief 142 (`results/b142`).

## Reproduce

Needs the OSS CAD Suite (Yosys with the slang plugin) at `~/.local/opt/oss-cad-suite` or `$FDA_OSS_CAD`:

```
python3 results/231_yosys_depth/compare.py     # about 6 minutes, two Yosys runs at a time, light (no slot needed)
```
