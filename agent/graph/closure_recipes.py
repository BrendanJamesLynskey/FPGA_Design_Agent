"""Brief 216: typed timing-closure recipes.

Stage 6 (timing closure) may change the implementation only by naming a **recipe** with typed parameters. A recipe is a pure
transformation of an :class:`ImplPlan` (the settings of each implementation step), with

- ``params``: a typed schema, checked before anything runs (an unknown name, a value outside its enum or range, a net name with a
  Tcl metacharacter is refused with a reason);
- ``pre``: what must be true before it is applied (device family, no clash with the plan so far, a legal region);
- ``post``: what must be true of the measured result for the candidate to count (the run finished, the clock was not touched, hold
  did not newly break, area stayed in budget);
- a rollback: a plan is immutable, so rolling back is returning to the parent plan and its checkpoint; the :class:`Journal` records
  every application, verdict and rollback.

There is one Tcl renderer (:func:`render_impl_tcl`), and it writes the text from fixed templates. Free-form Tcl is refused at stage 6
(:func:`guard_stage6_args`, :func:`guard_rendered_tcl`). Recipes never use ``set_clock_uncertainty`` and never write a timing
exception: a recipe that "closes" by moving the target is not closure (UG949 "Overconstraining the Design" is the flow's own,
separate, build.yaml ``timing_margin_ns``, which is taken off before routing).

Directive names are the ones in ``results/178_tournament/vendor_strategies.json`` (read from Vivado 2026.1 by the strategy probe) and
the tournament menu, not recalled: ``tests/test_216_closure_recipes.py`` checks every one of them is in :data:`DIRECTIVES`.
Device-family differences come from the knowledge bank's family matrix (``areas/toolflow.yaml``, ``areas/design_goals.yaml``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
VENDOR_STRATEGIES = ROOT / "results" / "178_tournament" / "vendor_strategies.json"

STEPS = ("opt", "place", "phys", "route", "post")        # post = phys_opt_design after route_design
#: ``-directive`` values per step (178 strategy probe + tournament menu); a value outside the step's set is refused
DIRECTIVES: dict[str, tuple[str, ...]] = {
    "opt": ("Default", "Explore", "ExploreArea", "ExploreSequentialArea", "ExploreWithRemap", "RuntimeOptimized"),
    "place": ("Default", "AltSpreadLogic_high", "AltSpreadLogic_low", "AltSpreadLogic_medium", "Auto_1", "Auto_2", "Auto_3",
              "EarlyBlockPlacement", "Explore", "ExtraNetDelay_high", "ExtraNetDelay_low", "ExtraPostPlacementOpt", "ExtraTimingOpt",
              "Quick", "RuntimeOptimized", "SSI_BalanceSLLs", "SSI_BalanceSLRs", "SSI_HighUtilSLRs", "SSI_SpreadLogic_high",
              "SSI_SpreadLogic_low", "SSI_SpreadSLLs", "WLDrivenBlockPlacement"),
    "phys": ("Default", "AggressiveExplore", "AggressiveFanoutOpt", "AlternateFlowWithRetiming", "Explore"),
    "route": ("Default", "AggressiveExplore", "AlternateCLBRouting", "Explore", "NoTimingRelaxation", "Quick", "RuntimeOptimized"),
    "post": ("Default", "Explore", "AggressiveExplore"),
}
#: directives that exist only for stacked-silicon (SLR) parts: refused on a monolithic part
SLR_ONLY = ("SSI_BalanceSLLs", "SSI_BalanceSLRs", "SSI_HighUtilSLRs", "SSI_SpreadLogic_high", "SSI_SpreadLogic_low", "SSI_SpreadSLLs")
#: ``phys_opt_design`` option flags a recipe may enable (UG904 ``phys_opt_design``; family matrix: "the rest of phys_opt_design is common")
PHYS_FLAGS = ("fanout_opt", "placement_opt", "rewire", "critical_cell_opt", "dsp_register_opt", "bram_register_opt", "shift_register_opt",
              "retime", "critical_pin_opt", "clock_opt", "bram_enable_opt", "hold_fix")
#: flags Vivado 2026.1 refuses after routing, measured 2026-11-26 (brief 216, adder A7: "Option -fanout_opt is specified but not supported yet for
#: post-route physical synthesis"); the other flags are not known to be refused there, and an error a run reports is recorded as that recipe's result
POST_ROUTE_REFUSED = ("fanout_opt",)
#: ``synth_design`` options a recipe may set: key -> allowed values (None: a flag with no value)
SYNTH_OPTIONS: dict[str, tuple[Any, ...]] = {
    "flatten_hierarchy": ("full", "none", "rebuilt"),
    "fsm_extraction": ("one_hot", "sequential", "auto", "off"),
    "shreg_min_size": (3, 4, 5, 6, 8, 16),
    "resource_sharing": ("on", "off", "auto"),
    "retiming": (None,),
    "keep_equivalent_registers": (None,),
    "fanout_limit": (25, 50, 100, 200, 400),
}
FAMILIES = ("7series", "ultrascale+")
_NAME = re.compile(r"^[A-Za-z0-9_./\[\]*\\:-]{1,200}$")          # a net or cell name or glob: no space, brace, quote, dollar, semicolon
_REGION = re.compile(r"^(SLICE|DSP48|RAMB18|RAMB36|DSP58)_X(\d{1,3})Y(\d{1,3}):(SLICE|DSP48|RAMB18|RAMB36|DSP58)_X(\d{1,3})Y(\d{1,3})$")
_RES = ("lut", "ff")


class RecipeError(ValueError):
    """A recipe call was refused; the message says why (it goes back to whoever chose the recipe)."""


class FreeFormTclRefused(RecipeError):
    """Stage 6 takes recipe names and typed parameters only."""


# ---- typed parameters -----------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Param:
    name: str
    kind: str                       # enum | int | bool | names | regions | flags
    choices: tuple[Any, ...] = ()
    lo: float | None = None
    hi: float | None = None
    max_items: int = 16
    required: bool = True
    default: Any = None

    def check(self, v: Any) -> str | None:
        k = self.kind
        if k == "enum":
            return None if v in self.choices else f"{self.name}={v!r} is not one of {list(self.choices)}"
        if k == "int":
            if isinstance(v, bool) or not isinstance(v, int):
                return f"{self.name}={v!r} is not an integer"
            if (self.lo is not None and v < self.lo) or (self.hi is not None and v > self.hi):
                return f"{self.name}={v} is outside [{self.lo}, {self.hi}]"
            return None
        if k == "bool":
            return None if isinstance(v, bool) else f"{self.name}={v!r} is not a boolean"
        if k in ("names", "regions", "flags"):
            if not isinstance(v, (list, tuple)) or not v:
                return f"{self.name} must be a non-empty list"
            if len(v) > self.max_items:
                return f"{self.name} has {len(v)} items, at most {self.max_items}"
            for x in v:
                if k == "names" and not (isinstance(x, str) and _NAME.match(x)):
                    return f"{self.name} item {x!r} is not a plain net or cell name (letters, digits, _ . / [ ] * \\ : -)"
                if k == "regions" and not (isinstance(x, str) and _REGION.match(x)):
                    return f"{self.name} item {x!r} is not a site range such as SLICE_X0Y0:SLICE_X9Y49"
                if k == "flags" and x not in self.choices:
                    return f"{self.name} item {x!r} is not one of {list(self.choices)}"
            return None
        return f"unknown parameter kind {k}"


# ---- the plan: the settings of each implementation step ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ImplPlan:
    synth: tuple[tuple[str, Any], ...] = ()                         # synth_design options (a synthesis-level recipe: needs a synthesis run)
    directives: tuple[tuple[str, str], ...] = ()                    # step -> directive (absent = the step's default call)
    phys_flags: tuple[tuple[str, tuple[str, ...]], ...] = ()        # step (phys | post) -> phys_opt_design flags
    force_replication: tuple[str, ...] = ()                         # nets for phys_opt_design -force_replication_on_nets
    max_fanout: tuple[tuple[str, int], ...] = ()                    # (net, limit): MAX_FANOUT property before placement
    pblocks: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = ()     # (name, site ranges, cells)
    applied: tuple[str, ...] = ()                                   # recipe ids, in order

    def d(self) -> dict[str, str]:
        return dict(self.directives)

    def flags(self, step: str) -> tuple[str, ...]:
        return dict(self.phys_flags).get(step, ())

    def runs(self) -> dict[str, bool]:
        """Which implementation steps the plan calls with something other than the default call."""
        return {s: bool(self.d().get(s, "Default") != "Default" or self.flags(s)) for s in STEPS}

    def needs_synth(self) -> bool:
        return bool(self.synth)

    def key(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def to_dict(self) -> dict[str, Any]:
        return {"synth": [list(x) for x in self.synth], "directives": dict(self.directives),
                "phys_flags": {k: list(v) for k, v in self.phys_flags}, "force_replication": list(self.force_replication),
                "max_fanout": [list(x) for x in self.max_fanout], "pblocks": [[n, list(r), list(c)] for n, r, c in self.pblocks],
                "applied": list(self.applied)}


@dataclass
class Context:
    """What a recipe may know about the design and the device: from the build's reports, never guessed."""
    family: str = "7series"                          # 7series | ultrascale+
    slr: bool = False                                # a stacked-silicon part
    clock_ns: float | None = None
    capacity: dict[str, float] = field(default_factory=dict)       # lut/ff the design uses (for the pblock fit check)
    budget: dict[str, float] = field(default_factory=dict)         # lut/ff budgets (G3 targets), where the spec has them
    nets: frozenset[str] = frozenset()               # names the reports show (fanout recipes may only name these when given)
    area_growth_max: float = 0.25                    # a candidate may grow LUT+FF by at most this fraction over its parent


