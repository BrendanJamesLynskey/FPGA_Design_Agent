# Brief 177: predicting the routed result from early stages

Everything here comes from `dataset.csv` (built by `tools/qor/build_dataset.py`, no Vivado run) and `evaluation.json`
(`python3 tools/qor/evaluate.py`; numpy only). Dates and tool versions are in the source records.

## Datasheet for `dataset.csv`

227 rows, one per (design point, clock) with an early-stage record and a routed outcome. `met` = routed setup WNS >= 0 and hold WNS >= 0.

| source | rows | met | where from | early-stage features present |
|---|---|---|---|---|
| `arith` | 164 | 61 | brief 160, 7 arithmetic functions, 2 parts (xc7a100t -1, xck26 -2LV), out of context, Vivado 2026.1; routed record JSON + `utilization_synth.rpt` of the same point | post-synthesis LUT, FF, SRL, carry cells, DSP, BRAM and capacity; the target clock. **No post-synthesis timing** (the runs did not write one) |
| `sweep` | 13 | 0 | brief 166 clock-sweep rounds that kept their own `utilization_synth.rpt`; each was run on purpose above the measured limit, so all fail | as `arith` |
| `gates` | 50 | 49 | `gates.json` files committed in this repo (briefs 20, 33, 54, 56a, 58a, 65a, 68, 95, 96, 102, 105A, 131, 140, 62b fixture), Vivado 2025.2 and 2026.1 | post-synthesis WNS/TNS/WHS and failing-endpoint fraction, utilization, post-place WNS/WHS; AMD `report_qor_assessment` score on 18 rows (2025.2 only) |

Biases and gaps, plainly:
- **The data is mostly small out-of-context arithmetic blocks** (at most a few thousand LUTs). Only 50 rows are full designs, and 49 of those passed: one routed failure (a closure fixture) is too few to fit or score anything. A predictor for full designs cannot be trained from what exists.
- **The agent-run builds of 82P2 to 82P7 contribute no rows.** Their final `build/base/gates.json` holds no timing: the stages did not reach Vivado (cap refusals, cached builds), so there is no early-and-routed pair. The 96/97/126/127 branches add no new committed `gates.json` beyond b96's two.
- The 164 arith points are 22 points of 7 functions, one run each, at clocks chosen by the build files, so the pass rate (37 %) says more about those clock choices than about the designs.
- Rows are not independent: points of one function share structure. All cross-validation here leaves one **function** out.
- 2025.2 and 2026.1 rows are both present; the AMD score exists only for 2025.2 (`report_qor_assessment` is refused on 2026.1 under the Basic licence, Implflow 47-29, recorded in each 2026.1 `gates.json`).

## Part 2: AMD's predictor

- `report_qor_assessment` cannot be run on the current release here (licence). It exists in 18 committed 2025.2 rows, so those are scored; `report_qor_suggestions` was not run anywhere (same tool family; not attempted).
- Post-synthesis score vs the routed outcome (18 rows, all small designs): score 3 on 8 rows, 4 on 5, 5 on 5, **every one met timing**. Post-route score is 5 on all 18 and all met. There is no routed failure among them, so AUC and the false-go rate are undefined; what the data shows is that a low post-synthesis score (3, "small chance of success") did not mean a failed route on small designs (8 of 8 met), the known predicted-congestion reading of brief 05g. Calibration against the 1 to 5 scale cannot be measured from these rows.
- A re-synthesis of a stratified sample to get post-synthesis timing, scores and logic levels is the missing piece: it needs a heavy slot and, for the score, a licence tier; queued in `vivado_later_queue.md` (not run in this brief).

## Part 3: our predictor (arith rows, leave-one-function-out, 164 rows)

Features: log LUT, FF, SRL, carry cells; DSP, BRAM; target frequency; is-K26. Table: `evaluation.json`.

| model | AUC | Brier (prior 0.234) |
|---|---|---|
| clock and part only | 0.748 | 0.198 |
| logistic regression, all features | 0.818 | 0.186 |
| boosted stumps, all features | 0.729 | 0.210 |

At p >= 0.8 the logistic model calls 39 builds "go": 7 of them fail (false-go rate 17.9 %), and it correctly holds back 96 of the 103 failing builds (93 %) while holding back 29 of 61 passing ones. At p >= 0.5 the false-go rate is 39.7 %. Within one function the ranking is good (per-function AUC 0.85 to 1.0) but the probability scale does not carry across functions (the 0.6 to 0.8 bin passes 29 %): calibration is the weak point. 13 of 13 sweep rows are predicted below 0.5 (mean pass probability 0.22).

What this is not: a gate. The model sees no timing from the synthesis run (the data has none), so it learns "big and fast target fails". The cheap generator of more rows is a synthesis-only run that writes `report_timing_summary` and the worst path's logic levels for every one of the 164 points plus about 30 full designs with a route, rows queued in `vivado_later_queue.md`.
