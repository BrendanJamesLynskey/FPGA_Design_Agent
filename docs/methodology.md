# The UltraFast Design Methodology as the backbone of the flow

AMD's UltraFast Design Methodology Guide for FPGAs and SoCs (**UG949, v2025.2**, 2025-11-20) is the vendor's own
end-to-end method: board and device planning (ch. 2), design creation with RTL (ch. 3), constraints (ch. 4),
implementation (ch. 5), and closure of timing, power and DRCs plus configuration and debug (ch. 6). This flow
follows it stage by stage, with each stage's exit checks taken from UG949 and run by a program (`flow/build.tcl`
writes the reports, `flow/gates.py` judges them, stage by stage). The agent (F2) runs the same stages as a state
machine (last section). Every statement about UG949 below is in our words and cited to its chapter and section;
the guide itself is not reproduced.

Where this flow **deviates** from UG949, the deviation and its reason are stated in the table and listed again
at the end.

## Stages, inputs, outputs, exit checks

The plan's nine flow steps (`_handoff` plan, "The flow the agent runs") map onto UG949's chapters like this.
"Gate" names are the keys in `gates.json` (`flow/gates.py`); the Tcl is what `flow/build.tcl` runs.

| # | UltraFast stage (UG949) | Plan step(s) | Takes in | Produces | Exit checks (gate, threshold, UG949 source) |
|---|---|---|---|---|---|
| 1 | **Board and device planning** (ch. 2: "Clock Resource Planning and Assignment", "I/O Planning Design Flows", "Pin Assignment", "Device Power Aspects", "Configuration", "Interface Bandwidth Validation") | 1 clarify, 2 architecture | `spec.yaml` (signed off), `boards/<board>/` (board.yaml, inventory.yaml, master XDC, power_budget.md) | `build.yaml` (part, board), the clock plan and pin list in the architecture note, the power budget the gate will apply | `tools/inventory_check.py` exit 0 (CI); every port has a pin and I/O standard (ch. 4 "Defining Physical Constraints"); banking rules by `report_drc` after synthesis (ch. 2: a skeleton design exercises the DRCs); clocks chosen before pins (ch. 2 "Clock Resource Planning") |
| 2 | **Design creation with RTL** (ch. 3: "Defining a Good RTL Design Hierarchy", "Working with IP", "RTL Coding Guidelines", "Clocking Guidelines", "Clock Domain Crossing", "Running RTL DRCs") | 2 architecture, 3 golden model, 4 RTL and IP, 5 verification | architecture note, `spec.yaml` | SystemVerilog RTL, IP by Tcl, `model.py` (blind), cocotb tests, lint | **stage `rtl`**: `synth_design -rtl -rtl_skip_ip` then `report_methodology -file methodology_rtl.rpt`: **0 Critical Warnings** (`rtl_methodology_no_critical`; ch. 1 "Using the UltraFast Design Methodology DRCs": run them at each stage and address critical warnings and warnings before moving on; ch. 3 "Running RTL DRCs"). Project checks UG949 does not have: Verilator lint clean, the blind model's cocotb tests pass, every mutant fails |
| 3 | **Design constraints** (ch. 4: "Organizing the Design Constraints for Compilation", "Defining Timing Constraints in Four Steps", "Constraining Input and Output Ports", "Defining Clock Groups and CDC Constraints", "Specifying Timing Exceptions", "Defining Power and Thermal Constraints", "Defining Physical Constraints") | 4 (the XDC) | RTL, board pins, clock plan | `design.xdc`: clocks, I/O delays, clock groups/CDC, exceptions, pins, I/O standards; `board.yaml` `thermal` applied by the flow | Checked on the synthesised netlist (next row): `check_timing` all categories 0 (ch. 6 "Checking for Valid Constraints": every clock pin reached by a clock, every endpoint with a requirement, every port with delays); `report_methodology` TIMING/XDC checks (ch. 4 "Verifying Clocks Definition and Coverage"); `report_clock_networks` no unconstrained clock; `report_clock_interaction` no unsafe pair (ch. 6 "Reviewing Clock Relationships") |
| 4 | **Synthesis** (ch. 5: "Running Synthesis", "Moving Past Synthesis": "Reviewing and Cleaning DRCs", "Running Report Methodology", "Reviewing the Synthesis Log", "Reviewing Timing Constraints", "Assessing Post-Synthesis Quality of Results", "Reviewing Utilization", "Reviewing Clock Trees") | 6 implementation (first half) | RTL + XDC | `post_synth.dcp`; `timing_summary_synth.rpt`, `check_timing_synth.rpt`, `methodology_synth.rpt`, `drc_synth.rpt`, `qor_assessment_synth.rpt`, `utilization_synth.rpt`, `clock_networks_synth.rpt`, `clock_interaction_synth.rpt`, `high_fanout_synth.rpt` | **stage `post_synth`**: `check_timing` nine categories all 0 (`post_synth_no_unconstrained_endpoints`); `report_methodology` 0 Critical Warnings (`post_synth_methodology_no_critical`; ch. 5: "resolve all Critical Warnings and most Warnings"); `report_drc` 0 Errors and 0 Critical Warnings (`post_synth_drc_clean`; ch. 6 "DRC Closure": critical warnings become errors at bitstream); the `report_qor_assessment` score is **recorded as a warning when below 4** (`post_synth_qor_assessment` in `stages.post_synth.warnings`, `warnings` in gates.json and the review page; not a gate since brief 05g; ch. 5 "Assessing Post-Synthesis Quality of Results": "Scores of 1 and 2 have no chance of meeting timing closure and a score of 3 is unlikely to close"; table 4: 4 will likely meet timing, 5 will). Reason: on small designs the post-synthesis predicted-congestion item reads 3 while the routed score is 5 (benchmark 06a: 11 of 24 references, all at most 1.2 % of the device, timing met). Post-synthesis WNS is **recorded, not gated** (ch. 1: synthesis is complete with a positive or a small negative margin, and the flow may continue) |
| 5 | **Implementation** (ch. 5 "Implementing the Design": non-project mode, default directives, `opt_design`, `place_design`, `phys_opt_design`, `route_design`, checkpoints; ch. 6 "Evaluating Design WNS After Each Step", "Pre- and Post-Placement", "Pre- and Post-Route") | 6 implementation | `post_synth.dcp` | `timing_summary_place.rpt`; `post_route.dcp` and the post-route reports | **stage `post_place`**: `report_timing_summary` after `phys_opt_design`: **WHS > -0.500 ns** (`post_place_hold`; ch. 6 "Pre- and Post-Placement": hold violations of -0.500 ns or more must be fixed before routing, smaller ones the router fixes); WNS recorded |
| 6 | **Timing closure** (ch. 6 "Timing Closure": "Checking for Positive Timing Slacks", "Fixing Issues Flagged by check_timing", "Fixing Issues Flagged by report_methodology", "Analyzing and Resolving Timing Violations") | 6 (the closure loop) | routed design | `timing_summary.rpt`, `check_timing.rpt`, `methodology.rpt`, `cdc.rpt`, `qor_assessment_route.rpt` | **stage `post_route`**: WNS >= 0 and TNS = 0; WHS >= 0 and THS = 0; WPWS >= 0 and TPWS = 0 (`setup`, `hold`, `pulse_width`; ch. 6 "Checking for Positive Timing Slacks"); `check_timing` all 0 (`no_unconstrained_endpoints`); `report_methodology` 0 Critical Warnings (`methodology_no_critical`; ch. 6 tables 6 and 7); `report_cdc` 0 Critical (`cdc_no_critical`; ch. 6 table 7: "use report_cdc"); **post-route QoR score >= 4** (`post_route_qor_assessment`, from `qor_assessment_route.rpt`; the QoR gate, brief 05g) |
| 7 | **Power closure** (ch. 6 "Power Closure": "Estimating Power Throughout the Flow", "Recommended Power Constraints", "Best Practices for Accurate Power Analysis"; ch. 4 "Defining Power and Thermal Constraints") | 6 (`report_power`), 9 (before programming) | routed design, `board.yaml` `thermal` | `power.rpt` for the board's environment | `set_operating_conditions -airflow 0 -heatsink none -board small -board_layers 4to7 -ambient_temp 40` then `report_power`: environment is the board's and **junction <= 85 C** (`power_junction_ok`, stage `post_route`); before programming, `flow/hw.py power_ok`: total on-chip <= 2.0 W (wall) / 0.5 W (USB), rail currents within `power_budget.md` (ch. 6: "Does the total power and junction temperature fit into your thermal and power budget?") |
| 8 | **DRC closure** (ch. 6 "DRC Closure"; ch. 5 "Reviewing and Cleaning DRCs"; ch. 6 "Running Debug-Related DRCs") | 6, 7 | each stage's netlist | `drc_synth.rpt`, `drc.rpt` | `report_drc` **0 Errors and 0 Critical Warnings** after synthesis and after routing (`post_synth_drc_clean`, `drc_clean`); warnings listed; waivers only with a written reason (ch. 5, ch. 6: the waiver mechanism) |
| 9 | **Configuration and debug** (ch. 6 "Configuration and Debug": "Configuration", "Debugging", "Using ILA Cores", "Choosing Debug Nets", "ILA Core and Timing Considerations", "Using VIO Cores") | 7 software, 8 bring-up guide, 9 hardware result | `<top>.bit`, `probes.yaml`, `BRINGUP.md` | **stage `bitstream`**: `write_bitstream` completes (`bitstream_present`); ILA build from `probes.yaml` passes every stage plus `debug_probes_present`; `program.py` DONE = 1; `bringup.py` JSON pass | `bitstream_present` (and `debug_probes_present` for the ILA variant); `power_ok` before programming; UART tests and ILA captures agree with the blind model (project checks; UG949 has no automated bring-up) |

