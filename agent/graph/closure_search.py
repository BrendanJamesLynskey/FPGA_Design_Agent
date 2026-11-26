"""Brief 216: knowledge-guided, budgeted search over closure recipes.

For a design that misses timing (or closes with little margin), :func:`order` ranks concrete recipe calls from three sources that
are all recorded, none of them a model's opinion:

1. **path classes** of the failing report (``Features``: logic levels, fanout, routing share, hold, utilisation, destination pin),
   through the rules in :data:`RULES`, each with the knowledge-bank row or report it comes from;
2. **the family matrix**: a recipe not offered on the device family is not generated (``closure_recipes`` checks ``Context.family``);
3. **past results**: the mean routed-WNS gain of each recipe in the recorded runs (:class:`Priors`, built from
   ``results/178_tournament``), shrunk towards zero when seen on few designs, never including the design being ordered.

:func:`search` explores a small tree, depth at most 2, within a budget of implementation runs: the root is the default flow's result;
level 1 runs the best-ranked recipes one at a time from the root; level 2 adds the next compatible recipe to the best level-1 node. Every
result goes through the recipe's ``post_check`` and is kept only if it scores better than its parent (otherwise rolled back); the best
checkpoint is kept. The search stops when timing is met with the requested margin, when the budget is spent, or when the failing
slack is so large that no implementation recipe can plausibly close it (the RTL loop of ``closure.py`` takes over then).

The runner is a callable, so the tests use recorded reports and the live runs use ``flow.closure_recipe_run``.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent.graph import closure_recipes as R

ROOT = Path(__file__).resolve().parents[2]
#: a failing slack worse than this is beyond what the recorded directive and option sweeps ever closed (178: best gain 0.69 ns): hand it to the RTL loop
HOPELESS_WNS_NS = -1.5
#: shrinkage of a recipe's mean past gain: n / (n + K) of the mean, so one design's win counts for a quarter
SHRINK_K = 3.0
NOISE_NS = 0.05                                    # 178: differences under ~0.05 ns are inside placement noise; a candidate must beat its parent by more


@dataclass
class Features:
    """What the failing report says about the design (all optional: an unknown feature triggers no rule)."""
    wns_ns: float | None = None
    whs_ns: float | None = None
    logic_levels: int | None = None
    carry_chain: int | None = None
    max_fanout: int | None = None
    fanout_nets: tuple[str, ...] = ()
    route_pct: float | None = None                  # share of the worst path's delay that is routing
    destination: str = ""
    util_pct: float | None = None                   # the largest of LUT/FF use, percent of the device
    clock_ns: float | None = None

    @classmethod
    def from_digest(cls, dg: dict[str, Any]) -> "Features":
        """From ``flow.digest.build`` output (the shape closure.py reads: ``timing``, ``setup_path``, ``setup_features``)."""
        p, f, t = dg.get("setup_path") or {}, dg.get("setup_features") or {}, dg.get("timing") or {}
        return cls(wns_ns=t.get("wns_ns"), whs_ns=t.get("whs_ns"), logic_levels=f.get("logic_levels") or p.get("logic_levels"),
                   carry_chain=f.get("carry_chain"), max_fanout=f.get("max_fanout"),
                   fanout_nets=tuple(x for x in [f.get("max_fanout_net")] if x), route_pct=p.get("route_pct"),
                   destination=str(p.get("destination") or ""), clock_ns=t.get("period_ns"))


# ---- rules: path class -> recipe calls, with a weight and the reason --------------------------------------------------------------
def _calls(f: Features, family: str) -> list[tuple[str, dict[str, Any], float, str]]:
    """Every (recipe, params, rule weight, reason) the features support. The weight orders rules; priors adjust within and across them."""
    out: list[tuple[str, dict[str, Any], float, str]] = []
    w = f.wns_ns if f.wns_ns is not None else 0.0
    route_bound = f.route_pct is not None and f.route_pct >= 55
    logic_bound = f.logic_levels is not None and f.logic_levels >= 4
    if f.whs_ns is not None and f.whs_ns < 0:
        out.append(("phys_opt_options", {"step": "post", "flags": ["hold_fix"]}, 90, f"hold slack {f.whs_ns} ns is negative: the hold repair pass"))
    if f.max_fanout and f.max_fanout >= 100 and f.fanout_nets:
        out.append(("fanout_replicate", {"nets": list(f.fanout_nets)[:4]}, 80, f"net {f.fanout_nets[0]} drives {f.max_fanout} loads on the failing path"))
        out.append(("max_fanout", {"nets": list(f.fanout_nets)[:4], "limit": 100}, 55, f"high-fanout net {f.fanout_nets[0]} ({f.max_fanout}): MAX_FANOUT"))
        out.append(("phys_opt_options", {"step": "phys", "flags": ["fanout_opt", "placement_opt"]}, 60, f"fanout {f.max_fanout} on the path"))
    if logic_bound:
        out.append(("retime", {"where": "synth"}, 70, f"{f.logic_levels} logic levels: retiming moves registers across the logic"))
        out.append(("amd_strategy", {"name": "Performance_Retiming"}, 62, f"{f.logic_levels} logic levels: AMD's retiming implementation set"))
    if route_bound:
        out.append(("amd_strategy", {"name": "Performance_NetDelay_high"}, 68, f"routing is {f.route_pct:.0f} % of the path delay"))
        out.append(("amd_strategy", {"name": "Performance_ExtraTimingOpt"}, 66, f"routing is {f.route_pct:.0f} % of the path delay"))
        out.append(("amd_strategy", {"name": "Performance_WLBlockPlacementFanoutOpt"}, 58, "routing-bound path: wirelength-driven placement"))
    if f.util_pct is not None and f.util_pct >= 70:
        out.append(("amd_strategy", {"name": "Congestion_SpreadLogic_high"}, 64, f"utilisation {f.util_pct:.0f} %: spread logic and route congestion-aware"))
    out += [("impl_set", {"name": n}, 28 - i, "a named directive set from the 178 tournament menu") for i, n in enumerate(
        ("aggressive", "extra_timing", "explore", "congestion", "extra_netdelay"))]
    # always offered, in the order the 178 evaluation found useful (the six menu sets and the AMD performance sets); weights below the path rules
    out += [("amd_strategy", {"name": n}, 30 - i, "the general performance sweep") for i, n in enumerate(
        ("Performance_Explore", "Performance_ExtraTimingOpt", "Performance_RefinePlacement", "Performance_NetDelay_high", "Performance_ExplorePostRoutePhysOpt",
         "Performance_WLBlockPlacement"))]
    out.append(("phys_opt_options", {"step": "post", "flags": ["fanout_opt", "placement_opt", "rewire", "critical_cell_opt"]}, 25,
                "a post-route phys_opt pass on the routed checkpoint (cheap: no re-placement)"))
    if w < -0.3 and not logic_bound:
        out.append(("retime", {"where": "phys"}, 20, "a large miss with no clear path class: phys_opt retiming"))
    return out


def _key(rid: str, args: dict[str, Any]) -> str:
    """The identity of a recipe call, for the priors table: recipe plus the one parameter that names it."""
    if rid == "amd_strategy":
        return "amd:" + args["name"]
    if rid == "impl_set":
        return args["name"]
    if rid == "retime":
        return "retime:" + args["where"]
    if rid == "phys_opt_options":
        return f"phys:{args['step']}:" + "+".join(sorted(args["flags"]))
    return rid


@dataclass
class Priors:
    """Mean routed-WNS gain over the default flow, per recipe call, from recorded runs, with the number of designs behind each."""
    gain: dict[str, list[float]] = field(default_factory=dict)       # key -> one gain per design
    designs: dict[str, list[str]] = field(default_factory=dict)

    def add(self, design: str, key: str, g: float) -> None:
        self.gain.setdefault(key, []).append(g)
        self.designs.setdefault(key, []).append(design)

    def score(self, key: str, exclude: str | None = None) -> float:
        xs = [g for g, d in zip(self.gain.get(key, []), self.designs.get(key, [])) if d != exclude]
        return 0.0 if not xs else (sum(xs) / len(xs)) * len(xs) / (len(xs) + SHRINK_K)

    def n(self, key: str, exclude: str | None = None) -> int:
        return sum(1 for d in self.designs.get(key, []) if d != exclude)

    @classmethod
    def from_178(cls, root: Path | None = None) -> "Priors":
        """Gain of each implementation set over the default implementation **of the same synthesis**, per design, from ``results/178_tournament/runs``
        (so the synthesis choice never leaks into an implementation recipe's gain). Identical results of two synthesis candidates (same WNS, LUT, FF)
        count once. ``retime:synth`` is the gain of the ``retime`` synthesis with default place and route over the default synthesis."""
        root = root or ROOT / "results" / "178_tournament" / "runs"
        pr = cls()
        for dd in sorted(root.glob("*")):
            try:
                base = json.loads((dd / "impl_base.json").read_text())
                top = json.loads((dd / "impl_top2.json").read_text())
            except (OSError, ValueError):
                continue
            ok = [c for c in top["candidates"] if c.get("status") == "ok" and c.get("wns_ns") is not None]
            b0 = next((c for c in base["candidates"] if c["id"] == "default/default" and c.get("wns_ns") is not None), None)
            per_syn: dict[str, dict[str, float]] = {}
            for c in ok:
                syn, _, imp = c["id"].partition("/")
                per_syn.setdefault(syn, {})[imp] = c["wns_ns"]
            seen_sets: list[dict[str, float]] = []
            for syn, imps in per_syn.items():
                if "default" not in imps or imps in seen_sets:
                    continue
                seen_sets.append(imps)
                if syn in ("retime", "perf_retime") and b0:
                    pr.add(dd.name, "retime:synth", imps["default"] - b0["wns_ns"])
                for imp, w in imps.items():
                    if imp != "default":
                        pr.add(dd.name, imp, w - imps["default"])
        return pr


# ---- ordering -----------------------------------------------------------------------------------------------------------------------------
@dataclass
class Call:
    recipe: str
    args: dict[str, Any]
    weight: float
    prior: float
    n_prior: int
    reason: str

    @property
    def score(self) -> float:
        return self.weight + 40.0 * self.prior          # a prior of +0.25 ns is worth 10 weight points: past data adjusts, rules lead

    @property
    def key(self) -> str:
        return _key(self.recipe, self.args)


def order(f: Features, plan: R.ImplPlan, ctx: R.Context, priors: Priors | None = None, *, exclude: str | None = None) -> list[Call]:
    """Every legal recipe call for the plan, best first. A call that the recipe's own checks refuse (family, clash with the plan) is left out."""
    priors = priors or Priors()
    seen, out = set(), []
    for rid, args, wt, why in _calls(f, ctx.family):
        try:
            R.apply_recipe(plan, rid, args, ctx)
        except R.RecipeError:
            continue
        k = _key(rid, args)
        if k in seen:
            continue
        seen.add(k)
        out.append(Call(rid, args, float(wt), priors.score(k, exclude), priors.n(k, exclude), why))
    return sorted(out, key=lambda c: (-c.score, c.key))


# ---- search ---------------------------------------------------------------------------------------------------------------------------------
Runner = Callable[[R.ImplPlan, str], dict[str, Any]]      # (plan, node id) -> {status, wns_ns, tns_ns, whs_ns, lut, ff, clock_ns, runtime_s, ...}


def better(a: dict[str, Any], b: dict[str, Any], margin: float = 0.0) -> bool:
    """True when result ``a`` beats ``b``: failed runs lose; setup slack decides (a gain must exceed the 0.05 ns noise); once both reach the
    target ``margin`` the smaller netlist wins."""
    if a.get("status") != "ok" or a.get("wns_ns") is None:
        return False
    if b.get("status") != "ok" or b.get("wns_ns") is None:
        return True
    d = a["wns_ns"] - b["wns_ns"]
    if b["wns_ns"] >= margin and a["wns_ns"] >= margin:        # both at the target: the smaller netlist, then slack
        return (a.get("lut", 0) + a.get("ff", 0), -a["wns_ns"]) < (b.get("lut", 0) + b.get("ff", 0), -b["wns_ns"])
    return d > NOISE_NS


def met(r: dict[str, Any], margin: float = 0.0) -> bool:
    return r.get("status") == "ok" and (r.get("wns_ns") or -1e9) >= margin and (r.get("whs_ns") if r.get("whs_ns") is not None else 0.0) >= 0.0


@dataclass
class Node:
    id: str
    plan: R.ImplPlan
    outcome: dict[str, Any]
    parent: str | None
    call: dict[str, Any] | None = None
    kept: bool = False
    verdict: str = ""


@dataclass
class SearchResult:
    best: Node
    nodes: list[Node]
    runs: int
    stop: str
    journal: R.Journal
    hopeless: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"best": self.best.id, "best_wns_ns": self.best.outcome.get("wns_ns"), "best_plan": self.best.plan.to_dict(), "runs": self.runs,
                "stop": self.stop, "hopeless": self.hopeless,
                "nodes": [{"id": n.id, "parent": n.parent, "call": n.call, "wns_ns": n.outcome.get("wns_ns"), "whs_ns": n.outcome.get("whs_ns"),
                           "lut": n.outcome.get("lut"), "ff": n.outcome.get("ff"), "status": n.outcome.get("status"), "kept": n.kept,
                           "verdict": n.verdict} for n in self.nodes],
                "rolled_back": self.journal.rolled_back()}


