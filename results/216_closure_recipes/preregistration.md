# Brief 216: pre-registration (written 2026-11-26 06:40 GMT, before any scored Vivado run)

Stamped from `date`. Committed before the first live run; the replay (`replay.json`, no Vivado) was run first, while the code was being built, and is
reported as a development result, not as the confirming test of anything here.

## Question

Does choosing implementation changes from a typed recipe menu, ordered by path class, the family matrix and recorded past gains, reach better routed
timing within a fixed budget of Vivado runs than the default implementation flow, and does the order matter beyond the menu?

## Designs (n = 5) and why they are these

The five 178 tournament blocks: `adder_csel_a7_w64b16` (xc7a100t, 5.0 ns), `divider_restpipe_k26_w16`, `isqrt_restpipe_k26_w32`, `lzc_treebarrel_k26_w32`
(K26, 1.4 ns), `mac_fabric_k26` (K26, 3.0 ns). They were fixed by brief 178 (arithmetic points near their clock limit), not chosen by a failing control in
this brief; the recorded default flow gave -0.426, -0.031, +0.002, -0.486, -0.161 ns, so four miss timing and one closes with no margin.
The default flow is **not re-run** (Vivado is deterministic for the same input; the recorded outcome is the control), so there is no regression to the mean
from selecting on a noisy control.

**Not in this brief (deviation from the brief's list):** the 209 pilot designs, the c14/c15 designs from 209a and the three course designs. Their routed
checkpoints are not recorded as post-synthesis checkpoints; building them needs agent runs (about $4.43 each, 209) or whole-board builds, and the closure
step here starts from a post-synthesis checkpoint. They are a follow-up (the report says so).

## Arms

| arm | what it is |
|---|---|
| `control` | the default implementation flow from the default synthesis checkpoint (`opt_design`, `place_design`, `route_design`): recorded in 178, not re-run |
| `guided` | `closure_search.search`: budget 6 Vivado runs, beam 3, depth 2, order from `closure_search.order` with priors from the other four designs only (leave-one-design-out) and the path-class rules |
| `shuffled` | the same recipe menu, validators, budget and tree, but the order is a seeded shuffle of the legal calls (`closure_search.shuffled(seed)`), seeds 216, 217 |

`guided` against `control` changes two things at once (the recipe menu, which adds post-route phys_opt, fanout and retiming recipes, and the order): it is
**exploratory**. `guided` against `shuffled` changes one thing (the order) and is the only confirming-style comparison. The 178 menu sets and AMD strategies are
inside both menus; the 20-run exhaustive 178 sweep is reported as a reference ceiling, not as an arm.

Synthesis-level recipes (`retime where=synth`, `register_duplication keep_equivalent`) can only use the post-synthesis checkpoints 178 kept (`default`,
`retime`, `keep_eq`); a plan whose synthesis options have no checkpoint is recorded `unavailable`, costs no Vivado run, and is not counted against the budget.
Candidates start from the default synthesis checkpoint and run the full opt/place/route flow (a post-route recipe is not run on a parent's routed checkpoint
in this brief: more runs, simpler accounting).

## Outcomes

Graded, in order: (1) **routed WNS gain over the control** (ns) at the end of the budget, best validator-clean result; (2) Fmax = 1000 / (clock - WNS), with
the K26 725.2 MHz cap rule from 178c (an Fmax over the cap is shown "over cap" and is not quoted); (3) **Vivado runs used**; (4) the stop reason and the number
of validator rejections and rollbacks (`journal`); (5) LUT+FF change; (6) CPU seconds (no model is called, so no dollar cost). Closure success (WNS >= 0 and WHS >= 0)
is secondary and descriptive only.

## Power line

* Vivado place and route is deterministic for identical input, so repeating a run gives no spread: there are **no seeds**, and the spread reported is over designs.
* Paired bootstrap over the 5 designs (`tools/stats/fpga_ablate.py`, `ablate.bootstrap_mean`), 95 %, plus the exact sign test.
* Smallest detectable mean gain: the sample SD of the 178 per-design winner gains is 0.26 ns (178 `gain_summary.json`); with 5 pairs and t(4) = 2.776 the interval half-width is
  about 0.32 ns, so **only a mean paired gain of about 0.3 ns or more is detectable**. The 178 exhaustive sweep itself gained 0.014 to 0.651 ns, mean 0.274: a search with
  budget 6 is expected to sit below the detectable range. A null is the expected result and will be stated first.
* Pass rate cannot be tested: with 5 pairs the exact two-sided sign test cannot go below p = 0.0625 even if all 5 are better. Closure counts are descriptive. (The 226 figure of 23 to 26
  points is for agent runs, 6 designs at 3 runs; it does not apply to a deterministic flow.)
* The ordering question was also replayed on the recorded 178 outcomes without Vivado (`tools/qor/closure_recipe_replay.py`, level 1 only, leave-one-design-out priors): reported as development evidence.

## Run hygiene

* Run order: designs shuffled with seed 216; within a design the arms' order is shuffled by the same generator, and budget-guard checks (free memory, load) are evaluated in that same order.
* A run stopped by a refused slot, a load or memory guard, a plan limit or a Vivado process killed by the memory cap is recorded with its own stop reason (`slot_refused`, `memory_cap`, ...) and **re-run**; it is never scored as a failure
  of the arm. A run that Vivado itself finishes with a failure status is a result.
* One Vivado at a time, under `systemd-run --user --scope -p MemoryMax=<peak+1>G nice -n 15`, one heavy slot held for the whole sequence.
* Stop at 75 % weekly usage (`BLOCKED:`). No model is called in these runs.

## Decision rule (written now)

* `guided - control` mean paired WNS gain with interval excluding 0: reported as exploratory support; with the interval including 0: "no detectable effect".
* `guided - shuffled` is the only order claim: "the order matters" only if that interval excludes 0; otherwise "no detectable effect of the order".
* Nothing here changes a gate or the default flow; stage 6 recipe use stays opt-in (`docs/closure_recipes.md`).