The per-stage procedures the agent reads are in the private knowledge bank, `procedures/ultrafast/<stage>/SKILL.md`
(nine skills, listed by name and hash in [knowledge/PACKS.md](../knowledge/PACKS.md)). They carry the same checks
as exact Tcl with thresholds, the common failures, and what is version-specific.

## What `flow/build.tcl` writes, stage by stage

| Stage | Tcl (in order) | Reports | Added by 04e |
|---|---|---|---|
| `rtl` | `synth_design -rtl -rtl_skip_ip -top ... -part ...`; `report_methodology` | `methodology_rtl.rpt` | yes |
| `post_synth` | `synth_design`; `write_checkpoint post_synth.dcp`; `report_timing_summary -max_paths 10 -report_unconstrained`; `check_timing -verbose`; `report_methodology`; `report_cdc -details` (05d); `report_drc`; `report_qor_assessment`; `report_utilization`; `report_clock_networks`; `report_clock_interaction -delay_type min_max`; `report_high_fanout_nets -timing -load_types -max_nets 25` | `*_synth.rpt` | all but `utilization_synth.rpt` |
| (ILA) | `insert_ila` from `probes.yaml` (ILA variant only) | `probe_map.txt` | no |
| `post_place` | `opt_design`; `place_design`; `phys_opt_design`; `report_timing_summary -max_paths 10` | `timing_summary_place.rpt` | yes |
| `post_route` | `route_design`; `write_checkpoint post_route.dcp`; `report_timing_summary`, `check_timing`, `report_utilization` (+ `-hierarchical`), `report_methodology`, `report_cdc -details`, `report_drc`, `report_qor_assessment`, `set_operating_conditions <board thermal>`, `report_power`, `report_io` | `timing_summary.rpt`, `check_timing.rpt`, `utilization*.rpt`, `methodology.rpt`, `cdc.rpt`, `drc.rpt`, `qor_assessment_route.rpt`, `power.rpt`, `io.rpt` | `qor_assessment_route.rpt` |
| `bitstream` | `write_bitstream`; `write_debug_probes` (ILA) | `<top>.bit`, `<top>.ltx` | no |

