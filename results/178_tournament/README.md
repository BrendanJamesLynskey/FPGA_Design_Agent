# Brief 178: candidate tournaments, results so far

Status (2026-11-24, brief 178b): part 1, the tool, triage, tests, docs and the Vivado evaluation (five designs) are done. Numbers below are from
`runs/<design>/{synth,impl_top2,impl_base}.json` and `gain_summary.json` (Vivado 2026.1, out of context, one run per candidate, no repeats).

## Part 1: does the early ranking predict the routed ranking? (49 full-design rows with post-synthesis, post-place and routed WNS)

Reproduce: `python3 tools/qor/rank_existing.py` (writes `part1_existing_data.json`).

* **Pooled over all 49 rows:** Spearman rho 0.94 (post-synthesis WNS vs routed WNS), 0.98 (post-place vs routed). This is misleading for the tournament question:
  the rows are different designs, and the spread between designs (WNS from -0.2 to +80 ns) dominates.
* **Within one design (the candidate-set case), designs with at least 3 rows** (the rows are variants: boards, constraints, incremental modes, rebuilds):

| design (n) | rho syn vs routed | rho place vs routed | best by syn = best routed | best by place = best routed | routed WNS spread (ns) |
|---|---|---|---|---|---|
| d20_adc_capture_top (5) | 0.90 | 0.82 | yes | yes | 3.47 |
| fcs_top (3) | 0.87 | 0.50 | yes | yes | 0.87 |
| d20_slow_fsm_ramp_top (3) | 0.87 | 0.50 | yes | yes | 68.5 (clock changes) |
| b95_smoke_top (3, different boards) | 0.87 | 1.00 | yes | yes | 73.8 (clock changes) |
| c13_nexys_harris_vga_top (5) | -0.21 | 0.40 | **no** | yes | 0.126 |
| kr260_10g_top (5) | **-0.53** | 0.90 | **no** | yes | 0.283 |

  Where the candidates differ by a lot (a different clock or board), the early WNS ranks them correctly. Where they are close (the two designs under real timing
  pressure, routed spread 0.13 and 0.28 ns), **post-synthesis WNS does not predict the routed order** (rho -0.21 and -0.53, best-by-synthesis was not best routed),
  and post-place WNS does (best-by-place was best routed in 6 of 6 designs). Small n (3 to 5 per design): this is direction, not a statistic.
* **The arith points (brief 160/166) cannot answer this:** they carry no post-synthesis timing (the runs did not write one) and their variants are different
  architectures, not options on one design; only area is available. New runs are what answers it (driver below).

**Consequence for the tournament design (stated from these numbers, to be confirmed by the new runs):** when candidates are close, the synthesis stage cannot pick
the routed winner alone, so a synthesis tournament must carry its top k (default 2) into place and route, and the score must keep a 0.05 ns bucket
so noise-level differences are decided by area and then the default. Post-place is a better early signal than post-synthesis.

## What is built (no Vivado needed to test)

`flow/tournament.py` (plan, run, score, triage, strategies), `flow/tests/test_178_tournament.py` (11 pass), `docs/tournament.md`, specs for five arith points
near their clock limit (`specs/`, made by `tools/qor/make_tournament_specs.py`), the evaluation driver `tools/qor/run_178_eval.sh`.

## Evaluation results (brief 178b, 2026-11-23 to 24)

Method: synthesis tournament (16 options) per design; the top two synthesis candidates each go through 10 place-and-route sets (6 directive sets and 4 AMD
`-strategy` sets, read from Vivado by the probe); baseline = default synthesis then default place and route. Routed WNS in ns, single run each.

| design (part, clock) | baseline routed WNS | tournament winner (routed WNS) | best of all 20 | best AMD strategy | best synthesis, default P&R |
|---|---|---|---|---|---|
| adder csel w64 (xc7a100t, 5.0 ns) | -0.426 | altroute + Performance_NetDelay_high (-0.129) | -0.129 | -0.129 | -0.524 |
| divider w16 (K26, 1.4 ns) | -0.031 | altroute + aggressive (+0.009) | +0.017 | +0.017 | -0.003 |
| isqrt w32 (K26, 1.4 ns) | +0.002 | altroute + aggressive (+0.016) | +0.016 | +0.016 | -0.014 |
| lzc w32 (K26, 1.4 ns) | -0.486 | retime + Performance_RefinePlacement (+0.165) | +0.196 | +0.196 | +0.119 |
| mac fabric (K26, 3.0 ns) | -0.161 | retime + congestion (+0.208) | +0.208 | +0.129 | +0.057 |

