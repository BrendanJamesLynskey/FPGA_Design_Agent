"""Typed goals (brief 159, review item F5): a goal is data (metric, bound, priority, source), not free text.

``spec.yaml`` carries them in one ``goals:`` block; ``--goal "lut<=700"`` on ``python -m agent revise`` writes the same shape::

    goals:
      - {metric: lut, op: le, bound: 700, unit: LUT, priority: must, source: "owner, 2026-11-22"}
      - {metric: fmax_mhz, op: ge, bound: 150, unit: MHz, name: sys_clk, priority: must, source: "--goal"}
      - {metric: latency_clk, op: le, bound: 22, unit: clk, name: echo, priority: should, source: "spec.md section 4"}

Readers (all take the same list; none re-parses text):

- the closure loop (``agent.graph.closure.goals_from_spec``): area goals set the G3 budget, ``fmax_mhz`` the G2 clock, ``power_w`` the
  G4 limit; a ``must`` goal wins over a ``budget:`` or ``clocks:`` value and the reason says so (a ``should`` goal is recorded only);
- the latency loop (``agent.graph.latency_loop``): ``latency_clk`` with the name ``tick_to_trade`` (or no name) is its target;
- the trace matrix (``flow.trace_v1.load``): each goal becomes a ``performance`` requirement ``GOAL-<metric>[-<name>]`` that a
  verification item must trace to (a goal with no item is an untraced requirement, a gate gap);
- the goal-revision plan (``agent.graph.revise``).

Syntax of a goal string, and what a user could guess wrong (also in ``agent revise --help``): ``<metric>[.<name>] <op> <number>[unit]``.

- metrics: ``lut``, ``ff``, ``bram`` (36 Kb tiles, as the closure budget counts them), ``dsp`` (no unit needed); ``fmax`` (unit MHz or GHz
  REQUIRED); ``power`` (unit W or mW REQUIRED; the build's vectorless on-chip estimate, not a board measurement); ``latency`` (unit clk,
  clks, clock or cycles REQUIRED; nanoseconds are refused because turning them into clocks needs a clock the goal does not name).
- the direction is fixed by the metric: ``<=`` or ``<`` for area, power and latency, ``>=`` or ``>`` for fmax. ``=`` is refused (a goal
  is a bound, not an exact value) and so is the wrong direction (``lut>=100``).
- ``.<name>`` picks one clock (fmax) or one named latency (``latency.echo``); without it, fmax means the first clock of the design and a latency
  means the design's only measured latency (``tick_to_trade`` for the latency loop). A name that matches nothing is reported, never guessed.
- units are converted once: GHz to MHz, mW to W. A bare number where a unit is required is an error, not a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: metric -> (kind, unit, allowed ops, key of the handover measurement that holds the evidence, unit words accepted)
METRICS: dict[str, dict[str, Any]] = {
    "lut": {"kind": "area", "unit": "LUT", "ops": ("le", "lt"), "evidence_key": "lut", "units": ("", "lut", "luts")},
    "ff": {"kind": "area", "unit": "FF", "ops": ("le", "lt"), "evidence_key": "ff", "units": ("", "ff", "ffs", "reg", "regs")},
    "bram_tile": {"kind": "area", "unit": "tile", "ops": ("le", "lt"), "evidence_key": "bram_tile", "units": ("", "tile", "tiles", "bram")},
    "dsp": {"kind": "area", "unit": "DSP", "ops": ("le", "lt"), "evidence_key": "dsp", "units": ("", "dsp", "dsps")},
    "fmax_mhz": {"kind": "fmax", "unit": "MHz", "ops": ("ge", "gt"), "evidence_key": "wns_ns", "units": ("mhz", "ghz")},
    "power_w": {"kind": "power", "unit": "W", "ops": ("le", "lt"), "evidence_key": "power_w", "units": ("w", "mw")},
    "latency_clk": {"kind": "latency", "unit": "clk", "ops": ("le", "lt"), "evidence_key": None,
                    "units": ("clk", "clks", "clock", "clocks", "cycle", "cycles")},
}
#: the words a user types for each metric
ALIAS = {"lut": "lut", "luts": "lut", "ff": "ff", "ffs": "ff", "bram": "bram_tile", "bram_tile": "bram_tile", "dsp": "dsp",
         "fmax": "fmax_mhz", "fmax_mhz": "fmax_mhz", "power": "power_w", "power_w": "power_w", "latency": "latency_clk",
         "latency_clk": "latency_clk"}
OPS = {"<=": "le", "<": "lt", ">=": "ge", ">": "gt"}
OP_TEXT = {"le": "<=", "lt": "<", "ge": ">=", "gt": ">"}
PRIORITIES = ("must", "should")
EXAMPLE = "lut<=700, fmax>=150MHz, power<=0.5W, latency<=22clk, latency.echo<=22clk"
_RX = re.compile(r"^\s*(?P<metric>[A-Za-z_]+)(?:\.(?P<name>[A-Za-z0-9_\-]+))?\s*(?P<op><=|>=|<|>|=)\s*"
                 r"(?P<num>[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)\s*(?P<unit>[A-Za-z]*)\s*$")


class GoalError(ValueError):
    """A goal that cannot be read; the message says what to write instead."""


@dataclass(frozen=True)
class Goal:
    metric: str
    op: str
    bound: float
    name: str | None = None
    priority: str = "must"
    source: str = ""

    @property
    def kind(self) -> str:
        return METRICS[self.metric]["kind"]

    @property
    def unit(self) -> str:
        return METRICS[self.metric]["unit"]

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.metric, self.name)

    def met_by(self, value: float) -> bool:
        return {"le": value <= self.bound, "lt": value < self.bound, "ge": value >= self.bound, "gt": value > self.bound}[self.op]

    def text(self) -> str:
        n = f"{self.bound:g}"
        return f"{self.metric.removesuffix('_mhz').removesuffix('_w').removesuffix('_clk').removesuffix('_tile')}" \
               f"{'.' + self.name if self.name else ''}{OP_TEXT[self.op]}{n}{'' if self.unit in ('LUT', 'FF', 'tile', 'DSP') else self.unit}"

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"metric": self.metric, "op": self.op, "bound": _num(self.bound), "unit": self.unit}
        if self.name:
            d["name"] = self.name
        d.update(priority=self.priority, source=self.source)
        return d


def _num(x: float) -> int | float:
    return int(x) if float(x).is_integer() else x


def parse_goal(text: str, source: str = "--goal", priority: str = "must") -> Goal:
    """``"lut<=700"`` -> Goal. Raises :class:`GoalError` with the form to write instead."""
    m = _RX.match(text or "")
    if not m:
        raise GoalError(f"cannot read goal {text!r}: write <metric>[.<name>]<op><number><unit>, for example {EXAMPLE}")
    word = m["metric"].lower()
    metric = ALIAS.get(word)
    if metric is None:
        raise GoalError(f"unknown goal metric {m['metric']!r} in {text!r}: the metrics are lut, ff, bram, dsp, fmax, power, latency")
    spec = METRICS[metric]
    op_word, num, unit = m["op"], float(m["num"]), m["unit"].lower()
    if op_word == "=":
        raise GoalError(f"{text!r}: a goal is a bound, not an exact value; use {'>=' if spec['kind'] == 'fmax' else '<='}")
    op = OPS[op_word]
    if op not in spec["ops"]:
        want = ">= or >" if spec["kind"] == "fmax" else "<= or <"
        raise GoalError(f"{text!r}: {word} is bounded with {want} (more is {'better' if spec['kind'] == 'fmax' else 'worse'}); "
                        f"say what the design must reach, for example {word}{'>=' if spec['kind'] == 'fmax' else '<='}{m['num']}")
    if unit not in spec["units"]:
        need = [u for u in spec["units"] if u]
        raise GoalError(f"{text!r}: the unit {m['unit'] or '(none)'!r} is not one of {', '.join(need)}" +
                        ("; a unit is required for this metric" if "" not in spec["units"] else ""))
    if unit == "ghz":
        num *= 1000.0
    elif unit == "mw":
        num /= 1000.0
    if num < 0 or (num == 0 and spec["kind"] != "area"):
        raise GoalError(f"{text!r}: the bound must be above zero (zero is allowed only for lut, ff, bram and dsp)")
    if priority not in PRIORITIES:
        raise GoalError(f"priority must be one of {', '.join(PRIORITIES)}")
    if m["name"] and spec["kind"] not in ("fmax", "latency"):
        raise GoalError(f"{text!r}: only fmax (a clock name) and latency (a latency name) take a .<name>")
    return Goal(metric, op, round(num, 9), m["name"], priority, source)


def from_dict(d: Any, i: int = 0) -> Goal:
    """One entry of the spec's ``goals:`` list; raises :class:`GoalError` naming the entry and the field."""
    where = f"goals[{i}]"
    if not isinstance(d, dict):
        raise GoalError(f"{where} must be a mapping: {{metric, op, bound, priority, source}}")
    metric = ALIAS.get(str(d.get("metric", "")).lower())
    if metric is None:
        raise GoalError(f"{where}: metric {d.get('metric')!r} is not one of {', '.join(sorted(METRICS))}")
    if d.get("op") not in METRICS[metric]["ops"]:
        raise GoalError(f"{where}: op for {metric} must be one of {', '.join(METRICS[metric]['ops'])} (got {d.get('op')!r})")
    b = d.get("bound")
    if isinstance(b, bool) or not isinstance(b, (int, float)) or b < 0 or (b == 0 and METRICS[metric]["kind"] != "area"):
        raise GoalError(f"{where}: bound must be a number above zero in {METRICS[metric]['unit']} (zero only for lut, ff, bram, dsp; got {b!r})")
    if d.get("unit") not in (None, METRICS[metric]["unit"]):
        raise GoalError(f"{where}: unit for {metric} is {METRICS[metric]['unit']} (got {d.get('unit')!r}); convert it first")
    pr = d.get("priority", "must")
    if pr not in PRIORITIES:
        raise GoalError(f"{where}: priority must be one of {', '.join(PRIORITIES)} (got {pr!r})")
    name = d.get("name")
    if name is not None and (not isinstance(name, str) or METRICS[metric]["kind"] not in ("fmax", "latency")):
        raise GoalError(f"{where}: only fmax and latency goals take a name (a string)")
    return Goal(metric, d["op"], float(b), name, pr, str(d.get("source") or ""))