def _flatten_regions(rs: tuple[str, ...]) -> list[tuple[str, int, int, int, int]]:
    out = []
    for r in rs:
        m = _REGION.match(r)
        if not m:
            raise RecipeError(f"bad region {r!r}")
        a, x0, y0, b, x1, y1 = m.groups()
        if a != b:
            raise RecipeError(f"region {r!r} mixes {a} and {b}")
        out.append((a, min(int(x0), int(x1)), min(int(y0), int(y1)), max(int(x0), int(x1)), max(int(y0), int(y1))))
    return out


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] == b[0] and not (a[3] < b[1] or b[3] < a[1] or a[4] < b[2] or b[4] < a[2])


# ---- recipes ------------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    level: str                          # synth | impl | post_route | constraint
    params: tuple[Param, ...]
    apply: Callable[[ImplPlan, dict[str, Any], Context], ImplPlan]
    pre: Callable[[ImplPlan, dict[str, Any], Context], list[str]] = lambda p, a, c: []
    families: tuple[str, ...] = FAMILIES
    source: str = ""                    # where the option is documented (guide, or the knowledge-bank row)

    def validate_params(self, args: dict[str, Any]) -> list[str]:
        out = [f"unknown parameter {k!r} (this recipe takes {[p.name for p in self.params]})" for k in args if k not in {p.name for p in self.params}]
        for p in self.params:
            if p.name not in args:
                if p.required and p.default is None:
                    out.append(f"missing parameter {p.name!r}")
                continue
            e = p.check(args[p.name])
            if e:
                out.append(e)
        return out


