"""The closure loop's repair playbook: strategy classes, when each applies, what it is predicted to cost on
the other goals, the stage it changes, and the instructions the Designer gets. Deterministic: the reports pick the
strategy, the model only writes the change, and the flow checks it.

Every strategy names:

- ``goal``: the goal it repairs (G2 timing, G3 area, G4 power, CHK the routed DRC and methodology checks);
- ``stage``: the earliest stage it changes (``rtl``, ``constraints``, ``architecture`` or ``spec``). The closure loop
  applies ``rtl`` and ``constraints`` changes itself; an ``architecture`` or ``spec`` change goes back to that stage
  (the agent graph's re-entry, the state shape of ``agent/graph/pickup.py``), because the architect or the clarify
  stage owns it;
- ``hard``: true when the change moves work onto a hard resource (DSP48E1, block RAM, SRL, carry chain); the joint
  planner (``agent.graph.closure_plan``) prefers these over general-purpose logic when the budget allows;
- ``predicted``: the usual effect on each resource (``lut ff bram_tile dsp power wns latency``: ``+`` more, ``-``
  less; for ``wns``, ``-`` means less slack), which the joint planner uses to keep a set of fixes from fighting each
  other or breaking a goal that is met;
- ``phase``: ``ready`` (chosen by the reports), ``gated`` (offered only with a stated reason from spec.yaml) or
  ``later`` (named in stop reports, never chosen).
"""

from __future__ import annotations

from agent.core.prompts import load as _p

from dataclasses import dataclass, field
from typing import Any

STAGES = ("spec", "architecture", "rtl", "constraints")          # the order of the agent's stages 0..3
STAGE_NUMBER = {"spec": 0, "architecture": 1, "rtl": 2, "constraints": 3}


@dataclass(frozen=True)
class Strategy:
    id: str
    cls: str                     # strategy class: the stall rule moves to another class, not another strategy of one class
    goal: str                    # G2 | G3 | G4 | CHK
    title: str
    instr_ref: str               # the prompt's name in the private knowledge repository (brief 99); read it as ``instructions``
    predicted: dict[str, str] = field(default_factory=dict)   # resource -> "+" / "-" (what it usually costs or saves)
    phase: str = "ready"                        # ready | gated (offered only with a stated reason) | later
    stage: str = "rtl"                          # rtl | constraints | architecture | spec: the earliest stage it changes
    hard: bool = False                          # moves work onto a hard resource (DSP, BRAM, SRL, carry chain)

    @property
    def instructions(self) -> str:
        return _p(self.instr_ref)



TIMING: tuple[Strategy, ...] = (
    Strategy("t_plan_map", "resource_map", "G2", "implement the plan's resource mapping",
             "graph/closure_playbook/t_plan_map",
             {"dsp": "+", "ff": "-", "lut": "-", "latency": "+"}, hard=True),
    Strategy("t_dsp_map", "resource_map", "G2", "map a multiply built in LUTs to a DSP48E1 with its pipeline registers",
             "graph/closure_playbook/t_dsp_map",
             {"dsp": "+", "ff": "+", "lut": "-", "latency": "+"}, hard=True),
    Strategy("t_pipeline", "pipeline", "G2", "pipeline the long path (add a register stage)",
             "graph/closure_playbook/t_pipeline",
             {"ff": "+", "latency": "+"}),
    Strategy("t_carry_split", "carry_split", "G2", "split a wide add, accumulate or compare chain across clocks",
             "graph/closure_playbook/t_carry_split",
             {"ff": "+", "latency": "+"}),
    Strategy("t_verdict_reg", "verdict", "G2", "register the end-of-frame verdict, act on it one clock later",
             "graph/closure_playbook/t_verdict_reg",
             {"ff": "+", "latency": "+"}),
    Strategy("t_fanout", "fanout", "G2", "register or replicate a high-fanout net on the path",
             "graph/closure_playbook/t_fanout",
             {"ff": "+"}),
    Strategy("t_tree", "tree", "G2", "balance a deep adder or comparator tree",
             "graph/closure_playbook/t_tree",
             {"ff": "+", "latency": "+"}),
    Strategy("t_retime", "retime", "G2", "retime: move an existing register across logic",
             "graph/closure_playbook/t_retime",
             {"ff": "+"}),
    Strategy("t_exception", "exception", "G2", "multicycle or false-path exception (only where the protocol proves it)",
             "graph/closure_playbook/t_exception",
             {"wns": "+"}, phase="gated", stage="constraints"),
    Strategy("t_impl", "implementation", "G2", "implementation directives or strategies",
             "graph/closure_playbook/t_impl", {}, phase="later", stage="constraints"),
)