def errors(spec: dict[str, Any]) -> list[str]:
    """Shape errors of ``spec['goals']`` for ``spec_schema.shape_errors``: a list of mappings, each valid, no (metric, name) twice."""
    g = spec.get("goals")
    if g is None:
        return []
    if not isinstance(g, list):
        return ["'goals' must be a list of mappings: {metric, op, bound, unit, priority, source}"]
    errs, seen = [], set()
    for i, d in enumerate(g):
        try:
            x = from_dict(d, i)
        except GoalError as e:
            errs.append(str(e))
            continue
        if x.key in seen:
            errs.append(f"goals[{i}]: a second goal for {x.metric}{'.' + x.name if x.name else ''}; one bound per metric and name")
        seen.add(x.key)
    return errs


def load(spec: dict[str, Any] | None) -> list[Goal]:
    """The goals of a spec (empty without a block). A malformed block raises :class:`GoalError` (never silently ignored)."""
    es = errors(spec or {})
    if es:
        raise GoalError("; ".join(es))
    return [from_dict(d, i) for i, d in enumerate((spec or {}).get("goals") or [])]


def merge(old: list[Goal], new: list[Goal]) -> list[Goal]:
    """``new`` replaces the old goal with the same (metric, name); others stay, in their order, new ones last."""
    keys = {g.key for g in new}
    return [g for g in old if g.key not in keys] + list(new)


