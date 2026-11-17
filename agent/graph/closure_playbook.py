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
    instructions: str
    predicted: dict[str, str] = field(default_factory=dict)   # resource -> "+" / "-" (what it usually costs or saves)
    phase: str = "ready"                        # ready | gated (offered only with a stated reason) | later
    stage: str = "rtl"                          # rtl | constraints | architecture | spec: the earliest stage it changes
    hard: bool = False                          # moves work onto a hard resource (DSP, BRAM, SRL, carry chain)


_KEEP = (" Keep every port and the externally visible behaviour; extra latency is allowed only where the handshake "
         "(busy/valid) already covers it, and every signal that travels beside the data must be delayed to match.")

TIMING: tuple[Strategy, ...] = (
    Strategy("t_plan_map", "resource_map", "G2", "implement the plan's resource mapping",
             "The design-time plan (TIMING_PLAN.md, below) put operations on hard resources that synthesis did not infer. "
             "Rewrite those operations with the plan's templates so synthesis infers the planned DSP48E1 or block RAM, with "
             "the pipeline registers the plan lists." + _KEEP,
             {"dsp": "+", "ff": "-", "lut": "-", "latency": "+"}, hard=True),
    Strategy("t_dsp_map", "resource_map", "G2", "map a multiply built in LUTs to a DSP48E1 with its pipeline registers",
             "The failing path is a long carry chain with no DSP on it: a multiply (or multiply-add) built from LUTs and "
             "CARRY4. Write the multiply so synthesis puts it in a DSP48E1: registered operands, then the product registered "
             "(MREG), then the following add registered (PREG); no asynchronous reset on those registers, operands within "
             "25 x 18 bits signed. If a table lookup or other logic feeds the operands, register its output first so it is "
             "not in series with the multiply. Add the matching delay to any control or valid signal that travels beside "
             "the data, and extend busy (or the equivalent) by the clocks you add.",
             {"dsp": "+", "ff": "+", "lut": "-", "latency": "+"}, hard=True),
    Strategy("t_pipeline", "pipeline", "G2", "pipeline the long path (add a register stage)",
             "Cut the failing path with a register stage near the middle of its delay, at the cell boundary the report "
             "shows (after the table lookup, after the multiply, between adder levels). Delay every signal that travels "
             "beside the data (valid, index, enable) by the same number of clocks, and extend busy (or the equivalent "
             "handshake) by the clocks you add, so the externally visible behaviour is unchanged apart from that latency.",
             {"ff": "+", "latency": "+"}),
    Strategy("t_carry_split", "carry_split", "G2", "split a wide add, accumulate or compare chain across clocks",
             "The failing path is a long carry chain of additions or comparisons that is not a multiply (a ones'-complement "
             "checksum fold, a running sum, a length or address compare). Do not map it to a DSP. Keep the running sum "
             "unfolded and add the words as they arrive; fold the carries and compare in one or two later registered stages "
             "(a stage that adds the high half to the low half, a stage that adds the last carry and compares with the "
             "constant). Compare against registered operands, not against a sum computed in the same clock. The result is "
             "needed only at the end of the frame or message, so the extra stages cost latency, not throughput. Delay every "
             "signal that travels beside the result by the same number of clocks." + _KEEP,
             {"ff": "+", "latency": "+"}),
    Strategy("t_verdict_reg", "verdict", "G2", "register the end-of-frame verdict, act on it one clock later",
             "The failing path ends at a control input (reset, clock enable or write enable) and starts at the registers of a "
             "check that is computed once per frame (checksums, lengths, header fields). Register the verdict (and the "
             "flags that go with it, such as 'store this frame') on the clock it is computed, and take the action that the "
             "verdict drives (start a reply, set busy, raise an event) one clock later from the registered copy. A value the "
             "action reads that the next frame can overwrite in that clock (a length, a flag set on the last beat) must be "
             "copied into the same stage. Anything that used the verdict in the same clock to protect a buffer must be "
             "re-derived from state that is known earlier (for example decide on the frame's later bytes instead of its first, "
             "if the early bytes are never read back), so that the observable behaviour does not change." + _KEEP,
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
             "spec.yaml states a multicycle protocol for this path. Write the exception in the design's XDC with "
             "set_multicycle_path -setup N and the matching -hold N-1, on the exact registers the protocol covers, never "
             "on a whole clock; the flow's exception check audits it.",
             {"wns": "+"}, phase="gated", stage="constraints"),
    Strategy("t_impl", "implementation", "G2", "implementation directives or strategies",
             "Not offered yet (a later phase).", {}, phase="later", stage="constraints"),
)