def _with_applied(p: ImplPlan, rid: str, **kw: Any) -> ImplPlan:
    return replace(p, applied=p.applied + (rid,), **kw)


def _set_directive(p: ImplPlan, step: str, name: str) -> tuple[tuple[str, str], ...]:
    d = p.d()
    d[step] = name
    return tuple(sorted(d.items(), key=lambda kv: STEPS.index(kv[0])))


# 1. per-step directives -------------------------------------------------------------------------------------------------------
def _apply_directive(p, a, c):
    return _with_applied(p, "impl_directive", directives=_set_directive(p, a["step"], a["directive"]))


def _pre_directive(p, a, c):
    out = []
    if a.get("directive") not in DIRECTIVES.get(a.get("step"), ()):
        out.append(f"{a.get('directive')!r} is not a {a.get('step')} directive")
    if a.get("directive") in SLR_ONLY and not c.slr:
        out.append(f"{a.get('directive')} is for stacked-silicon (SLR) parts and this part is monolithic")
    if a.get("step") in p.d():
        out.append(f"the {a.get('step')} step already has directive {p.d()[a['step']]} from {p.applied}")
    return out


def _strategies() -> dict[str, dict[str, str]]:
    return json.loads(VENDOR_STRATEGIES.read_text())["impl"] if VENDOR_STRATEGIES.exists() else {}


# 2. AMD strategy sets -----------------------------------------------------------------------------------------------------------
def _apply_strategy(p, a, c):
    st = _strategies()[a["name"]]
    d = p.d()
    for step in STEPS:
        if st.get(step) and st[step] != "Default":
            d[step] = st[step]
        elif step in ("phys", "post") and st.get(step) == "Default":
            d[step] = "Default"       # the strategy runs the step (with its default directive)
    return _with_applied(p, "amd_strategy", directives=tuple(sorted(d.items(), key=lambda kv: STEPS.index(kv[0]))))