def block_text(goals: list[Goal]) -> str:
    """The ``goals:`` block as YAML text (one flow mapping per line, so a diff shows one goal per line)."""
    import json
    if not goals:
        return "goals: []\n"
    return "goals:\n" + "".join("  - {" + ", ".join(f"{k}: {json.dumps(v)}" for k, v in g.as_dict().items()) + "}\n" for g in goals)


def set_block(spec_text: str, goals: list[Goal]) -> str:
    """spec.yaml text with its top-level ``goals:`` block replaced (or appended); every other line, comments included, is kept."""
    block = block_text(goals)
    rx = re.compile(r"^goals:[^\n]*\n(?:(?:[ \t]+[^\n]*|)\n)*", re.M)
    if rx.search(spec_text):
        return rx.sub(lambda _m: block, spec_text, count=1)
    return spec_text.rstrip("\n") + "\n\n" + block


def latency_target(goals: list[Goal], name: str = "tick_to_trade") -> Goal | None:
    """The ``must`` latency goal the latency loop reads: named ``name`` or unnamed."""
    return next((g for g in goals if g.metric == "latency_clk" and g.priority == "must" and g.name in (None, name)), None)


def requirements(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The goals as trace-v1 ``performance`` requirements (``flow.trace_v1.load`` adds the ones the plan does not already hold)."""
    out = []
    for g in load(spec):
        rid = "GOAL-" + g.metric.upper().replace("_", "-") + (f"-{g.name.upper()}" if g.name else "")
        out.append({"id": rid, "kind": "performance", "title": f"goal {g.text()} ({g.priority})",
                    "text": f"The design meets the typed goal {g.text()} from spec.yaml goals ({g.source or 'no source named'}).",
                    "source": "spec.yaml goals", "spec_status": "draft",
                    "performance": {"quantity": g.metric + (f".{g.name}" if g.name else ""), "unit": g.unit, "op": g.op,
                                    "bound": _num(g.bound), "condition": "the design's routed build or its named bench, as the verification item states"}})
    return out
