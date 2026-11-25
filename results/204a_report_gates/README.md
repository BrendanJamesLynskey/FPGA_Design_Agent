# Brief 204a: report-driven gates, measured on the recorded builds

The checks of [docs/report_gates.md](../../docs/report_gates.md) (`flow/report_gates.py`) run over the 65 recorded builds of this machine
(`build/bench/*/build/*`, `designs/*/build/*`, `runs/*/*/build/*`: 32 bench designs plus earlier agent runs and ILA variants; these
directories are git-ignored, the counts below are the record). `hits.json` has the per-build detail; `python3 tools/report_gate_hits.py
--repo <checkout with the builds> --session <session dir> --out results/204a_report_gates` reproduces it.

Reports the old builds never wrote (logic levels, clock utilisation, congestion, control sets) came from **one Vivado 2025.2 session**
that only opened the post-synthesis and post-route checkpoints of 32 designs (64 checkpoints) and wrote those reports (`flow/tests/data/204a/make/session.tcl`;
the Vivado version the checkpoints were made with; no synthesis, placement or routing was re-run). The IP-status report cannot be made from a
checkpoint, so `RPT-IP-01` has no recorded build to measure. A check whose report an old build lacks is "not measured" for that build.

## Records

`hits.json` (summary and per-build findings); fixtures in `flow/tests/data/204a/`.

| Check | Level | Builds measured | Builds with a hit | Hits | Hit builds that met timing | Gate (blocking) hits |
|---|---|---|---|---|---|---|
| RPT-LL-01 logic levels against the period | advisory | 39 | 8 | 8 | 4 of 32 | 0 |
| RPT-LL-02 fails with no net delay | gate | 55 | 3 | 30 | 0 of 45 | 30 |
| RPT-CLK-01 cascaded buffers, local clocks | advisory | 58 | 0 | 0 | 0 of 45 | 0 |
| RPT-CLK-02 uncertainty and skew | advisory | 59 | 9 | 48 | 7 of 49 | 0 |
| RPT-FO-01 high-fanout net | advisory | 55 | 1 | 5 | 0 of 45 | 0 |
| RPT-LOG-01 logic dropped in synthesis | advisory | 65 | 13 | 15 | 10 of 49 | 0 |
| RPT-LOG-02 message cut at 100 | advisory | 65 | 1 | 2 | 0 of 49 | 0 |
| RPT-LOG-03 generic the top does not have | gate | 65 | 12 | 12 | 6 of 49 | 0 (all are the flow's own `BUILD_STAMP`, listed not gated) |
| RPT-CONG-01 congestion level 4 or more | advisory | 65 | 1 | 6 | 0 of 49 | 0 |
| RPT-CONG-02 utilisation | advisory | 59 | 0 | 0 | 0 of 49 | 0 |
| RPT-IP-01 IP locked or not up to date | gate | 0 | 0 | 0 | none | 0 |
| RPT-CS-01 control sets 7.5 to 15 % | advisory | 36 | 0 | 0 | 0 of 32 | 0 |
| RPT-CS-02 control sets over 15 % | gate | 36 | 0 | 0 | 0 of 32 | 0 |

## What the hits are

- **The gates fire only on designs that cannot close.** RPT-LL-02 hit three builds, `c14_int8_dot_requant`, `c15_rmsnorm_unit` and `c15_softmax_unit`
  (post-synthesis slack of -20, -47 and -29 ns at a 10 ns clock; still -8.9, -26.7 and -7.8 ns with the net delay taken out). None of the
  45 builds that met timing after routing was hit.
- **Tuning that the counts forced.** The first version of RPT-LOG-01 counted ports driven by a constant (Synth 8-3917) and unconnected ports:
  it fired on 37 of 65 builds, all of them the tie-offs of the shared register-block template, so those ids were dropped (only removed
  sequential elements and unconnected internal registers count now: 13 builds). `Synth 8-3301` was dropped from RPT-LOG-01 and became
  RPT-LOG-03 (below).
- **Advisories that fire on good designs.** RPT-LL-01 flagged 4 of the 32 builds that met timing (13 or more levels at 100 MHz, counting
  carry levels, which the guide says inflate the count), RPT-CLK-02 7 of 49 (hold-path skew of 0.30 to 0.36 ns), RPT-LOG-01 10 of 49. That
  is 12 to 20 % of good builds, which is the price of advisories; none blocks.
- **RPT-LOG-03 (brief 203's finding).** `[Synth 8-3301] Unused top level parameter/generic` appears in 50 log lines of 12 recorded builds, and
  every one names `BUILD_STAMP`, the flow's own stamp generic on a top that does not use it. No other generic is unused in any recorded build.
  The check is a gate for every other generic name the build sets (fixture test: `EARLY_MAC`, `FAST_PRE`), and lists `BUILD_STAMP`.
- **Congestion.** One build (`c13_hough_lines`, the 19,391-load net design) shows placer congestion windows of 32x32 (level 5). Nothing else
  reaches 16x16. No recorded build has a router congestion table (the log prints it at level 4 or above), and
  `report_design_analysis -congestion` was empty on the 32 routed checkpoints it was run on (no window above level 5, no complexity rows).
- **Fan-out.** One build, the same 19,391-load carry net in `c13_hough_lines`. The other 54 have nets of at most 2,389 loads, under the 5,000 limit that applies at 100 MHz.
- **Clock tree.** No cascaded buffer and no local clock in any recorded build (one clock, one BUFG, from the pin); the toy design in the
  fixtures (a BUFG driving a BUFG, a counter-divided clock) is detected.

## Fixtures

`flow/tests/data/204a/`: real post-synthesis reports from the bench builds, the session's reports, and toy designs made for this brief
(`make/toy_*.v`, `make/toy.tcl`, Vivado 2025.2): a 12-level path timed at 1.6 ns and at 10 ns, a BUFG driving a BUFG with a fabric-divided clock, a
6,000-load net, 100/500/900 control-set designs on an xc7a35t (1.9 %, 9.6 % and 17.3 % of the device's 5,200), one Binary Counter IP.
**Edited, not recorded:** the congested placer table (a real one with one region size changed to 32x32 or 16x16) and the out-of-date IP status
(a real status table with its Status cell changed): Vivado 2025.2 cannot create an older IP version, and no recorded build is congested at
level 4 or above in the router table. The tests say so where they use them.

## Reproduce

```
python3 tools/report_gate_hits.py --repo ~/Claude_sandbox/FPGA_Design_Agent --session <dir with <design>_synth/ and <design>_route/ reports> \
    --out results/204a_report_gates
python3 -m pytest flow/tests/test_204a_report_gates.py
```

The session directory is made by `flow/tests/data/204a/make/session.tcl` (one Vivado 2025.2 batch session; arguments `<tag> <checkpoint> <synth|route>` triples).
The builds themselves are git-ignored and exist only on the machine that made them.

## Known gaps and limits

- The hit counts are over one machine's builds: 100 MHz designs on one Artix-7 part, no IP, one clock. They show the checks do not fire on
  most good designs; they do not show the thresholds suit a fast, multi-clock or UltraScale+ design.
- RPT-IP-01 has no recorded build to measure (the main flow reads no IP); its pass and fail paths are tested on a real status table and an edited one.
- No recorded build has a router congestion table, so RPT-CONG-01's router and short-share paths are tested on a hand-written table of the documented
  columns, not a recorded one.
- The gates are check-suite findings, not entries of `gates.json`.
- The session reports were made with Vivado 2025.2, the version the checkpoints came from; the tests' parsers were not run against 2026.1 output.
