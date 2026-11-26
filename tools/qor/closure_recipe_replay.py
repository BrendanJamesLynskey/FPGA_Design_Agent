#!/usr/bin/env python3
"""Brief 216: replay the recipe search on the recorded 178 tournament outcomes (no Vivado).

For each of the five 178 designs the root is the first-ranked synthesis candidate with default place and route (recorded), and the pool is
that synthesis' recorded implementation sets (4 AMD strategy sets and 5 named directive sets; the pool differs per design only by what ran).
A search is run with a budget of B implementation runs, level 1 only (a second-level combination was never recorded), under three orders:

* guided: ``closure_search.order`` with priors from the OTHER four designs (leave-one-design-out) and the path-class rules (only the
  features the recorded reports carry: setup slack and logic levels);
* menu: the tournament's own table order (named sets, then AMD sets in the strategy file's order);
* random: the expected value over 2000 shuffles of the pool.

Outcome (graded): best routed WNS reached within B runs, as a gain over the root; and runs to reach a result within 0.05 ns of the pool's best
(the noise level, 178). n = 5 designs: a direction, not a rate.

    python3 tools/qor/closure_recipe_replay.py            # writes results/216_closure_recipes/replay.json and prints the table
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.graph import closure_recipes as R          # noqa: E402
from agent.graph import closure_search as S           # noqa: E402
from flow import tournament as T                      # noqa: E402

RUNS = ROOT / "results" / "178_tournament" / "runs"
OUT = ROOT / "results" / "216_closure_recipes" / "replay.json"
BUDGETS = (1, 2, 3, 4, 6, 9)
NOISE = 0.05


def pool_plans(ctx: R.Context) -> dict[str, tuple[str, dict, str]]:
    """plan key -> (recipe, args, pool name) for every recorded implementation set."""
    out = {}
    for n in R._strategies():
        try:
            out[R.apply_recipe(R.ImplPlan(), "amd_strategy", {"name": n}, ctx).key()] = ("amd_strategy", {"name": n}, "amd:" + n)
        except R.RecipeError:
            pass
    for n in R.IMPL_SETS:
        out[R.apply_recipe(R.ImplPlan(), "impl_set", {"name": n}, ctx).key()] = ("impl_set", {"name": n}, n)
    return out


def design_data(dd: Path) -> tuple[str, dict, dict[str, dict]]:
    top = json.loads((dd / "impl_top2.json").read_text())
    syn = min((c for c in top["candidates"] if c.get("status") == "ok"), key=lambda c: c["rank"])["id"].split("/")[0]
    by = {c["id"].split("/", 1)[1]: c for c in top["candidates"] if c["id"].startswith(syn + "/") and c.get("status") == "ok"}
    return syn, by["default"], {k: v for k, v in by.items() if k != "default"}


def main() -> None:
    ctx = R.Context(family="ultrascale+")           # the K26 rows; the adder is a 7-series row, where no pool entry is SLR-only either
    plans = pool_plans(ctx)
    designs = {d.name: design_data(d) for d in sorted(RUNS.glob("*"))}
    rows = []
    for name, (syn, root, pool) in designs.items():
        priors_all = S.Priors.from_178()
        pool_by_plan = {k: pool[v[2]] for k, v in plans.items() if v[2] in pool}
        feats = S.Features(wns_ns=root["wns_ns"], logic_levels=root.get("levels"))
        valid = {k: c for k, c in pool_by_plan.items() if not R.post_check({**root, "clock_ns": 1.0}, {**c, "status": "ok", "clock_ns": 1.0}, ctx)}
        best_pool = max(c["wns_ns"] for c in valid.values())      # the best a validator-clean candidate reached

        def runner(plan, nid, _p=pool_by_plan):
            return {**_p[plan.key()], "status": "ok", "clock_ns": 1.0}

        def only_recorded(calls, _p=pool_by_plan):
            keep = []
            for c in calls:
                try:
                    if R.apply_recipe(R.ImplPlan(), c.recipe, c.args, ctx).key() in _p:
                        keep.append(c)
                except R.RecipeError:
                    pass
            return keep

        menu_keys = [n for n in R.IMPL_SETS] + [n for n in R._strategies()]
        order_menu = [Cl for Cl in (S.Call("impl_set" if n in R.IMPL_SETS else "amd_strategy", {"name": n}, 0, 0, 0, "menu order") for n in menu_keys)]
        res = {}
        for B in BUDGETS:
            row = {}
            for arm, ordering in (("guided", lambda f, p, c: only_recorded(S.order(f, p, c, priors_all, exclude=name))),
                                  ("menu", lambda f, p, c: only_recorded(order_menu))):
                r = S.search(root, feats, ctx, runner, budget=B, beam=B, ordering=ordering, margin=1e9)
                reach = next((i for i, n in enumerate(r.nodes[1:], 1) if n.outcome["wns_ns"] >= best_pool - NOISE), None)
                row[arm] = {"best_gain": round(max(n.outcome["wns_ns"] for n in r.nodes if not n.verdict.startswith("invalid")) - root["wns_ns"], 3), "runs": r.runs, "runs_to_best": reach}
            vals = []
            rng = random.Random(216)
            allc = [c for c in pool_by_plan.values() if c in valid.values()]
            for _ in range(2000):
                rng.shuffle(allc)
                head = allc[:B]
                vals.append(max([root["wns_ns"]] + [c["wns_ns"] for c in head]) - root["wns_ns"])
            row["random"] = {"best_gain": round(statistics.mean(vals), 3)}
            res[B] = row
        # runs to within noise of the pool's best, over the whole pool
        rt = {}
        for arm, ordering in (("guided", lambda f, p, c: only_recorded(S.order(f, p, c, priors_all, exclude=name))), ("menu", lambda f, p, c: only_recorded(order_menu))):
            r = S.search(root, feats, ctx, runner, budget=len(pool_by_plan), beam=len(pool_by_plan), ordering=ordering, margin=1e9)
            rt[arm] = next((i for i, n in enumerate(r.nodes[1:], 1) if n.outcome["wns_ns"] >= best_pool - NOISE), None)
        rng = random.Random(7)
        allc = [c for c in pool_by_plan.values() if c in valid.values()]
        pos = []
        for _ in range(2000):
            rng.shuffle(allc)
            pos.append(next(i for i, c in enumerate(allc, 1) if c["wns_ns"] >= best_pool - NOISE))
        rt["random"] = round(statistics.mean(pos), 2)
        rows.append({"design": name, "root_synth": syn, "root_wns_ns": root["wns_ns"], "pool_best_wns_ns": best_pool, "pool_size": len(pool_by_plan), "pool_valid": len(valid),
                     "by_budget": res, "runs_to_within_noise_of_pool_best": rt})
    summary = {}
    for B in BUDGETS:
        summary[B] = {arm: round(statistics.mean(r["by_budget"][B][arm]["best_gain"] for r in rows), 3) for arm in ("guided", "menu", "random")}
    out = {"note": "replay on recorded 178 outcomes, level 1 only; n=5 designs; gain = routed WNS over the root (ns)", "rows": rows,
           "mean_best_gain_by_budget": summary,
           "mean_runs_to_within_noise": {arm: round(statistics.mean(r["runs_to_within_noise_of_pool_best"][arm] for r in rows), 2)
                                         for arm in ("guided", "menu", "random")}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("mean_best_gain_by_budget", "mean_runs_to_within_noise")}, indent=1))
    for r in rows:
        print(r["design"], r["root_wns_ns"], "pool best", r["pool_best_wns_ns"], r["runs_to_within_noise_of_pool_best"])


if __name__ == "__main__":
    main()