def _pre_strategy(p, a, c):
    st = _strategies()
    if a.get("name") not in st:
        return [f"{a.get('name')!r} is not a measured AMD strategy ({len(st)} known)"]
    out = [f"the {s} step already has a directive from {p.applied}" for s in STEPS if s in p.d() and st[a["name"]].get(s)]
    out += [f"{v} is for stacked-silicon (SLR) parts" for v in st[a["name"]].values() if v in SLR_ONLY and not c.slr]
    return out


# 2b. the tournament's named directive sets (flow/tournament.py IMPL_MENU; a test keeps the two equal) -----------------------------------------------
IMPL_SETS: dict[str, dict[str, str]] = {
    "explore": {"opt": "Explore", "place": "Explore", "phys": "Explore", "route": "Explore", "post": "Explore"},
    "extra_timing": {"opt": "Explore", "place": "ExtraTimingOpt", "phys": "AggressiveExplore", "route": "Explore", "post": "AggressiveExplore"},
    "extra_netdelay": {"opt": "Explore", "place": "ExtraNetDelay_high", "phys": "Explore", "route": "NoTimingRelaxation", "post": "Explore"},
    "aggressive": {"opt": "ExploreWithRemap", "place": "ExtraPostPlacementOpt", "phys": "AggressiveExplore", "route": "AggressiveExplore",
                   "post": "AggressiveExplore"},
    "congestion": {"opt": "Default", "place": "AltSpreadLogic_high", "route": "AlternateCLBRouting"},
}


def _apply_set(p, a, c):
    d = p.d()
    d.update({k: v for k, v in IMPL_SETS[a["name"]].items() if v != "Default" or k in ("phys", "post")})
    return _with_applied(p, "impl_set", directives=tuple(sorted(d.items(), key=lambda kv: STEPS.index(kv[0]))))


def _pre_set(p, a, c):
    if a.get("name") not in IMPL_SETS:
        return [f"{a.get('name')!r} is not a named directive set ({sorted(IMPL_SETS)})"]
    return [f"the {s} step already has a directive from {p.applied}" for s in IMPL_SETS[a["name"]] if s in p.d()]


# 3. phys_opt_design options ------------------------------------------------------------------------------------------------------
def _apply_phys(p, a, c):
    pf = dict(p.phys_flags)
    pf[a["step"]] = tuple(sorted(set(a["flags"])))
    return _with_applied(p, "phys_opt_options", phys_flags=tuple(sorted(pf.items())))


def _pre_phys(p, a, c):
    out = []
    if a.get("step") not in ("phys", "post"):
        out.append("step must be phys (after placement) or post (after routing)")
    if a.get("step") in dict(p.phys_flags):
        out.append(f"{a.get('step')} already has option flags from {p.applied}")
    if a.get("step") in p.d() and a.get("flags"):
        out.append(f"{a.get('step')} already has a directive; options and a directive are separate recipes, one per step")
    fl = a.get("flags") or []
    if a.get("step") == "post":
        out += [f"{f} is refused by Vivado 2026.1 after routing (measured)" for f in fl if f in POST_ROUTE_REFUSED]
    if "hold_fix" in fl and len(fl) > 1:
        out.append("hold_fix is offered alone (it is a repair pass for hold, not a setup optimisation)")
    return out


# 4. fanout replication ---------------------------------------------------------------------------------------------------------------
def _apply_replicate(p, a, c):
    nets = tuple(dict.fromkeys(p.force_replication + tuple(a["nets"])))
    pf = dict(p.phys_flags)
    pf["phys"] = tuple(sorted(set(pf.get("phys", ())) | {"fanout_opt"}))
    return _with_applied(p, "fanout_replicate", force_replication=nets, phys_flags=tuple(sorted(pf.items())))


def _pre_replicate(p, a, c):
    out = []
    if c.nets:
        out += [f"net {n} is not in the build's reports" for n in a.get("nets", []) if n not in c.nets]
    if "phys" in p.d():
        out.append("the phys step (after placement) already has a directive")
    return out


# 5. MAX_FANOUT constraint ---------------------------------------------------------------------------------------------------------------
def _apply_maxfanout(p, a, c):
    return _with_applied(p, "max_fanout", max_fanout=tuple(dict.fromkeys(p.max_fanout + tuple((n, a["limit"]) for n in a["nets"]))))


