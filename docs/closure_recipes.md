# Closure recipes and knowledge-guided closure search (brief 216)

Timing closure at stage 6 changes the implementation only by naming a **recipe** with typed parameters. A recipe is checked before it runs, produces
the Tcl from a fixed template, is checked again on its measured result, and is rolled back when the result is invalid or not better. Free-form Tcl,
scripts and constraint text are refused at stage 6. The order in which recipes are tried comes from the failing report, the knowledge bank's family
matrix and recorded past gains, and a small budgeted tree keeps the best checkpoint.

Code: [agent/graph/closure_recipes.py](../agent/graph/closure_recipes.py) (recipes, validators, renderer, guard),
[agent/graph/closure_search.py](../agent/graph/closure_search.py) (features, order, priors, search),
[flow/closure_recipe_run.py](../flow/closure_recipe_run.py) (Vivado runner), tests `agent/tests/test_216_closure_recipes.py`.
Measured results and what they do not show: [results/216_closure_recipes/README.md](../results/216_closure_recipes/README.md). Status: **opt-in and
not wired into the stage-6 loop by default** (see "Where it plugs in").

## The recipes

| recipe | level | parameters | what it does | documented in |
|---|---|---|---|---|
| `impl_directive` | impl | `step` (opt, place, phys, route, post), `directive` | one step's `-directive`; the values are the ones in `results/178_tournament/vendor_strategies.json` and the tournament menu | UG904 |
| `amd_strategy` | impl | `name` (33 measured AMD strategy sets) | the five directives of one AMD implementation strategy | read from Vivado 2026.1 by `flow.tournament strategies` |
| `impl_set` | impl | `name` (explore, extra_timing, extra_netdelay, aggressive, congestion) | the tournament's named directive sets (kept equal to `flow/tournament.py IMPL_MENU` by a test) | docs/tournament.md |
| `phys_opt_options` | post_route | `step` (phys, post), `flags` (fanout_opt, placement_opt, rewire, critical_cell_opt, dsp/bram/shift_register_opt, retime, critical_pin_opt, clock_opt, bram_enable_opt, hold_fix) | `phys_opt_design` option flags after placement or after routing; `hold_fix` only alone | UG904 |
| `fanout_replicate` | post_route | `nets` (at most 8 plain names) | `phys_opt_design -fanout_opt -force_replication_on_nets` on the named nets | UG904 |
| `max_fanout` | constraint | `nets`, `limit` (16 to 2000) | `MAX_FANOUT` on named nets before placement | UG903 |
| `retime` | synth | `where` (synth: `-retiming`; phys: `-retime`) | retiming | UG901, UG904 |
| `register_duplication` | synth | `method` (keep_equivalent, force_replication), `nets` | `-keep_equivalent_registers`, or forced replication | UG901, UG904 |
| `pblock` | constraint | `name`, `regions` (site ranges), `cells` | a pblock; refused if it overlaps another, mixes site types, or holds under 30 % headroom over the design's LUTs | UG903, UG949 |
| `synth_option` | synth | `option` (flatten_hierarchy, fsm_extraction, shreg_min_size, resource_sharing, retiming, keep_equivalent_registers, fanout_limit), `value` | one allowed `synth_design` option | UG901 |

**Not recipes, on purpose:** `set_clock_uncertainty` (a recipe that closes by moving the target is not closure; the flow's separate build.yaml
`timing_margin_ns` is taken off before routing), any timing exception (multicycle, false path, clock groups: those go through the exception check and the
spec), any new clock, `source`, `exec`. The renderer's output is scanned against an allow-list of commands and a forbidden pattern before it is returned
(`guard_rendered_tcl`); a stage-6 call carries `recipe` and `params` only (`guard_stage6_args`).

**Device families.** From the family matrix (`areas/toolflow.yaml`, `areas/design_goals.yaml`): `phys_opt_design` fanout, placement, rewire, retime and
DSP/BRAM register options are common to 7-series and UltraScale+; auto-pipelining and SLR-crossing optimisation need UltraScale or later and are **not
recipes** here. The SLR-only placement directives (`SSI_*`) are refused on a monolithic part. No rule here is stated for a family it was not measured or documented for.

## The validators

Before (``pre``): parameter types and ranges, the device family, no clash with what the plan already holds (a step with a directive takes no second one),
legal site ranges, net names that appear in the build's reports when they are known. After (`post_check`, on the measured result): the run finished; a
setup slack was parsed; **the clock period is unchanged**; hold slack did not become newly negative; LUT+FF grew by no more than 25 % over the parent; no budget newly exceeded.
Valid is not better: a valid candidate that does not beat its parent by more than the 0.05 ns placement noise (178) is rolled back. Rollback is returning
to the parent plan, which is immutable, and to the checkpoint the search kept; the `Journal` records every application, verdict and rollback.

## The order

`closure_search.order` builds the legal calls from (1) the failing report's path classes, (2) the family matrix (what is not offered is not generated) and (3)
recorded past gains per recipe, from the OTHER designs only, shrunk towards zero (`n / (n + 3)`). Rules lead; priors adjust (a prior gain of +0.25 ns
is worth 10 weight points):

