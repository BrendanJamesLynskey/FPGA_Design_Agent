# Brief 178e: the cheap two-step tournament (2026-11-24)

Vivado 2026.1, out of context, five small blocks and clocks as in 178d. Question: can synthesis (default against retiming), then AMD's `Performance_*` implementation
sets on the better netlist, reach the full tournament's result for a fraction of the CPU? Numbers below come from `summary.json`, which `python3 tools/qor/run_178e_two_step.py score`
builds from `records/`, `validate/`, `stored_178b/` and the 178d `seeds/summary.json`.

## Answer (nulls first)

* **Not shown better than the full tournament, and not shown worse.** On all five blocks the two-step result is inside the 178d run-to-run noise of the tournament winner (differences -0.198 to +0.007 ns on 4-sample means).
  On the adder the noise floor is 0.273 ns, so "inside noise" is a weak statement there: neither flow meets timing and neither beats default beyond noise.
* **The two-step does not reproduce the divider's small 178d gain.** Divider winner +0.011 against two-step pick -0.010 (4-sample means; default -0.032): the pick is inside noise of both.
* **Where the tournament gain was large (lzc, mac), two-step gets it from step 1 alone.** Step 1 picks retime on both; retime with the default implementation gives +0.119 (lzc) and +0.057 (mac) against the winner means +0.151 and +0.061 (noise floors 0.122, 0.241).
* **Cheapest rule that matches the tournament winner within noise on all 5: two-step, walk the sets cheapest first, stop at the first with WNS >= 0.** It stops at the default implementation on lzc, mac and isqrt, at `WLBlockPlacementFanoutOpt` on the divider, and runs all 15 on the adder (nothing passes).
  CPU 6047 s against 42232 s for the five full tournaments (14.3 percent); without the adder 5.8 percent (4.5 to 9.7 percent per design; the adder 45.4 percent).
  "Default implementation only" is cheaper (1775 s, 4.2 percent) but fails the divider (WNS -0.031 against the winner mean +0.011, noise floor 0.030).
* **The stop is at WNS >= 0 on a single run.** Divider and isqrt pass by 0.002 to 0.005 ns, which is inside their noise (spreads 0.02 to 0.09 ns): "met timing" there means "at the boundary". The divider's stop-set was not repeated.

## Method

* **Step 1 (2 runs, reused).** The stored 178b synthesis results for `default` and `retime` (`stored_178b/<design>/synth.json`). `flow.tournament.two_step_pick` ranks them with the tournament's own score (0.05 ns WNS bucket, then LUT+FF, then logic levels, then menu order).
  Result: default on adder, divider, isqrt (retime gave the same netlist figures: identical WNS, LUT, FF); retime on lzc and mac.
  The winners of the full tournament on adder, divider and isqrt used `altroute` synthesis, which the two-step does not try.
* **Step 2 (15 sets).** `default` and the 14 `Performance_*` sets of the measured strategy file `vendor_strategies.json` (the four SLR-only sets, `BalanceSLLs`, `BalanceSLRs`, `HighUtilSLRs`, `SpreadSLLs`, are left out: all five parts are single-die).
  On the 7-series adder, Vivado logs "Directive Auto is not supported for 7-series devices. Switching to Explore mode" for the placer in `Auto_1/2/3`; their phys_opt and route directives still differ from `Explore`, and the results differ.
* **Reuse.** 13 of the 75 step-2 results were taken from the stored 178b runs (same netlist, same Tcl, same set: `source` = `178b stored` in `summary.json`; 178d showed an identical rerun reproduces the WNS). 62 were run now.
  Place and route was run one set at a time, one Vivado thread, `systemd-run MemoryMax=5G`, declared `peak 4G`, two workers at once where `take_heavy_slot.sh` admitted a second Vivado.