AREA: tuple[Strategy, ...] = (
    Strategy("a_ram", "ram_infer", "G3", "infer block RAM instead of registers",
             "Synthesis built a memory (or a deep register array) in flip-flops and LUT multiplexers. Rewrite it with the "
             "block-RAM inference template: one `always_ff` with a registered read (`rdata <= mem[raddr]`), a write port "
             "`if (we) mem[waddr] <= wdata`, no reset on the array, and `(* ram_style = \"block\" *)`. A one-clock 'clear "
             "all' becomes a valid bit per entry or a clearing sweep the handshake already covers." + _KEEP,
             {"bram_tile": "+", "ff": "-", "lut": "-", "latency": "+"}, hard=True),
    Strategy("a_dsp", "dsp_map", "G3", "move multiplies built in LUTs onto DSP48E1 slices",
             "Multiplies are built from LUTs and CARRY4 (see the LUT users and the carry count). Write each so synthesis "
             "puts it in a DSP48E1 (registered operands, registered product, operands within 25 x 18 signed); this frees "
             "the LUTs." + _KEEP,
             {"dsp": "+", "lut": "-", "latency": "+"}, hard=True),
    Strategy("a_srl", "srl", "G3", "use SRL shift registers for delay lines",
             "Delay lines and pipelines of flip-flops with no reset and no tap in the middle can be packed into SRL16/SRL32 "
             "LUTs: remove the reset from those registers (they still reach a known value once the line has been "
             "filled; keep the reset on the valid bits that travel beside them) and write them as a shift register. "
             "Behaviour and latency must not change.",
             {"ff": "-", "lut": "+"}, hard=True),
    Strategy("a_bram_merge", "bram_merge", "G3", "use both ports of one block RAM instead of two RAMs",
             "The design uses more block RAM than the budget. Find memories that hold the same data or are small enough "
             "to share one RAMB36/RAMB18: a duplicated copy made only to get a second read port can be one true dual-port "
             "RAM (port A and port B, each read or write), with the ports shared in time where needed (for example the "
             "user read port and the internal read-modify-write use port B on different clocks, as the handshake allows). "
             "Two small memories can share one RAM at different address ranges. The data must stay exactly the same." + _KEEP,
             {"bram_tile": "-", "lut": "+", "latency": "+"}, hard=True),
    Strategy("a_lutram", "lutram", "G3", "move a small memory from block RAM to distributed (LUT) RAM",
             "A memory that is small (a few thousand bits) or needs extra read ports can live in distributed RAM: write it "
             "with an asynchronous or registered read and `(* ram_style = \"distributed\" *)`. It costs LUTs (about one "
             "LUT per 64 bits per read port) and frees block RAM." + _KEEP,
             {"bram_tile": "-", "lut": "+"}),
    Strategy("a_dsp_share", "share", "G3", "share one DSP48E1 across cycles (time-multiplex)",
             "The design uses more DSP slices than the budget. Where the handshake gives several clocks per result, "
             "compute the multiplies one after another on one DSP48E1 (a small sequencer and operand multiplexers), and "
             "extend busy (or the equivalent) by the clocks this adds." + _KEEP,
             {"dsp": "-", "lut": "+", "ff": "+", "latency": "+"}),
    Strategy("a_lut_mult", "lut_mult", "G3", "build a small multiply in LUTs instead of a DSP48E1",
             "A multiply whose narrower operand is small (a few bits, or a constant) can be built from LUTs or as shifts "
             "and adds, which frees a DSP slice. Keep the arithmetic exact, and register the result if the path is long.",
             {"dsp": "-", "lut": "+", "wns": "-"}),
    Strategy("a_narrow", "narrow", "G3", "narrow an over-wide datapath or memory",
             "Registers, adders or memory words are wider than the values they can hold (check the ranges the spec gives). "
             "Narrow them to the width the spec needs; results must stay bit for bit the same at the ports.",
             {"lut": "-", "ff": "-", "bram_tile": "-"}),
    Strategy("a_unused", "unused", "G3", "remove logic the design does not use",
             "Remove logic whose outputs never reach a port (synthesis keeps it only because the RTL ties it to something "
             "observable, such as a debug register). Do not remove anything the spec names.",
             {"lut": "-", "ff": "-"}),
    Strategy("a_latch", "latch", "G3", "remove an inferred latch",
             "Synthesis inferred a latch: a combinational block does not assign the named signal on every path. Give it a "
             "default assignment at the top of the block (or make it a register if it is meant to hold its value).",
             {"lut": "-"}),
    Strategy("a_io", "io", "G3", "fewer I/O pins (a spec change)",
             "The design needs more I/O pins than the budget; only the spec can remove or multiplex ports.",
             {}, phase="gated", stage="spec"),
)