`report_qor_assessment` **is supported on 7-series in Vivado 2025.2** (checked on the xc7a100t: score 5 for T1 after
synthesis and after routing); only its "ML Strategy Availability" section reports that ML strategies are not
supported for 7-series, and Intelligent Design Runs need project mode and UltraScale(+) (ch. 6 "Using Intelligent
Design Runs"), so neither is used.

`gates.py` marks a stage whose reports are missing (a build made before 04e, e.g. `results/f0a/`) as `ran: false`
and skips it; the F0A gate names are unchanged, so earlier results still parse. Its output names the **first stage
that failed**, so the agent fixes the earliest problem first (ch. 1 "Maximizing Impact Early in the Development
Cycle": RTL changes have 10x the leverage of placement and routing changes).

**Cost of the added reports** (T1 base, same sources, `results/ultrafast/` vs `results/f0a/`): 191.0 s vs 187.0 s
wall (+4.0 s); peak RSS 2,693 vs 2,525 MiB (+168 MiB); peak anonymous memory of the scope 2,071 vs 1,898 MiB.
Elaboration for the RTL stage took 26.1 s, but the following `synth_design` then took 47.5 s instead of 79.5 s, so
the RTL stage was nearly free; the post-synthesis reports took 8.4 s, the post-placement report 0.7 s, the
post-route QoR assessment 0.4 s. Timing, utilisation, DRC, methodology and CDC results are identical to F0A; only
the power figures changed, for a reason unrelated to the added reports (see `results/ultrafast/README.md`).

## Where this flow deviates from UG949, and why

1. **Batch non-project flow, not project mode.** UG949 ch. 5 "Using Project Mode vs. Non-Project Mode" allows both;
   it writes most instructions for the IDE (the Timing Constraints Wizard, Report windows, Intelligent Design
   Runs). The agent needs every check to be a command with a file it can parse, and every build to be reproducible
   from sources (`BUILD_STAMP`), so the flow is a Tcl script that calls every report explicitly (which UG949 says
   non-project mode requires) and the GUI-only aids are replaced by their Tcl reports.
2. **No separate baselining pass.** UG949 ch. 6 "Baselining the Design" starts with clock constraints only, leaves
   I/O delays for later and iterates by hand through opt, place and route. Here the XDC must be complete before
   the first gated synthesis (the asynchronous-input idiom is a zero delay plus a false path, because
   `check_timing` counts a bare false path as `no_input_delay`), and the stages are checked in one batch run. The
   same checks UG949 places in the baselining procedure (steps 1-12 of "Baselining and Timing Constraints
   Validation Procedure") are run as reports at `post_synth`, `post_place` and `post_route`.
3. **Post-synthesis timing is recorded, not gated.** UG949 ch. 1 says synthesis is complete with a positive or a
   small negative margin, and that the flow may continue to learn the real slack; it gives no number, so the
   stage records WNS and the closure gate is at `post_route`.
4. **A blind golden model, independent verification, mutants and automated bring-up** are project rules UG949
   does not have (it covers hardware debug, not verification). They come from the CVDP lessons: an agent's own
   testbench shares its misreading of the spec, so only the blind model's tests, the gates and the board count.
5. **Power process.** UG949 recommends `set_operating_conditions -process maximum` for worst-case static power
   (ch. 4, ch. 6 "Recommended Power Constraints"). The flow applies the board's thermal environment but leaves the
   process at Vivado's default, because the board's power budget (04c) was derived with it; changing it raises
   every static-power figure and is a planner decision.
6. **Programming is SRAM over JTAG only, by cable serial;** flash is never written (house rule), so UG949's
   indirect-programming flow is out of scope.
7. **SSI and HBM** planning (ch. 2) does not apply to the Artix-7 100T or the Kria K26.
8. **XPM CDC exceptions are applied by cell name.** AMD ships the timing exceptions of its `xpm_cdc_*` macros as scoped
   constraint files. The non-project flow (`read_verilog` + `synth_design`) did not apply them in the quality review of
   2026-11-10 (QR1): a design with one `xpm_cdc_single` and one `xpm_cdc_gray` between two clocks showed Exception
   "None" for both crossings in `report_cdc` and a setup WNS of -1.364 ns on the crossing, i.e. each crossing was
   timed as a synchronous path. [flow/xpm_cdc.tcl](../flow/xpm_cdc.tcl), sourced by `flow/build.tcl` right after
   `synth_design`, applies the same rules by cell name (a false path to the first synchroniser stage, `max_delay
   -datapath_only` plus `set_bus_skew` for Gray buses, `max_delay -datapath_only` on handshake data). The rules come
   from the CDC soak rig, where they were proven. Re-run through the flow on the same probe (2026-11-10): both
   `report_cdc` rows now carry their exception and the clk_a -> clk_b setup WNS is +8.891 ns (was -1.364 ns).
   `xpm_cdc_pulse` and `xpm_cdc_async_rst` get no exception yet. `report_cdc` alone is not the CDC gate: it does not flag
   every mutant type the soak rig injects (see [hil/cdc_soak](../hil/cdc_soak/README.md)).

## The agent's stage machine (for brief 05, F2)

The agent moves through the same stages. In each it may do only what the stage allows; a stage's exit checks are
the gates above (run by the flow, never by the agent's own judgement), and a failure sends it back to the earliest
stage that can fix the cause.

| Stage | What the agent may do | Moves on when | Loops back to |
|---|---|---|---|
| 0 clarify | read the spec, write `spec.yaml` (ports, clocks, reset, latency, resources, power, assumptions with reasons, open questions, **requirements with a proof method each**) | the human signs `spec.yaml` off (the only mandatory human step before hardware) | - |
| 1 board-and-device-planning | choose part and board, map ports to pins and I/O standards from the inventory and master XDC, write the clock plan and the power budget into the architecture note **and `architecture.yaml`** (blocks, interfaces, clock domains, crossings, predicted resources) | inventory check passes; every port has a pin and standard; clocks planned; `architecture.yaml` valid. **The owner then approves the architecture (review on: always a pause; off: recorded as auto)** | 0 if the spec needs a pin or clock it cannot have |
| 2 rtl-design-creation | RTL and IP by Tcl, lint, cocotb tests against the blind model (written by a separate agent from `spec.yaml` alone) | **the architecture is approved and unchanged since**, `flow/lint.sh` clean, the blind model's tests pass, **the design standards pass (`standards_rtl`)**, verification reaches the required V-stage (V1 includes a proof method per requirement), stage `rtl` passes (`report_methodology` on the elaborated RTL has no critical warning) | 0 if the model and RTL disagree on the spec (an open question, not a code fix); 1 if the architecture must change |
| 3 constraints | write `design.xdc` in UG949's four steps (clocks, I/O delays, clock groups/CDC, exceptions), pins, I/O standards | stage `post_synth` constraint checks pass (`check_timing` all 0, methodology TIMING/XDC clean, no unsafe clock pair) | 2 for a CDC structure the constraints cannot make safe |
| 4 synthesis | run the flow; read the synthesis log, `drc_synth`, `methodology_synth`, `cdc_synth`, `qor_assessment_synth`, `utilization_synth`, post-synthesis WNS | stage `post_synth` passes (DRC, methodology, coverage, **resources within the architecture's prediction**) and the post-synthesis standards rules pass (`standards_post_synth`) | 1 if the resource prediction was wrong, 2 for RTL causes (unintended logic, a RAM that became LUTs, deep logic, unregistered RAM/DSP outputs, high fanout, QoR REVIEW items), 3 for constraint causes |
| 5 implementation | run opt, place, phys_opt, route; read `timing_summary_place` and the post-route reports | stage `post_place` passes (WHS > -0.5 ns) and stage `post_route` passes | 6 |
| 6 timing-closure | root cause with `report_timing_summary`, `report_design_analysis`, `report_qor_suggestions`; apply one change at the earliest stage that owns the cause, say what changed and why | `post_route` timing gates pass | 3 (clocks, exceptions, CDC), 2 (pipelining, fanout, control sets, hierarchy), 5 (directives, overconstraining) only when 2 and 3 are clean |
| 7 power-closure | read `power.rpt` (total, junction, rails, confidence); reduce power if over | `power_junction_ok` and `power_ok` pass | 2 (coding for power, fewer memories, enables) or 0 (a budget the spec cannot meet) |
| 8 drc-closure | read `drc_synth`, `drc`, `methodology`, `cdc`; fix or waive with a written reason | DRC gates pass at both stages; CDC no critical | 3 (constraint-shaped rules), 2 (structure rules) |
| 9 configuration-and-debug | write `BRINGUP.md`, `probes.yaml`, `tests/test_*_hw.py` and `hw_checks.py` (the last two by the test writer, against the blind model); build the ILA variant; the dry check of the bring-up files passes **before** the owner is asked to approve programming; program (power gate, serial, SRAM); run `bringup.py` | `bitstream` stage passes for both variants, the bring-up files pass `gates(kind=bringup_ready)`, DONE = 1, UART tests and ILA captures match the model, **the sign-off traceability table is all `pass`** | 9 itself when the bring-up files are missing or malformed (their writers fix them), 6 if the ILA build breaks timing (fewer or narrower probes first), 2 if the hardware contradicts the model and the spec is clear, 0 if the spec is not |

Rules that hold in every stage: the agent never edits a gate, a threshold or a report; it may not waive a rule to
pass a gate without a written reason; it searches only the frozen knowledge bank; and the stage it is in, what it
read, what it changed and why are written to the build note so the result is reproducible.

### Repair, not regeneration (stage 2, brief 05c2)

A stage-2 failure used to re-run the model writer, the test writer and the RTL writer from scratch, which re-broke
parts that had passed. Now the graph treats a failure as evidence about one artefact:

- each failing gate or tool result is traced to the role that wrote the failing artefact, from the evidence only
  (`agent/graph/repair.py`): the contract check or a traceback in `model.py` -> the model writer; a testplan or
  traceability failure, or a traceback in the bench -> the test writer; lint, an HDL compile error, or a mismatch
  between the RTL and the model -> the RTL writer;
- only those roles run, each given the failures that are its own and its previous output to edit ("edit, do not
  rewrite"); every other artefact is frozen and nobody rewrites it that visit; a repair deletes no file;
- if the failure signature is unchanged after a repair, the next visit adds the test writer to a behavioural
  mismatch (the bench may be wrong), and after a second repeat the model writer, which is told only the NAME of the
  disagreeing test, never RTL or RTL output. The blind-model separation is unchanged: the model writer sees the spec
  and its own model.

Other tool rules from the same brief: constraints are generated from board resource names (`board_constraints`),
never from pin numbers; the tool schemas offer only simulators installed here and only bank section ids that exist;
known artefacts are validated when written, with line and column; the gate failure names every untraced spec id.

### Taylor additions (brief 05d)

Adam Taylor's FPGA Horizons issue 5 article ("What Star Trek can teach us about using AI in FPGA design") argues that
the AI is a junior engineer held to the same gates as human RTL. Six of its ideas are standard in the flow; each is
enforced by code, from both harnesses, and none can be switched off.

1. **A proof method per requirement** ([verification.md](verification.md)): V1 fails without one, sign-off fails
   unless each has passing evidence.
2. **Architecture first.** Stage 1 ends with `ARCHITECTURE.md` and `architecture.yaml` (schema in `flow/architecture.py`).
   With `--review on` the stage-1 review always pauses and the owner chooses: approve, edit (a prompt to the writing
   role, or a hand edit), or **supply** their own files. With `--review off` the approval is written at once and
   recorded as `auto`. The approval record (`build/approvals/architecture.json`) holds the SHA-256 of both files: stage 2
   does not start RTL without a matching record, the RTL writer's jail refuses to write the files after approval, and a
   later change makes the `arch_approved` gate fail and routes back to stage 1. The build note says whether the
   architecture was written by the agent or is an owner contribution.
3. **Design standards v1.0** ([design_standards.md](design_standards.md)), checked by `flow/standards_check.py`: gate
   `standards_rtl` at stage 2, `standards_post_synth` at stage 4 (Vivado `report_cdc`, `report_methodology`,
   clock-network scan). An unchecked checkable rule counts as failed.
4. **Resource sanity.** `architecture.yaml` predicts LUT, FF, BRAM and DSP ranges; at post-synthesis the counts must lie
   within the range widened by the factor in `flow/gates.yaml` (default 2x). A failure is `post_synth_resources_in_range`
   and goes to stage 1 (the prediction was wrong) or stage 2 (a RAM that did not map while logic is over; a latch).
5. **Review pages for line-by-line review**: the RTL diff against the previous stage (highlighted, no external script),
   corner cases hit (requirement, tests, bins hit of total), waveforms with buses as hex values, `design.xdc` in full with
   each pin traced to the board inventory, the traceability table and the standards results; light and dark.
6. **Change by prompting; owner edits logged.** With `--review on`, `edit` takes a prompt for the writing role (`role` in
   the reply, default the stage's writer). Files the owner changes by hand while the run is paused are found by comparing
   with the stage snapshot, committed separately with author `owner`, gated again (the agent does not rewrite them) and
   listed in `build/who_did_what.json` and the build note's "Who did what" table: **owner**, **agent** or **auto**.
