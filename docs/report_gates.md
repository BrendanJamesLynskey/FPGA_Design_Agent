# Report-driven checks (brief 204a)

Seven checks that read reports the build already writes (or one Vivado session can write from a checkpoint) against thresholds in AMD's
UltraFast Design Methodology Guide (UG949) and the Timing Closure Quick Reference (UG1292); page numbers are the PDF pages of the editions kept in the machine's `_amd_docs` folder. They come from the gap study of
brief 204 (ranks 1, 2, 5, 11, 12, 13, 14). Code: `flow/report_gates.py`, wired into the [check suite](check_suite.md) as the checks
`logic_levels`, `clock_tree`, `fanout`, `synth_log`, `congestion`, `ip_status` and `control_sets` (extended). Rules: FDA-HDL v1.7
(HDL-TIM-01, HDL-CLK-03, HDL-FO-01, HDL-LOG-01, HDL-CONG-01, HDL-IP-01, HDL-CS-01). Measured on the recorded builds:
[results/204a_report_gates](../results/204a_report_gates/README.md).

**Gate or advisory.** A *gate* finding blocks the check (status `fail`). It is a gate only where the guide calls the item a requirement, or says the
design cannot work. Everything else is advisory: listed with its fix, never blocking. The gates are findings of the check suite; they are **not** entries of
`gates.json`, which the stage controller reads. **Since brief 209a** the agent's stage machine acts on three of them: a blocking RPT-LL-02, RPT-CS-02 or RPT-LOG-03 on the post-synthesis reports fails the `report_gates` exit gate of stages 2, 3 and 4 and sends the run back to the Designer (stage 2) with the finding's own text and the advisories of the same checks (`agent/graph/stages.py` `report_gates_stage`, `agent/graph/run.py` `report_gates_eval`); every advisory stays advisory.

| Id | Level | Source (PDF page) | Rule | Reads |
|---|---|---|---|---|
| RPT-LL-01 | advisory | UG949 p.75, p.234-235; UG1292 p.5 | a clock's logic-level distribution has paths with 13 or more levels when its requirement is 8 ns or longer, 6 or more above 125 MHz (the guide's table: fewer than 13 up to 125 MHz, fewer than 6 from 125 to 250 MHz, "advanced pipelining" above 250 MHz with no figure) | `logic_levels_synth.rpt` |
| RPT-LL-02 | **gate** | UG949 p.200 | a setup path of the post-synthesis timing report that is violated and still fails when its own net delay is taken out (slack plus route delay below zero) | `timing_summary_synth.rpt` |
| RPT-CLK-01 | advisory | UG949 p.111-112, p.139, p.200-201 | a global buffer driven by another global buffer (cascaded); a clock made in fabric (a counter-divided clock, "Local Clock Details", an unconstrained clock sourced by a flip-flop) | `clock_utilization_*.rpt`, `clock_networks_synth.rpt` |
| RPT-CLK-02 | advisory | UG949 p.232, p.248 | setup path uncertainty over 100 ps; hold uncertainty over 200 ps; hold skew over 300 ps; skew over 500 ps on a violated setup path | the timing paths of the stage |
| RPT-FO-01 | advisory | UG949 p.73-75 (table 1) | a non-clock net over 5000 loads; over 200 loads on a clock above 125 MHz; over 100 loads on a clock above 250 MHz. The message gives the guide's fixes (balanced RTL tree with KEEP, FD driver, `phys_opt_design -directive Explore`, no `MAX_FANOUT` on global nets, no replicated `ASYNC_REG`). Not a gate on `MAX_FANOUT` | `high_fanout_synth.rpt`, Clock Summary |
| RPT-LOG-01 | advisory | UG949 p.198, p.200 | message ids that say logic was dropped: `Synth 8-3332`, `8-6014` (sequential elements removed), `8-3936` (unconnected internal register) | `vivado.log` |
| RPT-LOG-02 | advisory | UG949 p.198 | a message the tool switched off after 100 occurrences (`Common 17-14`). `flow/build.tcl` now sets `messaging.defaultLimit` to 100000 | `vivado.log` |
| RPT-LOG-03 | **gate** | `Synth 8-3301`; brief 203 | the build sets a generic or parameter that the top does not have: Vivado only warns, the value never reaches the design. The flow's own `BUILD_STAMP` is listed, not gated | `vivado.log`, `inputs.tcl` |
| RPT-CONG-01 | advisory | UG949 p.240, p.244; UG1292 p.6 | a placer or router congestion region of 16x16 or larger in the log (level 4: small variation), or level 5 (32x32, "likely degrades QoR"); the same levels and a short-interconnect share over 5 % in `report_design_analysis -congestion` | `vivado.log`, `congestion_route.rpt` |
| RPT-CONG-02 | advisory | UG949 p.273, p.278; UG1292 p.6 | the used LUT, FF, block RAM and DSP percentages average over 75 %; LUT over 60 % while block RAM or DSP is over 80 %; LUT combining over 40 % in a congested window | `utilization*.rpt`, `congestion_route.rpt` |
| RPT-IP-01 | **gate** | UG949 p.49 | `report_ip_status` shows an IP locked or with a status other than Up-to-date | `ip_status_synth.rpt` |
| RPT-CS-01 | advisory | UG949 p.265 (table 17) | control sets 7.5 % to 15 % of the device's capacity (CLB registers / 8): reduction recommended | `control_sets_synth.rpt`, utilisation |
| RPT-CS-02 | **gate** | UG949 p.265 | control sets above 15 % of the capacity: reduction required | the same |

## What the checks cannot see

- The guide's logic-level numbers come from a fan-out table for medium-performance 7 series devices; they are review points, not limits, and
  carry levels count like any other (UG1292 p.5 says cascaded CARRY and MUXF cells inflate the count). On the recorded 100 MHz builds the advisory flagged
  4 of 32 designs that met timing.
- The report from `report_design_analysis -congestion` lists windows above level 5 only; level 4 is seen in the placer log table. The 26 % MUXF
  figure in UG949 p.277 is an example in a figure, not a threshold, and is not used. A router congestion table was never present in a recorded build.
- `report_ip_status` needs IP in the Vivado session. The main flow reads no `.xci`; only the debug (ILA) build creates IP in its session, so the report is written
  there and the check applies only to builds that have it. A checkpoint carries no IP status, so the check suite's own session cannot make it.
- Builds made before this brief lack the new reports; the check suite then runs them in its one Vivado session when it may, otherwise reports the part as not run
  (the check is `incomplete`, never a clean pass).
- Skew and uncertainty are read from the paths the reports list (the worst ten per group, and the worst setup and hold path), not from every path.

## Running

```
python3 -m flow.checks designs/<d> --names logic_levels,clock_tree,fanout,synth_log,congestion,ip_status,control_sets --scope synth
python3 tools/report_gate_hits.py --repo <checkout> --session <dir> --out results/204a_report_gates
```
