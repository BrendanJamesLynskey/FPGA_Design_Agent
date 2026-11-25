# Brief 178d: are the tournament gains real? Seed repeats (2026-11-24)

Vivado 2026.1, out of context, place and route re-run from the stored 178b synthesis checkpoints. 43 runs, all completed (14335 s of Vivado run time in total, summed from `records/`).

## Method

* **Mechanism.** Vivado 2026.1 has no placer or router seed that `report_param` lists, and a search of the `lib/lnx64.o` libraries for `*seed*` parameter names found none
  for place, route, opt or phys_opt (only `place.GPSeedRectAspectRatio`, a shape setting, and `route.ilpNetGenSeed`, not documented and not tried). So the perturbation is the fallback
  the brief names: the clock period is overridden after `open_checkpoint` with `create_clock -period P -name clk [get_ports clk]`, P = nominal x 0.99, x 1.01, x 1.02 (three repeats).
  An identical rerun is deterministic (check: the adder winner rerun at the nominal period gave -0.129 ns again, the same as the stored run), so the period change is the only source of variation here.
* **Metric.** WNS referred to the nominal period: `WNS_nominal = WNS + (nominal - P)` (equivalent to comparing the achieved period `P - WNS`). The raw WNS and period are kept per sample.
* **Samples per setting.** The stored 178b run (nominal, repeat 0) plus the three repeats: n = 4. "Fresh" statistics use only the three repeats.
* **Settings.** (a) default synthesis + default implementation; (b) the 178b winner (rank 1 of the implementation tournament); (c) the best AMD `-strategy` set among the stored candidates, skipped when it is the winner (adder: the winner is that set).
  Each setting uses its own synthesis checkpoint (`default`, `altroute`, `retime`). 14 settings x 3 + 1 determinism check = 43 runs, one at a time through `take_heavy_slot.sh`, `MemoryMax=5G`, one thread, declared peak 4G.

## Results (WNS in ns, referred to the nominal period; n = 4: stored run + 3 repeats)

| design (clock) | setting | mean | min..max | spread | fresh 3 mean |
|---|---|---|---|---|---|
| adder csel w64 (A7, 5.0) | default/default | -0.475 | -0.542..-0.402 | 0.140 | -0.491 |
| | winner (altroute + NetDelay_high, = best AMD set) | -0.234 | -0.402..-0.129 | 0.273 | -0.268 |
| divider w16 (K26, 1.4) | default/default | -0.032 | -0.039..-0.018 | 0.021 | -0.032 |
| | winner (altroute + aggressive) | +0.011 | +0.002..+0.032 | 0.030 | +0.012 |
| | best AMD (NetDelay_high) | -0.007 | -0.055..+0.017 | 0.072 | -0.015 |
| isqrt w32 (K26, 1.4) | default/default | -0.027 | -0.084..+0.003 | 0.087 | -0.037 |
| | winner (altroute + aggressive) | +0.001 | -0.015..+0.016 | 0.031 | -0.004 |
| | best AMD (RefinePlacement) | -0.002 | -0.015..+0.016 | 0.031 | -0.008 |
| lzc w32 (K26, 1.4) | default/default | -0.457 | -0.489..-0.367 | 0.122 | -0.447 |
| | winner (retime + RefinePlacement) | +0.151 | +0.122..+0.181 | 0.059 | +0.146 |
| | best AMD (retime + NetDelay_high) | +0.127 | +0.075..+0.196 | 0.121 | +0.103 |
| mac fabric (K26, 3.0) | default/default | -0.250 | -0.311..-0.161 | 0.150 | -0.280 |
| | winner (retime + congestion) | +0.061 | -0.033..+0.208 | 0.241 | +0.012 |
| | best AMD (retime + ExtraTimingOpt) | +0.068 | +0.007..+0.129 | 0.056 | +0.047 |

K26 rows are compared on WNS (no Fmax headline: the K26 clock buffer caps Fmax at 725.2 MHz, brief 199).

## Is the winner's gain larger than the spread?

