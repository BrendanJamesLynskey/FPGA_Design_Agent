# Latency, phase 2: a planning loop over all relevant modules (plan for brief 97B)

Status 2026-11-17: a plan, written by brief 97 after phase 1 (the tools and the one-change loop of
[latency_reduction.md](latency_reduction.md)). Nothing in this file has been run except where it cites a recorded result. Owner direction
(2026-11-17): "the agent takes a wider view of all potentially relevant modules, plans multiple possible strategies to reduce overall
latency, executes, evaluates, and updates the plan", and "for small blocks, consider whether our own tools might do better than the Xilinx
tools (latency-optimised synthesis, latency-optimised placement, latency-optimised routing)".

## The loop

Phase 1 changes one thing per visit and keeps or reverts it. Phase 2 keeps a **plan**: a table of strategies over the modules of the
latency chain (from `latency_path`), each with a predicted saving, cost, risk and the evidence that would confirm it.

1. **Survey**: `latency_path` and `latency_budget` for every direction (tick-to-trade, echo), post-route slack per stage, run-to-run
   spread of those slacks over seeds (the repeatability of a stage is part of its latency), what the board adds.
2. **Plan**: for each stage and technique below, one row: expected clocks or ns saved, what it costs (heavy-slot minutes, LUT, FF, risk,
   board session needed), what would show it failed. Rank by expected ns saved per heavy-slot minute, after a risk filter (a strategy
   that needs a board session is batched, never interleaved).
3. **Execute** the top strategy as an experiment with its own budget (iterations, heavy-slot minutes, dollars).
4. **Evaluate** with the same three measures as phase 1 (clocks in simulation, post-route timing, the board) plus the spread over seeds
   for anything that touches placement or routing. Vivado's timing analysis is the referee; a number from our own tool or a model is
   reported, never used to claim closure.
5. **Update** the plan: strike the row, re-estimate those that interact (two techniques that act on the same net or stage), add rows the
   result suggests, stop when the remaining expected saving is below the cost of one more heavy run. Every iteration is recorded
   (`results/b97/...` schema `fda.latency_plan/1` in 97B): the plan before, the action, the measures, the plan after.

Stop rules, fixed before the run: total heavy-slot minutes; at most one board session per batch; stop a technique after two failed
attempts; any change that fails the independent bench or the model twin is reverted at once.

## Techniques: what each is, cost, risk, AMD source

Sources are named by document; section numbers are given only where they were checked, and every property or command name below is checked
against Vivado 2026.1's own property and help tables by `results/b97/phase2_probe.tcl` (output `results/b97/phase2_probe.txt`) before 97B
uses it. A document without a checked section is cited by title.