* **Noise.** The 178d clock-period perturbation (x0.99, x1.01, x1.02; Vivado 2026.1 has no placer seed) is the only noise measure. Noise floor per design = the largest of the 178d spreads of the tournament winner, of default/default and of the two-step pick.
  For rules scored on one run, the larger of the winner's and default's 178d spread. A difference inside it is not called real, in either direction.
* **Validation of the pick (9 runs).** The rule "run all 15, take the best by the tool's score" is selected from single runs, so it is biased upward like the tournament winner. Its pick was repeated three times at the perturbed clocks (`validate/`) on adder, divider, isqrt.
  On lzc and mac the pick is the same netlist and set as a 178d setting (winner, best AMD), so its 178d samples are used.
* **Cost.** CPU = summed Vivado run times (`runtime_s`): step 1 is the stored default and retime synthesis times, step 2 the sum of the sets run (stored ones at their stored time). Wall time is not reported: runs waited for slots behind other jobs.

## Results (WNS in ns referred to the nominal period; 4 samples: single run plus 3 perturbed repeats)

| design | step 1 pick | tournament winner (mean, spread) | default/default (mean, spread) | two-step, best of 15 by rank (mean, spread; source) | pick minus winner | noise floor |
|---|---|---|---|---|---|---|
| adder csel w64 (A7, 5.0 ns) | default | altroute + NetDelay_high (-0.234, 0.273) | (-0.475, 0.140) | WLBlockPlacementFanoutOpt (-0.432, 0.235; 178e validation) | -0.198 | 0.273 |
| divider w16 (K26, 1.4 ns) | default | altroute + aggressive (+0.011, 0.030) | (-0.032, 0.021) | ExtraTimingOpt (-0.010, 0.053; 178e validation) | -0.021 | 0.053 |
| isqrt w32 (K26, 1.4 ns) | default | altroute + aggressive (+0.001, 0.031) | (-0.027, 0.087) | Auto_1 (+0.006, 0.064; 178e validation) | +0.005 | 0.087 |
| lzc w32 (K26, 1.4 ns) | retime | retime + RefinePlacement (+0.151, 0.059) | (-0.457, 0.122) | RefinePlacement (+0.151, 0.059; 178d winner) | +0.000 | 0.122 |
| mac fabric (K26, 3.0 ns) | retime | retime + congestion (+0.061, 0.241) | (-0.250, 0.150) | ExtraTimingOpt (+0.068, 0.122; 178d best AMD) | +0.007 | 0.241 |

Gain of the two-step pick over default/default (means): adder +0.043, divider +0.022, isqrt +0.033 (all inside noise), lzc +0.608 and mac +0.318 (beyond noise). The same measure for the tournament winner (178d) is +0.241, +0.043, +0.028, +0.608, +0.311.
So the two-step reproduces the large gains; it does not reproduce the adder's (itself not shown) or the divider's small gain. K26 rows are compared on WNS (Fmax capped at 725.2 MHz, brief 199).

### Rules, scored on single runs (share = CPU of step 1 + step 2 over the full tournament's CPU for that design)

| design | rule | stops at | WNS | CPU s | share | inside noise of winner | meets 0 |
|---|---|---|---|---|---|---|---|
| adder | best of all 15 | WLBlockPlacementFanoutOpt | -0.316 | 4113 | 45.4% | yes (weak: noise 0.273) | no |
| adder | default implementation only | default | -0.426 | 230 | 2.5% | yes (weak) | no |
| adder | first WNS>=0, cheapest first | none passes; best WLBlockPlacement | -0.309 | 4113 | 45.4% | yes (weak) | no |
| divider | best of all 15 | ExtraTimingOpt | +0.013 | 4084 | 52.3% | yes | yes |
| divider | default implementation only | default | -0.031 | 372 | 4.8% | **no** | no |
| divider | first WNS>=0, cheapest first | WLBlockPlacementFanoutOpt | +0.005 | 761 | 9.7% | yes | yes |
| divider | first WNS>=0, alphabetical | ExplorePostRoutePhysOpt | +0.005 | 2036 | 26.1% | yes | yes |
| isqrt | best of all 15 | Auto_1 | +0.003 | 3833 | 45.2% | yes | yes |
| isqrt | default only = first WNS>=0 (any order) | default | +0.002 | 394 | 4.7% | yes | yes |
| lzc | best of all 15 | RefinePlacement | +0.165 | 4167 | 49.2% | yes | yes |
| lzc | default only = first WNS>=0 (any order) | default | +0.119 | 378 | 4.5% | yes | yes |
| mac | best of all 15 | ExtraTimingOpt | +0.129 | 4261 | 50.5% | yes | yes |
| mac | default only = first WNS>=0 (any order) | default | +0.057 | 401 | 4.8% | yes | yes |