def _pre_maxfanout(p, a, c):
    return [f"net {n} is not in the build's reports" for n in a.get("nets", []) if c.nets and n not in c.nets]


# 6. retiming ---------------------------------------------------------------------------------------------------------------------------
def _apply_retime(p, a, c):
    if a["where"] == "synth":
        return _with_applied(p, "retime", synth=tuple(sorted(dict(p.synth, retiming=None).items())))
    pf = dict(p.phys_flags)
    pf["phys"] = tuple(sorted(set(pf.get("phys", ())) | {"retime"}))
    return _with_applied(p, "retime", phys_flags=tuple(sorted(pf.items())))


def _pre_retime(p, a, c):
    out = []
    if a.get("where") == "phys" and "phys" in p.d():
        out.append("the phys step already has a directive")
    if a.get("where") == "synth" and "retiming" in dict(p.synth):
        out.append("synthesis retiming is already on")
    return out


# 7. register duplication -------------------------------------------------------------------------------------------------------------------
def _apply_dup(p, a, c):
    if a["method"] == "keep_equivalent":
        return _with_applied(p, "register_duplication", synth=tuple(sorted(dict(p.synth, keep_equivalent_registers=None).items())))
    pf = dict(p.phys_flags)
    pf["phys"] = tuple(sorted(set(pf.get("phys", ())) | {"fanout_opt"}))
    return _with_applied(p, "register_duplication", force_replication=tuple(dict.fromkeys(p.force_replication + tuple(a["nets"]))),
                         phys_flags=tuple(sorted(pf.items())))


def _pre_dup(p, a, c):
    if a.get("method") == "force_replication" and not a.get("nets"):
        return ["method force_replication needs nets"]
    if a.get("method") == "keep_equivalent" and a.get("nets"):
        return ["method keep_equivalent is global (a synthesis option); nets are not taken"]
    return []


# 8. pblock -----------------------------------------------------------------------------------------------------------------------------------
def _apply_pblock(p, a, c):
    return _with_applied(p, "pblock", pblocks=p.pblocks + ((a["name"], tuple(a["regions"]), tuple(a["cells"])),))


def _pre_pblock(p, a, c):
    out = []
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", str(a.get("name", ""))):
        out.append("pblock name must be letters, digits and underscore")
    if any(n == a.get("name") for n, _, _ in p.pblocks):
        out.append(f"pblock {a.get('name')} already exists")
    try:
        new = _flatten_regions(tuple(a.get("regions", ())))
        for _, rs, _ in p.pblocks:
            for o in _flatten_regions(rs):
                if any(_overlap(n, o) for n in new):
                    out.append("the region overlaps an existing pblock")
        slices = sum((r[3] - r[1] + 1) * (r[4] - r[2] + 1) for r in new if r[0] == "SLICE")
        per = 8 if c.family == "ultrascale+" else 4          # LUTs per SLICE: 8 on UltraScale+ (SLICEL/M), 4 on 7-series
        need = c.capacity.get("lut")
        if need and slices and slices * per < need * 1.3:
            out.append(f"the region holds {slices * per} LUTs and the cells' design uses {need}: under 30 % headroom")
    except RecipeError as e:
        out.append(str(e))
    return out


# 9. synthesis options ------------------------------------------------------------------------------------------------------------------------
def _apply_synth(p, a, c):
    return _with_applied(p, "synth_option", synth=tuple(sorted(dict(p.synth, **{a["option"]: a.get("value")}).items(), key=lambda kv: kv[0])))


def _pre_synth(p, a, c):
    o, v = a.get("option"), a.get("value")
    if o not in SYNTH_OPTIONS:
        return [f"{o!r} is not an allowed synth_design option ({sorted(SYNTH_OPTIONS)})"]
    if v not in SYNTH_OPTIONS[o]:
        return [f"{o}={v!r} is not one of {list(SYNTH_OPTIONS[o])}"]
    return [f"{o} is already set"] if o in dict(p.synth) else []