* **Gain over the default flow:** 0.03 to 0.69 ns of routed WNS. Three designs went from failing to meeting timing (divider, lzc, mac); the adder improved by 0.30 ns
  and still fails at 5.0 ns; isqrt met timing either way (+0.002 to +0.016, inside run noise). Single runs, no seed repeats: differences under about 0.03 ns are not shown to be real.
* **Against AMD's own strategies:** the best AMD `-strategy` equalled the best result on 4 of 5 designs (and the tournament's implementation menu includes them); the mac design
  was the one clear win (+0.208 versus +0.129, from the congestion directive set). Nothing here shows our menu beating the AMD sets by a margin.
* **Where the gain came from:** on lzc and mac most of it is the synthesis choice (`retime`: +0.119 and +0.057 with default P&R, versus -0.486 and -0.161 baseline), the rest is place and route.
  `retime` costs flip-flops (mac 116 to 197, lzc 112 to 137). On the adder the synthesis rank was wrong for default place and route (altroute -0.628 against area_high -0.524, though altroute won once the best P&R set was applied), and the best P&R set differed per design, which agrees with part 1.
* **Carrying the top two:** on 4 of 5 designs the two best synthesis candidates were identical netlists (same LUT, FF and WNS: altroute = carry, retime = perf_retime), so the second
  slot added nothing. Only the adder's two differed (altroute -0.129 against area_high, which was worse). The top-k step should pick the top two *distinct* results; the driver now picks them by distinct (WNS, LUT, FF) (178b follow-up commit; not re-run).
* **Cost:** synthesis 1160 to 1632 CPU-s per design (16 runs); place and route 6056 to 7814 CPU-s (20 runs) against 76 to 236 CPU-s for the baseline: about 30 to 90 times the CPU of one default run.
  Wall time (3500 s synthesis, 8700 to 21900 s place and route) includes waiting for slots behind other jobs, so it is not a speed measurement.
* **Winner choice:** the score's 0.05 ns bucket plus area tie-break picked a smaller netlist over the highest WNS on divider (+0.009 against +0.017) and lzc (+0.165 against +0.196). Intended, and documented.
* **Not measured:** seed or run-to-run noise, triage thresholds against these outcomes, a full design (needs the implementation stage only).

## What 178b found and fixed

* Four of the five original tournaments recorded no winner because every synthesis child was killed at the 2 GiB cap: UltraScale+ synthesis reached about 3.07 GB (the Vivado-reported
  peak in the logs). The tool then wrote an all-"not run" record that the driver treated as finished. Now K26 synthesis is declared at 4 GiB (one child at a time, not light class),
  a stage in which nothing completes writes `tournament_failed.txt` and raises, and the driver feeds place and route the top two ids.
* The memory gate (free memory must cover running peaks plus 8 GiB) cannot admit a child while other jobs hold memory; with nothing running, the driver now falls back to one child alone
  after 120 s when MemAvailable covers the child's peak plus 1 GiB. The log line "gate refused ... running one child alone" in `build/178b_eval.log` is that fallback working (it appears for every 4 GiB child, by design).
* The strategy probe stored only IS_ENABLED flags, never the directives, so all 33 AMD strategies were empty and identical to default. It now reads each step's directive.

## Scoring (brief 178c, 2026-11-24, from the stored reports only, no new Vivado)

Fmax = 1000 / (clock period - routed WNS), out of context. **K26 caps at 725.2 MHz** (clock buffer BUFGCE minimum period 1.379 ns at -2LV, brief 199), so K26 rows
are compared on WNS; an Fmax above the cap is shown as "over cap" and must not be quoted.