POWER: tuple[Strategy, ...] = (
    Strategy("p_bram_en", "bram_enable", "G4", "enable block RAM only when it is accessed",
             "Block RAM power is a large share of the dynamic power, and the RAMs are enabled on every clock. Give each "
             "RAM port an enable that is true only on the clocks it is read or written (`if (en) rdata <= mem[raddr]`), so "
             "the RAM is idle otherwise. A registered read output must hold its last value while not enabled, so check "
             "every reader still sees the data at the same clock." + _KEEP,
             {"power": "-"}, hard=True),
    Strategy("p_gate", "toggle", "G4", "gate data on valid (operand isolation)",
             "Signals and logic toggle on clocks where their result is not used. Register operands only when their valid "
             "(or enable) is true, and hold multiplexer selects and wide buses steady when idle, so the datapath does not "
             "toggle on idle clocks. Behaviour at the ports must not change.",
             {"power": "-", "lut": "+"}),
    Strategy("p_ce", "clock_enable", "G4", "clock enables instead of free-running registers",
             "Registers load on every clock even when their value does not change. Give register groups a clock enable "
             "(load only when the stage has new data); Vivado maps it to the flip-flop CE pin. Do not gate the clock "
             "itself in logic.",
             {"power": "-"}),
    Strategy("p_dsp", "dsp_power", "G4", "move a multiply from LUTs to a DSP48E1 (less switching)",
             "A multiply built from LUTs and carry chains toggles many nets; on a DSP48E1 it uses far less dynamic power. "
             "Write it so synthesis infers the DSP (registered operands and product)." + _KEEP,
             {"power": "-", "dsp": "+", "lut": "-"}, hard=True),
    Strategy("p_clock", "clock", "G4", "a lower clock (only if the spec allows it)",
             "spec.yaml allows a lower clock for this domain. Lower it in the design's XDC to the slowest rate that still "
             "meets the stated throughput.", {"power": "-", "wns": "+"}, phase="gated", stage="constraints"),
)

CHECKS: tuple[Strategy, ...] = (
    Strategy("c_constraints", "constraints", "CHK", "fix the constraints the routed checks flag",
             "The routed DRC or methodology checks report Critical Warnings or Errors about constraints (TIMING-*, "
             "XDCB-*, NSTD-*, UCIO-*: a missing I/O standard, a clock defined twice, an unconstrained input or output). "
             "Fix the XDC: one create_clock per clock, an IOSTANDARD and PACKAGE_PIN on every port, input and output delays "
             "on the I/O the spec times. Do not add a false path or a multicycle path to silence a check.",
             {}, stage="constraints"),
    Strategy("c_rtl_check", "rtl_check", "CHK", "fix the RTL a routed check flags",
             "The routed DRC or methodology checks report Critical Warnings or Errors about the netlist (for example "
             "asynchronous resets on DSP or RAM registers (DPIR, RMIR), or a combinational loop (LUTLP)). Fix the RTL they "
             "point at, following the rule's one-line fix.", {}, stage="rtl"),
)

_REPLAN = ("The RTL strategies for this goal are used up. Go back to the architecture: re-plan the datapath (pipeline "
           "depth, which operations go on DSP slices or block RAM, how memories are shared) with the design-time plan, "
           "and say what the plan must change and why.")
REPLAN: tuple[Strategy, ...] = (
    Strategy("x_replan_timing", "replan", "G2", "re-plan the architecture for timing", _REPLAN, {}, stage="architecture"),
    Strategy("x_replan_area", "replan", "G3", "re-plan the architecture for the resource budget", _REPLAN, {}, stage="architecture"),
    Strategy("x_replan_power", "replan", "G4", "re-plan the architecture for the power budget", _REPLAN, {}, stage="architecture"),
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