| design | winner minus default (mean, n = 4) | fresh 3 only | winner's worst above default's best? | verdict |
|---|---|---|---|---|
| lzc | +0.608 | +0.593 | yes (+0.122 vs -0.367) | **real**, gain 5x the spread |
| mac | +0.311 | +0.292 | yes (-0.033 vs -0.161) | **real** (gain about equal to the winner's own spread 0.241, ranges separate) |
| divider | +0.043 | +0.044 | yes (+0.002 vs -0.018) | **real but small**: ranges separate by 0.020 ns; gain 0.043 is larger than both spreads (0.021, 0.030) |
| adder | +0.241 | +0.223 | no (-0.402 vs -0.402, tie) | **not shown**: mean gain is inside the winner's spread (0.273); the ranges touch |
| isqrt | +0.028 | +0.033 | no | **noise**: gain is below the default's spread (0.087) |

Versus the best AMD `-strategy` set (same synthesis): the winner's mean advantage is +0.018 (divider), +0.003 (isqrt), +0.024 (lzc), -0.007 (mac); the winner's worst never exceeds the AMD set's best. **No design shows our menu beating the best AMD set outside the noise.**
The single stored mac run (+0.208 against AMD's +0.129, which 178b called the one clear win) is the highest of its four samples; the three fresh repeats average +0.012 against AMD's +0.047, so that win was selection from about 20 noisy runs.

## Findings

* The gain of the tournament over default/default is real on lzc and mac (large) and detectable on divider (0.04 ns). It is not shown on the adder (still failing at 5.0 ns either way) and not present on isqrt.
* The winner is chosen as the best of about 20 runs, so the stored run is biased upward (the winner's stored run is its own maximum on 3 of 5 designs (adder, isqrt, mac)). Use the fresh-repeat mean for the claim: the gain shrinks by 0.02 to 0.05 ns when the stored run is dropped.
* Run-to-run noise under a 1 to 2 % clock change is 0.02 to 0.27 ns spread (4 samples), the largest on the adder and mac. Any single-run difference under about 0.1 ns on these blocks is not evidence.
* The "failing to meeting timing" claims: lzc is robust (all four winner samples positive, all four default negative); divider is positive for the winner in all four, negative for default in all four; mac's winner is positive in 3 of 4 samples (fresh +0.007 to +0.037 at nominal-referred WNS: +0.037, +0.032, -0.033), so on mac the "meets timing" claim holds only marginally.
* The cheaper conclusion stands: the AMD strategy set is statistically as good as our menu on all five.

## Records

* `summary.json`: per design and setting, every sample (factor, period, raw WNS, nominal-referred WNS, LUT, FF, source) and the verdict fields.
* `records/<design>/<setting>/p<factor>.json`: one record per run (status, WNS/TNS/WHS, LUT, FF, runtime).
* The stored 178b runs are read from `results/178_tournament/runs/` of the 178 worktree: that directory is excluded by the repository's `runs/` ignore rule, so it is not in PR #304 (follow-up for the planner).

## Reproduce

Needs Vivado 2026.1, the 178b synthesis checkpoints (`build/tournament/<design>/synth/<id>/post_synth.dcp`, 48 to 152 KB each, regenerated by `tools/qor/run_178_eval.sh`) and a heavy slot per run:
`python3 tools/qor/run_178d_seeds.py run --src <178 worktree>` (resumable; about 4.5 hours wall including slot waits, 14335 s of Vivado run time), then `python3 tools/qor/run_178d_seeds.py score`.
Scoring alone needs no Vivado but needs `build/seeds/*/*/*/record.json` or the committed `records/` copied back.

## Known gaps and limits

* The perturbation is a clock-period change of 1 to 2 %, not a placer seed, so the spread it measures is the sensitivity to a small constraint change, which may differ from seed sensitivity. No documented seed exists in 2026.1.
* n = 4 per setting (3 repeats and the stored run); range comparisons with so few samples are indicative, not a significance test.
* Five small out-of-context arithmetic blocks (one 7-series, four K26); no full design.
* The best AMD set was chosen from the single stored runs (also selected as best of its group), so it carries the same upward bias as the winner.
* Triage thresholds and the two-step variant (default vs retime, then strategies) are still unmeasured.