| path class (from `worst_path.rpt` or the build digest) | first calls |
|---|---|
| hold slack negative | post-route `phys_opt_design -hold_fix` |
| a net with fanout of 100 or more on the path | `fanout_replicate`, `phys_opt` fanout and placement, `max_fanout` |
| 4 or more logic levels | `retime` in synthesis, AMD's retiming strategy |
| routing at least 55 % of the path delay | AMD's NetDelay_high and ExtraTimingOpt sets, wirelength-driven placement |
| utilisation of 70 % or more | the congestion sets |
| always | the performance sweep in the order the 178 evaluation found useful, the named sets, one post-route `phys_opt` pass |

The thresholds are first values chosen before the measurement, not fitted; they change only with a dated note and a measurement.

## The search

`closure_search.search(root_outcome, features, ctx, runner, budget=6, beam=3, margin=...)`: the root is the build the loop already has (not counted as a run).
Level 1 runs the best-ranked calls from the root, one at a time (up to `beam` of them); level 2 adds the next compatible call to the best node so far; a plan that
already ran is not run twice; a call whose synthesis checkpoint is not available costs no Vivado run. It stops when timing is met with the margin, when the budget is spent,
when no further recipe applies, or **before any run when the failing slack is worse than -1.5 ns** (no recorded directive or option sweep gained more than 0.69 ns; that
design goes back to the RTL loop of `closure.py`).

## Where it plugs in

Stage 6 today is the RTL-edit loop (`agent/graph/closure.py`, `closure_playbook.py`); there is no free-form Tcl tool in stage 6 (`test_stage6_has_no_tool_that_takes_tcl`).
The recipe search is the implementation-level step that belongs before an RTL edit: the playbook's `t_impl` entry ("implementation directives or strategies") is
still `phase="later"`. This brief builds the recipe layer, its guard, the search and the Vivado runner and measures them on recorded post-synthesis checkpoints.
It does **not** change a prompt, a gate or the default flow, so no request golden or prompt pin changes. Wiring `closure.graph_stage` to call the search first
(and the Designer or controller to choose recipes through a tool whose schema is `recipes.menu_text()`) is a follow-up that needs its own prompt change and golden.

## Part 3 (scoped, not built): a RapidWright post-route ECO stage

Plan, for the planner's go. **Not built here**, as the brief says: parts 1 and 2 did not show a gain that justifies it (results README).

* **What it is.** A stage after `route_design`, before the stage-6 gates: read `post_route.dcp` with RapidWright (the 100 and 102 work already reads and writes
  Vivado 2026.1 checkpoints for K26 and Artix-7: `flow/rw/*`), apply typed ECO steps to the worst endpoints' nets (rip-up and re-route with RWRoute on the critical nets,
  replication of a high-fanout driver, re-placement of one cell into a better site), write the checkpoint, let Vivado verify it.
* **Typed, like the recipes.** ECO steps are named with typed parameters and validators (net names from the report, site legality from the device model, a cap on the number of cells moved); no free-form
  Java or Python is accepted. PACT (2608.23602, FPT 2026) reports that typed Vivado and RapidWright skills with evidence-gated cases reached +22.30 % Fmax geomean on 35 UltraScale+ checkpoints at $0.16 per
  checkpoint, against +9.78 % for a free-form agent and +15.14 % for DATuner (211 landscape study; abstract-level reading, numbers are theirs).
* **The equivalence check.** For a place-and-route-only change: the logical netlist before and after must be identical (`write_edif` of both, compared ignoring placement attributes), Vivado `report_route_status` must show no routing
  errors, `report_drc` and `check_timing` must be clean, and timing is re-run by Vivado, never taken from RapidWright. For a change that touches logic (replication of a driver): `eqy` on the pre and post netlists (the
  102 work: eqy proved a 16-bit block in seconds and did not finish 32 or 64 bits in 120 s, so the replication case is limited to small cones, and is refused beyond them).
* **Comparison with PACT's numbers.** On the FPL'26 Agentic FPGA Backend contest harness (AMD/Xilinx, public starter repo, five finalists; methods not read in 211). Needs: the harness and its checkpoints
  (licence check first), UltraScale+ parts (our K26 flow covers xck26), the same Vivado version. Our numbers would be the geomean Fmax gain over the harness baseline per checkpoint, runs used and cost.
  The comparison is not made here and no PACT number is claimed as ours.
* **Estimate.** 3 to 5 working days of one executor for the typed ECO steps, the equivalence gate and tests; 10 to 20 Vivado checkpoint reads and re-timings per design (a few minutes each on K26,
  one heavy slot at a time); about $5 to $15 of model cost if an LLM chooses among the typed steps (a deterministic controller needs none). Risks: RapidWright's `RWRoute` on a design Vivado routed can
  leave Vivado unable to re-route (100: Artix-7 WNS -5.398 before, -5.36 after, i.e. the gain was small there); the 7-series support is thinner than UltraScale+; PACT's anonymous repository may not be reproducible.
* **Go/no-go rule proposed.** Build only if the recipe search leaves designs failing by a small, route-bound margin (the results README says how many did), since a post-route ECO addresses exactly those.