_STEP = Param("step", "enum", STEPS)
RECIPES: dict[str, Recipe] = {r.id: r for r in (
    Recipe("impl_directive", "set one implementation step's directive", "impl",
           (_STEP, Param("directive", "enum", tuple(sorted({d for v in DIRECTIVES.values() for d in v})))),
           _apply_directive, _pre_directive, source="UG904 *_design -directive; values measured by results/178_tournament/vendor_strategies.json"),
    Recipe("amd_strategy", "an AMD implementation strategy set (measured, one name)", "impl",
           (Param("name", "enum", tuple(sorted(_strategies()))),), _apply_strategy, _pre_strategy,
           source="vendor_strategies.json (read from Vivado 2026.1 by flow.tournament strategies)"),
    Recipe("impl_set", "one of the tournament's named directive sets across all steps", "impl",
           (Param("name", "enum", tuple(IMPL_SETS)),), _apply_set, _pre_set, source="flow/tournament.py IMPL_MENU (178; docs/tournament.md)"),
    Recipe("phys_opt_options", "phys_opt_design option flags after placement or routing", "post_route",
           (Param("step", "enum", ("phys", "post")), Param("flags", "flags", PHYS_FLAGS)), _apply_phys, _pre_phys,
           source="UG904 phys_opt_design; family matrix areas/toolflow.yaml (common to 7-series and UltraScale+)"),
    Recipe("fanout_replicate", "replicate the drivers of named high-fanout nets (phys_opt after placement)", "post_route",
           (Param("nets", "names", max_items=8),), _apply_replicate, _pre_replicate, source="UG904 phys_opt_design -force_replication_on_nets"),
    Recipe("max_fanout", "MAX_FANOUT on named nets before placement (a constraint, no clock change)", "constraint",
           (Param("nets", "names", max_items=8), Param("limit", "int", lo=16, hi=2000)), _apply_maxfanout, _pre_maxfanout,
           source="UG903 MAX_FANOUT"),
    Recipe("retime", "retiming: in synthesis (-retiming) or in phys_opt_design (-retime)", "synth",
           (Param("where", "enum", ("synth", "phys")),), _apply_retime, _pre_retime, source="UG901 synth_design -retiming; UG904 phys_opt_design -retime"),
    Recipe("register_duplication", "duplicate registers: keep equivalent registers (synthesis) or force replication on nets", "synth",
           (Param("method", "enum", ("keep_equivalent", "force_replication")), Param("nets", "names", max_items=8, required=False, default=())),
           _apply_dup, _pre_dup, source="UG901 -keep_equivalent_registers; UG904 -force_replication_on_nets"),
    Recipe("pblock", "a pblock for named cells on a legal site range", "constraint",
           (Param("name", "names", max_items=1), Param("regions", "regions", max_items=4), Param("cells", "names", max_items=8)), _apply_pblock, _pre_pblock,
           source="UG903 pblocks; UG949 floorplanning"),
    Recipe("synth_option", "one synth_design option from the allowed list", "synth",
           (Param("option", "enum", tuple(SYNTH_OPTIONS)), Param("value", "enum", (None, "full", "none", "rebuilt", "one_hot", "sequential", "auto", "off", "on", 3, 4, 5, 6, 8, 16, 25, 50, 100, 200, 400), required=False, default=None)),
           _apply_synth, _pre_synth, source="UG901 synth_design; flow/tournament.py SYNTH_MENU"),
)}

# ---- applying a recipe ---------------------------------------------------------------------------------------------------------------------
def apply_recipe(plan: ImplPlan, rid: str, args: dict[str, Any], ctx: Context | None = None) -> ImplPlan:
    """Check the recipe's parameters and preconditions, then return the new plan. Raises :class:`RecipeError` with every reason."""
    ctx = ctx or Context()
    if rid not in RECIPES:
        raise RecipeError(f"unknown recipe {rid!r}; the recipes are {sorted(RECIPES)}")
    r = RECIPES[rid]
    if ctx.family not in r.families:
        raise RecipeError(f"recipe {rid} is not offered on {ctx.family}")
    a = dict(args)
    if rid == "pblock" and isinstance(a.get("name"), str):
        a["name"] = [a["name"]]                                  # the schema checks a one-item name list
        why = r.validate_params(a)
        a["name"] = a["name"][0]
    else:
        why = r.validate_params(a)
    if why:
        raise RecipeError(f"{rid}: " + "; ".join(why))
    for p in r.params:                                           # a missing optional parameter takes its default
        if p.name not in a and p.default is not None:
            a[p.name] = p.default
    why = r.pre(plan, a, ctx)
    if why:
        raise RecipeError(f"{rid}: " + "; ".join(why))
    return r.apply(plan, a, ctx)


