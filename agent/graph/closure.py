"""The closure loop (brief 62A): iterate until every goal is met, or stop with an honest report.

Goals (all must hold to finish; brief 62, "The goals"):

- **G1** functional correctness in simulation: the independent bench (the hidden acceptance bench of a benchmark task,
  or the V-gates in the agent graph) passes.
- **G2** timing: WNS >= 0 and WHS >= 0 at the spec's clocks, no unconstrained endpoint, exceptions and I/O timing clean.
- **G3** area: LUT, FF, BRAM, DSP, IO within ``spec.yaml`` ``budget`` (else a default share of the part, 80 %); no
  inferred latch, no RAM built in registers.
- **G4** power: Vivado's total on-chip power within ``budget.power_w`` (else the board limit, 2.0 W on the Nexys A7 on
  wall power) and junction temperature within 85 C.
- **G5** hardware: not evaluated in 62A (``met: None``).

The controller (:class:`Closure`):

1. requires G1 at the start (functional repair is stage 2's job, not this loop's);
2. builds once and computes the goal vector;
3. picks the unmet goal with the largest normalised shortfall, and the best strategy for it from the playbook
   (``agent.graph.closure_playbook``) that is not exhausted and whose predicted cost fits the other goals' headroom;
4. asks the RTL writer for the change, re-runs G1 (one functional retry, then revert), rebuilds, and judges the new
   vector against the last accepted one: kept when it improves an unmet goal and worsens none, else reverted;
5. counts iterations without progress per (goal, strategy class); after ``stall_n`` the class is exhausted (the H4
   "stall rule" of brief 42); when every class for a goal is exhausted, or a limit is reached, it stops with
   "goal X not met; best value Y; what was tried".

Every iteration is recorded (vector before and after, strategy and why, the diff, the delta on every goal, cost).
The build, the G1 check and the RTL writer are passed in, so CI tests the controller with fakes and recorded reports.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent.graph import closure_playbook as pb

GOALS = ("G1", "G2", "G3", "G4", "G5")
DEFAULT_SHARE = 0.80
BOARD_POWER_W = {"nexys_a7_100t": 2.0}      # house rules: wall power, report_power total on-chip <= 2.0 W
TJ_MAX_C = 85.0
EPS = {"G1": 1e-9, "G2": 0.0005, "G3": 0.0005, "G4": 0.0005}     # a shortfall change below this is no change
RES = ("lut", "ff", "bram_tile", "dsp", "iob")
_AVAIL = {"lut": "lut_available", "ff": "ff_available", "bram_tile": "bram_tile_available", "dsp": "dsp_available",
          "iob": "iob_available"}
PART_DEFAULT = {"lut": 63400, "ff": 126800, "bram_tile": 135, "dsp": 240, "iob": 210}


# --- goals --------------------------------------------------------------------------------------------------------

def goals_from_spec(spec: dict[str, Any], board: str = "nexys_a7_100t") -> dict[str, Any]:
    """The targets of G1..G5 from spec.yaml: ``clocks`` (freq_mhz), ``budget: {lut, ff, bram, dsp, io, power_w}``.
    A missing budget entry gets the default (80 % of the part; the board power limit), with that reason recorded."""
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
    clocks = [{"name": c.get("name"), "freq_mhz": c.get("freq_mhz"), "period_ns": round(1000 / float(c["freq_mhz"]), 3)}
              for c in spec.get("clocks") or [] if c.get("freq_mhz")]
    pw = b.get("power_w")
    return {
        "G1": {"what": "the independent bench and the verification gates pass"},
        "G2": {"wns_min_ns": 0.0, "whs_min_ns": 0.0, "clocks": clocks},
        "G3": {"budget": g3, "why": why, "no_latches": True, "no_ram_in_registers": True},
        "G4": {"power_w": float(pw) if pw is not None else BOARD_POWER_W.get(board, 2.0),
               "why": "spec.yaml budget" if pw is not None else f"no budget in spec.yaml: the board limit ({board})",
               "tj_max_c": TJ_MAX_C},
        "G5": {"what": "board checks (62C)"},
    }


def goal_vector(g1: dict[str, Any] | None, dg: dict[str, Any] | None, goals: dict[str, Any],
                plan_fails: list[str] | None = None) -> dict[str, Any]:
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
        period = t.get("period_ns") or ((goals["G2"]["clocks"] or [{}])[0].get("period_ns")) or 10.0
        wns, whs = t.get("wns_ns"), t.get("whs_ns")
        gates = dg.get("gates") or {}
        cons_ok = all(gates.get(k, True) for k in ("no_unconstrained_endpoints", "exceptions_clean", "io_timing_clean", "pulse_width"))
        sf = (max(0.0, -(wns or 0)) + max(0.0, -(whs or 0))) / period
        met2 = wns is not None and whs is not None and wns >= 0 and whs >= 0 and cons_ok
        if not cons_ok and sf == 0:
            sf = 0.01
        v["G2"] = {"met": met2, "value": {"wns_ns": wns, "whs_ns": whs, "tns_ns": t.get("tns_ns"),
                                          "failing_endpoints": t.get("failing_endpoints")},
                   "target": {"wns_ns": 0.0, "whs_ns": 0.0, "period_ns": period}, "shortfall": round(sf, 5),
                   "detail": "" if cons_ok else "constraints: unconstrained endpoints, exceptions or I/O timing not clean"}
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
        syn = dg.get("synth") or {}
        if (syn.get("multi_driven") or syn.get("removed_instances")) and v["G1"]["met"]:
            # the simulated design is not the built one: G1 cannot be claimed from simulation
            v["G1"] = {**v["G1"], "met": False, "shortfall": 1.0,
                       "detail": f"synthesis disagrees with simulation: {syn.get('multi_driven')} multi-driven net messages, "
                                 f"removed instances {syn.get('removed_instances')[:3]}"}
    v["G5"] = {"met": None, "value": None, "target": "board checks", "shortfall": None, "detail": "not run in 62A"}
    return v


def all_met(v: dict[str, Any]) -> bool:
    return all(v[g]["met"] for g in ("G1", "G2", "G3", "G4"))


def choose_goal(v: dict[str, Any], skip: set[str] = frozenset()) -> str | None:
    """G1 first when it fails; then the unmet goal with the largest normalised shortfall."""
    if v["G1"]["met"] is False:
        return "G1"
    unmet = [(v[g]["shortfall"] or 0, g) for g in ("G2", "G3", "G4") if v[g]["met"] is False and g not in skip]
    return max(unmet)[1] if unmet else None


def judge(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """(decision, improved goals, worsened goals). ``accept`` when an unmet goal improved (or became met) and no goal
    worsened; a met goal that stays met is not 'worsened' (a few more FFs inside the budget are fine)."""
    imp, wor = [], []
    for g in ("G1", "G2", "G3", "G4"):
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
        return f"{g} {'met' if x['met'] else 'NOT met'} ({val})"
    return "; ".join(f(g) for g in GOALS)


# --- the RTL writer -----------------------------------------------------------------------------------------------

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


@dataclass
class EditResult:
    files: dict[str, str]                 # rel path -> new text (only changed files)
    note: str = ""
    usd: float = 0.0
    tokens: int = 0
    calls: int = 0


SYSTEM = ("You are the RTL engineer in an FPGA timing-closure loop (Vivado 2026.1, Artix-7 -1). The flow, not you, decides "
          "whether a change worked: it re-runs an independent simulation bench you cannot see and rebuilds the design. "
          "Make one focused change of the kind asked for. Reply with every file you change in full, each as\n"
          "=== FILE: <path> ===\n```systemverilog\n<whole file>\n```\nand nothing else after the last block except one line "
          "starting NOTE: that says what you changed and the latency it adds (in clocks).")


def edit_prompt(r: EditRequest) -> str:
    parts = [f"GOAL {r.goal}. Strategy: {r.strategy.title}.\nWhy this strategy: {r.why}\n\n{r.strategy.instructions}",
             "\nWHAT MUST NOT CHANGE:\n" + r.contract,
             "\nREPORT DIGEST (from the last build):\n" + r.digest]
    if r.plan:
        parts.append("\n" + r.plan)
    if r.history:
        parts.append("\nEARLIER ITERATIONS (do not repeat a change that was reverted):\n" + "\n".join(r.history[-6:]))
    if r.failure:
        parts.append("\nYOUR LAST CHANGE FAILED THE INDEPENDENT BENCH. Fix it, keeping the timing change:\n" + r.failure[:2500])
    parts.append("\nOther design files (not shown; do not change them): " + (", ".join(r.other_files) or "none"))
    for p, t in r.files.items():
        parts.append(f"\n=== FILE: {p} ===\n```systemverilog\n{t}\n```")
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


def llm_editor(client: Callable, log: list | None = None) -> Callable[[EditRequest], EditResult]:
    """The RTL writer as one model call through ``client`` (agent.graph.llm.OpenRouterClient or a Replay)."""
    def edit(r: EditRequest) -> EditResult:
        rep = client([{"role": "system", "content": SYSTEM}, {"role": "user", "content": edit_prompt(r)}])
        files, note = parse_reply(rep.text, set(r.files) | {f for f in r.other_files if f.endswith((".sv", ".v"))})
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
        return {f"rtl/{p.name}": p.read_text() for p in sorted(self.rtl.glob("*.sv"))}

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            (self.root / rel).write_text(text)

    def restore(self, snap: dict[str, str]) -> None:
        for p in self.rtl.glob("*.sv"):
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
    return want or sorted(files)


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

    def _hier_modules(self, dg: dict[str, Any]) -> dict[str, str]:
        mods = {}
        for k in ("lut", "ff"):
            for r in (dg.get("util_top") or {}).get(k) or []:
                mods[r["path"]] = r["module"]
        return {**mods, **(dg.get("hier_modules") or {})}

    def run(self) -> dict[str, Any]:
        t0 = time.monotonic()
        snap = self.ws.read()
        g1 = self.g1(self.ws.rtl)
        dg = self.build(self.ws.root) if g1.get("pass") else None
        vec = goal_vector(g1, dg, self.goals, self._plan_fails(dg))
        start = {"vector": vec, "digest": _small(dg)}
        self.log(f"[closure] start: {vector_line(vec)}")
        self._rec({"iter": 0, "kind": "start", "vector": vec, "digest": _small(dg)})
        best = vec
        tried: dict[tuple[str, str], int] = {}          # (goal, class) -> iterations without progress
        attempts: list[dict[str, Any]] = []
        stop = None
        if not g1.get("pass"):
            stop = "G1 fails at the start: functional repair belongs to stage 2, not the closure loop"
        elif dg is not None and not dg.get("ran"):
            stop = "the first build did not finish (no gates.json): nothing to measure; see build/last_build.out"
        it = 0
        while stop is None:
            if all_met(vec):
                stop = "all goals met (G1-G4; G5 not run in 62A)"
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
            goal = choose_goal(vec)
            if goal is None:
                stop = "no unmet goal this loop can act on"
                break
            plan_fails = self._plan_fails(dg)
            cands = [(s, why) for s, why in pb.applicable(goal, dg or {}, vec, self.spec, plan_fails)
                     if s.phase == "62A" and tried.get((goal, s.cls), 0) < self.stall_n]
            if not cands:
                stop = f"goal {goal} not met; strategy classes exhausted"
                break
            strat, why = cands[0]
            it += 1
            files = self.ws.read()
            hm = self._hier_modules(dg or {})
            want = files_for_path(dg or {}, files, hm)
            from flow.digest.build import digest_text
            req = EditRequest(goal=goal, strategy=strat, why=why, digest=digest_text(dg or {}, goal),
                              files={p: files[p] for p in want}, other_files=[p for p in files if p not in want],
                              contract=self.contract, plan=self.plan_text,
                              history=[f"iteration {a['iter']}: {a['strategy']} -> {a['decision']} ({a['summary']})" for a in attempts])
            self.log(f"[closure] iteration {it}: goal {goal}, strategy {strat.id} ({why[:120]})")
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
            if not res.files or not diff:
                decision, imp, wor, vec2, dg2 = "revert", [], [], vec, dg
                summary = "the writer changed nothing"
            elif not g1n.get("pass"):
                vec2 = goal_vector(g1n, None, self.goals)
                vec2 = {**vec, "G1": vec2["G1"]}
                decision, imp, wor, dg2 = "revert", [], ["G1"], dg
                summary = f"G1 failed after {retries} functional retr{'y' if retries == 1 else 'ies'}: {vec2['G1']['value']}"
            else:
                dg2 = self.build(self.ws.root)
                vec2 = goal_vector(g1n, dg2, self.goals, self._plan_fails(dg2))
                decision, imp, wor = judge(vec, vec2)
                summary = vector_line(vec2) + "".join(f"; {g}: {vec2[g]['detail'][:300]}" for g in wor if vec2[g].get("detail"))
            delta = _delta(vec, vec2)
            row = {"iter": it, "kind": "iteration", "goal": goal, "strategy": strat.id, "class": strat.cls, "why": why,
                   "note": res.note, "g1_retries": retries, "decision": decision, "improved": imp, "worsened": wor,
                   "vector_before": vec, "vector_after": vec2, "delta": delta, "diff": diff, "summary": summary,
                   "digest_after": _small(dg2), "usd_total": round(self.usd, 6), "tokens_total": self.tokens}
            attempts.append(row)
            self._rec(row)
            self.log(f"[closure] iteration {it}: {decision}; {summary}")
            if decision == "accept":
                snap, vec, dg = after_files, vec2, dg2
                if goal in imp:
                    tried[(goal, strat.cls)] = 0
                else:
                    tried[(goal, strat.cls)] = tried.get((goal, strat.cls), 0) + 1
                best = vec
            else:
                self.ws.restore(snap)
                tried[(goal, strat.cls)] = tried.get((goal, strat.cls), 0) + 1
        report = self.stop_report(stop or "stopped", start, vec, attempts, time.monotonic() - t0)
        if self.record:
            (self.record / "summary.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
        self.log(f"[closure] stop: {report['stop']}")
        return report

    def _plan_fails(self, dg: dict[str, Any] | None) -> list[str]:
        if not (self.plan_check and dg and dg.get("ran")):
            return []
        try:
            return list(self.plan_check(dg))
        except Exception as e:                       # noqa: BLE001 (a plan check must never stop the loop)
            return [f"plan: check not run ({type(e).__name__})"]

    def _spend(self, r: EditResult) -> None:
        self.usd += r.usd
        self.tokens += r.tokens
        self.calls += r.calls

    def stop_report(self, stop: str, start: dict, vec: dict, attempts: list[dict], secs: float) -> dict[str, Any]:
        unmet = {g: {"best": vec[g]["value"], "target": vec[g]["target"],
                     "tried": [f"{a['strategy']} ({a['decision']})" for a in attempts if a["goal"] == g]}
                 for g in ("G1", "G2", "G3", "G4") if vec[g]["met"] is False}
        text = [f"goal {g} not met; best value {u['best']}; tried: {', '.join(u['tried']) or 'nothing'}" for g, u in unmet.items()]
        return {"stop": stop, "all_met": all_met(vec), "start": start["vector"], "final": vec,
                "start_line": vector_line(start["vector"]), "final_line": vector_line(vec), "unmet": unmet, "unmet_text": text,
                "iterations": len(attempts), "accepted": sum(a["decision"] == "accept" for a in attempts),
                "reverted": sum(a["decision"] == "revert" for a in attempts),
                "strategies": [(a["strategy"], a["decision"]) for a in attempts],
                "usd": round(self.usd, 6), "tokens": self.tokens, "llm_calls": self.calls, "seconds": round(secs, 1)}


def _delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for g in ("G1", "G2", "G3", "G4"):
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
    ``_build(rt, "route")``. Returns a note for the stage's gate (the gate still decides)."""
    from agent.core import dispatch
    from agent.graph import run as gr
    from agent.graph.llm import OpenRouterClient
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
    client = rt.client if callable(rt.client) else OpenRouterClient(rt.cfg.model)
    c = Closure(ws=Workspace(rt.design), goals=goals_from_spec(spec, rt.cfg.board), g1=g1, build=build,
                editor=llm_editor(client), contract=contract_from_spec(spec), spec=spec,
                plan_text=timing_plan.plan_text(plan) if plan else "",
                plan_check=(lambda _dg: timing_plan.post_synth_failures(rt.design, json.loads((rt.design / "build" / "base" / "gates.json").read_text())))
                if plan else None,
                max_iter=int(rt.cfg.run_limits.get("closure_iter", 6)), max_usd=float(rt.cfg.run_limits.get("closure_usd", 1.0)),
                record=rt.run_dir / "closure")
    rep = c.run()
    return {"note": "", "detail": "[closure] " + rep["stop"] + "; " + rep["final_line"]}


def contract_from_spec(spec: dict[str, Any]) -> str:
    """What the closure writer must keep: the ports, and the handshake/latency text of spec.yaml."""
    beh = spec.get("behaviour") or {}
    hs = []
    for k, v in (beh.items() if isinstance(beh, dict) else []):
        if any(w in k.lower() for w in ("handshake", "latency", "timing", "busy", "valid")):
            hs += v if isinstance(v, list) else [str(v)]
    lat = (spec.get("timing") or {}).get("latency") if isinstance(spec.get("timing"), dict) else None
    return ("Keep every module's name, ports and parameters, and the arithmetic results bit for bit. "
            + ("Handshake and latency rules from the spec: " + " ".join(map(str, hs)) if hs else "")
            + (f" Stated latencies: {lat}." if lat else "")
            + " Extra clocks of latency are allowed only where the handshake (busy or valid) already lets the user wait.")
