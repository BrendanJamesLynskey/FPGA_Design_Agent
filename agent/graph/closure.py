"""The closure loop: iterate until every goal is met, or stop with an honest report.

Terms: WNS / WHS are the worst setup / hold slack of the routed design (both must be 0 or more); the **goal vector** is
the five goals' values and verdicts, recorded before and after every iteration.

Goals (all must hold to finish):

- **G1** functional correctness in simulation: the independent bench (the hidden acceptance bench of a benchmark task,
  or the V-gates in the agent graph) passes.
- **G2** timing: WNS >= 0 and WHS >= 0 at the spec's clocks, no unconstrained endpoint, exceptions and I/O timing clean.
- **G3** area: LUT, FF, BRAM, DSP, IO within ``spec.yaml`` ``budget`` (else a default share of the part, 80 %); no
  inferred latch, no RAM built in registers.
- **G4** power: Vivado's total on-chip power within ``budget.power_w`` (else the board limit, 2.0 W on the Nexys A7 on
  wall power) and junction temperature within 85 C.
- **G5** hardware: not evaluated yet (no board in this phase; ``met: None``).
- **CHK** the routed checkpoint's DRC and methodology checks: no Error and no Critical Warning (``met: None`` when the
  build reported neither, as in a trimmed fixture).

The joint loop (default): every build's reports are diagnosed together and one plan picks a set of fixes that do not
conflict, preferring hard resources (``agent.graph.closure_plan``); each attempt is checked first after synthesis (the
early check: utilisation and the plan's primitives, before any implementation run), then built in full; when every goal
holds, the flow's sequential gates and the independent bench run once more on the accepted design as the **sign-off**,
and closure is claimed only if they pass. A plan that needs the spec or the architecture changed stops the loop with the
agent graph's re-entry state for that stage (``reentry`` in the report).

The controller (:class:`Closure`):

1. requires G1 at the start (functional repair is stage 2's job, not this loop's);
2. builds once and computes the goal vector;
3. picks the unmet goal with the largest normalised shortfall, and the best strategy for it from the playbook
   (``agent.graph.closure_playbook``) that is not exhausted and whose predicted cost fits the other goals' headroom;
4. asks the Designer for the change, re-runs G1 (one functional retry, then revert), rebuilds, and judges the new
   vector against the last accepted one: kept when it improves an unmet goal and worsens none, else reverted;
5. counts iterations without progress per (goal, strategy class); after ``stall_n`` the class is exhausted (the
   **stall rule**: a strategy class is given up after N tries without progress); when every class for a goal is exhausted, or a limit is reached, it stops with
   "goal X not met; best value Y; what was tried".

Every iteration is recorded (vector before and after, strategy and why, the diff, the delta on every goal, cost).
The build, the G1 check and the Designer are passed in, so CI tests the controller with fakes and recorded reports.
"""

from __future__ import annotations

from agent.core.prompts import load as _p
from agent.core import prompts as _prompts

import difflib
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent.graph import closure_playbook as pb

GOALS = ("G1", "G2", "G3", "G4", "G5", "CHK")
JUDGED = ("G1", "G2", "G3", "G4", "CHK")
DEFAULT_SHARE = 0.80
BOARD_POWER_W = {"nexys_a7_100t": 2.0}      # house rules: wall power, report_power total on-chip <= 2.0 W
TJ_MAX_C = 85.0
EPS = {"G1": 1e-9, "G2": 0.0005, "G3": 0.0005, "G4": 0.0005, "CHK": 1e-9}     # a shortfall change below this is no change
RES = ("lut", "ff", "bram_tile", "dsp", "iob")
_AVAIL = {"lut": "lut_available", "ff": "ff_available", "bram_tile": "bram_tile_available", "dsp": "dsp_available",
          "iob": "iob_available"}
PART_DEFAULT = {"lut": 63400, "ff": 126800, "bram_tile": 135, "dsp": 240, "iob": 210}


# --- goals --------------------------------------------------------------------------------------------------------

def goals_from_spec(spec: dict[str, Any], board: str = "nexys_a7_100t") -> dict[str, Any]:
    """The targets of G1..G5 from spec.yaml: ``clocks`` (freq_mhz), ``budget: {lut, ff, bram, dsp, io, power_w}``.
    A missing budget entry gets the default (80 % of the part; the board power limit), with that reason recorded.
    Brief 159: the ``must`` goals of ``goals:`` (``agent.graph.goals``) win over ``budget:`` and ``clocks:`` (lut, ff, bram, dsp, fmax,
    power), the reason says so, and the goals are listed under ``typed_goals``."""
    b = spec.get("budget") or {}
    alias = {"bram_tile": ("bram_tile", "bram"), "iob": ("iob", "io"), "lut": ("lut",), "ff": ("ff",), "dsp": ("dsp",)}
    g3, why = {}, {}
    for k in RES:
        v = next((b[a] for a in alias[k] if a in b), None)
        if v is None:
            g3[k] = round(PART_DEFAULT[k] * DEFAULT_SHARE, 1)
            why[k] = f"no budget in spec.yaml: default {int(DEFAULT_SHARE * 100)} % of the part"
        else:
            g3[k], why[k] = float(v), "spec.yaml budget"
    clocks = [{"name": c.get("name"), "freq_mhz": c.get("freq_mhz"), "period_ns": round(1000 / float(c["freq_mhz"]), 3),
               **({"min_freq_mhz": c["min_freq_mhz"]} if c.get("min_freq_mhz") else {})}
              for c in spec.get("clocks") or [] if c.get("freq_mhz")]
    pw = b.get("power_w")
    typed = _typed_goals(spec, g3, why, clocks)
    if typed.get("power_w") is not None:
        pw, power_why = typed["power_w"], f"typed goal {typed['power_text']}"
    else:
        power_why = None
    out = {
        "G1": {"what": "the independent bench and the verification gates pass"},
        "G2": {"wns_min_ns": 0.0, "whs_min_ns": 0.0, "clocks": clocks},
        "G3": {"budget": g3, "why": why, "no_latches": True, "no_ram_in_registers": True},
        "G4": {"power_w": float(pw) if pw is not None else BOARD_POWER_W.get(board, 2.0),
               "why": power_why or ("spec.yaml budget" if pw is not None else f"no budget in spec.yaml: the board limit ({board})"),
               "tj_max_c": TJ_MAX_C},
        "G5": {"what": "board checks (not run yet)"},
    }
    if typed["goals"]:
        out["typed_goals"] = typed["goals"]
    return out