AREA: tuple[Strategy, ...] = (
    Strategy("a_ram", "ram_infer", "G3", "infer block RAM instead of registers",
             "graph/closure_playbook/a_ram",
             {"bram_tile": "+", "ff": "-", "lut": "-", "latency": "+"}, hard=True),
    Strategy("a_dsp", "dsp_map", "G3", "move multiplies built in LUTs onto DSP48E1 slices",
             "graph/closure_playbook/a_dsp",
             {"dsp": "+", "lut": "-", "latency": "+"}, hard=True),
    Strategy("a_srl", "srl", "G3", "use SRL shift registers for delay lines",
             "graph/closure_playbook/a_srl",
             {"ff": "-", "lut": "+"}, hard=True),
    Strategy("a_bram_merge", "bram_merge", "G3", "use both ports of one block RAM instead of two RAMs",
             "graph/closure_playbook/a_bram_merge",
             {"bram_tile": "-", "lut": "+", "latency": "+"}, hard=True),
    Strategy("a_lutram", "lutram", "G3", "move a small memory from block RAM to distributed (LUT) RAM",
             "graph/closure_playbook/a_lutram",
             {"bram_tile": "-", "lut": "+"}),
    Strategy("a_dsp_share", "share", "G3", "share one DSP48E1 across cycles (time-multiplex)",
             "graph/closure_playbook/a_dsp_share",
             {"dsp": "-", "lut": "+", "ff": "+", "latency": "+"}),
    Strategy("a_lut_mult", "lut_mult", "G3", "build a small multiply in LUTs instead of a DSP48E1",
             "graph/closure_playbook/a_lut_mult",
             {"dsp": "-", "lut": "+", "wns": "-"}),
    Strategy("a_narrow", "narrow", "G3", "narrow an over-wide datapath or memory",
             "graph/closure_playbook/a_narrow",
             {"lut": "-", "ff": "-", "bram_tile": "-"}),
    Strategy("a_unused", "unused", "G3", "remove logic the design does not use",
             "graph/closure_playbook/a_unused",
             {"lut": "-", "ff": "-"}),
    Strategy("a_latch", "latch", "G3", "remove an inferred latch",
             "graph/closure_playbook/a_latch",
             {"lut": "-"}),
    Strategy("a_io", "io", "G3", "fewer I/O pins (a spec change)",
             "graph/closure_playbook/a_io",
             {}, phase="gated", stage="spec"),
)

POWER: tuple[Strategy, ...] = (
    Strategy("p_bram_en", "bram_enable", "G4", "enable block RAM only when it is accessed",
             "graph/closure_playbook/p_bram_en",
             {"power": "-"}, hard=True),
    Strategy("p_gate", "toggle", "G4", "gate data on valid (operand isolation)",
             "graph/closure_playbook/p_gate",
             {"power": "-", "lut": "+"}),
    Strategy("p_ce", "clock_enable", "G4", "clock enables instead of free-running registers",
             "graph/closure_playbook/p_ce",
             {"power": "-"}),
    Strategy("p_dsp", "dsp_power", "G4", "move a multiply from LUTs to a DSP48E1 (less switching)",
             "graph/closure_playbook/p_dsp",
             {"power": "-", "dsp": "+", "lut": "-"}, hard=True),
    Strategy("p_clock", "clock", "G4", "a lower clock (only if the spec allows it)",
             "graph/closure_playbook/p_clock", {"power": "-", "wns": "+"}, phase="gated", stage="constraints"),
)

