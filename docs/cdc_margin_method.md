# Clock-crossing margins: one method for AMD and Altera

Brief 207, 2026-11-24. The owner asked: "Clock-crossing margins: can we develop our own method that combines the two?" Altera's
Design Recommendations suggest adding clock uncertainty of 10 to 15 % of the clock delay. AMD removes the sources of uncertainty and
bounds each crossing with `set_max_delay -datapath_only`, `set_bus_skew` and the XPM synchroniser constraints. This document is the
method we use instead of either. The measurements behind it are in [results/207_cdc_margin](../results/207_cdc_margin/README.md),
and the check that enforces it is `flow/cdc_margin.py` (check `cdc_margin`, gate `post_route_bus_skew_met`, rule HDL-CDC-03).

Each section keeps three things apart: what the vendor says (cited), what we measured (from `results.md`), and what we infer. The
house rule comes last and is built from all three.

## 1. What each vendor's crossing check guarantees (vendor text)

Tags: **B** = body text read; **S** = a search snippet only. Full table with all sources: [results/207_cdc_margin/README.md](../results/207_cdc_margin/README.md) section 1.

| | AMD (Vivado 2026.1) | Altera (Quartus Prime Standard 25.1std) |
|---|---|---|
| Latency bound | `set_max_delay -datapath_only`: the data path alone, no clock skew, the hold check becomes a false path (UG903 v2025.2 pp. 129-131, B). A clock group overrides it. | `set_max_delay` includes clock skew; `set_net_delay -max` bounds the net only (Quartus help, B). `set_data_delay` (the datapath-only form) is Pro-only in practice: **25.1std accepts the command but its Timing Analyzer rejects it** (measured, section 2). |
| Skew bound | `set_bus_skew`: the spread of capture times across the bits of one constraint, **clock uncertainty excluded** (UG906 v2025.2 p. 163, B), slow and fast corners, optimised only by `route_design` (UG903 p. 143, B). Not in `report_timing_summary`: run `report_bus_skew`. | `set_max_skew`: data and clock arrival, micro-parameters, **clock uncertainty included**, on-die variation (Quartus help `set_max_skew`, B). **Cut by `set_false_path` and `set_clock_groups`**, not by `set_max_delay`/`set_min_delay`. Reported by `report_max_skew`. |
| Recommended values | Gray bus: max delay at the source period, bus skew at min(source, destination); handshake (up to 100 bits): both at destination period x the request's sync stages; single bit and reset synchronisers: a false path to stage 0, so **no latency bound** (the XPM constraint files shipped with 2026.1, B). Bus skew should be more than half the smaller period (UG903 p. 144, B). | Pro guide: keep crossings short with `set_net_delay` and put `set_max_skew` on buses (S). |
| Margin | No percentage for crossings. User uncertainty is for overconstraining a failing clock before routing: setup only, removed before routing, never above 0.5 ns (UG949 v2025.2 p. 283, B; TIMING-44/45, UG906 App. A, B). | Setup and hold uncertainty of 10 to 15 % of the clock delay, in "Optimizing Clocking Schemes" (Design Recommendations 18.1 body via brief 204's study, B; that its scope is timed paths between clock domains, not asynchronous crossings, is S). |
| MTBF | `report_synchronizer_mtbf`, UltraScale only; chains found only through `ASYNC_REG`; settling time = the positive slack after the stages; UNDEFINED on a violation, an unconstrained clock or a zero toggle rate (UG835 v2025.2 pp. 1528-1530, B). 7 series: take the default `DEST_SYNC_FF` (UG949 p. 144, B). | `report_metastability`: typical and worst-case design MTBF; per-chain MTBF needs "Forced If Asynchronous" identification; default toggle rate 12.5 % of the source clock (Quartus help, B). Values are capped at "Greater than 1 Billion" years. |

<!-- SECTION-MEASURED -->

<!-- SECTION-METHOD -->

<!-- SECTION-CHECKS -->

<!-- SECTION-LIMITS -->
