"""The closure loop's repair playbook: strategy classes, when each applies, what it is predicted to cost on
the other goals, and the instructions the RTL writer gets. Deterministic: the reports pick the strategy, the model only
writes the change, and the flow checks it.

Timing (G2) strategies are ready. Area (G3) and power (G4) classes are listed so the controller can name them in a stop
report, but they are marked ``phase: later`` and never chosen yet (except the plan's own mapping, which fixes a G3 plan
failure).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Strategy:
    id: str
    cls: str                     # strategy class: the stall rule moves to another class, not another strategy of one class
    goal: str                    # G2 | G3 | G4
    title: str
    instructions: str
    predicted: dict[str, str] = field(default_factory=dict)   # goal resource -> "+" / "-" / "0" (what it usually costs)
    phase: str = "ready"                        # ready | gated (offered only with a stated reason) | later


TIMING: tuple[Strategy, ...] = (
    Strategy("t_plan_map", "resource_map", "G2", "implement the plan's resource mapping",
             "The design-time plan (TIMING_PLAN.md, below) put operations on hard resources that synthesis did not infer. "
             "Rewrite those operations with the plan's templates so synthesis infers the planned DSP48E1 or block RAM, with "
             "the pipeline registers the plan lists. Keep every port and the externally visible behaviour; extra latency is "
             "allowed only where the handshake (busy/valid) already covers it.",
             {"dsp": "+", "ff": "-", "lut": "-", "latency": "+"}),
    Strategy("t_dsp_map", "resource_map", "G2", "map a multiply built in LUTs to a DSP48E1 with its pipeline registers",
             "The failing path is a long carry chain with no DSP on it: a multiply (or multiply-add) built from LUTs and "
             "CARRY4. Write the multiply so synthesis puts it in a DSP48E1: registered operands, then the product registered "
             "(MREG), then the following add registered (PREG); no asynchronous reset on those registers, operands within "
             "25 x 18 bits signed. If a table lookup or other logic feeds the operands, register its output first so it is "
             "not in series with the multiply. Add the matching delay to any control or valid signal that travels beside "
             "the data, and extend busy (or the equivalent) by the clocks you add.",
             {"dsp": "+", "ff": "+", "lut": "-", "latency": "+"}),
    Strategy("t_pipeline", "pipeline", "G2", "pipeline the long path (add a register stage)",
             "Cut the failing path with a register stage near the middle of its delay, at the cell boundary the report "
             "shows (after the table lookup, after the multiply, between adder levels). Delay every signal that travels "
             "beside the data (valid, index, enable) by the same number of clocks, and extend busy (or the equivalent "
             "handshake) by the clocks you add, so the externally visible behaviour is unchanged apart from that latency.",
             {"ff": "+", "latency": "+"}),
    Strategy("t_fanout", "fanout", "G2", "register or replicate a high-fanout net on the path",
             "A net on the failing path drives many loads (see 'largest fanout'). Replicate its driving register (one copy "
             "per group of loads) or add `(* max_fanout = 16 *)` to it, or register the decoded value it feeds so the "
             "decode is not in series with the rest of the path. Do not change behaviour or latency.",
             {"ff": "+"}),
    Strategy("t_tree", "tree", "G2", "balance a deep adder or comparator tree",
             "The failing path chains several adds or compares one after another. Restructure them as a balanced tree "
             "(pairwise adds), register between tree levels if one level is still too long, and keep the arithmetic exact "
             "(same widths, same rounding and shift).",
             {"ff": "+", "latency": "+"}),
    Strategy("t_retime", "retime", "G2", "retime: move an existing register across logic",
             "Move an existing register earlier or later along the failing path so the logic on either side is balanced "
             "(for example register the decoded table value instead of the index that feeds the table). Keep the latency "
             "of every output the same.",
             {"ff": "+"}),
    Strategy("t_exception", "exception", "G2", "multicycle or false-path exception (only where the protocol proves it)",
             "Not offered unless spec.yaml states a multicycle protocol for this path; any exception is audited by the flow's exception check.",
             {}, phase="gated"),
    Strategy("t_impl", "implementation", "G2", "implementation directives or strategies",
             "Not offered yet (a later phase).", {}, phase="later"),
)

AREA: tuple[Strategy, ...] = tuple(Strategy(i, c, "G3", t, "", {}, phase="later") for i, c, t in (
    ("a_share", "share", "share a resource across cycles"), ("a_ram", "ram_infer", "infer RAM instead of registers"),
    ("a_narrow", "narrow", "narrow an over-wide datapath"), ("a_srl", "srl", "use SRL for delay lines"),
    ("a_unused", "unused", "remove logic synthesis reports unused")))
POWER: tuple[Strategy, ...] = tuple(Strategy(i, c, "G4", t, "", {}, phase="later") for i, c, t in (
    ("p_ce", "clock_enable", "clock enables instead of free-running logic"), ("p_gate", "toggle", "gate data on valid"),
    ("p_bram_en", "bram_enable", "BRAM enable control"), ("p_bus", "bus", "fewer high-toggle wide buses"),
    ("p_clock", "clock", "a lower clock, if the spec allows it")))

ALL = TIMING + AREA + POWER
BY_ID = {s.id: s for s in ALL}


def _headroom(vec: dict[str, Any], key: str) -> float | None:
    g3 = (vec.get("G3") or {}).get("value") or {}
    tgt = (vec.get("G3") or {}).get("target") or {}
    if key in g3 and tgt.get(key) is not None:
        return float(tgt[key]) - float(g3[key] or 0)
    return None


def applicable(goal: str, dg: dict[str, Any], vec: dict[str, Any], spec: dict[str, Any] | None = None,
               plan_fails: list[str] | None = None) -> list[tuple[Strategy, str]]:
    """The strategies for ``goal`` that the reports support, best first, each with the reason it was chosen. A strategy
    whose predicted cost would break another goal's budget is left out (its reason says so in the controller's log)."""
    # a plan failure is a G3 failure, but its repair (the plan's mapping) is offered under G2 only, so it has one stall
    # counter; the controller skips G3 (no area strategy yet) and reaches G2 when the plan check is the only G3 problem
    if goal != "G2":
        return []
    f = dg.get("setup_features") or {}
    p = dg.get("setup_path") or {}
    period = (dg.get("timing") or {}).get("period_ns") or 10.0
    out: list[tuple[float, Strategy, str]] = []
    dsp_room = _headroom(vec, "dsp")
    ff_room = _headroom(vec, "ff")
    if plan_fails:
        out.append((100, BY_ID["t_plan_map"], "the post-synthesis plan check failed: " + "; ".join(plan_fails)[:300]))
    if f.get("lut_arith") and (dsp_room is None or dsp_room >= 1):
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
    return [(s, why) for _, s, why in sorted(out, key=lambda x: -x[0])]
