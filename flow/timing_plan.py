"""Design-time timing and resource plan (brief 62A, "Pre-empt at design time"; owner, 2026-11-12).

The architecture stage declares its datapaths in ``architecture.yaml``; this module maps every operation to a resource
(hard resource first), estimates each operation's delay from a per-family **delay model** kept in the knowledge bank
(``FPGA_Design_Agent_Knowledge/family_matrix/delay_model/<family>.yaml``, calibrated on our own Vivado 2026.1 builds by
``flow/delay_calib/``), and chooses the pipeline depth so every stage fits a share of the clock period (default 70 %)
before any build. It records the latency that results. After synthesis it checks the inferred primitives against the
plan; after routing it compares the measured path with the planned stage and writes a calibration row.

``architecture.yaml`` (optional key, schema fpga-design-agent/architecture/v1)::

    datapaths:
    - name: rho                      # one registered chain from a source register to a destination register
      clock: sys                     # a clock_domains name (its freq_mhz sets the period)
      instance: u_regs/u_core        # optional: the RTL instance (post-route comparison and per-instance checks)
      latency_fixed: null            # cycles, when the spec fixes the latency (the plan says what that forces)
      ops:                           # in order along the chain; "parallel: true" runs beside the previous op
      - {name: angle_table, op: table, index_bits: 4, width: 9}
      - {name: x_cos, op: mul, a_bits: 9, b_bits: 9}
      - {name: y_sin, op: mul, a_bits: 9, b_bits: 9, parallel: true}
      - {name: sum, op: add, bits: 19, inputs: 3}
      - {name: offset, op: add, bits: 16}

Operations: ``mul`` (a_bits, b_bits), ``add`` (bits, inputs), ``compare`` (bits), ``table`` (index_bits, width), ``mux``
(inputs, width), ``memory`` (depth, width, read: sync), ``delay`` (depth, width: a delay line), ``fifo`` (depth, width,
async), ``logic`` (levels: LUT levels, when nothing above fits), ``shift`` (constant shifts cost no logic).
An op may carry ``map: lut`` with ``reason`` to override the hard-resource choice (the reason is recorded).

No model call here: the plan is computed, so CI tests it with a fixture delay model.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import yaml

PLAN_SCHEMA = "fpga-design-agent/timing-plan/v1"
OPS = ("mul", "add", "compare", "table", "mux", "memory", "delay", "fifo", "logic", "shift")
TARGET_FRACTION = 0.70           # owner's example: aim for 70 % of the period before routing
CAL_MISS = 0.25                  # a measured stage more than 25 % off its estimate is a calibration miss

# Inference templates the RTL writer must follow (our own patterns; the KB skill each one comes from is named).
TEMPLATES = {
    "dsp_mul_p0": ("DSP48E1 multiply, no internal register: `p_r <= a_r * b_r;` with a_r, b_r, p_r plain registers "
                   "(synthesis pulls them into AREG/BREG/PREG when it can)", "artix7-dsp48e1"),
    "dsp_mul_p1": ("DSP48E1 multiply with input and output registers: registered operands, `p <= a_r * b_r;` in the next "
                   "clock (AREG/BREG + PREG); no reset, or a synchronous reset, on those registers", "artix7-dsp48e1"),
    "dsp_mul_p2": ("DSP48E1 multiply fully pipelined: registered operands, then `m <= a_r * b_r;`, then `p <= m (+ c);` "
                   "(AREG/BREG, MREG, PREG; a following add of another product or a constant can go in the P stage); "
                   "no asynchronous reset on any of them, or synthesis builds them in fabric", "artix7-dsp48e1"),
    "lut_mul": ("multiply in LUTs and carry chains: mark the product `(* use_dsp = \"no\" *)`", "artix7-design-for-lut6"),
    "carry_add": ("adder or subtractor `s <= a + b;` on the carry chain (CARRY4); a sum of three or more terms is "
                  "a tree of two-input adds, registered between levels if the plan says so", "artix7-clb-and-carry"),
    "carry_compare": ("magnitude compare `lt <= a < b;` on the carry chain", "artix7-clb-and-carry"),
    "lut_table": ("constant table as a `case` in a function, registered output", "artix7-design-for-lut6"),
    "lut_mux": ("wide mux `y <= d[sel*W +: W];`, registered output", "artix7-design-for-lut6"),
    "bram_sdp": ("block RAM: `(* ram_style = \"block\" *)` array, write `if (we) mem[wa] <= wd;`, synchronous read "
                 "`q <= mem[ra];` (a second register `q2 <= q;` uses the RAM's output register)", "artix7-block-ram-and-fifo"),
    "lutram": ("distributed RAM: `(* ram_style = \"distributed\" *)` array with synchronous write", "artix7-srl-lutram-bram-choice"),
    "srl_delay": ("delay line as a shift register with no reset: `sh <= {sh[N-2:0], d};` (SRL16/SRL32)",
                  "artix7-srl-lutram-bram-choice"),
    "xpm_fifo": ("FIFO from the XPM macro the KB recommends (xpm_fifo_sync / xpm_fifo_async)", "artix7-async-fifo-cdc"),
    "lut_logic": ("plain LUT logic", "artix7-design-for-lut6"),
}

# The parts the owner's boards carry (count of hard resources); the delay model names its family.
PARTS = {
    "xc7a100tcsg324-1": {"family": "7series", "dsp": 240, "bram_tile": 135, "lut": 63400, "ff": 126800,
                         "dsp_a_bits": 25, "dsp_b_bits": 18},
}


# --- the delay model ----------------------------------------------------------------------------------------------

def kb_root() -> Path:
    return Path(os.environ.get("FDA_KNOWLEDGE", Path(__file__).resolve().parents[2] / "FPGA_Design_Agent_Knowledge"))


def load_model(family: str = "7series", path: Path | None = None) -> dict[str, Any]:
    """The family's delay model from the knowledge bank (or ``path``). Raises FileNotFoundError when absent: the plan is
    never made from built-in numbers."""
    env = os.environ.get("FDA_DELAY_MODEL")          # a model file outside the bank (a calibration in progress)
    p = Path(path) if path else Path(env) if env else kb_root() / "family_matrix" / "delay_model" / f"{family}.yaml"
    m = yaml.safe_load(p.read_text())
    if m.get("schema") != "fpga-design-agent/delay-model/v1":
        raise ValueError(f"{p}: not a delay model (schema {m.get('schema')!r})")
    m["_path"] = str(p)
    return m


def _lin(m: dict, key: str, x: float) -> float:
    """``{a, b}`` in the model: a + b * x (a straight-line fit over the calibration points)."""
    f = m["fit"][key]
    return float(f["a"]) + float(f["b"]) * float(x)


def op_delay(op: dict[str, Any], resource: str, m: dict[str, Any]) -> list[dict[str, Any]]:
    """The op as a list of *segments*, each ``{ns, reg_after}``: the logic-and-route delay of that piece (no clock-to-out,
    no setup) and the register that may follow it. ``reg_after`` is ``free`` (a DSP or BRAM internal register: no fabric
    FF), ``fabric`` (fabric flip-flops) or ``none`` (no register can go there)."""
    k = op["op"]
    lut = float(m["lut_level_ns"])
    if k == "mul" and resource == "dsp":
        d = m["dsp48"]
        return [{"ns": float(d["in_route_ns"]), "reg_after": "free", "what": "operand into AREG/BREG"},
                {"ns": float(d["mult_ns"]), "reg_after": "free", "what": "multiply (to MREG)"},
                {"ns": float(d["madd_ns"]), "reg_after": "free", "what": "M to P (post-add)"},
                {"ns": float(d["out_route_ns"]), "reg_after": "fabric", "what": "P out to fabric"}]
    if k == "mul":
        w = max(int(op.get("a_bits", 8)), int(op.get("b_bits", 8)))
        return [{"ns": _lin(m, "lut_mul_by_width", w), "reg_after": "fabric", "what": f"{w}-bit multiply in LUTs"}]
    if k == "add":
        n_in = int(op.get("inputs", 2))
        lv = max(1, math.ceil(math.log2(max(n_in, 2))))
        return [{"ns": _lin(m, "add_by_bits", int(op.get("bits", 16))), "reg_after": "fabric", "what": f"add level {i + 1}"}
                for i in range(lv)]
    if k == "compare":
        return [{"ns": _lin(m, "compare_by_bits", int(op.get("bits", 16))), "reg_after": "fabric", "what": "compare"}]
    if k == "table":
        lv = max(1, math.ceil((int(op.get("index_bits", 4)) - 6) / 5) + 1) if int(op.get("index_bits", 4)) > 6 else 1
        return [{"ns": float(m["table_ns"]) + (lv - 1) * lut, "reg_after": "fabric", "what": "table"}]
    if k == "mux":
        n = int(op.get("inputs", 4))
        lv = max(1, math.ceil(math.log(max(n, 2), 4)))
        return [{"ns": float(m["mux16_ns"]) * lv / 2, "reg_after": "fabric", "what": f"{n}:1 mux"}]
    if k in ("memory", "fifo") and resource in ("bram", "fifo"):
        return [{"ns": float(m["bram"]["clk_to_out_reg_ns"]), "reg_after": "fabric", "what": "BRAM read (output register)"}]
    if k == "memory":
        return [{"ns": 2 * lut, "reg_after": "fabric", "what": "LUTRAM read"}]
    if k == "delay":
        return [{"ns": lut, "reg_after": "fabric", "what": "SRL"}]
    if k == "logic":
        return [{"ns": int(op.get("levels", 1)) * lut, "reg_after": "fabric", "what": f"{op.get('levels', 1)} LUT levels"}]
    if k == "shift":
        return [{"ns": 0.0, "reg_after": "none", "what": "constant shift (wiring)"}]
    raise ValueError(f"unknown op {k!r}")


# --- the resource plan ------------------------------------------------------------------------------------------

#: A variant-cost source (brief 63A's flow/ipvariants.py when it lands, or a test stub): ``source(op) -> list of
#: {variant, resource, lut, ff, dsp, bram_tile, fmax_mhz?, source}`` measured for an operation of that kind and size,
#: or ``[]``. When given, the planner records the measured cost of the variant it picks and of the plain-logic
#: alternative in the reason, and refuses a hard-resource variant whose measured cost does not fit what is left.
VariantSource = "Callable[[dict], list[dict]]"


def _variant_note(op: dict[str, Any], resource: str, source, left: dict[str, float]) -> tuple[bool, str]:
    """(fits, note) for the chosen resource from the variant-cost source; (True, "") when there is no source or no data."""
    if source is None:
        return True, ""
    try:
        vs = source(op) or []
    except Exception as e:                                       # noqa: BLE001 (a cost source must never stop the plan)
        return True, f"; variant costs unavailable ({type(e).__name__})"
    if not vs:
        return True, ""
    mine = [v for v in vs if v.get("resource") == resource]
    logic = [v for v in vs if v.get("resource") in ("lut", "carry")]
    fmt = lambda v: f"{v.get('variant')}: LUT {v.get('lut')} FF {v.get('ff')} DSP {v.get('dsp', 0)} BRAM {v.get('bram_tile', 0)}"  # noqa: E731
    note = "; measured " + ", ".join(fmt(v) for v in (mine[:1] + logic[:1])) + f" ({(mine or logic)[0].get('source', 'variant table')})"
    if mine and (mine[0].get("dsp", 0) > left.get("dsp", 1e9) or mine[0].get("bram_tile", 0) > left.get("bram_tile", 1e9)):
        return False, note
    return True, note

def choose_resource(op: dict[str, Any], part: dict[str, Any], left: dict[str, float], variants=None) -> tuple[str, str, str]:
    """(resource, template, reason): hard resource first when the part has it and the budget allows; with a
    variant-cost source, the measured costs are quoted and a variant that does not fit falls back to logic."""
    res, tpl, why = _choose(op, part, left)
    fits, note = _variant_note(op, res, variants, left)
    if not fits:
        return ("lut", "lut_mul" if op["op"] == "mul" else "lut_logic",
                f"measured cost of the {res} variant does not fit what is left of the budget{note}")
    return res, tpl, why + note


def _choose(op: dict[str, Any], part: dict[str, Any], left: dict[str, float]) -> tuple[str, str, str]:
    k = op["op"]
    if op.get("map"):                     # the architect's override, with its reason
        r = op["map"]
        tpl = {"lut": "lut_mul" if k == "mul" else "lut_logic", "dsp": "dsp_mul_p2", "bram": "bram_sdp",
               "lutram": "lutram", "srl": "srl_delay", "carry": "carry_add"}.get(r, "lut_logic")
        return r, tpl, str(op.get("reason") or "architect's choice (no reason given)")
    if k == "mul":
        a, b = sorted((int(op.get("a_bits", 8)), int(op.get("b_bits", 8))))
        if a <= 4:
            return "lut", "lut_mul", f"operand of {a} bits: too small to be worth a DSP slice (a few LUTs)"
        if b > part["dsp_a_bits"] or a > part["dsp_b_bits"]:
            n = math.ceil(b / part["dsp_a_bits"]) * math.ceil(a / part["dsp_b_bits"])
        else:
            n = 1
        if left.get("dsp", 0) < n:
            return "lut", "lut_mul", f"DSP budget exhausted ({left.get('dsp', 0)} left, {n} needed)"
        left["dsp"] -= n
        return "dsp", "dsp_mul_p2", f"{a} x {b} multiply: the part has DSP48E1 slices free ({n} slice{'s' if n > 1 else ''})"
    if k in ("memory", "fifo"):
        bits = int(op.get("depth", 0)) * int(op.get("width", 0))
        if k == "fifo":
            return "fifo", "xpm_fifo", "FIFO: the XPM macro the KB recommends (BRAM or LUTRAM chosen by its depth)"
        if bits >= 2048 and left.get("bram_tile", 0) >= 0.5:
            left["bram_tile"] -= math.ceil(bits / 18432) / 2 if bits <= 18432 else math.ceil(bits / 36864)
            return "bram", "bram_sdp", f"{op.get('depth')} x {op.get('width')} = {bits} bits: block RAM"
        return "lutram", "lutram", f"{bits} bits: too small for a block RAM (under 2 kbit)"
    if k == "delay":
        d = int(op.get("depth", 1))
        if d <= 64:
            return "srl", "srl_delay", f"delay of {d} clocks: SRL32 per bit"
        return "bram", "bram_sdp", f"delay of {d} clocks: block RAM as a circular buffer"
    if k == "add":
        return "carry", "carry_add", "adder: carry chain"
    if k == "compare":
        return "carry", "carry_compare", "comparator: carry chain"
    if k == "table":
        return "lut", "lut_table", "small constant table: LUTs (a ROM in BRAM costs a clock and a 18 kbit block)"
    if k == "mux":
        return "lut", "lut_mux", "mux: LUTs and MUXF7/F8"
    if k == "shift":
        return "wire", "lut_logic", "constant shift: wiring"
    return "lut", "lut_logic", "plain logic: no hard resource fits"


# --- pipelining --------------------------------------------------------------------------------------------------

def _chain(ops: list[dict], maps: dict[str, tuple], m: dict) -> list[dict[str, Any]]:
    """The ops as one sequence of segments; a parallel op is merged with the previous one (the slower of each pair)."""
    seq: list[dict[str, Any]] = []
    for op in ops:
        segs = [dict(s, op=op["name"]) for s in op_delay(op, maps[op["name"]][0], m)]
        if op.get("parallel") and seq:
            n = len(segs)
            base = seq[-n:] if len(seq) >= n else seq
            for a, b in zip(base, segs):
                if b["ns"] > a["ns"]:
                    a["ns"] = b["ns"]
                a["op"] = f"{a['op']}|{b['op']}"
            continue
        seq += segs
    return seq


def pipeline(seq: list[dict[str, Any]], budget_ns: float, overhead_ns: float) -> list[dict[str, Any]]:
    """Greedy stage cut: add segments to the current stage while clock-to-out + logic + setup fits ``budget_ns``; a
    register goes after the last segment that fits (free DSP/BRAM registers count like fabric ones but cost no FFs).
    Returns stages ``[{segments, est_ns, reg: free|fabric}]``; a single segment over the budget is its own stage
    (``over: True``)."""
    stages: list[dict[str, Any]] = []
    cur: list[dict] = []
    for s in seq:
        cand = cur + [s]
        if cur and overhead_ns + sum(x["ns"] for x in cand) > budget_ns:
            cut = max((i for i, x in enumerate(cur) if x["reg_after"] != "none"), default=None)
            if cut is None:
                cur = cand
                continue
            stages.append(cur[:cut + 1])
            cur = cur[cut + 1:] + [s]
        else:
            cur = cand
    if cur:
        stages.append(cur)
    out = []
    for st in stages:
        est = overhead_ns + sum(x["ns"] for x in st)
        out.append({"segments": [f"{x['op']}: {x['what']}" for x in st], "est_ns": round(est, 3),
                    "reg": st[-1]["reg_after"], "over": est > budget_ns})
    return out


def plan_datapath(dp: dict[str, Any], period_ns: float, m: dict[str, Any], part: dict[str, Any], left: dict[str, float],
                  fraction: float = TARGET_FRACTION, variants=None) -> dict[str, Any]:
    maps = {op["name"]: choose_resource(op, part, left, variants) for op in dp["ops"]}
    overhead = float(m["ff"]["clk_to_q_ns"]) + float(m["ff"]["setup_ns"]) + float(m.get("uncertainty_ns", 0.035))
    budget = round(period_ns * fraction, 3)
    seq = _chain(dp["ops"], maps, m)
    unpiped = round(overhead + sum(s["ns"] for s in seq), 3)
    stages = pipeline(seq, budget, overhead)
    latency = len(stages)
    fabric_regs = sum(1 for s in stages[:-1] if s["reg"] == "fabric")
    lat_fixed = dp.get("latency_fixed")
    forced = None
    if lat_fixed is not None and latency > int(lat_fixed):
        forced = (f"the spec fixes the latency at {lat_fixed} cycles but the plan needs {latency} at {fraction:.0%} of "
                  f"{period_ns} ns: a stage will run at {max(s['est_ns'] for s in stages[-int(lat_fixed):]):.2f} ns or more; "
                  "move work out of this path, use a hard resource, or ask for a slower clock")
    return {
        "name": dp["name"], "clock": dp.get("clock"), "instance": dp.get("instance"),
        "ops": [{"name": op["name"], "op": op["op"], "resource": maps[op["name"]][0], "template": maps[op["name"]][1],
                 "template_text": TEMPLATES[maps[op["name"]][1]][0], "kb_skill": TEMPLATES[maps[op["name"]][1]][1],
                 "reason": maps[op["name"]][2]} for op in dp["ops"]],
        "period_ns": period_ns, "budget_ns": budget, "unpipelined_est_ns": unpiped,
        "stages": stages, "latency_cycles": latency, "fabric_pipeline_regs": fabric_regs,
        "fits": all(not s["over"] for s in stages), "latency_forced": forced,
        "planned": {"dsp": sum(1 for op in dp["ops"] if maps[op["name"]][0] == "dsp"),
                    "bram": sum(1 for op in dp["ops"] if maps[op["name"]][0] == "bram")},
    }


def _period(arch: dict, clock: str | None) -> float:
    doms = arch.get("clock_domains") or []
    for d in doms:
        if clock in (d.get("name"), d.get("clock")) or (clock is None and len(doms) == 1):
            return round(1000.0 / float(d["freq_mhz"]), 3)
    if doms:
        return round(1000.0 / float(doms[0]["freq_mhz"]), 3)
    raise ValueError("architecture.yaml has no clock_domains to take the period from")


def check_datapaths(arch: dict[str, Any]) -> list[str]:
    """Schema errors of the optional ``datapaths`` key (flow/architecture.py calls this)."""
    dps = arch.get("datapaths")
    if dps is None:
        return []
    if not isinstance(dps, list):
        return ["'datapaths' must be a list"]
    errs = []
    names = set()
    for i, dp in enumerate(dps):
        if not isinstance(dp, dict) or not dp.get("name") or not isinstance(dp.get("ops"), list) or not dp["ops"]:
            errs.append(f"datapaths[{i}] needs a name and a non-empty ops list")
            continue
        if dp["name"] in names:
            errs.append(f"datapaths: name {dp['name']!r} used twice")
        names.add(dp["name"])
        for j, op in enumerate(dp["ops"]):
            if not isinstance(op, dict) or op.get("op") not in OPS or not op.get("name"):
                errs.append(f"datapaths[{dp['name']}].ops[{j}] needs a name and an op from {', '.join(OPS)}")
            elif op.get("map") and not op.get("reason"):
                errs.append(f"datapaths[{dp['name']}].ops[{op['name']}]: a map override needs a reason")
    return errs


def plan(arch: dict[str, Any], model: dict[str, Any], part_name: str = "xc7a100tcsg324-1",
         budget: dict[str, float] | None = None, fraction: float = TARGET_FRACTION, variants=None) -> dict[str, Any]:
    """The whole plan for an architecture: every datapath mapped and pipelined. ``budget`` caps the hard resources
    (default: the part's count less what ``predicted_resources`` already reserves for other uses is NOT subtracted; the
    architect's prediction is checked after synthesis instead)."""
    part = PARTS[part_name]
    left = {"dsp": float((budget or {}).get("dsp", part["dsp"])), "bram_tile": float((budget or {}).get("bram_tile", part["bram_tile"]))}
    dps = [plan_datapath(dp, _period(arch, dp.get("clock")), model, part, left, fraction, variants) for dp in arch.get("datapaths") or []]
    return {"schema": PLAN_SCHEMA, "family": part["family"], "part": part_name, "model": Path(model.get("_path", "")).name,
            "model_version": model.get("version"), "target_fraction": fraction, "datapaths": dps,
            "variant_costs": variants is not None,
            "planned": {"dsp": sum(d["planned"]["dsp"] for d in dps), "bram": sum(d["planned"]["bram"] for d in dps)},
            "fits": all(d["fits"] for d in dps), "problems": plan_problems(dps)}


def plan_problems(dps: list[dict[str, Any]]) -> list[str]:
    out = []
    for d in dps:
        for s in d["stages"]:
            if s["over"]:
                out.append(f"plan: datapath {d['name']}: one stage ({'; '.join(s['segments'])}) is estimated at {s['est_ns']} ns, "
                           f"over the {d['budget_ns']} ns stage budget even alone: split that operation or use a hard resource")
        if d["latency_forced"]:
            out.append(f"plan: datapath {d['name']}: {d['latency_forced']}")
    return out


def plan_text(p: dict[str, Any]) -> str:
    """The plan as the RTL writer's instructions (compact)."""
    lines = [f"TIMING AND RESOURCE PLAN (computed from the {p['family']} delay model, {p['target_fraction']:.0%} of the period per stage). "
             "Write the RTL to this plan: use each named template so synthesis infers the planned primitive; after synthesis a "
             "planned DSP or BRAM that comes out as LUTs or registers fails the gate."]
    for d in p["datapaths"]:
        lines.append(f"- datapath {d['name']} (clock period {d['period_ns']} ns, stage budget {d['budget_ns']} ns; one stage "
                     f"unpipelined would be {d['unpipelined_est_ns']} ns): {d['latency_cycles']} register stages, latency "
                     f"{d['latency_cycles']} clocks from the source register.")
        for op in d["ops"]:
            lines.append(f"    {op['name']} ({op['op']}) -> {op['resource']}: {op['template_text']} [{op['reason']}]")
        for i, s in enumerate(d["stages"]):
            lines.append(f"    stage {i + 1} (~{s['est_ns']} ns, register after it: {s['reg']}): {'; '.join(s['segments'])}")
        if d["latency_forced"]:
            lines.append(f"    NOTE: {d['latency_forced']}")
    return "\n".join(lines)


# --- checking the plan after synthesis and after routing ---------------------------------------------------------

def check_post_synth(p: dict[str, Any], util: dict[str, Any], hier_rows: list[dict[str, Any]] | None = None) -> list[str]:
    """A planned DSP or BRAM that did not come out as one is a failure (c13's case: two multiplies built in LUTs).
    Checked per instance when the datapath names one and the hierarchical report is given, else on the design totals."""
    from flow.digest.utilization import paths as hier_paths
    fails = []
    rows = hier_paths(hier_rows) if hier_rows else []

    def used(inst: str | None, key: str) -> float | None:
        if inst and rows:
            for r in rows:
                if not r["own"] and r["path"] == inst:
                    return float(r.get(key) or 0)
            return None
        return float(util.get(key) or 0)

    by_inst: dict[str | None, dict[str, int]] = {}
    for d in p.get("datapaths") or []:
        b = by_inst.setdefault(d.get("instance") if rows else None, {"dsp": 0, "bram": 0})
        b["dsp"] += d["planned"]["dsp"]
        b["bram"] += d["planned"]["bram"]
    for inst, need in by_inst.items():
        where = f"instance {inst}" if inst else "the design"
        u = used(inst, "dsp")
        if need["dsp"] and u is not None and u < need["dsp"]:
            fails.append(f"plan: {where} has {int(u)} DSP48E1 where the plan put {need['dsp']} multiplies on DSP slices "
                         "(they were built in LUTs or optimised away): use the dsp_mul template, no asynchronous reset on its "
                         "registers, operands within 25 x 18")
        ub = used(inst, "bram_tile")
        if need["bram"] and ub is not None and ub <= 0:
            fails.append(f"plan: {where} has no block RAM where the plan put {need['bram']} memories in BRAM "
                         "(the RAM became registers or LUTs): use the bram_sdp template")
    return fails


def compare_post_route(p: dict[str, Any], setup_path: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Calibration rows: the worst routed setup path, when it lies inside a planned datapath's instance, against that
    datapath's worst planned stage. ``miss`` when the measurement is more than CAL_MISS off the estimate."""
    rows = []
    if not setup_path:
        return rows
    s, d = setup_path.get("source_reg") or {}, setup_path.get("dest_reg") or {}
    for dp in p.get("datapaths") or []:
        inst = dp.get("instance")
        if not inst or not (s.get("instance", "").startswith(inst) and d.get("instance", "").startswith(inst)):
            continue
        est = max(st["est_ns"] for st in dp["stages"])
        meas = round((setup_path.get("data_path_ns") or 0) + 0.062 + 0.035, 3)      # setup + uncertainty, as the estimate has
        ratio = round(meas / est, 3) if est else None
        rows.append({"datapath": dp["name"], "est_worst_stage_ns": est, "measured_ns": meas, "ratio": ratio,
                     "miss": ratio is not None and abs(ratio - 1) > CAL_MISS, "path": f"{setup_path.get('source')} -> {setup_path.get('destination')}",
                     "levels": setup_path.get("levels_by_type")})
    return rows


# --- the design-level entry points (hooks call these) ------------------------------------------------------------

PLAN_JSON = Path("build") / "plan" / "timing_plan.json"
PLAN_MD = "TIMING_PLAN.md"

#: the CONVENTIONS bullet the architecture stage gets with ``--design-plan`` (agent/graph/run.py hook; appended after
#: CONVENTIONS is formatted, so single braces).
DATAPATHS_CONVENTION = """
- Design-time timing and resource plan (brief 62A): architecture.yaml also lists `datapaths`, one entry per registered
  chain of arithmetic or logic on the design's critical paths (multiplies, adder and comparator trees, table lookups,
  wide muxes, memories, delay lines, FIFOs): {name, clock (a clock_domains name), instance (the RTL instance path, for
  example u_regs/u_core), latency_fixed (cycles, only if the spec fixes it), ops: [...]}. Each op is {name, op, ...}
  with op one of mul {a_bits, b_bits} (signed operand widths), add {bits, inputs}, compare {bits},
  table {index_bits, width}, mux {inputs, width}, memory {depth, width}, delay {depth, width}, fifo {depth, width},
  logic {levels}, shift; list them in order along the chain, and mark an op that runs beside the previous one with
  `parallel: true`. Do not choose resources or pipeline depth yourself: the gate computes them from the device family's
  measured delay model (hard resources first: multiplies on DSP slices, memories in block RAM, short delays in SRLs)
  and writes TIMING_PLAN.md; to override a choice give the op `map: lut` (or bram, srl ...) and a `reason`. The RTL
  writer then follows TIMING_PLAN.md, and after synthesis a planned DSP or block RAM that was not inferred fails the gate.
"""


def plan_design(design: Path, model: dict[str, Any] | None = None, require: bool = False) -> dict[str, Any]:
    """Plan the design's architecture.yaml datapaths and write build/plan/timing_plan.json and TIMING_PLAN.md (the RTL
    writer reads it). Returns ``{ok, problems, plan}``; ``ok`` is True with no plan when there are no datapaths, unless
    ``require`` (the graph's ``--design-plan``) and the key is absent altogether."""
    design = Path(design)
    try:
        arch = yaml.safe_load((design / "architecture.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        return {"ok": False, "problems": [f"plan: architecture.yaml unreadable: {e}"], "plan": None}
    if require and "datapaths" not in arch:
        return {"ok": False, "plan": None, "problems": [
            "plan: architecture.yaml has no 'datapaths': list the arithmetic and wide-logic chains of the critical paths "
            "(or write 'datapaths: []' if there are none)"]}
    if not arch.get("datapaths"):
        return {"ok": True, "problems": [], "plan": None}
    errs = check_datapaths(arch)
    if errs:
        return {"ok": False, "problems": ["plan: " + e for e in errs], "plan": None}
    try:
        model = model or load_model("7series")
    except (OSError, ValueError) as e:
        return {"ok": False, "problems": [f"plan: no delay model ({e})"], "plan": None}
    p = plan(arch, model)
    (design / PLAN_JSON).parent.mkdir(parents=True, exist_ok=True)
    (design / PLAN_JSON).write_text(json.dumps(p, indent=1) + "\n")
    (design / PLAN_MD).write_text("# Timing and resource plan (computed; do not edit)\n\n" + plan_text(p) + "\n")
    return {"ok": not p["problems"], "problems": p["problems"], "plan": p}


def load_plan(design: Path) -> dict[str, Any] | None:
    try:
        return json.loads((Path(design) / PLAN_JSON).read_text())
    except (OSError, ValueError):
        return None


def post_synth_failures(design: Path, gates: dict[str, Any] | None) -> list[str]:
    """For the stage-4 gate hook: the plan check on the design's own synthesis reports (empty with no plan)."""
    p = load_plan(design)
    if not p:
        return []
    from flow.digest.utilization import parse_hier
    st = ((gates or {}).get("stages") or {}).get("post_synth") or {}
    util = (gates or {}).get("utilization") or st.get("utilization") or {}
    hier = Path(design) / "build" / "base" / "utilization_hier_synth.rpt"
    rows = parse_hier(hier.read_text()) if hier.is_file() else None
    return check_post_synth(p, util, rows)


def record_calibration(design: Path, out: Path) -> list[dict[str, Any]]:
    """After routing: append the plan-versus-measured rows of this build to ``out`` (JSON lines)."""
    from flow.digest.build import digest_build
    p = load_plan(design)
    if not p:
        return []
    rows = compare_post_route(p, digest_build(Path(design) / "build" / "base").get("setup_path"))
    if rows:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as f:
            for r in rows:
                f.write(json.dumps({"design": Path(design).name, **r}) + "\n")
    return rows


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Plan a design's datapaths (architecture.yaml) from the KB delay model.")
    ap.add_argument("design", type=Path)
    ap.add_argument("--model", type=Path, help="delay model YAML (default: the knowledge bank's)")
    a = ap.parse_args(argv)
    r = plan_design(a.design, load_model(path=a.model) if a.model else None)
    print(plan_text(r["plan"]) if r["plan"] else "no datapaths")
    for pr in r["problems"]:
        print(pr)
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