| design | clock | baseline WNS / Fmax | winner WNS / Fmax | gain WNS | CPU s: tournament vs baseline | wall s (incl. slot waits) |
|---|---|---|---|---|---|---|
| adder csel w64 (A7) | 5.0 ns | -0.426 / 184.3 MHz | -0.129 / 195.0 MHz | +0.297 | 8974 vs 76 (118x) | 10967 |
| divider w16 (K26) | 1.4 ns | -0.031 / 698.8 MHz | +0.009 / 718.9 MHz (cap 725.2) | +0.040 | 7638 vs 177 (43x) | 12292 |
| isqrt w32 (K26) | 1.4 ns | +0.002 / 715.3 MHz | +0.016 / 722.5 MHz (cap 725.2) | +0.014 (inside noise) | 8277 vs 194 (43x) | 25428 |
| lzc w32 (K26) | 1.4 ns | -0.486 / 530.2 MHz | +0.165 / over cap | +0.651 (WNS only) | 8247 vs 218 (38x) | 12947 |
| mac fabric (K26) | 3.0 ns | -0.161 / 316.4 MHz | +0.208 / 358.2 MHz | +0.369 | 8195 vs 236 (35x) | 12872 |

CPU = synthesis (16 runs) + place and route (20 runs), summed per-run runtimes from `runs/*/synth.json`, `impl_top2.json`, `impl_base.json`; wall includes waiting for other jobs' slots.
(The 178b text above quotes "30 to 90 times" for the P&R part alone; the totals above are per whole tournament.) Single runs, no repeats: gains under ~0.03 ns are not shown to be real.

**Did the synthesis ranking predict the routed winner?** Only partly testable: only the top two synthesis candidates went to place and route, and on 4 of 5 designs they were
identical netlists, so those four give no ranking information. Findings:
* Adder (the one design with two different candidates): synthesis ranked altroute (-0.519) above area_high (-0.893). With *default* P&R the order reversed (-0.628 vs -0.524); with the best
  P&R set altroute won (-0.129 vs -0.306). So the synthesis rank-1 was the routed winner only after P&R was also searched; as a prediction for a fixed flow it was wrong. This agrees with part 1 (close candidates: synthesis ranking unreliable).
* On the other four the rank-1 synthesis result (retime, or altroute = carry) was the routed winner, but nothing else was routed, so "rank 1 won" is not evidence that the ranking works.
  What is measured is that the default synthesis ranked 3rd to 5th of 16 on every design (`default_rank` 3, 5, 3, 4, 5), i.e. the default synthesis was never the best by its own post-synthesis WNS.
* `default_rank` is null in the impl records because the reference id there is `default/default`, not `default` (a bug in the lookup, fixed in 178c; stored records are unchanged). For the baseline file (one candidate) it is trivially 1.

**Recommendation for the agent:** a tournament is worth running only when the design is failing or near zero slack at its target (three of five here went fail to pass, lzc and mac by large margins);
it costs 35 to 120 times the CPU of one default run, so it is opt-in after triage, never default. Most of the gain on lzc and mac is the `retime` synthesis option; a cheaper
two-step (default vs `retime` synthesis, then the AMD `-strategy` sets and the congestion set on the better one) captures that gain at a fraction of the cost, but that cheaper variant is **not measured** here. No gain is claimed beyond these five designs; K26 Fmax values are capped, so quote WNS.

## Memory gate bug (brief 178c)

The log line `MemAvailable 99.0 G` was not a fallback: `run()` called `run_children(..., avail=lambda: 99.0)` for place and route, a hard-coded stub (the intent: one Vivado at a time inside the held slot, memory
is policed by the slot). The 4 GiB P&R child also failed the light-class gate (declared peak above 2 GiB), so every P&R run logged "gate refused" and then ran via the 120 s fallback (about 2 minutes of idle slot per run, 20+ runs per design), with a
fake reading. Fix: single-child stages (`max_children == 1`: K26 synthesis, all P&R) use the real `MemAvailable` and admit at once when it covers the peak plus 1 GiB, with no light-class limit and no stub; the one-hour error still fires if memory never frees.
Test `test_single_child_stage_uses_the_real_memory_reading_and_no_light_gate` (14 tests pass in total). The multi-child light class path is unchanged.