CHECKS: tuple[Strategy, ...] = (
    Strategy("c_constraints", "constraints", "CHK", "fix the constraints the routed checks flag",
             "graph/closure_playbook/c_constraints",
             {}, stage="constraints"),
    Strategy("c_rtl_check", "rtl_check", "CHK", "fix the RTL a routed check flags",
             "graph/closure_playbook/c_rtl_check", {}, stage="rtl"),
)

REPLAN: tuple[Strategy, ...] = (
    Strategy("x_replan_timing", "replan", "G2", "re-plan the architecture for timing", "graph/closure_playbook/x_replan_timing", {}, stage="architecture"),
    Strategy("x_replan_area", "replan", "G3", "re-plan the architecture for the resource budget", "graph/closure_playbook/x_replan_area", {}, stage="architecture"),
    Strategy("x_replan_power", "replan", "G4", "re-plan the architecture for the power budget", "graph/closure_playbook/x_replan_power", {}, stage="architecture"),
)

ALL = TIMING + AREA + POWER + CHECKS + REPLAN
BY_ID = {s.id: s for s in ALL}


def _headroom(vec: dict[str, Any], key: str) -> float | None:
    g3 = (vec.get("G3") or {}).get("value") or {}
    tgt = (vec.get("G3") or {}).get("target") or {}
    if key in g3 and tgt.get(key) is not None:
        return float(tgt[key]) - float(g3[key] or 0)
    return None


def over_budget(vec: dict[str, Any]) -> dict[str, float]:
    """Resources over their G3 budget: {resource: used / budget}."""
    g3 = vec.get("G3") or {}
    used, bud = g3.get("value") or {}, g3.get("target") or {}
    if not isinstance(used, dict) or not isinstance(bud, dict):
        return {}
    return {k: round(float(used[k] or 0) / float(bud[k]), 4) for k in used
            if bud.get(k) and used.get(k) is not None and float(used[k]) > float(bud[k])}


def _timing(dg, vec, spec, plan_fails):
    f = dg.get("setup_features") or {}
    p = dg.get("setup_path") or {}
    period = (dg.get("timing") or {}).get("period_ns") or 10.0
    out: list[tuple[float, Strategy, str]] = []
    dsp_room = _headroom(vec, "dsp")
    ff_room = _headroom(vec, "ff")
    if plan_fails:
        out.append((100, BY_ID["t_plan_map"], "the post-synthesis plan check failed: " + "; ".join(plan_fails)[:300]))
    # a multiply is the only arithmetic a DSP48E1 helps (brief 88: three network blocks were sent to t_dsp_map for a ones'-
    # complement checksum fold); ``rtl_has_multiply`` is set by drivers that scan the RTL, unset means "unknown: offer it"
    has_mult = dg.get("rtl_has_multiply", True)
    dst = str(p.get("destination") or "")
    if f.get("lut_arith") and not has_mult and (f.get("carry_chain") or 0) >= 4:
        out.append((92, BY_ID["t_carry_split"], f"{f.get('carry_chain')} CARRY4 in series and no multiply in the RTL: an "
                                                 "add or compare chain, to split across clocks"))
    if dst.endswith(("/R", "/CE", "/S", "/CLR", "/WE", "/ENARDEN")) and (f.get("logic_levels") or 0) >= 6:
        out.append((91, BY_ID["t_verdict_reg"], f"the path ends at a control pin ({dst}) after {f.get('logic_levels')} logic "
                                                 "levels: a per-frame verdict driving enables"))
    if f.get("lut_arith") and has_mult and (dsp_room is None or dsp_room >= 1):
        out.append((90, BY_ID["t_dsp_map"], f"{f.get('carry_chain')} CARRY4 on the path and no DSP: arithmetic in LUTs; "
                                            f"DSP headroom {dsp_room}"))
    if (f.get("logic_levels") or 0) >= 4 or (p.get("data_path_ns") or 0) > 0.7 * period:
        if ff_room is None or ff_room >= 64:
            out.append((70, BY_ID["t_pipeline"], f"{f.get('logic_levels')} logic levels, data path {p.get('data_path_ns')} ns "
                                                 f"of a {period} ns period; FF headroom {ff_room}"))
    if f.get("high_fanout"):
        out.append((60, BY_ID["t_fanout"], f"net {f.get('max_fanout_net')} drives {f.get('max_fanout')} loads on the path"))
    if (f.get("carry_chain") or 0) >= 6:
        out.append((50, BY_ID["t_tree"], f"{f.get('carry_chain')} CARRY4 in series"))
    if (f.get("logic_levels") or 0) >= 3:
        out.append((40, BY_ID["t_retime"], "logic on both sides of an existing register can be rebalanced"))
    mc = ((spec or {}).get("timing") or {}).get("multicycle") if isinstance((spec or {}).get("timing"), dict) else None
    if mc:
        out.append((10, BY_ID["t_exception"], f"spec.yaml states a multicycle protocol: {str(mc)[:200]}"))
    return out


