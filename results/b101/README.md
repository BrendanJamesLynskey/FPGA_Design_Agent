# Brief 101: Yosys + ABC into Vivado, and eqy equivalence (results)

Every number here is from a record in this directory; the method and its limits are in
[docs/oss_synth_eqy.md](../../docs/oss_synth_eqy.md). Vivado 2026.1, out of context, one thread, one clock, placed and routed;
Yosys and eqy from OSS CAD Suite 20261112. Vivado's timing analysis is the referee for every period, latency and LUT-level figure;
Yosys's own cell counts are recorded in each arm's `yosys` entry and are not used for any comparison.

| File | What |
|---|---|
| [summary.md](summary.md), [summary.json](summary.json) | every block x arm x part: closed period, Fmax, latency (two clocks), LUT levels, LUT/FF/CARRY, seed spread, run times |
| [a7/](a7), [k26/](k26) | one JSON per arm (every clock-search pass, perturbation points, the Yosys script text) and the reports of the closing run |
| [eqy/summary.md](eqy/summary.md), [eqy/](eqy) | one JSON per eqy proof: Yosys netlists, Vivado netlists, planted faults |

Rebuild the tables without any tool: `python3 -m flow.oss_compare.run --table` and `python3 -m flow.oss_compare.eqy_run --table`.

## Headline: best Yosys arm against Vivado, same RTL and wrapper

The three Vivado directives (Default, PerformanceOptimized, PerformanceOptimized with retiming) produced the same numbers on each block
and part (the logs confirm each directive was applied); the wrapper already registers both ends, so retiming has nothing to move.
Latency is two clocks at the arm's own closed period. "Spread" is the range of the achievable period over three runs (the closed clock,
+0.01 ns and +0.02 ns); see the docs for what that does and does not measure.

| part | block | Vivado (Default = PerformanceOptimized = with retiming) | Yosys, best of three scripts | Yosys against Vivado |
|---|---|---|---|---|
| xc7a100t | adder_tree8 | 5.35 ns (187 MHz), latency 10.7 ns, 7 LUT levels, 63 LUT, 75 FF, 9 CARRY; spread 0.243 ns | ys_abc_d: 4.30 ns (233 MHz), latency 8.6 ns, 6 LUT levels, 75 LUT, 75 FF, 3 CARRY; spread 0.148 ns | -20% period (Yosys faster) |
| xc7a100t | crc64_rx | 3.30 ns (303 MHz), latency 6.6 ns, 3 LUT levels, 208 LUT, 97 FF, 0 CARRY; spread 0.047 ns | ys_abc9: 10.60 ns (94 MHz), latency 21.2 ns, 10 LUT levels, 244 LUT, 97 FF, 0 CARRY; spread 0.341 ns | +221% period (Vivado faster) |
| xc7a100t | lg_small_comb | 12.05 ns (83 MHz), latency 24.1 ns, 14 LUT levels, 259 LUT, 42 FF, 9 CARRY; spread 0.207 ns | ys_abc9_dff: 13.30 ns (75 MHz), latency 26.6 ns, 14 LUT levels, 382 LUT, 42 FF, 13 CARRY; spread 0.236 ns | +10% period (Vivado faster) |
| xc7a100t | pcs_tx | 9.50 ns (105 MHz), latency 19.0 ns, 9 LUT levels, 624 LUT, 264 FF, 0 CARRY; spread 0.253 ns | ys_abc_d: 10.00 ns (100 MHz), latency 20.0 ns, 16 LUT levels, 867 LUT, 264 FF, 2 CARRY; spread 0.224 ns | +5% period (Vivado faster) |
| K26 | adder_tree8 | 2.05 ns (488 MHz), latency 4.1 ns, 6 LUT levels, 57 LUT, 75 FF, 6 CARRY; spread 0.063 ns | ys_abc9: 1.65 ns (606 MHz), latency 3.3 ns, 6 LUT levels, 70 LUT, 75 FF, 2 CARRY; spread 0.035 ns | -20% period (Yosys faster) |
| K26 | crc64_rx | 1.30 ns (769 MHz; **1.38 ns, 725 MHz at the BUFG limit**), latency 2.6 ns (2.76 ns at the limit), 2 LUT levels, 172 LUT, 97 FF, 0 CARRY; spread 0.045 ns | ys_abc9: 3.50 ns (286 MHz), latency 7.0 ns, 9 LUT levels, 300 LUT, 97 FF, 0 CARRY; spread 0.035 ns | +169% period (+154% at the BUFG limit; Vivado faster) |
| K26 | lg_small_comb | 4.50 ns (222 MHz), latency 9.0 ns, 13 LUT levels, 325 LUT, 42 FF, 1 CARRY; spread 0.117 ns | ys_abc9_dff: 4.75 ns (210 MHz), latency 9.5 ns, 15 LUT levels, 407 LUT, 42 FF, 10 CARRY; spread 0.091 ns | +6% period (Vivado faster) |
| K26 | pcs_tx | 3.25 ns (308 MHz), latency 6.5 ns, 9 LUT levels, 753 LUT, 264 FF, 0 CARRY; spread 0.014 ns | ys_abc9: 3.35 ns (298 MHz), latency 6.7 ns, 11 LUT levels, 731 LUT, 264 FF, 1 CARRY; spread 0.06 ns | +3% period (Vivado faster) |
On xc7a100t, `pcs_tx` with `ys_abc9` did not close in ten passes (the nearest failing periods are 10.1 to 10.85 ns); `ys_abc9_dff` closed at
11.1 ns and `ys_abc_d` at 10.0 ns (the row above).