def _typed_goals(spec: dict[str, Any], g3: dict[str, float], why: dict[str, str], clocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Brief 159: apply the ``must`` goals of ``spec.yaml goals:`` (``agent.graph.goals``) over ``budget:`` and ``clocks:``, in place
    (``g3``, ``why`` and ``clocks`` are the caller's); a ``should`` goal and a latency goal are only listed (``typed_goals`` in the result),
    because this loop judges no latency and a ``should`` goal never fails closure. A goal that names no clock (fmax) means the first clock;
    one that names a clock the spec lacks is listed as ``unapplied``."""
    from agent.graph import goals as G
    out: dict[str, Any] = {"goals": [], "power_w": None, "power_text": None}
    for g in G.load(spec):
        row = {**g.as_dict(), "text": g.text(), "applied": None}
        if g.priority == "must":
            if g.kind == "area":
                prev = g3.get(g.metric)
                g3[g.metric], why[g.metric] = float(g.bound), f"typed goal {g.text()}" + (f" (replaces {prev:g} from the budget or default)" if prev != g.bound else "")
                row["applied"] = f"G3 budget {g.metric}"
            elif g.kind == "fmax":
                c = next((c for c in clocks if g.name in (None, c.get("name"))), None)
                if c is None:
                    row["applied"] = "unapplied: no clock " + (g.name or "in the spec")
                else:
                    c["freq_mhz"], c["period_ns"] = g.bound, round(1000 / g.bound, 3)
                    c.pop("min_freq_mhz", None)
                    row["applied"] = f"G2 clock {c.get('name')}"
            elif g.kind == "power":
                out["power_w"], out["power_text"] = g.bound, g.text()
                row["applied"] = "G4 power_w"
        out["goals"].append(row)
    return out


def goal_vector(g1: dict[str, Any] | None, dg: dict[str, Any] | None, goals: dict[str, Any],
                plan_fails: list[str] | None = None, baseline_synth: dict[str, Any] | None = None) -> dict[str, Any]:
    """{goal: {met, value, target, shortfall, detail}}. ``shortfall`` is normalised (0 when met): G1 the failing share
    of tests, G2 the negative slack over the period, G3 the worst over-use ratio, G4 the power over-use ratio."""
    v: dict[str, Any] = {}
    if g1 is None:
        v["G1"] = {"met": None, "value": None, "target": "pass", "shortfall": None, "detail": "not run"}
    else:
        tests = g1.get("tests") or {}
        n, ok = len(tests), sum(1 for x in tests.values() if x)
        sf = 0.0 if g1.get("pass") else (1.0 - ok / n if n else 1.0)
        v["G1"] = {"met": bool(g1.get("pass")), "value": f"{ok}/{n}" if n else ("pass" if g1.get("pass") else "fail"),
                   "target": "all pass", "shortfall": round(sf, 4), "detail": str(g1.get("detail") or "")[:300]}
    if dg is not None and not dg.get("ran"):            # the build was attempted and produced no gates (killed, failed)
        for k in ("G2", "G3", "G4"):
            v[k] = {"met": False, "value": None, "target": None, "shortfall": 1.0,
                    "detail": "the build did not finish (no gates.json; see build/last_build.out)"}
    elif not dg or not dg.get("ran"):
        for k in ("G2", "G3", "G4"):
            v[k] = {"met": None, "value": None, "target": None, "shortfall": None, "detail": "no build"}
    else:
        t = dg.get("timing") or {}
        spec_clk = (goals["G2"]["clocks"] or [{}])[0]
        spec_period = spec_clk.get("period_ns")
        period = t.get("period_ns") or spec_period or 10.0
        wns, whs = t.get("wns_ns"), t.get("whs_ns")
        gates = dg.get("gates") or {}
        cons_ok = all(gates.get(k, True) for k in ("no_unconstrained_endpoints", "exceptions_clean", "io_timing_clean", "pulse_width"))
        # the build must be timed at the spec's clock: a slower clock in the XDC would turn any WNS positive. A period up
        # to 1000 / min_freq_mhz is allowed only when spec.yaml states min_freq_mhz (the gated lower-clock strategy)
        max_period = (1000.0 / float(spec_clk["min_freq_mhz"])) if spec_clk.get("min_freq_mhz") else spec_period
        slow_clock = bool(spec_period and t.get("period_ns") and float(t["period_ns"]) > float(max_period) * 1.001 + 1e-6)
        if slow_clock:
            cons_ok = False
        sf = (max(0.0, -(wns or 0)) + max(0.0, -(whs or 0))) / period
        met2 = wns is not None and whs is not None and wns >= 0 and whs >= 0 and cons_ok
        if not cons_ok and sf == 0:
            sf = 0.01
        v["G2"] = {"met": met2, "value": {"wns_ns": wns, "whs_ns": whs, "tns_ns": t.get("tns_ns"),
                                          "failing_endpoints": t.get("failing_endpoints")},
                   "target": {"wns_ns": 0.0, "whs_ns": 0.0, "period_ns": period}, "shortfall": round(sf, 5),
                   "detail": "" if cons_ok else (f"the build is timed at {t.get('period_ns')} ns, slower than the spec's "
                                                 f"{spec_period} ns clock" if slow_clock else
                                                 "constraints: unconstrained endpoints, exceptions or I/O timing not clean")}
        u = dg.get("utilization") or {}
        bud = goals["G3"]["budget"]
        used = {k: u.get(k) for k in RES}
        ratios = {k: (float(used[k] or 0) / bud[k]) for k in RES if bud.get(k)}
        syn = dg.get("synth") or {}
        bad_syn = bool(syn.get("latches")) or bool(syn.get("ram_in_registers"))
        sf3 = max([0.0] + [r - 1 for r in ratios.values()])
        if bad_syn and sf3 == 0:
            sf3 = 0.01
        v["G3"] = {"met": sf3 == 0, "value": used, "target": bud, "shortfall": round(sf3, 5),
                   "detail": (f"latches {syn.get('latches')}, RAM in registers {syn.get('ram_in_registers')}" if bad_syn else "")}
        p = dg.get("power") or {}
        tot, tj = p.get("total_w"), p.get("junction_c")
        lim = goals["G4"]["power_w"]
        sf4 = max(0.0, (tot or 0) / lim - 1) + max(0.0, ((tj or 0) - goals["G4"]["tj_max_c"]) / goals["G4"]["tj_max_c"])
        v["G4"] = {"met": tot is not None and sf4 == 0, "value": {"total_w": tot, "junction_c": tj},
                   "target": {"power_w": lim, "tj_max_c": goals["G4"]["tj_max_c"]}, "shortfall": round(sf4, 5),
                   "detail": f"vectorless estimate, confidence {p.get('confidence')}"}
        if plan_fails:                                  # the design-time plan: a planned DSP/BRAM missing is an area failure
            v["G3"] = {**v["G3"], "met": False, "shortfall": max(v["G3"]["shortfall"], 0.01),
                       "detail": "; ".join(x for x in (v["G3"]["detail"], *plan_fails) if x)[:600]}
        new_multi, new_removed = synth_regressions(dg.get("synth") or {}, baseline_synth)
        if (new_multi or new_removed) and v["G1"]["met"]:
            # the simulated design is not the built one: G1 cannot be claimed from simulation
            v["G1"] = {**v["G1"], "met": False, "shortfall": 1.0,
                       "detail": f"synthesis disagrees with simulation: {new_multi} new multi-driven net messages, "
                                 f"newly removed instances {new_removed[:3]}"}
    v["G5"] = {"met": None, "value": None, "target": "board checks", "shortfall": None, "detail": "not run yet (no board in this phase)"}
    v["CHK"] = check_goal(dg)
    return v


def check_goal(dg: dict[str, Any] | None) -> dict[str, Any]:
    """CHK: the routed DRC and methodology reports (one checkpoint): no Error and no Critical Warning."""
    if not dg or not dg.get("ran") or (dg.get("drc") is None and dg.get("methodology") is None):
        return {"met": None, "value": None, "target": "no Error or Critical Warning", "shortfall": None,
                "detail": "not reported"}
    bad = [f"{k} {r['rule']} x{r['count']}" for k in ("drc", "methodology") for r in ((dg.get(k) or {}).get("rules") or [])
           if r.get("severity") in ("Error", "Critical Warning")]
    n = sum((dg.get(k) or {}).get(s) or 0 for k in ("drc", "methodology") for s in ("errors", "critical_warnings"))
    return {"met": n == 0, "value": {"blocking": n}, "target": "no Error or Critical Warning",
            "shortfall": round(min(1.0, 0.01 * n), 5), "detail": "; ".join(bad)[:400]}


def synth_regressions(syn: dict[str, Any], baseline: dict[str, Any] | None) -> tuple[int, list[str]]:
    """(new multi-driven-net messages, newly removed instances) of a build against the loop's starting build. A RAM or ROM
    that synthesis already removed from the starting design (a constant table, a disabled option) is the design as it
    is, not a regression; one removed only after a change is logic the design needed. With no baseline (the start build
    itself) nothing counts."""
    if baseline is None:
        return 0, []
    multi = max(0, int(syn.get("multi_driven") or 0) - int(baseline.get("multi_driven") or 0))
    gone = set(baseline.get("removed_instances") or [])
    return multi, [r for r in (syn.get("removed_instances") or []) if r not in gone]


def all_met(v: dict[str, Any]) -> bool:
    """G1 to G4 hold, and CHK holds or was not reported (the sign-off gates then decide)."""
    return all(v[g]["met"] for g in ("G1", "G2", "G3", "G4")) and (v.get("CHK") or {}).get("met") is not False


def choose_goal(v: dict[str, Any], skip: set[str] = frozenset()) -> str | None:
    """G1 first when it fails; then the unmet goal with the largest normalised shortfall (``skip``: goals with no
    strategy left, so a goal the loop cannot act on never hides one it can)."""
    if v["G1"]["met"] is False:
        return "G1"
    unmet = [(v[g]["shortfall"] or 0, g) for g in ("G2", "G3", "G4", "CHK") if (v.get(g) or {}).get("met") is False and g not in skip]
    return max(unmet)[1] if unmet else None


def judge(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """(decision, improved goals, worsened goals). ``accept`` when an unmet goal improved (or became met) and no goal
    worsened; a met goal that stays met is not 'worsened' (a few more FFs inside the budget are fine)."""
    imp, wor = [], []
    for g in JUDGED:
        if g not in before or g not in after:
            continue
        b, a = before[g], after[g]
        if a["met"] is None or b["met"] is None:
            continue
        if b["met"] and not a["met"]:
            wor.append(g)
        elif not b["met"] and a["met"]:
            imp.append(g)
        elif not b["met"] and not a["met"]:
            if (a["shortfall"] or 0) < (b["shortfall"] or 0) - EPS[g]:
                imp.append(g)
            elif (a["shortfall"] or 0) > (b["shortfall"] or 0) + EPS[g]:
                wor.append(g)
    return ("accept" if imp and not wor else "revert"), imp, wor


def vector_line(v: dict[str, Any]) -> str:
    def f(g):
        x = v[g]
        if x["met"] is None:
            return f"{g} -"
        val = x["value"]
        if g == "G2" and isinstance(val, dict):
            val = f"WNS {val['wns_ns']} WHS {val['whs_ns']}"
        elif g == "G3" and isinstance(val, dict):
            val = f"LUT {val.get('lut')} FF {val.get('ff')} BRAM {val.get('bram_tile')} DSP {val.get('dsp')}"
        elif g == "G4" and isinstance(val, dict):
            val = f"{val.get('total_w')} W"
        elif g == "CHK" and isinstance(val, dict):
            val = f"{val.get('blocking')} blocking"
        return f"{g} {'met' if x['met'] else 'NOT met'} ({val})"
    return "; ".join(f(g) for g in GOALS if g in v)


# --- the Designer -----------------------------------------------------------------------------------------------

@dataclass
class EditRequest:
    goal: str
    strategy: pb.Strategy
    why: str
    digest: str
    files: dict[str, str]                 # rel path -> text (the files the writer may change)
    other_files: list[str]
    contract: str                         # what must not change (ports, behaviour, allowed latency)
    plan: str = ""
    history: list[str] = field(default_factory=list)
    failure: str = ""                     # a G1 failure of the previous attempt in this iteration (the functional retry)
    also: list[tuple[pb.Strategy, str, str]] = field(default_factory=list)   # joint plan: (strategy, goal, why) made together


@dataclass
class EditResult:
    files: dict[str, str]                 # rel path -> new text (only changed files)
    note: str = ""
    usd: float = 0.0
    tokens: int = 0
    calls: int = 0




def edit_prompt(r: EditRequest) -> str:
    parts = [_p("graph/closure/edit_prompt_1").format(r.goal, r.strategy.title, r.why, r.strategy.instructions)]
    for s, g, why in r.also:
        parts.append(_p("graph/closure/edit_prompt_2").format(g, s.title, why, s.instructions))
    parts += [
             "\nWHAT MUST NOT CHANGE:\n" + r.contract,
             "\nREPORT DIGEST (from the last build):\n" + r.digest]
    if r.plan:
        parts.append("\n" + r.plan)
    if r.history:
        parts.append(_p("graph/closure/edit_prompt_3") + "\n".join(r.history[-6:]))
    if r.failure:
        parts.append(_p("graph/closure/edit_prompt_4") + r.failure[:2500])
    parts.append(_p("graph/closure/edit_prompt_5") + (", ".join(r.other_files) or "none"))
    for p, t in r.files.items():
        parts.append(f"\n=== FILE: {p} ===\n```{'tcl' if p.endswith('.xdc') else 'systemverilog'}\n{t}\n```")
    return "\n".join(parts)


_BLOCK = re.compile(r"=== FILE: (\S+?)(?: ===)?[ \t]*\n```[a-zA-Z]*\n(.*?)\n```", re.S)     # the closing === is optional (models drop it)


def parse_reply(text: str, allowed: set[str]) -> tuple[dict[str, str], str]:
    files = {}
    for m in _BLOCK.finditer(text or ""):
        p = m.group(1).strip().lstrip("/")
        if p in allowed:
            files[p] = m.group(2).rstrip() + "\n"
    note = next((l[5:].strip() for l in (text or "").splitlines() if l.startswith("NOTE:")), "")
    return files, note


def llm_editor(client: Callable, log: list | None = None, meter: Any = None) -> Callable[[EditRequest], EditResult]:
    """The Designer as one model call through ``client`` (agent.graph.llm.OpenRouterClient or a Replay). With ``meter``
    (the agent graph's Meter) every call is checked against, and counted in, the run's own turn and cost limits."""
    def edit(r: EditRequest) -> EditResult:
        if meter is not None:
            meter.check()                        # raises BudgetExceeded at the run's limit
        rep = client([{"role": "system", "content": _p("graph/closure/system")}, {"role": "user", "content": edit_prompt(r)}])
        if meter is not None:
            meter.add(rep)
        files, note = parse_reply(rep.text, set(r.files) | {f for f in r.other_files if f.endswith((".sv", ".v"))})
        files = {k: v for k, v in files.items() if not k.endswith(".xdc") or k in r.files}   # the XDC only when offered
        usd = rep.cost if rep.cost is not None else 0.05          # unreported cost counts at the ceiling (llm.py rule)
        if log is not None:
            log.append({"goal": r.goal, "strategy": r.strategy.id, "cost": rep.cost, "prompt_tokens": rep.prompt_tokens,
                        "completion_tokens": rep.completion_tokens, "seconds": rep.seconds, "files": sorted(files), "note": note})
        return EditResult(files=files, note=note, usd=usd, tokens=rep.prompt_tokens + rep.completion_tokens, calls=1)
    return edit


# --- the controller -----------------------------------------------------------------------------------------------

@dataclass
class Workspace:
    """The design under closure: ``root`` holds ``rtl/``; snapshots are plain copies (no git: a design dir may sit in
    any checkout)."""
    root: Path

    @property
    def rtl(self) -> Path:
        return self.root / "rtl"

    def read(self) -> dict[str, str]:
        """The RTL (SystemVerilog, Verilog and VHDL: brief 153), and the design's own XDC files (a constraints fix changes them; restored like the RTL)."""
        from flow import sources
        out = {f"rtl/{p.name}": p.read_text() for p in sources.design_rtl(self.root)}
        out.update({p.name: p.read_text() for p in sorted(self.root.glob("*.xdc"))})
        return out

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            (self.root / rel).write_text(text)

    def restore(self, snap: dict[str, str]) -> None:
        from flow import sources
        for p in sources.design_rtl(self.root):
            if f"rtl/{p.name}" not in snap:
                p.unlink()
        self.write(snap)


def unified_diff(a: dict[str, str], b: dict[str, str]) -> str:
    out = []
    for p in sorted(set(a) | set(b)):
        if a.get(p) != b.get(p):
            out += difflib.unified_diff((a.get(p) or "").splitlines(True), (b.get(p) or "").splitlines(True), f"a/{p}", f"b/{p}")
    return "".join(out)


def module_files(files: dict[str, str]) -> dict[str, str]:
    """module name -> the file that defines it."""
    out = {}
    for p, t in files.items():
        for m in re.findall(r"^\s*module\s+(\w+)", t, re.M):
            out[m] = p
    return out


def files_for_path(dg: dict[str, Any], files: dict[str, str], hier_modules: dict[str, str]) -> list[str]:
    """The RTL files that hold the failing path's registers (by instance -> module -> file); all files if unknown."""
    mf = module_files(files)
    want = []
    p = dg.get("setup_path") or {}
    for end in (p.get("source_reg"), p.get("dest_reg")):
        inst = (end or {}).get("instance")
        mod = hier_modules.get(inst or "")
        if mod and mod in mf and mf[mod] not in want:
            want.append(mf[mod])
    return want or sorted(p for p in files if p.startswith("rtl/"))


@dataclass
class Closure:
    ws: Workspace
    goals: dict[str, Any]
    g1: Callable[[Path], dict[str, Any]]                 # rtl dir -> {pass, tests, detail}
    build: Callable[[Path], dict[str, Any]]              # design dir -> flow.digest.build.digest_build(...)
    editor: Callable[[EditRequest], EditResult]
    contract: str
    spec: dict[str, Any] = field(default_factory=dict)
    plan_text: str = ""
    plan_check: Callable[[dict[str, Any]], list[str]] | None = None    # digest -> plan failures (post-synthesis)
    max_iter: int = 8
    max_usd: float = 3.0
    max_seconds: float = 6 * 3600
    stall_n: int = 2
    g1_retries: int = 1
    record: Path | None = None
    log: Callable[[str], None] = print
    # the joint loop (agent.graph.closure_plan): fixes for several goals in one change; off = one goal per iteration
    joint: bool = True
    max_actions: int = 3
    # the early check: design dir -> flow.digest.build.digest_synth(...) of a synthesis-only build (None: skipped)
    synth: Callable[[Path], dict[str, Any]] | None = None
    # the sign-off: the accepted design's full digest -> {pass, failed: [gate names]} (None: not run, never claimed)
    signoff: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    case: str = ""

    history: list[dict[str, Any]] = field(default_factory=list)
    usd: float = 0.0
    tokens: int = 0
    calls: int = 0

    def _rec(self, row: dict[str, Any]) -> None:
        self.history.append(row)
        if self.record:
            self.record.mkdir(parents=True, exist_ok=True)
            with (self.record / "history.jsonl").open("a") as f:
                f.write(json.dumps(row, default=str) + "\n")

    def _act(self, row: dict[str, Any]) -> None:
        """One row of the action log (closure_actions.jsonl, schema fda.closure_action/1)."""
        if self.record:
            self.record.mkdir(parents=True, exist_ok=True)
            with (self.record / "closure_actions.jsonl").open("a") as f:
                f.write(json.dumps(row, default=str) + "\n")

    def _hier_modules(self, dg: dict[str, Any]) -> dict[str, str]:
        mods = {}
        for k in ("lut", "ff"):
            for r in (dg.get("util_top") or {}).get(k) or []:
                mods[r["path"]] = r["module"]
        return {**mods, **(dg.get("hier_modules") or {})}

    def _choose(self, vec, dg, tried) -> dict[str, Any]:
        """The plan for this iteration: the joint plan, or (``joint=False``) 62A's one goal and one strategy."""
        plan_fails = self._plan_fails(dg)
        if self.joint:
            from agent.graph import closure_plan as cp
            exhausted = {k for k, n in tried.items() if n >= self.stall_n}
            return cp.plan(vec, dg, self.spec, plan_fails, exhausted, self.max_actions)
        skip: set[str] = set()
        while True:                          # the worst goal that still has a strategy; skip the ones that have none
            g = choose_goal(vec, skip)
            if g is None:
                return {"actions": [], "skipped": [], "target_stage": "rtl", "violations": []}
            cands = [(s, why) for s, why in pb.applicable(g, dg or {}, vec, self.spec, plan_fails)
                     if s.phase == "ready" and tried.get((g, s.cls), 0) < self.stall_n]
            if cands:
                s, why = cands[0]
                return {"actions": [{"id": s.id, "cls": s.cls, "goal": g, "stage": s.stage, "hard": s.hard, "why": why,
                                     "predicted": dict(s.predicted)}],
                        "skipped": [], "target_stage": s.stage, "violations": []}
            if g == "G1":
                return {"actions": [], "skipped": [], "target_stage": "rtl", "violations": []}
            skip.add(g)

    def run(self) -> dict[str, Any]:
        from agent.graph import closure_plan as cp
        t0 = time.monotonic()
        snap = self.ws.read()
        g1 = self.g1(self.ws.rtl)
        tb = time.monotonic()
        dg = self.build(self.ws.root) if g1.get("pass") else None
        build_s = round(time.monotonic() - tb, 1)
        vec = goal_vector(g1, dg, self.goals, self._plan_fails(dg))
        base_synth = (dg or {}).get("synth") or {}
        built = snap                                     # the files the last full build in build/ was made from
        start = {"vector": vec, "digest": _small(dg)}
        self.log(f"[closure] start: {vector_line(vec)}")
        self._rec({"iter": 0, "kind": "start", "vector": vec, "digest": _small(dg), "build_seconds": build_s})
        tried: dict[tuple[str, str], int] = {}          # (goal, class) -> iterations without progress
        attempts: list[dict[str, Any]] = []
        stop, reent, signoff = None, None, None
        if not g1.get("pass"):
            stop = "G1 fails at the start: functional repair belongs to stage 2, not the closure loop"
        elif dg is not None and not dg.get("ran"):
            stop = "the first build did not finish (no gates.json): nothing to measure; see build/last_build.out"
        it = 0
        while stop is None:
            if all_met(vec):
                signoff = self._signoff(dg, snap, built)
                if signoff is None or signoff["pass"]:
                    stop = ("all goals met (G1-G4; G5, the board, not run yet); sign-off passed" if signoff else
                            "goals met on the loop's measures (G1-G4); sign-off not run, closure not claimed")
                else:
                    stop = ("goals met on the loop's measures, but the sign-off failed: "
                            + ", ".join(signoff.get("failed") or [])[:300] + "; closure not claimed")
                break
            if it >= self.max_iter:
                stop = f"iteration limit {self.max_iter} reached"
                break
            if self.usd >= self.max_usd:
                stop = f"cost limit ${self.max_usd} reached (${self.usd:.4f})"
                break
            if time.monotonic() - t0 > self.max_seconds:
                stop = f"time limit {self.max_seconds} s reached"
                break
            joint = self._choose(vec, dg, tried)
            if not joint["actions"]:
                unmet = [g for g in ("G2", "G3", "G4", "CHK") if (vec.get(g) or {}).get("met") is False]
                stop = (f"goal {', '.join(unmet)} not met; strategy classes exhausted" if unmet
                        else "no unmet goal this loop can act on")
                break
            if joint["target_stage"] in ("spec", "architecture"):
                reent = cp.reentry(joint)
                stop = f"loop back to the {joint['target_stage']} stage: " + "; ".join(
                    f"{a['goal']} {a['id']}" for a in joint["actions"])
                self._rec({"iter": it + 1, "kind": "loopback", "plan": joint, "reentry": reent})
                self._act(cp.action_record(run=str(self.record.name if self.record else self.case), iteration=it + 1,
                                           tags=cp.design_tags(self.spec, self.ws.read(), self.case), dg_before=dg,
                                           vec_before=vec, joint=joint, decision="loopback", reason=stop,
                                           outcome="loopback", improved=[], worsened=[], dg_after=None, vec_after=vec,
                                           early=None, usd=0.0, tokens=0, build_seconds=None, synth_seconds=None))
                break
            acts = [(pb.BY_ID[a["id"]], a["goal"], a["why"]) for a in joint["actions"]]
            strat, goal, why = acts[0]
            it += 1
            files = self.ws.read()
            hm = self._hier_modules(dg or {})
            want = files_for_path(dg or {}, files, hm)
            if any(s.stage == "constraints" for s, _, _ in acts):      # a constraints fix: the design's XDC is offered too
                want += [p for p in files if p.endswith(".xdc") and p not in want]
            from flow.digest.build import digest_text
            digest = digest_text(dg or {}, goal) if goal in ("G2", "G3", "G4") else digest_text(dg or {})
            if any(g == "CHK" for _, g, _ in acts) or (vec.get("CHK") or {}).get("met") is False:
                digest += "\nCHECKS (routed DRC and methodology): " + str((vec.get("CHK") or {}).get("detail") or "none")
            req = EditRequest(goal=goal, strategy=strat, why=why, digest=digest,
                              files={p: files[p] for p in want}, other_files=[p for p in files if p not in want],
                              contract=self.contract, plan=self.plan_text, also=[(s, g, w) for s, g, w in acts[1:]],
                              history=[f"iteration {a['iter']}: {'+'.join(a['strategies_all'])} -> {a['decision']} ({a['summary']})"
                                       for a in attempts])
            self.log(f"[closure] iteration {it}: " + "; ".join(f"goal {g} strategy {s.id}" for s, g, _ in acts)
                     + (f" (skipped: {', '.join(x['id'] + ' ' + x['why'] for x in joint['skipped'])[:200]})" if joint["skipped"] else ""))
            usd0, tok0 = self.usd, self.tokens
            res = self.editor(req)
            self._spend(res)
            g1n, retries = None, 0
            if res.files:
                self.ws.write(res.files)
                g1n = self.g1(self.ws.rtl)
                while not g1n.get("pass") and retries < self.g1_retries and self.usd < self.max_usd:
                    retries += 1
                    req.failure = str(g1n.get("detail") or g1n.get("tests"))
                    req.files = {p: self.ws.read().get(p, "") for p in want}
                    r2 = self.editor(req)
                    self._spend(r2)
                    if r2.files:
                        self.ws.write(r2.files)
                        res.files.update(r2.files)
                        res.note = r2.note or res.note
                    g1n = self.g1(self.ws.rtl)
            after_files = self.ws.read()
            diff = unified_diff(snap, after_files)
            early, synth_s, build_s = None, None, None
            clock_edit = clock_lines_changed(snap, after_files) and not any(s.id == "p_clock" for s, _, _ in acts)
            if not res.files or not diff:
                decision, imp, wor, vec2, dg2 = "revert", [], [], vec, dg
                summary, outcome = "the writer changed nothing", "no_change"
            elif clock_edit:
                decision, imp, wor, vec2, dg2 = "revert", [], ["G2"], vec, dg
                summary, outcome = "the change edits a clock definition in the XDC, which no chosen fix allows", "clock_edit"
            elif not g1n.get("pass"):
                vec2 = goal_vector(g1n, None, self.goals)
                vec2 = {**vec, "G1": vec2["G1"]}
                decision, imp, wor, dg2 = "revert", [], ["G1"], dg
                outcome = "g1_fail"
                summary = f"G1 failed after {retries} functional retr{'y' if retries == 1 else 'ies'}: {vec2['G1']['value']}"
            else:
                if self.synth is not None:
                    ts = time.monotonic()
                    early = early_check(self.synth(self.ws.root), dg, vec, self.goals, acts,
                                        self._plan_fails_synth(), base_synth)
                    synth_s = round(time.monotonic() - ts, 1)
                if early and early["reject"]:
                    decision, imp, wor, vec2, dg2 = "revert", [], list(early.get("worsened") or []), vec, dg
                    summary, outcome = "early check after synthesis: " + early["reason"], "early_reject"
                    built = None                         # build/ now holds a synthesis-only build of the rejected change
                else:
                    tb = time.monotonic()
                    dg2 = self.build(self.ws.root)
                    build_s = round(time.monotonic() - tb, 1)
                    built = after_files
                    vec2 = goal_vector(g1n, dg2, self.goals, self._plan_fails(dg2), base_synth)
                    decision, imp, wor = judge(vec, vec2)
                    outcome = "accepted" if decision == "accept" else "built_reverted"
                    summary = vector_line(vec2) + "".join(f"; {g}: {vec2[g]['detail'][:300]}" for g in wor if vec2[g].get("detail"))
            delta = _delta(vec, vec2)
            row = {"iter": it, "kind": "iteration", "goal": goal, "strategy": strat.id, "class": strat.cls, "why": why,
                   "strategies_all": [s.id for s, _, _ in acts], "plan": joint,
                   "note": res.note, "g1_retries": retries, "decision": decision, "improved": imp, "worsened": wor,
                   "early": early, "vector_before": vec, "vector_after": vec2, "delta": delta, "diff": diff, "summary": summary,
                   "digest_after": _small(dg2), "usd_total": round(self.usd, 6), "tokens_total": self.tokens,
                   "build_seconds": build_s, "synth_seconds": synth_s}
            attempts.append(row)
            self._rec(row)
            self._act(cp.action_record(run=str(self.record.name if self.record else self.case), iteration=it,
                                       tags=cp.design_tags(self.spec, files, self.case),
                                       dg_before=dg, vec_before=vec, joint=joint, decision=decision, reason=summary,
                                       outcome=outcome, improved=imp, worsened=wor,
                                       dg_after=dg2 if dg2 is not dg else None, vec_after=vec2, early=early,
                                       usd=self.usd - usd0, tokens=self.tokens - tok0, build_seconds=build_s,
                                       synth_seconds=synth_s))
            self.log(f"[closure] iteration {it}: {decision}; {summary}")
            for s, g, _ in acts:
                if decision == "accept" and g in imp:
                    tried[(g, s.cls)] = 0
                else:
                    tried[(g, s.cls)] = tried.get((g, s.cls), 0) + 1
            if decision == "accept":
                snap, vec, dg = after_files, vec2, dg2
            else:
                self.ws.restore(snap)
        report = self.stop_report(stop or "stopped", start, vec, attempts, time.monotonic() - t0)
        report["signoff"] = signoff
        report["closure_claimed"] = bool(all_met(vec) and signoff is not None and signoff.get("pass"))
        report["reentry"] = reent
        if self.record:
            (self.record / "summary.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
        self.log(f"[closure] stop: {report['stop']}")
        return report

    def _signoff(self, dg: dict[str, Any] | None, snap: dict[str, str], built: dict[str, str] | None) -> dict[str, Any] | None:
        """The final sign-off on the accepted design: the independent bench once more, a full build of exactly these
        files (rebuilt when build/ holds another attempt), and the flow's sequential gates."""
        if self.signoff is None:
            return None
        g1 = self.g1(self.ws.rtl)
        if built != snap:
            self.log("[closure] sign-off: rebuilding the accepted design (build/ holds another attempt)")
            dg = self.build(self.ws.root)
        out = dict(self.signoff(dg or {}))
        out["rebuilt"] = built != snap
        if not g1.get("pass"):
            out["pass"] = False
            out["failed"] = ["G1 (independent bench)"] + list(out.get("failed") or [])
        vec = goal_vector(g1, dg, self.goals, self._plan_fails(dg))
        if not all_met(vec):
            out["pass"] = False
            out["failed"] = list(out.get("failed") or []) + [f"goal vector on the rebuilt design: {vector_line(vec)}"]
        return out

    def _plan_fails(self, dg: dict[str, Any] | None) -> list[str]:
        if not (self.plan_check and dg and dg.get("ran")):
            return []
        try:
            return list(self.plan_check(dg))
        except Exception as e:                       # noqa: BLE001 (a plan check must never stop the loop)
            return [f"plan: check not run ({type(e).__name__})"]

    def _plan_fails_synth(self) -> list[str] | None:
        if not self.plan_check:
            return None
        try:
            return list(self.plan_check({"ran": True}))
        except Exception:                            # noqa: BLE001
            return None

    def _spend(self, r: EditResult) -> None:
        self.usd += r.usd
        self.tokens += r.tokens
        self.calls += r.calls

    def stop_report(self, stop: str, start: dict, vec: dict, attempts: list[dict], secs: float) -> dict[str, Any]:
        unmet = {g: {"best": vec[g]["value"], "target": vec[g]["target"],
                     "tried": [f"{'+'.join(a.get('strategies_all') or [a['strategy']])} ({a['decision']})" for a in attempts
                               if g in [x["goal"] for x in (a.get("plan") or {}).get("actions") or [{"goal": a["goal"]}]]]}
                 for g in JUDGED if (vec.get(g) or {}).get("met") is False}
        text = [f"goal {g} not met; best value {u['best']}; tried: {', '.join(u['tried']) or 'nothing'}" for g, u in unmet.items()]
        return {"stop": stop, "all_met": all_met(vec), "start": start["vector"], "final": vec,
                "start_line": vector_line(start["vector"]), "final_line": vector_line(vec), "unmet": unmet, "unmet_text": text,
                "iterations": len(attempts), "accepted": sum(a["decision"] == "accept" for a in attempts),
                "reverted": sum(a["decision"] == "revert" for a in attempts),
                "early_rejected": sum(bool((a.get("early") or {}).get("reject")) for a in attempts),
                "strategies": [(a["strategy"], a["decision"]) for a in attempts],
                "strategies_all": [(a.get("strategies_all") or [a["strategy"]], a["decision"]) for a in attempts],
                "usd": round(self.usd, 6), "tokens": self.tokens, "llm_calls": self.calls, "seconds": round(secs, 1)}


def clock_lines_changed(a: dict[str, str], b: dict[str, str]) -> bool:
    """True when an XDC's clock definitions differ (create_clock, create_generated_clock, set_clock_groups): the loop
    must not close timing by slowing or regrouping the clocks the spec fixes."""
    pat = re.compile(r"^\s*(?:create_clock|create_generated_clock|set_clock_groups)\b.*$", re.M)
    for p in set(a) | set(b):
        if p.endswith(".xdc") and pat.findall(a.get(p) or "") != pat.findall(b.get(p) or ""):
            return True
    return False


def early_check(syn: dict[str, Any] | None, dg: dict[str, Any] | None, vec: dict[str, Any], goals: dict[str, Any],
                acts: list[tuple[pb.Strategy, str, str]], plan_fails: list[str] | None,
                base_synth: dict[str, Any] | None) -> dict[str, Any]:
    """The post-synthesis estimate of a change, before any implementation run. Rejects (revert without implementing)
    only on what synthesis already knows exactly or nearly so:

    - a block RAM or DSP count over its budget that was within it (these counts do not change in implementation);
    - an area fix aimed at BRAM or DSP that did not lower that count, or one aimed at LUT/FF whose post-synthesis count
      did not fall below the last build's post-synthesis count;
    - LUT or FF more than 10 % over a budget that was met (implementation trims little);
    - new multi-driven nets or newly removed instances (the netlist is not the simulated design);
    - a planned DSP or BRAM the netlist does not have.

    Timing and power after synthesis are estimates: recorded, never a reason to reject."""
    if not syn or not syn.get("ran"):
        return {"reject": False, "reason": "no post-synthesis reports", "estimate": None}
    u = syn.get("utilization") or {}
    bud = goals["G3"]["budget"]
    before = ((dg or {}).get("post_synth") or {}).get("utilization") or {}
    met3 = (vec.get("G3") or {}).get("met")
    reasons, worse = [], []
    for k in ("bram_tile", "dsp"):
        if u.get(k) is not None and bud.get(k) is not None and float(u[k]) > float(bud[k]) \
                and float(((dg or {}).get("utilization") or {}).get(k) or 0) <= float(bud[k]):
            reasons.append(f"{k} {u[k]} over its budget {bud[k]} (was within it)")
            worse.append("G3")
    for s, g, _ in acts:
        if g != "G3":
            continue
        for k in ("bram_tile", "dsp", "lut", "ff"):
            if s.predicted.get(k) == "-" and k in pb.over_budget(vec) and u.get(k) is not None and before.get(k) is not None \
                    and float(u[k]) >= float(before[k]):
                reasons.append(f"{s.id} was to lower {k}, but synthesis still has {u[k]} (was {before[k]})")
    for k in ("lut", "ff"):
        if met3 and u.get(k) is not None and bud.get(k) and float(u[k]) > 1.10 * float(bud[k]):
            reasons.append(f"{k} {u[k]} more than 10 % over its budget {bud[k]}")
            worse.append("G3")
    nm, nr = synth_regressions(syn.get("synth") or {}, base_synth)
    if nm or nr:
        reasons.append(f"synthesis disagrees with simulation: {nm} new multi-driven net messages, newly removed {nr[:3]}")
        worse.append("G1")
    if plan_fails:
        reasons.append("; ".join(plan_fails)[:300])
    est = {"utilization": {k: u.get(k) for k in (*RES, "carry4")}, "wns_est_ns": (syn.get("timing") or {}).get("wns_ns"),
           "drc": syn.get("drc"), "methodology": syn.get("methodology")}
    return {"reject": bool(reasons), "reason": "; ".join(reasons) or "within the post-synthesis estimates",
            "worsened": sorted(set(worse)), "estimate": est}


def _delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for g in JUDGED:
        if g not in a or g not in b:
            continue
        x, y = a[g]["value"], b[g]["value"]
        if isinstance(x, dict) and isinstance(y, dict):
            out[g] = {k: (round(y[k] - x[k], 4) if isinstance(x.get(k), (int, float)) and isinstance(y.get(k), (int, float)) else None)
                      for k in x}
        else:
            out[g] = None if x == y else {"from": x, "to": y}
    return out


def _small(dg: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dg:
        return None
    p = dg.get("setup_path") or {}
    return {"timing": dg.get("timing"), "utilization": {k: (dg.get("utilization") or {}).get(k) for k in (*RES, "carry4")},
            "power": {k: (dg.get("power") or {}).get(k) for k in ("total_w", "dynamic_w", "junction_c")},
            "setup_path": {k: p.get(k) for k in ("slack_ns", "source", "destination", "data_path_ns", "logic_levels",
                                                 "levels_by_type", "route_pct")} if p else None,
            "setup_features": dg.get("setup_features"), "synth": dg.get("synth")}


# --- the agent-graph hook (stage 6, --closure on) ----------------------------------------------------------------

def graph_stage(rt: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Stage 6 with ``--closure on``: run the controller on the run's design. G1 is the stage-2 evidence the graph
    already trusts (lint, simulate, verification gates), re-run after every change; the build is the graph's own
    ``_build(rt, "route")``. Returns a note for the stage's gate (the gate still decides).

    Cost: the writer's calls count against the run's own turn and USD limits (``rt.meter``) as well as ``closure_usd``.
    Builds: the stage's gate then calls ``_build(rt, "route")`` again; that is a cache hit when the loop's last build is
    the design it leaves, and one more Vivado run when the last iteration was reverted (the cache keeps one key)."""
    from agent.core import dispatch
    from agent.graph import run as gr
    from flow import timing_plan
    from flow.digest.build import digest_build

    def g1(_rtl: Path) -> dict[str, Any]:
        lint = dispatch(rt.session, "lint", {})
        sim = gr.simulate_gate(rt.session) if lint.get("ok") else {"ok": False}
        ver = (dispatch(rt.session, "gates", {"kind": "verif"}).get("gates") or {})
        ok = bool(lint.get("ok")) and bool(sim.get("ok")) and (ver.get("reached") or "") >= rt.cfg.verif_level
        return {"pass": ok, "tests": {"lint": bool(lint.get("ok")), "simulate": bool(sim.get("ok")),
                                      f"verif>={rt.cfg.verif_level}": (ver.get("reached") or "") >= rt.cfg.verif_level},
                "detail": str(sim.get("text") or lint.get("output") or "")[-1500:]}

    def build(d: Path) -> dict[str, Any]:
        gr._build(rt, "route")
        return digest_build(d / "build" / "base")

    spec = gr._spec(rt)
    plan = timing_plan.load_plan(rt.design)
    client = rt.resolver.chat("closure")
    c = Closure(ws=Workspace(rt.design), goals=goals_from_spec(spec, rt.cfg.board), g1=g1, build=build,
                editor=llm_editor(client, meter=rt.meter), contract=contract_from_spec(spec), spec=spec,
                plan_text=timing_plan.plan_text(plan) if plan else "",
                plan_check=(lambda _dg: timing_plan.post_synth_failures(rt.design, json.loads((rt.design / "build" / "base" / "gates.json").read_text())))
                if plan else None,
                max_iter=int(rt.cfg.run_limits.get("closure_iter", 6)), max_usd=float(rt.cfg.run_limits.get("closure_usd", 1.0)),
                record=rt.run_dir / "closure", case=rt.cfg.name)
    # sign-off: stages 7 (power) and 8 (DRC) and the stage gates still run after this stage, as the sequential sign-off
    from agent.graph.llm import BudgetExceeded
    try:
        rep = c.run()
    except BudgetExceeded as e:                      # the run's own limit: the graph's node_work handles it the same way
        if str(e).startswith("run "):
            return {"stop": f"budget: {e}"}
        return {"note": "", "detail": f"[closure] stage visit ended: {e}"}
    if rep.get("reentry"):                          # the plan needs the spec or the architecture changed: go back there
        return {"note": "", "loopback": rep["reentry"], "detail": "[closure] " + rep["stop"]}
    return {"note": "", "detail": "[closure] " + rep["stop"] + "; " + rep["final_line"]}


def contract_from_spec(spec: dict[str, Any]) -> str:
    """What the closure writer must keep: the ports, and the handshake/latency text of spec.yaml."""
    beh = spec.get("behaviour") or {}
    hs = []
    for k, v in (beh.items() if isinstance(beh, dict) else []):
        if any(w in k.lower() for w in ("handshake", "latency", "timing", "busy", "valid")):
            hs += v if isinstance(v, list) else [str(v)]
    lat = (spec.get("timing") or {}).get("latency") if isinstance(spec.get("timing"), dict) else None
    return (_p("graph/closure/contract_from_spec_1")
            + (_p("graph/closure/contract_from_spec_2") + " ".join(map(str, hs)) if hs else "")
            + (f" Stated latencies: {lat}." if lat else "")
            + _p("graph/closure/contract_from_spec_3"))


__getattr__ = _prompts.module_getattr(__name__, {'SYSTEM': 'graph/closure/system'})