def search(root_outcome: dict[str, Any], features: Features, ctx: R.Context, runner: Runner, *, budget: int = 6, beam: int = 3,
           margin: float = 0.0, priors: Priors | None = None, exclude: str | None = None, root_plan: R.ImplPlan | None = None,
           ordering: Callable[[Features, R.ImplPlan, R.Context], list[Call]] | None = None) -> SearchResult:
    """Explore at most ``budget`` implementation runs (the root's run is not counted: it is the build the loop already has).

    ``ordering`` replaces the knowledge-guided order (the baselines in the evaluation use it: menu order, random)."""
    plan0 = root_plan or R.ImplPlan()
    root = Node("n0", plan0, root_outcome, None, kept=True, verdict="root")
    nodes, journal, runs = [root], R.Journal(), 0
    best = root
    ordf = ordering or (lambda f, p, c: order(f, p, c, priors, exclude=exclude))

    def stop(why: str, hopeless: bool = False) -> SearchResult:
        return SearchResult(best, nodes, runs, why, journal, hopeless)

    if met(root_outcome, margin):
        return stop("the root already meets timing")
    if (root_outcome.get("wns_ns") is not None and root_outcome["wns_ns"] < HOPELESS_WNS_NS):
        return stop(f"setup slack {root_outcome['wns_ns']} ns is beyond the recorded reach of implementation recipes ({HOPELESS_WNS_NS} ns): "
                    "back to the RTL loop", hopeless=True)

    def try_call(parent: Node, c: Call) -> Node | None:
        nonlocal runs, best
        try:
            plan = R.apply_recipe(parent.plan, c.recipe, c.args, ctx)
        except R.RecipeError as e:
            journal.record(parent.plan, c.recipe, c.args, "refused", [str(e)], True)
            return None
        if any(n.plan.key() == plan.key() for n in nodes):
            return None                                           # the same plan was run: no second run
        runs += 1
        nid = f"n{len(nodes)}"
        out = runner(plan, nid)
        if str(out.get("status", "")).startswith("no synth checkpoint"):      # nothing ran: not a Vivado run, not a failure
            runs -= 1
            journal.record(parent.plan, c.recipe, c.args, "unavailable", [out["status"]], True, out)
            nodes.append(Node(nid, plan, out, parent.id, {"recipe": c.recipe, "args": c.args}, verdict="unavailable: " + out["status"]))
            return None
        why = R.post_check(parent.outcome, out, ctx)
        node = Node(nid, plan, out, parent.id, {"recipe": c.recipe, "args": c.args, "reason": c.reason, "weight": c.weight, "prior": round(c.prior, 4)})
        if why:
            node.verdict = "invalid: " + "; ".join(why)
            journal.record(parent.plan, c.recipe, c.args, "invalid", why, True, out)
        elif better(out, parent.outcome, margin):
            node.kept, node.verdict = True, "kept"
            journal.record(parent.plan, c.recipe, c.args, "kept", [], False, out)
            if better(out, best.outcome, margin):
                best = node
        else:
            node.verdict = "rolled back: not better than its parent"
            journal.record(parent.plan, c.recipe, c.args, "not_better", [], True, out)
        nodes.append(node)
        return node

    # level 1: the top-ranked calls from the root, one at a time
    level1: list[Node] = []
    for c in ordf(features, plan0, ctx)[:max(beam, 1) * 2]:
        if runs >= budget or len(level1) >= beam:
            break
        n = try_call(root, c)
        if n is not None:
            level1.append(n)
            if met(n.outcome, margin) and not n.verdict.startswith("invalid"):
                return stop("timing met")
    # level 2: from the best node so far, the next calls that fit beside what it already has
    while runs < budget and best is not root:
        tried = False
        for c in ordf(features, best.plan, ctx):
            if runs >= budget:
                break
            n = try_call(best, c)
            if n is not None:
                tried = True
                if met(n.outcome, margin) and not n.verdict.startswith("invalid"):
                    return stop("timing met")
                break                                             # re-rank from the (possibly new) best
        if not tried:
            break
    return stop("budget spent" if runs >= budget else "no further recipe applies")


# ---- baselines for the evaluation ------------------------------------------------------------------------------------------------------------------
def shuffled(seed: int) -> Callable[[Features, R.ImplPlan, R.Context], list[Call]]:
    def f(feat: Features, plan: R.ImplPlan, ctx: R.Context) -> list[Call]:
        cs = order(feat, plan, ctx, None)
        random.Random(seed).shuffle(cs)
        return cs
    return f