Totals over the five designs (CPU s; full tournaments 42232): best of all 15 = 20458 (48.4%); default implementation only = 1775 (4.2%); stop at first WNS >= 0, cheapest first = 6047 (14.3%).
"Inside noise of winner" means rule WNS >= winner mean minus the noise floor (one-sided: only a worse result counts). Full per-set results for every design are in `summary.json` (`rows`).

## Records

* `summary.json`: per design step 1 pick and cost, all 15 step-2 results (WNS, LUT, FF, run time, source), the pick's repeat statistics, the rule table and the 178d reference numbers.
* `records/<design>/<set>.json`: the 62 new place-and-route runs (status, WNS, TNS, WHS, LUT, FF, run time). `validate/<design>/p<factor>.json`: the 9 perturbed repeats of the pick.
* `stored_178b/<design>/{synth,impl_base,impl_top2}.json`: copies of the 178b records this work reuses (the originals sit under an ignored `runs/` directory and are not in the earlier PRs).
* Cost of this brief: 62 + 9 = 71 Vivado runs, 18472 s of run time.

## Reproduce

Needs Vivado 2026.1, the 178b synthesis checkpoints (`build/tournament/<design>/synth/{default,retime}/post_synth.dcp` in the 178 worktree) and a heavy slot per run:
`python3 tools/qor/run_178e_two_step.py plan`, then `... run [--src <178 worktree>]` (resumable, start two copies to use two slots), `... validate`, `... score` (no Vivado needed with the committed records).
The tool itself: `python3 -m flow.tournament run <spec.yaml> --mode two-step [--stop-at-pass]` (tests: `pytest flow/tests/test_178_tournament.py`, 17 pass).

## Known gaps and limits

* Five small out-of-context blocks (one 7-series, four K26); no full design. Nothing here shows the two-step on a design where the winner needs a synthesis option other than retiming: on adder, divider and isqrt the full tournament's winners came from `altroute` synthesis, which the two-step never tries.
* The noise measure is a 1 to 2 percent clock-period change, not a seed; n = 4; single runs for the rule comparisons. The adder's noise floor (0.273 ns) is larger than any difference between its settings.
* The cheapest-first walk order (`PERF_ORDER`) is the median run time over these five designs, fixed after seeing them. The stop rule was therefore also chosen with this data: it is not a held-out result.
* Divider and isqrt stop at WNS +0.002 to +0.005, inside noise; the divider's stopping set was not repeated.
* Step 1 selects by post-synthesis WNS, which 178 part 1 found unreliable between close candidates. Here the two candidates differed on only lzc and mac, and by a large margin.
* The tournament's winners are best of about 20 single runs (biased upward); the two-step pick is best of 15. Both were compared on repeat means, not on the stored runs.

## Recommendation for `flow/tournament.py`

When a tournament is run at all (still opt-in after triage; never a gate), run `--mode two-step --stop-at-pass` first: 4.5 to 10 percent of the full tournament's CPU on four of five blocks, same result within noise. Keep `--mode full` (the command-line default for now, as it alone tries our own synthesis and directive menus) for a design where the two-step ends below 0 and the extra CPU is wanted: on the adder it spent 45 percent of the full cost and learned nothing the full run did not. The planner decides whether to change the command-line default.