# ---- the validator after a run ---------------------------------------------------------------------------------------------------------------
def post_check(before: dict[str, Any], after: dict[str, Any], ctx: Context | None = None) -> list[str]:
    """Why a measured result may not count (empty list: valid). ``before`` and ``after`` hold ``status``, ``wns_ns``, ``whs_ns``, ``lut``, ``ff``,
    ``clock_ns`` (the period the report was timed against). Validity is not improvement: a valid result that is worse is rolled back by the search."""
    ctx = ctx or Context()
    out: list[str] = []
    if after.get("status") != "ok":
        return [f"the run did not finish: {after.get('status')}"]
    if after.get("wns_ns") is None:
        out.append("no setup slack in the report (unconstrained or the report did not parse)")
    if before.get("clock_ns") is not None and after.get("clock_ns") is not None and abs(before["clock_ns"] - after["clock_ns"]) > 1e-9:
        out.append(f"the clock period changed ({before['clock_ns']} to {after['clock_ns']} ns): a recipe never moves the target")
    bw, aw = before.get("whs_ns"), after.get("whs_ns")
    if aw is not None and aw < 0 and not (bw is not None and bw < 0 and aw >= bw):
        out.append(f"hold slack {aw} ns is newly negative (before: {bw})")
    b_area, a_area = sum(before.get(k) or 0 for k in _RES), sum(after.get(k) or 0 for k in _RES)
    if b_area and a_area > b_area * (1 + ctx.area_growth_max):
        out.append(f"LUT+FF grew from {b_area} to {a_area}, more than {ctx.area_growth_max:.0%}")
    for k in _RES:
        bud = ctx.budget.get(k)
        if bud and (after.get(k) or 0) > bud and (before.get(k) or 0) <= bud:
            out.append(f"{k} {after.get(k)} is now over its budget {bud}")
    return out


# ---- the journal and rollback ---------------------------------------------------------------------------------------------------------------
@dataclass
class Journal:
    """Every application of a recipe: the plan before, the verdict, and whether it was rolled back to the parent."""
    rows: list[dict[str, Any]] = field(default_factory=list)

    def record(self, parent: ImplPlan, rid: str, args: dict[str, Any], verdict: str, reasons: list[str], rolled_back: bool,
               outcome: dict[str, Any] | None = None) -> None:
        self.rows.append({"recipe": rid, "args": args, "parent": parent.key(), "verdict": verdict, "reasons": reasons,
                          "rolled_back": rolled_back, "outcome": outcome})

    def rollback_of(self, parent: ImplPlan) -> ImplPlan:
        """Rolling back is returning the immutable parent plan; its checkpoint is the one the search kept."""
        return parent

    def rolled_back(self) -> int:
        return sum(1 for r in self.rows if r["rolled_back"])


# ---- the one renderer -----------------------------------------------------------------------------------------------------------------------
def _q(s: str) -> str:
    return "{" + s + "}"


def _phys_line(step: str, plan: ImplPlan) -> list[str]:
    d, fl = plan.d().get(step), plan.flags(step)
    if not d and not fl:
        return []
    parts = ["phys_opt_design"]
    if d and d != "Default":
        parts.append(f"-directive {d}")
    for f in fl:
        parts.append(f"-{f}")
    if step == "phys" and plan.force_replication:
        parts.append("-force_replication_on_nets [get_nets -quiet " + _q(" ".join(plan.force_replication)) + "]")
    return [" ".join(parts)]


def render_synth_args(plan: ImplPlan) -> str:
    out = []
    for k, v in plan.synth:
        out.append(f"-{k}" if v is None else f"-{k} {v}")
    return " ".join(out)