def _area(dg, vec, spec):
    over = over_budget(vec)
    syn = dg.get("synth") or {}
    u = dg.get("utilization") or {}
    out: list[tuple[float, Strategy, str]] = []
    room = {k: _headroom(vec, k) for k in ("lut", "ff", "bram_tile", "dsp")}
    if syn.get("latches"):
        out.append((95, BY_ID["a_latch"], f"synthesis inferred latches: {syn['latches'][:3]}"))
    if syn.get("ram_in_registers") and (room["bram_tile"] is None or room["bram_tile"] >= 0.5):
        out.append((92, BY_ID["a_ram"], f"synthesis built RAM in registers: {syn['ram_in_registers'][:3]}; "
                                        f"BRAM headroom {room['bram_tile']}"))
    if "ff" in over or "lut" in over:
        big_ff = max(((r.get("ff") or 0) for r in (dg.get("util_top") or {}).get("ff") or []), default=0)
        if big_ff >= 256 and (room["bram_tile"] is None or room["bram_tile"] >= 0.5):
            out.append((80, BY_ID["a_ram"], f"one instance holds {big_ff} flip-flops: a register array that block RAM can "
                                            f"hold; BRAM headroom {room['bram_tile']}"))
        if "lut" in over and (u.get("carry4") or 0) >= 24 and (room["dsp"] is None or room["dsp"] >= 1):
            out.append((78, BY_ID["a_dsp"], f"{u.get('carry4')} CARRY4 in the design: arithmetic in LUTs; DSP headroom "
                                            f"{room['dsp']}"))
        if "ff" in over:
            out.append((70, BY_ID["a_srl"], f"FF {over['ff']:.2f} x budget: delay lines can go into SRLs"))
        out.append((40, BY_ID["a_narrow"], "LUT or FF over budget: check for over-wide datapaths"))
        out.append((30, BY_ID["a_unused"], "LUT or FF over budget: check for logic that reaches no port"))
    if "bram_tile" in over:
        out.append((85, BY_ID["a_bram_merge"], f"BRAM {over['bram_tile']:.2f} x budget: share one RAM's two ports or "
                                               "merge memories (keeps the data in block RAM)"))
        lut_room = room["lut"]
        if lut_room is None or lut_room >= 256:
            out.append((60, BY_ID["a_lutram"], f"BRAM over budget; LUT headroom {lut_room} for distributed RAM"))
        out.append((35, BY_ID["a_narrow"], "BRAM over budget: check for over-wide memory words"))
    if "dsp" in over:
        out.append((80, BY_ID["a_dsp_share"], f"DSP {over['dsp']:.2f} x budget: share a DSP across cycles"))
        if room["lut"] is None or room["lut"] >= 128:
            out.append((55, BY_ID["a_lut_mult"], f"DSP over budget; LUT headroom {room['lut']} for small multiplies"))
    if "iob" in over:
        out.append((10, BY_ID["a_io"], f"IO {over['iob']:.2f} x budget: only a spec change helps"))
    return out