| Technique | What it does for latency | Cost | Main risk | Source |
| --- | --- | --- | --- | --- |
| **Manual placement**: Pblocks on the PCS and MAC and the logic next to the GT quad | shorter routes between the stages of the chain, so two stages may merge or the clock may rise | low: a few XDC lines; one heavy run to try | placement elsewhere gets worse; fragile when the RTL changes; a Pblock is an area, not a guarantee | UG903 (physical constraints, `create_pblock`), UG949 (floorplanning), UG912 (property reference); the KB library holds UG906's Pblock report notes |
| **LOC and BEL** on the few registers of the chain | exact placement of the capture register next to the GT, the toggle and synchroniser flops of the crossing in one slice | low-medium | a wrong BEL is refused at place; a LOC kept across builds keeps the placement only while the netlist names stay | UG903, UG912 (`LOC`, `BEL`) |
| **Relative placement (RLOC, `U_SET`/`HU_SET`)** of a bus of registers (the PCS output register `gt_d`, the MAC `x_d`) | keeps a group together as one macro, whatever the placer does around it | low | RLOC is a hint relative to the set; sets cannot cross hierarchy boundaries cleanly | UG901 (synthesis attributes), UG912 |
| **Manual routing**: `FIXED_ROUTE` and `ROUTE` on the few nets that set the period or sit on the chain; `route_design -nets`, `-preserve`; `lock_design -level routing` | fixed delay on those nets, independent of the router's run | medium-high: the routes must be extracted from a good run (`get_property ROUTE`), re-applied, checked | valid only with the same placement; a net whose source or load moves loses its route; high maintenance | UG835 (`route_design`, `lock_design`), UG912 (`FIXED_ROUTE`, `ROUTE`, `IS_ROUTE_FIXED`) |
| **Keeping it stable across builds**: incremental implementation from a reference checkpoint (`read_checkpoint -incremental`) | reuses placement and routing of an unchanged part, so a change elsewhere does not move the chain | low | the reuse percentage falls if the netlist changes a lot; the reference must itself close | UG904 (incremental compile); UG949 (incremental compile) |
| **Per-block resynthesis**: out-of-context synthesis of one block with its own directives (`-directive PerformanceOptimized` or `AlternateRoutability`, `-retiming`, `-flatten_hierarchy`, `KEEP_HIERARCHY`, FSM encoding), stitched into the top | shorter stage delay for a block whose stage is timing-critical, so its neighbour may merge | low-medium: `synth_design -mode out_of_context`, a block checkpoint, `read_checkpoint -cell` | retiming moves registers: it must keep the cycle behaviour the twin checks (it never removes a clock; it can only change ns per stage); a hierarchy kept apart loses cross-boundary optimisation | UG901 (synthesis options and attributes), UG905 (hierarchical design, OOC), UG835 (`synth_design`, `read_checkpoint`, `update_design`) |
| **Implementation directives** (`place_design`, `phys_opt_design`, `route_design` directives; seed sweeps) | spread of the chain's slack over seeds, best-of-N | one heavy run per seed (about 20 minutes each on this PC) | picking the best seed is not a design improvement unless it is repeatable: the run-to-run spread is reported with it | UG904, UG1292 (timing closure quick reference) |
| **Own synthesis for small blocks** (write LUT6, CARRY8 and FDRE primitives with INIT values: the brief 89 generator already does this for LUT nets) | an exact structure with a stated depth, for a block such as the PCS gearbox or the CRC | medium: a generator and a proof of equivalence to the RTL | equivalence proof; Vivado may still re-map unless the primitives are protected (`DONT_TOUCH`) | UG974 (UltraScale Libraries Guide: primitives), UG903 |
| **Own placement and routing for small blocks** | latency-aware placement and routing of the chain | high; this is brief 100 (RapidWright in the agent) | the open tools' delay estimates are not Vivado's; Vivado stays the referee and writes the bitstream | RapidWright (AMD Research, Apache 2.0, the project's documentation); survey below |
| **Device characterisation** (this die's real delays) | a measured margin for this chip, this temperature, this voltage | high: a separate test design, MMCM dynamic reconfiguration, SYSMON logging, a board session | out of AMD's specification if used to run faster; never closure | UG572 (clocking resources, MMCM dynamic reconfiguration), UG580 (UltraScale system monitor), XAPP888 for the 7-series ancestor |

### The survey of open tools (97B stage 0; the brief 100 report holds the measured part)

- RapidWright: reads and writes Vivado checkpoints, pre-implemented relocatable blocks, its own router (RWRoute); the one open tool that
  covers the K26's device (UltraScale+). Whether it reads a Vivado 2026.1 `.dcp` is brief 100's stage 0.
- nextpnr-xilinx and Project X-Ray: open place-and-route and bitstream documentation for the 7-series; no UltraScale+ coverage that would
  produce a KR260 bitstream.
- Project U-Ray: database effort for UltraScale and UltraScale+; incomplete, not a route to a bitstream here.
- Consequence: for the K26, "our own tools" means our own synthesis (primitives) and RapidWright's placement and routing on checkpoints, with
  Vivado doing the final route check, timing, DRC and the bitstream. The pick for 97B: the PCS gearbox or the CRC, compared with Vivado's
  own result on latency (ns at its own Fmax), Fmax, LUT and FF, run time and repeatability over seeds. A loss is reported as a loss.

## Device characterisation, with its honesty rule

Methods, each needing its own small design and a board session: (a) a clock-frequency sweep to first failure per path, the frequency
stepped through an MMCM's dynamic reconfiguration port; (b) a carry-chain delay line (a time-to-digital converter) or a ring oscillator whose frequency
gives the real LUT and routing delay; (c) die temperature and the VCCINT, VCCAUX and VCCBRAM rails logged from the SYSMON beside every
sample (house rule: operating conditions are evidence). **Honesty rule:** signed-off timing always uses Vivado's models. A characterised
margin is reported separately as "this die, this temperature, this voltage", is out of AMD's specification if used to run faster, and is never
used to claim closure.

## What phase 1 learned that shapes this plan

See [latency_reduction.md](latency_reduction.md) and the report `reports/97_agent_latency_report.md`: the independent bench and the twin
fix the cycle behaviour of the PCS and MAC, so a change there needs a latency parameter in the twin before an agent may try it;
the transceiver's share (about 15 clocks of the 20 in the echo) is not reachable from simulation at all and needs a board session per
variant; and the simulation's in-phase clocks hide the receive-to-transmit crossing's phase, so a crossing change is judged on the board.

## What the probe read from Vivado 2026.1 (results/b97/phase2_probe.txt, brief 97)

Confirmed from the tool's own help: `synth_design -directive` includes `PerformanceOptimized`, `AlternateRoutability` and `LogicCompaction`, and has `-incremental_mode`; `opt_design` has `-directive` values including the Explore family; the 96 checkpoint's cells carry `LOC`, `BEL`, `RLOC`, `H_SET`, `KEEP`, `DONT_TOUCH`, `KEEP_HIERARCHY`, `IS_BEL_FIXED`, `IS_LOC_FIXED`, `PBLOCK`. `U_SET` and `HU_SET` were not listed on a plain register (they appear only once set; to be re-checked by 97B). The net-property half of the probe (`FIXED_ROUTE`, `ROUTE`, `IS_ROUTE_FIXED`, `USER_CLOCK_ROOT`) did not complete and the GT Wizard bypass probe failed (a missing scratch directory in the script, fixed in the script, not re-run): both are open and 97B re-runs them first.
