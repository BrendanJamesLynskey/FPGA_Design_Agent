# Brief 216: closure recipes and knowledge-guided closure search, results

Typed timing-closure recipes with validators and rollback, a Tcl guard for stage 6, and a knowledge-guided budgeted search over them, measured on the five
recorded 178 blocks. **Nulls first: on the recorded 178 outcomes the guided order was no better than the tournament's menu order or random, and the live
runs do not change that.** The gains that appeared came from one recipe (retiming in synthesis), which the 178 evaluation already found, and they appeared
whether the order was guided or shuffled. Pre-registration: [preregistration.md](preregistration.md) (committed before any scored run).

## Results

Replay on recorded 178 outcomes (`replay.json`, no Vivado, level 1 only, n = 5 designs, priors from the other four designs): mean best routed-WNS gain over the root
at 6 runs is 0.14 ns guided, 0.152 menu order, 0.147 random; runs to reach within 0.05 ns of the pool's best are 3 guided, 2.2 menu, 2.43 random. Development evidence, not a confirming test.

Live (`records.jsonl`, `paired.json`, `live/*__*.json`; Vivado 2026.1; control = the recorded 178 default flow, not re-run; Vivado is deterministic, so no seeds and the spread is over designs):

| design | control WNS (ns) | guided | shuffled216 | shuffled217 |
|---|---|---|---|---|
| adder csel w64 (A7, 5.0 ns) | -0.426 | -0.426 (3 runs) | -0.426 (3 runs) | -0.309 (5 runs) |
| divider w16 (K26, 1.4 ns) | -0.031 | -0.031 (3) | -0.031 (3) | -0.031 (3) |
| isqrt w32 (K26, 1.4 ns) | 0.002 | 0.002 (3) | 0.002 (3) | 0.002 (3) |
| lzc w32 (K26, 1.4 ns) | -0.486 | 0.119 (1 run, timing met) | -0.486 (3) | 0.119 (2, timing met) |
| mac fabric (K26, 3.0 ns) | -0.161 | 0.057 (6, budget spent) | -0.161 (3) | 0.057 (6, budget spent) |

* **Mean paired WNS gain over the control** (95 % paired bootstrap over 5 designs; better/worse/same; exact sign test): guided 0.165 ns [0.0, 0.407], 2/0/3, p = 0.5; shuffled216 0.0 [0.0, 0.0], 0/0/5;
  shuffled217 0.188 [0.023, 0.407], 3/0/2, p = 0.25. The arms disagree with each other, so the recipe menu's gain is **not shown to be robust** (exploratory, as pre-registered: it changes the menu and the order together).
* **The order (the only confirming-style comparison):** guided minus shuffled216 0.165 ns [0.0, 0.407], p = 0.5 (it differs only on lzc and mac, where shuffled216 never tried retiming in synthesis); guided minus shuffled217 -0.023 ns [-0.07, 0.0] (the adder, where shuffled217 found a 0.117 ns gain
  that guided did not). **No detectable effect of the order.** Power line: only a mean gain of about 0.3 ns was detectable with 5 designs, and the closure counts cannot be tested (a 5-pair sign test cannot go below p = 0.0625).
* **Where the gains came from:** `retime` in synthesis (lzc +0.605 ns, mac +0.218 ns; its cost is flip-flops, as 178 found) and, on the adder in one arm, the `Performance_WLBlockPlacement` strategy (+0.117 ns, still failing at -0.309 ns). The 178 evaluation had found `retime` before this brief. Over all arms the 18 rolled-back nodes were mostly AMD strategies (NetDelay_high, Retiming, Explore) and named sets that did not beat the parent by more than the 0.05 ns noise.
* **Closure:** lzc and mac go from failing to meeting timing (setup and hold) in the guided and shuffled217 arms; the adder (still -0.309 or -0.426 ns) and divider (-0.031 ns) do not close; isqrt had closed at +0.002 ns and gained nothing. The lzc Fmax of 780.6 MHz is above the K26 clock-buffer cap of 725.2 MHz and is **over cap: compare WNS, not Fmax**.
* **Vivado runs used:** 3 for most tasks (level 1 stops when no candidate beats the root, so level 2 never runs), 1 to 2 where timing was met early, 5 to 6 on the adder and mac when something was kept. Not a cost saving: the control is one run.
* **Measured Vivado 2026.1 behaviour:** `phys_opt_design -fanout_opt` is refused after routing ("Option -fanout_opt is specified but not supported yet for post-route physical synthesis"); the recipes refuse it (`POST_ROUTE_REFUSED`) and replication runs after placement.

## Records

* [preregistration.md](preregistration.md): arms, designs, outcomes, power line, run hygiene, decision rule, written before the first scored run.
* [replay.json](replay.json): the replay of the order on the recorded 178 outcomes.
* [records.jsonl](records.jsonl), [paired.json](paired.json): one row per (arm, design); paired effects with intervals and sign tests (`tools/stats/fpga_ablate.py`, CVDP's `ablate.py` bootstrap).
* [live/](live/): per task the full search tree (every node: recipe, parameters, reason, WNS, verdict) and each design's `cache.json` of Vivado outcomes (a plan runs once per design and is reused across arms; each arm still counts it as its own run).
* Code: `agent/graph/closure_recipes.py`, `agent/graph/closure_search.py`, `flow/closure_recipe_run.py`, `tools/qor/run_216_eval.py`, `tools/qor/closure_recipe_replay.py`; docs [docs/closure_recipes.md](../../docs/closure_recipes.md); tests `agent/tests/test_216_closure_recipes.py`.

## Reproduce

```
python3 tools/qor/closure_recipe_replay.py            # the replay, no Vivado
python3 -m pytest agent/tests/test_216_closure_recipes.py
python3 tools/qor/run_216_eval.py stage               # needs the 178 post-synthesis checkpoints (EVAL216_SRC)
python3 tools/qor/run_216_eval.py run                 # Vivado 2026.1, one heavy slot per task; finished tasks are skipped
python3 tools/qor/run_216_eval.py summary             # records.jsonl and paired.json
```

## Known gaps and limits

* 5 designs, one run each per arm and no seeds (deterministic flow): a direction, not a rate. The 209 pilot designs, c14/c15 and the course designs were not run (no recorded post-synthesis checkpoints; they need agent runs).
* The recipes that were new here (post-route `phys_opt` options, fanout replication, pblocks, `max_fanout`) were almost never exercised: no path had a net with fanout of 100 or more, no pblock hint was given, and one post-route `phys_opt` run was rolled back. **Their value is untested**; only the retiming and strategy recipes were measured.
* The search stops at level 1 when nothing beats the root, so it used 3 of 6 runs on most tasks; combinations (level 2) were reached on the adder and mac only.
* Each candidate runs the full flow from the default post-synthesis checkpoint (post-route recipes are not run on a parent's routed checkpoint). Synthesis-level recipes use only the checkpoints 178 kept (default, retime, keep_eq).
* The rules' thresholds are first values, not fitted. The LATCH and PACT comparisons were not run. Part 3 (RapidWright ECO) is scoped in docs/closure_recipes.md, not built; its go/no-go rule needs designs that fail by a small, route-bound margin, and here the unclosed designs (adder -0.3 to -0.4 ns, divider -0.031 ns) are such cases, so a post-route ECO is the more promising next step than a better order.
* Not wired into `closure.graph_stage`: it is opt-in code and tests; no prompt, gate or default changed.