def render_impl_tcl(plan: ImplPlan, start_dcp: str, out_dir: str, *, start: str = "post_synth", write_dcp: bool = True) -> str:
    """The Tcl for one candidate: open the start checkpoint (post-synthesis, or routed for a post-route recipe), apply the constraint-level
    changes, run the steps, write the reports the parser reads and the final checkpoint. Every line comes from a fixed template."""
    L = ["set_param general.maxThreads 1", f"file mkdir {_q(out_dir)}", "set t0 [clock seconds]", f"open_checkpoint {_q(start_dcp)}"]
    if start == "post_synth":
        for net, lim in plan.max_fanout:
            L.append(f"set_property MAX_FANOUT {lim} [get_nets -quiet {_q(net)}]")
        for name, regions, cells in plan.pblocks:
            L.append(f"create_pblock {name}")
            for r in regions:
                L.append(f"resize_pblock [get_pblocks {name}] -add {_q(r)}")
            L.append(f"add_cells_to_pblock [get_pblocks {name}] [get_cells -quiet {_q(' '.join(cells))}]")
        d = plan.d()
        L.append(f"opt_design -directive {d['opt']}" if d.get("opt", "Default") != "Default" else "opt_design")
        L.append(f"place_design -directive {d['place']}" if d.get("place", "Default") != "Default" else "place_design")
        L += _phys_line("phys", plan)
        L.append(f"route_design -directive {d['route']}" if d.get("route", "Default") != "Default" else "route_design")
    L += _phys_line("post", plan)
    L += [f"report_utilization -file {_q(out_dir + '/utilization.rpt')}",
          f"report_timing_summary -max_paths 5 -file {_q(out_dir + '/timing_summary.rpt')}",
          f"report_timing -max_paths 1 -path_type full -file {_q(out_dir + '/worst_path.rpt')}"]
    if write_dcp:
        L.append(f"write_checkpoint -force {_q(out_dir + '/result.dcp')}")
    L.append(f"set f [open {_q(out_dir + '/done.txt')} w]; puts $f [expr {{[clock seconds] - $t0}}]; close $f")
    tcl = "\n".join(L) + "\n"
    guard_rendered_tcl(tcl)
    return tcl


# ---- free-form Tcl is refused at stage 6 -------------------------------------------------------------------------------------------------------
_ALLOWED_CMDS = {"set_param", "file", "set", "open_checkpoint", "set_property", "create_pblock", "resize_pblock", "add_cells_to_pblock",
                 "opt_design", "place_design", "phys_opt_design", "route_design", "report_utilization", "report_timing_summary",
                 "report_timing", "write_checkpoint"}
_FORBIDDEN = re.compile(r"set_clock_uncertainty|set_false_path|set_multicycle_path|set_clock_groups|set_max_delay|set_min_delay|set_input_delay|"
                        r"set_output_delay|create_clock|create_generated_clock|set_case_analysis|\bsource\b|\bexec\b|\beval\b|\bopen_hw|\bprogram_hw", re.I)
_STAGE6_FREE_KEYS = ("tcl", "script", "command", "cmd", "source", "xdc", "code")


def guard_rendered_tcl(tcl: str) -> None:
    """The renderer's own output must contain only the allowed commands and no constraint that moves the target."""
    for ln in tcl.splitlines():
        s = ln.strip()
        if not s:
            continue
        cmd = s.split()[0]
        if cmd not in _ALLOWED_CMDS:
            raise FreeFormTclRefused(f"command {cmd!r} is not one of the closure recipes' templates")
        if _FORBIDDEN.search(s):
            raise FreeFormTclRefused(f"the line {s[:60]!r} changes the constraints or runs code")
        if cmd == "set_property" and not re.match(r"set_property MAX_FANOUT \d+ ", s):
            raise FreeFormTclRefused("set_property is allowed only for MAX_FANOUT")


def guard_stage6_args(args: dict[str, Any]) -> dict[str, Any]:
    """A stage-6 call is ``{recipe, params}`` and nothing else. Any Tcl, script or constraint text is refused with the reason."""
    free = [k for k in args if k in _STAGE6_FREE_KEYS]
    if free or set(args) - {"recipe", "params"}:
        raise FreeFormTclRefused(f"stage 6 takes a recipe name and typed params only; got {sorted(args)}. Free-form Tcl, scripts and "
                                 f"constraint text are not accepted here: choose from {sorted(RECIPES)}")
    for v in json.dumps(args.get("params", {})).split('"'):
        if _FORBIDDEN.search(v):
            raise FreeFormTclRefused(f"a parameter value contains a constraint or code command: {v[:60]!r}")
    return args


def menu_text() -> str:
    """The recipe menu as text for whoever chooses (the closure controller, or a model through a tool): name, parameters, source."""
    rows = []
    for r in RECIPES.values():
        ps = ", ".join(f"{p.name}:{p.kind}" + (f"[{len(p.choices)} choices]" if p.choices else "") for p in r.params)
        rows.append(f"- {r.id} ({r.level}): {r.title}. params: {ps}. source: {r.source}")
    return "\n".join(rows)