def _power(dg, vec, spec):
    p = dg.get("power") or {}
    comp = p.get("components") or {}
    dyn = p.get("dynamic_w") or sum((v or 0) for k, v in comp.items() if k not in ("Static Power", "Total") and not k.startswith(" "))
    dyn = dyn or 1e-9
    share = {k: (v or 0) / dyn for k, v in comp.items() if k not in ("Static Power", "Total")}
    f = dg.get("setup_features") or {}
    u = dg.get("utilization") or {}
    out: list[tuple[float, Strategy, str]] = []
    if share.get("Block RAM", 0) >= 0.10:
        out.append((90, BY_ID["p_bram_en"], f"block RAM is {share['Block RAM']:.0%} of the dynamic power ({comp['Block RAM']} W)"))
    sig = share.get("Signals", 0) + share.get("Slice Logic", 0)
    if sig >= 0.30:
        out.append((75, BY_ID["p_gate"], f"signals and logic are {sig:.0%} of the dynamic power"))
    if share.get("Clocks", 0) >= 0.20 or sig >= 0.30:
        out.append((65, BY_ID["p_ce"], f"clocks {share.get('Clocks', 0):.0%}, signals and logic {sig:.0%} of the dynamic power"))
    dsp_room = _headroom(vec, "dsp")
    if (f.get("lut_arith") or (u.get("carry4") or 0) >= 24) and (dsp_room is None or dsp_room >= 1):
        out.append((70, BY_ID["p_dsp"], f"arithmetic in LUTs ({u.get('carry4')} CARRY4); DSP headroom {dsp_room}"))
    clk = [c for c in (spec or {}).get("clocks") or [] if c.get("min_freq_mhz")]
    if clk:
        out.append((20, BY_ID["p_clock"], f"spec.yaml allows {clk[0].get('name')} down to {clk[0]['min_freq_mhz']} MHz"))
    return out


def _checks(dg):
    out: list[tuple[float, Strategy, str]] = []
    rows = []
    for k in ("drc", "methodology"):
        for r in ((dg.get(k) or {}).get("rules") or []):
            if r.get("severity") in ("Error", "Critical Warning"):
                rows.append(r)
    cons = [r for r in rows if r["rule"].split("-")[0] in ("TIMING", "XDCB", "XDCC", "XDCH", "NSTD", "UCIO")]
    rtl = [r for r in rows if r not in cons]
    if cons:
        out.append((80, BY_ID["c_constraints"], "; ".join(f"{r['rule']} x{r['count']}: {r['description'][:80]}" for r in cons[:4])))
    if rtl:
        out.append((70, BY_ID["c_rtl_check"], "; ".join(f"{r['rule']} x{r['count']}: {r['description'][:80]}" for r in rtl[:4])))
    return out


def applicable(goal: str, dg: dict[str, Any], vec: dict[str, Any], spec: dict[str, Any] | None = None,
               plan_fails: list[str] | None = None) -> list[tuple[Strategy, str]]:
    """The strategies for ``goal`` that the reports support, best first, each with the reason it was chosen. A strategy
    whose predicted cost would break another goal's budget is left out here (no headroom) or by the joint planner
    (conflicts between fixes). Among strategies the reports support equally, a hard-resource strategy ranks first.

    A plan failure is a G3 failure, but its repair (the plan's mapping) is offered under G2 only, so it has one stall
    counter; with no other area problem the controller skips G3 and reaches G2."""
    if goal == "CHK":
        return _rank(_checks(dg))
    if goal == "G2":
        out = _timing(dg, vec, spec, plan_fails)
    elif goal == "G3":
        out = _area(dg, vec, spec)
    elif goal == "G4":
        out = _power(dg, vec, spec)
    else:
        return []
    if out or goal != "G3":
        # the last resort, ranked below every RTL class: back to the architecture stage (the loop hands the design back)
        out.append((1, BY_ID[{"G2": "x_replan_timing", "G3": "x_replan_area", "G4": "x_replan_power"}[goal]],
                    "no RTL strategy class for this goal is left (each was tried without progress, or conflicts with "
                    "another goal)"))
    return _rank(out)


def _rank(out: list[tuple[float, Strategy, str]]) -> list[tuple[Strategy, str]]:
    seen, res = set(), []
    for _, s, why in sorted(out, key=lambda x: -(x[0] + (5 if x[1].hard else 0))):
        if s.id not in seen:
            seen.add(s.id)
            res.append((s, why))
    return res