## eqy

* RTL against the Yosys netlists: 24 of 24 proved (4 blocks x 3 scripts x 2 families); `pcs_tx` needs the whole-design proof (`group`).
* RTL against the Vivado post-synthesis funcsim netlists (Default arm only): 1 of 8 proved (`lg_small_comb`, xc7a100t, 385 s); the
  other 7 did not finish within 15 min (adder tree and CRC: 15 min limit; `pcs_tx`: 45 and 50 min over the whole `auto` sequence) and are **unproved**, not passed.
* Planted faults on the Yosys `abc9` UltraScale+ netlists: 25 caught, 1 not (`pcs_tx` `lut_init_0`, which `abc pdr` proves
  equivalent: the flipped INIT bit is on an input combination no reachable state produces), 3 not plantable (`N/A`), and all 4 clean netlists pass.

## Records

Per-arm JSON in [a7/](a7) and [k26/](k26) (`<block>__<arm>.json`, with every clock-search pass and the Yosys commands), the closing runs'
reports under `reports/`, and per-proof JSON in [eqy/](eqy) (`yosys__`, `vivado__`, `fault__` prefixes, with the eqy and Yosys versions).
The 2.00 ns first pass of the EDIF arms on both parts also holds earlier "Project 1-68" errors from an import bug fixed during the work
(`link_design -top` fails on an EDIF read in non-project mode); the passes list shows them with `status: error` and they are ignored by the search.

## Reproduce

The commands below rebuild every table and proof. The Vivado runs take hours and need a heavy-job slot; the eqy runs need only the OSS CAD Suite.

```
python3 -m flow.oss_compare.run --part xck26-sfvc784-2LV-c --perturb      # then --part xc7a100tcsg324-1 (Vivado 2026.1; hours)
python3 -m flow.oss_compare.run --table
python3 -m flow.oss_compare.netlist --part <part>                           # Vivado funcsim netlists
python3 -m flow.oss_compare.eqy_run --yosys | --faults | --vivado build/b101/netlists/<part>/<block>__viv_default --timeout 900
python3 -m flow.oss_compare.eqy_run --table
```

## Known gaps and limits

* Out of context only, one clock, wrapper registers at both ends; no full design and no board.
* Four small blocks; adder_tree8 replaced a 16 x 12-bit tree that eqy could not prove within an hour.
* Vivado has no placer seed: the "spread" is over three clock constraints (closed, +0.01, +0.02 ns). For the Vivado RTL arms the constraint
  reaches synthesis, for the EDIF arms only placement, so the spreads are not like for like.
* Closed periods are points on a 0.05 ns grid, not bounds. xc7a100t `pcs_tx` `ys_abc9` never closed (ten passes).
* Only the Vivado Default netlists went through eqy (the other two directives gave identical timing, so the netlists are probably the same,
  which was not checked). 7 of 8 did not finish: a SAT or PDR proof of XOR networks and restructured adders is the limit, not a finding of a difference.
* The brief 100 (RapidWright) netlist route is documented, not exercised.

## Change log

- 2026-11-24 (brief 201): the runs are out of context, with no clock buffer; on the K26 (-2LV) a BUFGCE limits a real clock to 725.2 MHz (Min Period 1.379 ns, [flow/fmax_cap.py](../../flow/fmax_cap.py), [results/201_fmax_cap](../201_fmax_cap/README.md)). The three K26 `crc64_rx` Vivado arms closed at 1.30 ns (769.2 MHz), above it; `summary.json` and `summary.md` now carry `fmax_capped_mhz` (725.2), `fmax_bound`, `fmax_clock_buffer_mhz` and `latency_capped_ns` (2.758 against 2.6) beside the raw closed-clock figures, which are unchanged in the per-arm records. The K26 crc64_rx period ratio of Yosys `ys_abc9` (3.50 ns) to Vivado becomes +154 % at the limit instead of +169 %; the direction (Vivado faster) does not change. No other arm, and no Artix-7 arm (464 MHz limit, highest 303 MHz), is affected.
