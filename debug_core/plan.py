"""Request intent -> a checked debug plan for the vendor ILA on the Basic licence tier (brief 50A).

``make_plan(design, intent)`` is deterministic: it resolves every signal name against the RTL (debug_core/rtl_index.py),
compiles the trigger into per-bit compare patterns, sizes the window, packs the probes into at most 5 ILA ports
(flow/prepare.py ``pack_probes``), checks one clock domain and a block-RAM budget, and validates the result against
``schemas/plan.schema.json``. A plan with ``errors`` is shown but never built; each error says why and, where there is
one, the cut that would fit.

The limits are the measured Basic-tier ones (brief 48, Vivado 2026.1): one ILA instance, so one clock domain; at most
5 probe ports; widths up to 256 bits per port and depths up to 4096 were built (wider or deeper is allowed by the IP and
is flagged as not measured). Trigger compares are per bit (0, 1, X and the edge letters R, F, B), because a packed port
holds several named probes and one named probe can be split over several hardware probes; so ``!=`` and magnitude
compares on buses are refused unless they reduce to a per-bit pattern.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import yaml

from debug_core.rtl_index import ROOT, RtlIndex

try:
    from flow.prepare import ILA_MAX_PORTS, pack_probes
except ImportError:                                     # pragma: no cover
    from prepare import ILA_MAX_PORTS, pack_probes      # type: ignore

SCHEMAS = Path(__file__).with_name("schemas")
DEPTHS = (1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072)
MEASURED_PORT_BITS = 256          # brief 48: 1 port x 256 bits built on 2026.1 Basic
MEASURED_DEPTH = 4096             # brief 48: depth 4096 built on 2026.1 Basic
PORT_BITS = 1024                  # ILA IP probe-port width limit used for packing (wider ports are split)
BRAM36_BITS = 36 * 1024
DEFAULT_BRAM_BUDGET = 32          # BRAM36 tiles the debug core may take (xc7a100t has 135); a plan over it is cut
DEFAULT_PRE, DEFAULT_POST = 128, 895
EDGE_OPS = {"rise": "R", "fall": "F", "change": "B"}


class PlanError(ValueError):
    pass


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text())


def validate(obj: dict[str, Any], name: str) -> list[str]:
    import jsonschema
    v = jsonschema.Draft202012Validator(load_schema(name))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in v.iter_errors(obj)]


# --- values and patterns ------------------------------------------------------------------------------------------------------

def parse_value(v: Any, width: int) -> str:
    """An integer, '0x4?', '0b10x1', "'A'" or a decimal string -> a bit pattern of ``width`` chars (MSB first, X = don't care)."""
    if isinstance(v, bool):
        v = int(v)
    if isinstance(v, int):
        if v < 0 or v >= 1 << width:
            raise PlanError(f"value {v} does not fit in {width} bits")
        return format(v, f"0{width}b")
    if not isinstance(v, str) or not v.strip():
        raise PlanError(f"no value given ({v!r})")
    t = v.strip().replace("_", "")
    m = re.fullmatch(r"'(.)'", t)
    if m:
        return parse_value(ord(m.group(1)), width)
    m = re.fullmatch(r"(?:\d+)?'?([hHbBdD])([0-9a-fA-FxX?]+)", t) or re.fullmatch(r"0([xXbB])([0-9a-fA-FxX?]+)", t)
    if m:
        base, digits = m.group(1).lower(), m.group(2).lower().replace("?", "x")
        if base == "d":
            return parse_value(int(digits), width)
        per = 4 if base in ("h", "x") else 1
        bits = "".join(("x" * per) if c == "x" else format(int(c, 16 if per == 4 else 2), f"0{per}b") for c in digits)
        bits = bits.upper()
        if len(bits) > width:
            extra = bits[:-width]
            if extra.strip("0"):
                raise PlanError(f"value {v} does not fit in {width} bits")
            bits = bits[-width:]
        return bits.rjust(width, "0")
    if re.fullmatch(r"\d+", t):
        return parse_value(int(t), width)
    raise PlanError(f"cannot read the value {v!r} (use an integer, 0x.., 0b.. with x for don't care, or 'c')")


def compile_condition(op: str, value: Any, width: int) -> str:
    """One condition on one probe -> its per-bit pattern (MSB first). Raises PlanError with a proposal if the ILA's
    per-bit compare cannot express it."""
    if op in EDGE_OPS:
        if width != 1:
            raise PlanError(f"'{op}' needs a 1-bit signal (this one is {width} bits); trigger on one bit of it, "
                            f"or on == a value")
        return EDGE_OPS[op]
    if op == "==":
        return parse_value(value, width)
    if op == "!=":
        if width == 1:
            p = parse_value(value, 1)
            return "0" if p == "1" else "1"
        raise PlanError(f"'!=' on a {width}-bit bus is an OR over its bits, which the packed per-bit compare cannot "
                        "express; trigger on == a value (X for don't-care bits), or on a 1-bit flag")
    if op in ("<", "<="):
        n = parse_value(value, max(width, 64)).lstrip("0") or "0"
        if "X" in n:
            raise PlanError("a magnitude compare needs a plain number")
        lim = int(n, 2) + (1 if op == "<=" else 0)
        if lim <= 0:
            raise PlanError(f"{op} {value} is never true")
        k = int(math.log2(lim))
        if 1 << k == lim and k >= width:
            raise PlanError(f"'{op} {value}' is always true on a {width}-bit signal, so it would trigger at once; "
                            "use a smaller bound or another condition")
        if 1 << k != lim or k > width:
            raise PlanError(f"'{op} {value}' is a per-bit pattern only when the bound is a power of two (x < 2^k means "
                            f"the top bits are 0); use < {1 << k} or < {1 << (k + 1)}, or == with X bits")
        return "0" * (width - k) + "X" * k
    if op in (">", ">="):
        raise PlanError(f"'{op}' is an OR over bits on a bus, which the packed per-bit compare cannot express; use == "
                        "with X for don't-care bits (for example 0b1xxxxxxx for >= 128 on 8 bits)")
    raise PlanError(f"unknown compare '{op}'")


def merge_patterns(a: str, b: str) -> str:
    """AND of two per-bit patterns. An edge implies the level after it (R with 1 is R, F with 0 is F)."""
    implied = {"R": "1", "F": "0"}
    out = []
    for x, y in zip(a, b):
        if x == "X":
            out.append(y)
        elif y == "X" or x == y:
            out.append(x)
        elif implied.get(x) == y:
            out.append(x)
        elif implied.get(y) == x:
            out.append(y)
        else:
            raise PlanError(f"two conditions on the same signal contradict each other ({a} and {b})")
    return "".join(out)


def pattern_text(p: str) -> str:
    if len(p) == 1:
        return {"R": "rises", "F": "falls", "B": "changes", "1": "== 1", "0": "== 0", "X": "any"}[p]
    if set(p) <= {"0", "1"}:
        return f"== 0x{int(p, 2):0{(len(p) + 3) // 4}X}"
    return f"matches 0b{p}"


# --- design facts -------------------------------------------------------------------------------------------------------------

def design_cfg(design: Path) -> dict[str, Any]:
    return yaml.safe_load((design / "build.yaml").read_text())


def clock_info(design: Path, domain: str | None) -> dict[str, Any]:
    """The ILA clock net and frequency for a clock domain rooted at a top-level port (Vivado names the buffered clock
    net ``<port>_IBUF_BUFG``; the design's probes.yaml ``ila.clock_net`` is used when it is that net)."""
    if domain is None:
        return {"domain": None, "net": None, "mhz": None}
    cfg = design_cfg(design)
    net = f"{domain}_IBUF_BUFG" if "." not in domain else None
    pf = ROOT / cfg["probes"] if cfg.get("probes") else None
    if pf and pf.is_file():
        cn = ((yaml.safe_load(pf.read_text()) or {}).get("ila") or {}).get("clock_net")
        if cn and cn.startswith(domain):
            net = cn
    mhz = None
    for pat in cfg.get("constraints", []):
        for x in sorted(ROOT.glob(pat)):
            for line in x.read_text(errors="replace").splitlines():
                m = re.search(r"create_clock\b.*-period\s+([\d.]+).*get_ports\s*\{?\s*" + re.escape(domain) + r"\b", line)
                if m:
                    mhz = round(1000.0 / float(m.group(1)), 6)
    return {"domain": domain, "net": net, "mhz": mhz}


def register_map(design: Path) -> dict[str, int]:
    """Register name -> shell address: the shell's own registers and the design's window (spec.yaml registers.map)."""
    from shell.host import protocol as p
    regs = {"DESIGN_ID": p.REG_DESIGN_ID, "SHELL_VERSION": p.REG_SHELL_VERSION, "BUILD_STAMP": p.REG_BUILD_STAMP,
            "SCRATCH": p.REG_SCRATCH, "STATUS": p.REG_STATUS}
    spec = design / "spec.yaml"
    if spec.is_file():
        s = yaml.safe_load(spec.read_text()) or {}
        for r in ((s.get("registers") or {}).get("map") or []):
            regs[str(r["name"]).upper()] = p.WINDOW_BASE + int(r["offset"])
    return regs


def resolve_ops(design: Path, ops: list[dict[str, Any]] | None, errors: list[dict[str, Any]], where: str) -> list[dict[str, Any]]:
    regs = register_map(design)
    out = []
    for o in ops or []:
        op = dict(o)
        if op["op"] in ("write", "read"):
            r = op.get("register")
            addr = None
            if isinstance(r, int):
                addr = r
            elif isinstance(r, str):
                if r.upper() in regs:
                    addr = regs[r.upper()]
                elif re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", r.strip()):
                    addr = int(r.strip(), 0)
            if addr is None or not 0 <= addr <= 0xFF:
                errors.append({"what": f"{where}: register {r!r}", "why": "not a shell register or design register name",
                               "suggestions": sorted(regs)})
                continue
            op["address"] = addr
            name = next((k for k, v in regs.items() if v == addr), None)
            op["register"] = name or f"0x{addr:02X}"
            if op["op"] == "write":
                try:
                    op["value"] = int(parse_value(op.get("value"), 32), 2)
                except PlanError as e:
                    errors.append({"what": f"{where}: write {op['register']}", "why": str(e)})
                    continue
            else:
                op.pop("value", None)
        elif op["op"] == "wait_ms":
            op["ms"] = float(op.get("ms") or 0)
        out.append({k: v for k, v in op.items() if v is not None})
    return out


def _label(path: str, taken: set[str], asked: str = "") -> str:
    if re.fullmatch(r"[A-Za-z_]\w*", asked) and asked not in taken:
        taken.add(asked)
        return asked
    leaf = re.sub(r"\[(\d+)\]", r"_\1", path.split(".")[-1])
    lab = leaf if leaf not in taken else re.sub(r"\W", "_", path.replace(".", "__"))
    taken.add(lab)
    return lab


# --- the plan ------------------------------------------------------------------------------------------------------------------

def make_plan(design: Path | str, intent: dict[str, Any], request: str | None = None, *,
              index: RtlIndex | None = None, bram_budget: int = DEFAULT_BRAM_BUDGET,
              max_ports: int = ILA_MAX_PORTS) -> dict[str, Any]:
    design = Path(design)
    design = design if design.is_absolute() else ROOT / design
    bad = validate(intent, "intent")
    if bad:
        raise PlanError("the parsed request does not match the intent schema: " + "; ".join(bad))
    idx = index or RtlIndex.from_design(design)
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1. resolve every name (trigger signals first, so they are kept by any cut)
    trig = intent["trigger"]
    names: list[tuple[str, str]] = [(c["signal"], "trigger") for c in trig["conditions"]]
    names += [(n, "data") for n in intent.get("probes", [])]
    probes: dict[str, dict[str, Any]] = {}            # by pins
    by_query: dict[str, dict[str, Any]] = {}
    taken: set[str] = set()
    for q, role in names:
        r = idx.resolve(q)
        if not r.ok:
            err = {"what": f"signal '{q}'", "why": f"{r.kind}: " + "; ".join(r.notes or ["not found"])}
            if r.suggestions:
                err["suggestions"] = r.suggestions
            if r.candidates:
                err["candidates"] = r.candidates
            if not any(e["what"] == err["what"] for e in errors):
                errors.append(err)
            continue
        if r.pins in probes:
            p = probes[r.pins]
            if role not in p["role"]:
                p["role"] = "trigger+data"
        else:
            p = {"label": _label(r.path, taken, q), "path": r.path, "width": int(r.width or 1), "pins": r.pins,
                 "kind": r.kind, "requested_as": q, "clock": r.clock, "role": role, "notes": list(r.notes)}
            if r.kind == "top_input":
                warnings.append(f"{q}: a raw input pin; it is asynchronous to the ILA clock, so an edge on it can be "
                                "seen one cycle early or late")
            probes[r.pins] = p
        by_query[q] = p
    plist = list(probes.values())

    # 2. one clock domain (Basic tier: one ILA instance)
    domains = {p["clock"] for p in plist if p["clock"]}
    want = intent.get("clock")
    if want and want not in domains and domains:
        warnings.append(f"the request names clock {want!r}; the probes are in {sorted(domains)}")
    if len(domains) > 1:
        tdom = [p["clock"] for p in plist if "trigger" in p["role"] and p["clock"]]
        keep = max(set(tdom or [p["clock"] for p in plist if p["clock"]]), key=(tdom or [p["clock"] for p in plist]).count)
        cut = [p["path"] for p in plist if p["clock"] and p["clock"] != keep]
        errors.append({"what": "clock domains", "why": f"the probes are in {len(domains)} clock domains {sorted(domains)}; "
                       "the Basic tier allows one ILA, so one domain per build",
                       "proposal": {"keep_domain": keep, "drop": cut,
                                    "note": "probe each dropped signal's synchronised copy in the kept domain if the "
                                            "design has one, or capture the other domain in a second build"}})
    domain = next(iter(domains)) if len(domains) == 1 else (want or None)
    if domain is None and plist:
        domain = idx._default_clock()
    clock = clock_info(design, domain)
    if plist and clock["net"] is None:
        errors.append({"what": "clock", "why": f"no ILA clock net known for domain {domain!r} (only clocks that enter "
                       "on a top-level port are supported in 50A)"})
    for p in plist:
        p["clock"] = p["clock"] or domain

    # 3. trigger patterns
    conds: list[dict[str, Any]] = []
    merged: dict[str, dict[str, Any]] = {}
    for c in trig["conditions"]:
        p = by_query.get(c["signal"])
        if p is None:
            continue
        try:
            pat = compile_condition(c["op"], c.get("value"), p["width"])
        except PlanError as e:
            errors.append({"what": f"trigger on '{c['signal']}' {c['op']} {c.get('value', '')}".strip(), "why": str(e)})
            continue
        if p["label"] in merged:
            prev = merged[p["label"]]
            if trig["combine"] == "AND":
                try:
                    prev["pattern"] = merge_patterns(prev["pattern"], pat)
                except PlanError as e:
                    errors.append({"what": f"trigger on '{c['signal']}'", "why": str(e)})
                continue
            # OR on a signal that already has a term. The ILA arms one compare value per hardware probe, so two OR terms
            # on one signal would leave only the last one armed (review of brief 50A). Rising OR falling is "either edge";
            # the same term twice is one term; anything else is refused.
            both = {prev["pattern"], pat}
            if both == {"R", "F"}:
                prev.update({"pattern": "B", "op": "change", "value": None})
            elif prev["pattern"] != pat:
                errors.append({"what": f"trigger OR on '{c['signal']}'",
                               "why": f"two OR terms on the same signal ({p['label']} {pattern_text(prev['pattern'])} OR "
                                      f"{pattern_text(pat)}); the logic analyser holds one compare value per signal, so "
                                      "only one of them would be armed",
                               "proposal": "use 'change' for rising OR falling; otherwise capture each term separately, "
                                           "or trigger on a register that combines them"})
            continue
        cond = {"probe": p["label"], "op": c["op"], "value": c.get("value"), "pattern": pat}
        merged[p["label"]] = cond
        conds.append(cond)
    for c in conds:
        c["text"] = f"{c['probe']} {pattern_text(c['pattern'])}"
    combine = trig["combine"]
    if len(conds) <= 1 and combine == "OR":
        combine = "AND"          # one condition: the same meaning, and the ILA's AND never involves the probes not named
    if not trig["conditions"]:
        errors.append({"what": "trigger", "why": "the request gives no trigger condition",
                       "proposal": "say when to capture, for example 'when win_wr is 1'"})
    if trig["combine"] == "OR" and len(conds) > 1:
        multi = [c["probe"] for c in conds if len(c["pattern"]) > 1]
        if multi:
            errors.append({"what": "trigger OR", "why": f"OR across hardware probes is only exact for 1-bit signals; "
                           f"{multi} are buses, and a bus can be split over several hardware probes, so OR would fire "
                           "on a part of the value", "proposal": "use AND, or OR of 1-bit flags only"})

    # 4. window
    pre = intent.get("pre")
    post = intent.get("post")
    pre = DEFAULT_PRE if pre is None else int(pre)
    if post is None:
        post = max(0, DEFAULT_PRE + DEFAULT_POST - pre)
    need = pre + post + 1
    depth = next((d for d in DEPTHS if d >= need), None)
    if depth is None:
        errors.append({"what": "window", "why": f"{pre} + {post} + 1 = {need} samples is more than the ILA's largest "
                       f"depth {DEPTHS[-1]}", "proposal": {"pre": min(pre, DEPTHS[-1] // 4),
                                                            "post": DEPTHS[-1] - 1 - min(pre, DEPTHS[-1] // 4)}})
        depth = DEPTHS[-1]
    window = {"pre": pre, "post": depth - pre - 1, "depth": depth, "position": min(pre, depth - 1),
              "requested": {"pre": intent.get("pre"), "post": intent.get("post")}}
    if depth > MEASURED_DEPTH:
        warnings.append(f"depth {depth} is more than the {MEASURED_DEPTH} built so far on the Basic tier; untested beyond that")

    # 5. pack into ports, check the port count and the block RAM
    ports: list[dict[str, Any]] = []
    fit: dict[str, Any] = {"ok": True, "max_ports": max_ports, "bram_budget": bram_budget}
    if plist:
        _assign_groups(plist)
        if combine == "OR" and len(conds) > 1:
            # measured on Vivado 2026.1 Basic (brief 50A): the ILA is built with one comparator per port, and compares on
            # one port merge into that comparator only under AND (Labtools 27-3239 / 27-3241), so each OR term gets a port
            for c in conds:
                p = next(x for x in plist if x["label"] == c["probe"])
                p["group"] = f"or_{p['label']}"
        try:
            ports = pack_probes([{**p, "name": p["label"]} for p in plist], max_ports=max_ports, clock_net=None)
        except ValueError as e:
            keep, drop = _cut_ports(plist, max_ports)
            errors.append({"what": "ports", "why": str(e), "proposal": {"keep": [p["path"] for p in keep],
                                                                          "drop": [p["path"] for p in drop]}})
        width = sum(p["width"] for p in plist)
        bram = math.ceil(width * depth / BRAM36_BITS)
        fit.update({"ports_used": len(ports), "total_bits": width, "bram36_estimate": bram})
        if any(pt["width"] > MEASURED_PORT_BITS for pt in ports):
            warnings.append(f"a port wider than the {MEASURED_PORT_BITS} bits built so far on the Basic tier; untested beyond that")
        if bram > bram_budget:
            d_ok = max((d for d in DEPTHS if math.ceil(width * d / BRAM36_BITS) <= bram_budget and d >= need), default=None)
            prop: dict[str, Any] = {}
            if d_ok:
                prop["depth"] = d_ok
            else:
                keep, drop = _cut_bits(plist, depth, bram_budget)
                prop["drop"] = [p["path"] for p in drop]
                prop["keep"] = [p["path"] for p in keep]
                small = max((d for d in DEPTHS if math.ceil(width * d / BRAM36_BITS) <= bram_budget), default=None)
                if small:
                    prop["or_depth"] = small
            errors.append({"what": "block RAM", "why": f"{width} bits x {depth} samples needs about {bram} BRAM36 tiles; "
                           f"the debug budget is {bram_budget}", "proposal": prop})
    else:
        errors.append({"what": "probes", "why": "nothing to probe: no signal in the request resolved"})
    fit["ok"] = not errors

    setup = resolve_ops(design, intent.get("setup"), errors, "setup")
    stimulus = resolve_ops(design, intent.get("stimulus"), errors, "stimulus")
    readback = resolve_ops(design, intent.get("readback"), errors, "readback")
    fit["ok"] = not errors

    plan = {"schema": "fda-debug-plan/1", "design": str(design.relative_to(ROOT)) if design.is_relative_to(ROOT) else str(design),
            "request": request, "backend": "vendor_ila", "clock": clock, "probes": plist,
            "trigger": {"combine": combine, "conditions": conds}, "window": window,
            "ports": [{"port": pt["port"], "group": pt["group"], "width": pt["width"],
                       "slices": [{"label": s["name"], "offset": s["offset"], "width": s["width"]} for s in pt["slices"]]}
                      for pt in ports],
            "setup": setup, "stimulus": stimulus, "readback": readback, "fit": fit, "errors": errors,
            "warnings": warnings, "question": intent.get("question"), "unclear": intent.get("unclear", [])}
    plan["probeset"] = probeset_hash(plan)
    bad = validate(plan, "plan")
    if bad:
        raise PlanError("internal: the plan does not match its schema: " + "; ".join(bad))
    return plan


def _assign_groups(plist: list[dict[str, Any]]) -> None:
    """1-bit probes share the 'flags' port; wider ones fill 'data', 'data2', ... up to PORT_BITS each."""
    n, used = 1, 0
    for p in plist:
        if p["width"] == 1:
            p["group"] = "flags"
            continue
        if used + p["width"] > PORT_BITS:
            n, used = n + 1, 0
        p["group"] = "data" if n == 1 else f"data{n}"
        used += p["width"]


def _cut_ports(plist, max_ports):
    keep: list = []
    for p in sorted(plist, key=lambda p: "trigger" not in p["role"]):
        trial = keep + [p]
        _assign_groups(trial)
        if len({q["group"] for q in trial}) <= max_ports:
            keep = trial
    _assign_groups(plist)
    return keep, [p for p in plist if p not in keep]


def _cut_bits(plist, depth, budget):
    keep: list = []
    for p in sorted(plist, key=lambda p: "trigger" not in p["role"]):
        if math.ceil((sum(q["width"] for q in keep) + p["width"]) * depth / BRAM36_BITS) <= budget:
            keep.append(p)
    return keep, [p for p in plist if p not in keep]


def probeset_hash(plan: dict[str, Any]) -> str:
    """What decides the debug build: the probe pins in port order, the clock net and the depth. Two plans with the same
    hash share one bitstream (the trigger, window position and stimulus are run-time settings)."""
    key = {"pins": [[(s["label"], next(p["pins"] for p in plan["probes"] if p["label"] == s["label"]), s["width"])
                     for s in pt["slices"]] for pt in plan["ports"]],
           "clock": plan["clock"].get("net"), "depth": plan["window"]["depth"]}
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]


def probes_yaml(plan: dict[str, Any]) -> str:
    """The probes.yaml the ILA build reads (flow/prepare.py), written from the plan."""
    if plan["errors"]:
        raise PlanError("the plan has errors; it is not built")
    data = {"ila": {"name": "u_ila_0", "clock_net": plan["clock"]["net"], "depth": plan["window"]["depth"],
                    "input_pipe_stages": 0},
            "probes": [{"name": p["label"], "pins": p["pins"], "width": p["width"], "group": p["group"],
                        "why": f"debug plan {plan['probeset']}: {p['requested_as']} -> {p['path']}"} for p in plan["probes"]]}
    return ("# generated by debug_core/plan.py from a debug plan; do not edit\n"
            + yaml.safe_dump(data, sort_keys=False, width=200))


def render(plan: dict[str, Any]) -> str:
    """The plan in plain words, shown to the user or the agent before anything is built."""
    L = []
    if plan.get("request"):
        L.append(f"Request: {plan['request']}")
    c = plan["clock"]
    mhz = f", {c['mhz']:g} MHz" if c.get("mhz") else ""
    L.append(f"Back end: vendor ILA (one ILA IP, Basic tier), clock domain {c['domain']} (net {c['net']}{mhz}).")
    if plan["probes"]:
        L.append("Probes:")
        for p in plan["probes"]:
            L.append(f"  {p['label']:<14} {p['width']:>3} bit{'s' if p['width'] > 1 else ' '}  {p['path']:<28} "
                     f"<- '{p['requested_as']}' ({p['kind']}, {p['role']}) pins {p['pins']}")
            for n in p.get("notes", []):
                L.append(f"  {'':<14} note: {n}")
    t = plan["trigger"]
    if t["conditions"]:
        L.append(f"Trigger ({t['combine']}): " + f" {t['combine']} ".join(c["text"] for c in t["conditions"]))
    w = plan["window"]
    req = w.get("requested") or {}
    asked = (f"the smallest size that holds the {req.get('pre')} before and {req.get('post')} after you asked for; "
             "the answer covers your window" if req.get("pre") is not None or req.get("post") is not None
             else "no window was asked for, so the default is used")
    L.append(f"Window: {w['depth']} samples, {w['pre']} before the trigger and {w['post']} after ({asked}).")
    if plan["ports"]:
        L.append("Ports: " + "; ".join(f"probe{pt['port']} {pt['group']} {pt['width']} bit{'s' if pt['width'] != 1 else ''} = "
                                        + " + ".join(f"{s['label']}[{s['width']}]" for s in pt["slices"])
                                        for pt in plan["ports"])
                 + f" ({len(plan['ports'])} of the {plan['fit']['max_ports']} allowed ports; about "
                   f"{plan['fit'].get('bram36_estimate', '?')} block RAM tile{'s' if plan['fit'].get('bram36_estimate') != 1 else ''}).")
    for k, title in (("setup", "Before arming"), ("stimulus", "After arming"), ("readback", "After the capture")):
        if plan.get(k):
            L.append(f"{title}: " + "; ".join(_op_text(o) for o in plan[k]))
    for wtxt in plan["warnings"]:
        L.append(f"Warning: {wtxt}")
    if plan["errors"]:
        L.append("CANNOT BE BUILT:")
        for e in plan["errors"]:
            L.append(f"  - {e['what']}: {e['why']}")
            for k in ("suggestions", "candidates"):
                if e.get(k):
                    L.append(f"      {k}: {', '.join(e[k])}")
            if e.get("proposal"):
                L.append(f"      proposal: {json.dumps(e['proposal'])}")
    else:
        L.append(f"Can be built (probe set {plan['probeset']}).")
    return "\n".join(L)


def _op_text(o: dict[str, Any]) -> str:
    if o["op"] == "write":
        return f"write {o['register']} (0x{o['address']:02X}) = 0x{o['value']:X}"
    if o["op"] == "read":
        return f"read {o['register']} (0x{o['address']:02X})"
    return f"wait {o['ms']:g} ms"
