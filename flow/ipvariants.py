#!/usr/bin/env python3
"""Implementation variants of the ip_lib entries: the `variants:` schema, its validation, and the read API a planner
uses to choose a variant. The data contract is docs/ip_variants.md.

    python3 -m flow.ipvariants                       # validate every entry that declares variants (exit 1 on errors)
    python3 -m flow.ipvariants fir                   # one entry: variants ranked, with predicted and measured costs
    python3 -m flow.ipvariants fir --params TAPS=32,FOLD=8 --clock-ns 5 --budget dsp=4,bram_tiles=2
    python3 -m flow.ipvariants --search fir filter   # library search by whole words in names and summaries

Read API (no Vivado, no simulator; plain Python and PyYAML):

    entries_with_variants() -> list[str]
    search(text) -> list[dict]                                  # library search: look here before writing new RTL
    variants(block) -> dict[str, dict]                          # the ip.yaml `variants:` block, as written
    check_point(block, variant, params) -> list[str]            # why a parameter point is outside the space ([] = fine)
    predict(block, variant, params) -> dict                     # latency, ii and `uses` at a point (ValueError outside)
    measured(block, part=None) -> list[dict]                    # rows of ip_lib/<block>/char/<part>.json
    variant_costs(block, params=None, part=None, clock_ns=None) -> list[dict]   # one row per variant: the two above
    choose(block, params=None, part=None, budget=None, clock_ns=None, need_ii=None, objective="area") -> list[dict]
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IP = ROOT / "ip_lib"
SCHEMA = "ipchar/1"
DEFAULT_PART = "xc7a100tcsg324-1"
TOOL = "Vivado 2026.1"                                               # every measured row must come from this release
COST_KEYS = ("lut", "ff", "lutram", "srl", "bram_tiles", "ramb36", "ramb18", "dsp")
RESOURCE_KEYS = ("lut", "ff", "lutram", "bram_tiles", "dsp")       # what `uses` and a budget may name
VARIANT_KEYS = {"summary", "uses", "latency", "ii", "when", "params", "requires", "rtl", "fmax_hint", "notes"}
ROW_KEYS = {"variant", "params", "status", *COST_KEYS, "wns_ns", "fmax_mhz", "power_w", "latency", "ii"}


# ---- expressions ---------------------------------------------------------------------------------------------------
_FUNCS = {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max,
          "clog2": lambda n: max(0, math.ceil(math.log2(n))) if n > 0 else 0, "log2": math.log2}
_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call, ast.Add, ast.Sub,
          ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.IfExp, ast.Compare, ast.Eq,
          ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.BoolOp, ast.And, ast.Or, ast.Not)


def evaluate(expr, params: dict):
    """An integer-valued expression over the entry's parameters: + - * / // % **, ceil, floor, min, max, clog2, log2,
    comparisons, and/or/not and `a if c else b`. A number is returned unchanged. Anything else is refused: the text is
    parsed and checked, never run as code."""
    if isinstance(expr, (int, float)):
        return expr
    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as ex:
        raise ValueError(f"expression {expr!r} does not parse: {ex.msg}") from None
    for n in ast.walk(tree):
        if not isinstance(n, _NODES):
            raise ValueError(f"expression {expr!r}: {type(n).__name__} is not allowed "
                             "(use arithmetic, comparisons and the functions " + ", ".join(sorted(_FUNCS)) + ")")
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in _FUNCS):
            raise ValueError(f"expression {expr!r}: only {', '.join(sorted(_FUNCS))} may be called")
        if isinstance(n, ast.Name) and n.id not in _FUNCS and n.id not in params:
            raise ValueError(f"expression {expr!r}: unknown name {n.id} (use the entry's numeric parameters "
                             f"{', '.join(sorted(params))} or the functions {', '.join(sorted(_FUNCS))})")
    v = eval(compile(tree, "<ip.yaml>", "eval"), {"__builtins__": {}}, {**_FUNCS, **params})   # noqa: S307 (checked above)
    return int(v) if isinstance(v, float) and v.is_integer() else v


# ---- reading entries ------------------------------------------------------------------------------------------------
def _yaml(block: str) -> dict:
    f = IP / block / "ip.yaml"
    if not f.exists():
        raise ValueError(f"no library entry {block!r}; entries: {', '.join(entries())}")
    return yaml.safe_load(f.read_text())


def entries() -> list[str]:
    return sorted(p.parent.name for p in IP.glob("*/ip.yaml"))


def entries_with_variants() -> list[str]:
    return [b for b in entries() if _yaml(b).get("variants")]


def variants(block: str) -> dict:
    return _yaml(block).get("variants") or {}


def variant_param(block: str) -> str | None:
    return _yaml(block).get("variant_param")


def defaults(block: str) -> dict:
    return {k: s["default"] for k, s in (_yaml(block).get("parameters") or {}).items()}


def point(block: str, params: dict | None = None, variant: str | None = None) -> dict:
    """The full parameter point: defaults, then `params`, then the variant's own fixed parameters."""
    y = _yaml(block)
    p = {**defaults(block), **(params or {})}
    if variant:
        vp = y.get("variant_param")
        if vp:
            p[vp] = variant
        p.update((y["variants"][variant].get("params") or {}))
    return p


def _numeric(p: dict) -> dict:
    return {k: x for k, x in p.items() if isinstance(x, (int, float)) and not isinstance(x, bool)}


def check_point(block: str, variant: str, params: dict | None = None) -> list[str]:
    """Why `params` is outside the entry's space for this variant: unknown names, values outside a parameter's range
    or set, and the entry's `constraints` and the variant's `requires` (expressions that must hold). The RTL refuses
    the same points at elaboration, so a planner must never be offered one. Empty list: the point is fine."""
    y = _yaml(block)
    pars = y.get("parameters") or {}
    why = []
    if variant not in (y.get("variants") or {}):
        return [f"{block} has no variant {variant!r} (variants: {', '.join(y.get('variants') or {})})"]
    unknown = sorted(set(params or {}) - set(pars))
    if unknown:
        why.append(f"unknown parameter{'s' if len(unknown) > 1 else ''} {', '.join(unknown)} "
                   f"(declared: {', '.join(pars)})")
    p = point(block, {k: v for k, v in (params or {}).items() if k in pars}, variant)
    for k, s in pars.items():
        v = p.get(k)
        if "range" in s and not (isinstance(v, (int, float)) and s["range"][0] <= v <= s["range"][1]):
            why.append(f"{k}={v} outside {s['range'][0]}..{s['range'][1]}")
        if "set" in s and v not in s["set"]:
            why.append(f"{k}={v} not one of {', '.join(map(str, s['set']))}")
    if why:
        return why
    num = _numeric(p)
    for c in list(y.get("constraints") or []) + list(y["variants"][variant].get("requires") or []):
        try:
            if not evaluate(c, num):
                why.append(f"constraint {c} does not hold")
        except ValueError as ex:
            why.append(f"constraint {c} cannot be checked: {ex}")
    return why


def predict(block: str, variant: str, params: dict | None = None) -> dict:
    """Latency, initiation interval and predicted resource use of one variant at a parameter point, from ip.yaml.
    Raises ValueError when the point is outside the entry's space (see check_point)."""
    why = check_point(block, variant, params)
    if why:
        raise ValueError(f"{block}/{variant} at {params or 'defaults'}: " + "; ".join(why))
    v = variants(block)[variant]
    full = point(block, params, variant)
    p = _numeric(full)
    out = {"variant": variant, "params": full}
    for k in ("latency", "ii"):
        if k in v:
            out[k] = evaluate(v[k], p)
    out["uses"] = {k: evaluate(e, p) for k, e in (v.get("uses") or {}).items()}
    return out


def char_file(block: str, part: str | None = None) -> Path:
    return IP / block / "char" / f"{(part or DEFAULT_PART)}.json"


def measured(block: str, part: str | None = None) -> list[dict]:
    """The characterisation rows for a part (empty if the entry has not been characterised on it)."""
    f = char_file(block, part)
    if not f.exists():
        return []
    d = json.loads(f.read_text())
    return [dict(r, part=d["part"], clock_ns=d["clock_ns"], tool=d["tool"]) for r in d["results"]]


def _distance(a: dict, b: dict) -> float:
    """How far two parameter points are apart (sum of log ratios over shared numeric keys)."""
    s = 0.0
    for k in set(a) & set(b):
        x, y = a[k], b[k]
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x > 0 and y > 0:
            s += abs(math.log(x / y))
        elif x != y:
            s += 10.0
    return s


def variant_costs(block: str, params: dict | None = None, part: str | None = None, clock_ns: float | None = None) -> list[dict]:
    """One row per variant at a parameter point.

    - `valid` and `reasons`: whether the point is inside the variant's space (if not, `predicted` is None).
    - `predicted`: the ip.yaml prediction at this exact point (latency, ii, `uses`).
    - `measured`: the nearest characterised row, with `exact` True only when it was measured at this very point. A
      non-exact row is context only: `cost` never takes a value from it.
    - `cost`: what is known at this point: the predicted `uses`, overlaid with the measured values when exact.
    - with clock_ns, `meets_clock` (True/False) only when the Fmax estimate was measured at this point, else None."""
    rows = measured(block, part)
    vp = variant_param(block)
    out = []
    for name, spec in variants(block).items():
        why = check_point(block, name, params)
        row = {"variant": name, "summary": spec.get("summary", ""), "when": spec.get("when", ""),
               "valid": not why, "reasons": why, "predicted": None, "measured": None, "cost": {}}
        if not why:
            pr = predict(block, name, params)
            row["predicted"] = pr
            row["cost"] = dict(pr["uses"])
            want = {k: v for k, v in pr["params"].items() if k != vp}
            mine = [r for r in rows if r["variant"] == name and r.get("status", "ok") == "ok"]
            best = min(mine, key=lambda r: _distance(r["params"], want), default=None)
            if best:
                m = {k: best.get(k) for k in (*COST_KEYS, "wns_ns", "fmax_mhz", "power_w", "latency", "ii", "params")}
                m["exact"] = best["params"] == want
                m["part"], m["clock_ns"], m["tool"] = best["part"], best["clock_ns"], best["tool"]
                row["measured"] = m
                if m["exact"]:
                    row["cost"].update({k: m[k] for k in (*RESOURCE_KEYS, "fmax_mhz") if m.get(k) is not None})
            if clock_ns:
                f = row["cost"].get("fmax_mhz")
                row["meets_clock"] = None if f is None else f >= 1000.0 / clock_ns
        out.append(row)
    return out


def choose(block: str, params: dict | None = None, part: str | None = None, budget: dict | None = None,
           clock_ns: float | None = None, need_ii: int | None = None, objective: str = "area") -> list[dict]:
    """Rank the variants for a plan at one parameter point. Each row gets `fits` and `reasons`.

    A variant fits only when every check can be made at this point:
      - the point is inside its space (ranges, sets, constraints, the variant's `requires`);
      - each budget key is known at this point (predicted by ip.yaml, or measured at exactly this point) and within
        the budget; a key known only from a different measured point is a reason, not a pass;
      - with clock_ns, the Fmax estimate was measured at this point and reaches the clock;
      - with need_ii, the predicted II is at most need_ii.
    Fitting rows come first, ordered by the objective:
      area        fewest DSP, then block RAM tiles, then LUTs (unknown counts sort last)
      fabric      fewest LUTs, then FFs (save general logic; spend DSP and block RAM)
      throughput  lowest II, then highest Fmax
      fmax        highest Fmax estimate
    Every row carries `note` when the part has no characterisation at all: the ranking then rests on predictions."""
    keys = {
        "area": lambda c, pr: (c.get("dsp", math.inf), c.get("bram_tiles", math.inf), c.get("lut", math.inf)),
        "fabric": lambda c, pr: (c.get("lut", math.inf), c.get("ff", math.inf)),
        "throughput": lambda c, pr: ((pr or {}).get("ii", math.inf), -c.get("fmax_mhz", 0)),
        "fmax": lambda c, pr: (-c.get("fmax_mhz", 0),),
    }
    if objective not in keys:
        raise ValueError(f"objective must be one of {', '.join(sorted(keys))}, not {objective!r}")
    for k in budget or {}:
        if k not in RESOURCE_KEYS:
            raise ValueError(f"budget key {k!r} is not one of {', '.join(RESOURCE_KEYS)}")
    rows = variant_costs(block, params, part, clock_ns)
    no_data = not measured(block, part)
    for r in rows:
        why = list(r["reasons"])
        if r["valid"]:
            c, pr = r["cost"], r["predicted"]
            for k, cap in (budget or {}).items():
                if k in c:
                    if c[k] > cap:
                        why.append(f"{k} {c[k]} > budget {cap}")
                else:
                    why.append(f"{k} is not known at this point (not predicted, not measured here)")
            if clock_ns:
                if r.get("meets_clock") is None:
                    why.append(f"Fmax not measured at this point on {part or DEFAULT_PART}")
                elif not r["meets_clock"]:
                    why.append(f"estimated Fmax {c['fmax_mhz']} MHz < {round(1000.0 / clock_ns, 1)} MHz")
            if need_ii is not None and pr.get("ii") is not None and pr["ii"] > need_ii:
                why.append(f"II {pr['ii']} > needed {need_ii}")
        r["fits"], r["reasons"] = not why, why
        if no_data:
            r["note"] = f"{block} has no characterisation on {part or DEFAULT_PART}: ranked on ip.yaml predictions only"
    return sorted(rows, key=lambda r: (not r["fits"], not r["valid"], keys[objective](r["cost"], r["predicted"])))


def search(text: str) -> list[dict]:
    """Library search: entries whose name, summary or variant summaries contain every word of `text` as a whole word
    (so "fir" does not match "first")."""
    words = [w.lower() for w in re.findall(r"\w+", text)]
    out = []
    for b in entries():
        y = _yaml(b)
        hay = " ".join([b, y.get("summary", ""), *(f"{k} {v.get('summary', '')}" for k, v in (y.get("variants") or {}).items())]).lower()
        toks = set(re.findall(r"\w+", hay))
        if all(w in toks for w in words):
            out.append({"block": b, "version": y.get("version"), "summary": y.get("summary"),
                        "variants": list((y.get("variants") or {}).keys())})
    return out


# ---- validation -----------------------------------------------------------------------------------------------------
def _rtl_text(block: str, y: dict) -> str:
    return "\n".join((IP / block / f).read_text() for f in y.get("rtl", []) if (IP / block / f).exists())


def _test_text(y: dict) -> str:
    return "\n".join((ROOT / t).read_text() for t in (y.get("evidence") or {}).get("tests", []) if (ROOT / t).exists())


def validate(block: str) -> list[str]:
    """Check an entry's variants block against the schema (docs/ip_variants.md) and its characterisation file.
    Reports problems as text; malformed input is a problem, never a traceback."""
    try:
        return _validate(block)
    except Exception as ex:      # noqa: BLE001 (a malformed file must be reported, not crash the checker)
        return [f"{block}: malformed ({type(ex).__name__}: {ex})"]


def _validate(block: str) -> list[str]:
    y = _yaml(block)
    v = y.get("variants")
    if not v:
        return []
    if not isinstance(v, dict):
        return [f"{block}: variants is not a mapping"]
    e = []
    pars = y.get("parameters") or {}
    vp = y.get("variant_param")
    if vp:
        spec = pars.get(vp)
        if not spec:
            e.append(f"{block}: variant_param {vp} is not a declared parameter")
        else:
            if set(spec.get("set", [])) != set(v):
                e.append(f"{block}: {vp} set {spec.get('set')} != variants {sorted(v)}")
            if spec.get("default") not in v:
                e.append(f"{block}: {vp} default {spec.get('default')} is not a variant")
    elif len(v) > 1:
        e.append(f"{block}: several variants but no variant_param")
    rtl, tests = _rtl_text(block, y), _test_text(y)
    tested = set()
    for pt in y.get("sweep_tested") or []:
        sel = pt.get(vp, (pars.get(vp) or {}).get("default")) if vp else None
        tested |= set(sel if isinstance(sel, list) else [sel])
    good = []
    for name, spec in v.items():
        if not isinstance(spec, dict):
            e.append(f"{block}/{name}: not a mapping")
            continue
        extra = set(spec) - VARIANT_KEYS
        if extra:
            e.append(f"{block}/{name}: unknown keys {sorted(extra)}")
        for k in ("summary", "latency", "ii", "uses", "when"):
            if k not in spec:
                e.append(f"{block}/{name}: missing {k}")
        for k in (spec.get("uses") or {}):
            if k not in RESOURCE_KEYS:
                e.append(f"{block}/{name}: uses.{k} is not one of {RESOURCE_KEYS}")
        # every variant has its own RTL branch (the selecting literal appears in the RTL, which is also what its
        # elaboration guard accepts) and is run by the tests (a sweep_tested point, and named in a test file unless
        # it is the default)
        if vp and f'"{name}"' not in rtl:
            e.append(f"{block}/{name}: no RTL branch (the literal \"{name}\" does not appear in the entry's RTL)")
        if vp and name not in tested:
            e.append(f"{block}/{name}: no sweep_tested point runs this variant")
        if vp and name != (pars.get(vp) or {}).get("default") and not re.search(rf"\b{re.escape(name)}\b", tests):
            e.append(f"{block}/{name}: not named in any test file of evidence.tests")
        ok = True
        for pt in [{}] + list(y.get("sweep_tested") or []) + list((y.get("characterisation") or {}).get("points") or []):
            sel = pt.get(vp) if vp else None
            if sel is not None and name not in (sel if isinstance(sel, list) else [sel]):
                continue
            try:
                predict(block, name, {k: x for k, x in pt.items() if k != vp})
            except Exception as ex:      # noqa: BLE001 (report every bad expression or point)
                e.append(f"{block}/{name}: at {pt or 'defaults'}: {ex}")
                ok = False
                break
        if ok:
            good.append(name)
    ch = y.get("characterisation")
    if not ch:
        e.append(f"{block}: variants but no characterisation block")
        return e
    for k in ("part", "clock_ns", "points"):
        if k not in ch:
            e.append(f"{block}: characterisation.{k} missing")
    f = char_file(block, ch.get("part"))
    if not f.exists():
        e.append(f"{block}: no characterisation file {f.relative_to(ROOT)} (python3 -m flow.ipchar {block})")
        return e
    d = json.loads(f.read_text())
    rel = f.relative_to(ROOT)
    if d.get("schema") != SCHEMA:
        e.append(f"{rel}: schema {d.get('schema')} != {SCHEMA}")
    if not str(d.get("tool", "")).startswith(TOOL):
        e.append(f"{rel}: tool {d.get('tool')!r} is not {TOOL}")
    for r in d.get("results", []):
        if set(r) - ROW_KEYS:
            e.append(f"{rel}: row keys {sorted(set(r) - ROW_KEYS)} not in the schema")
        if r.get("variant") not in v:
            e.append(f"{rel}: row for unknown variant {r.get('variant')}")
            continue
        if r.get("status") != "ok":
            e.append(f"{rel}: {r['variant']} at {r.get('params')}: status {r.get('status')!r}")
            continue
        if r["variant"] not in good:
            continue
        try:
            pr = predict(block, r["variant"], r["params"])
        except ValueError as ex:
            e.append(f"{rel}: {r['variant']} row outside the space: {ex}")
            continue
        for k in ("latency", "ii"):
            if r.get(k) is not None and pr.get(k) != r[k]:
                e.append(f"{rel}: {r['variant']} {k} {r[k]} != ip.yaml {pr.get(k)}")
        for k in ("dsp", "bram_tiles"):            # the declared hard resources are the ones synthesis used
            if k in pr["uses"] and r.get(k) != pr["uses"][k]:
                e.append(f"{rel}: {r['variant']} at {r['params']}: measured {k} {r.get(k)} != declared {pr['uses'][k]}")
    got = {(r["variant"], json.dumps(r["params"], sort_keys=True)) for r in d.get("results", [])}
    for name in v:
        for pt in ch.get("points", []):
            if (name, json.dumps({k: x for k, x in point(block, pt, None).items() if k != vp}, sort_keys=True)) not in got:
                e.append(f"{rel}: no row for {name} at {pt}")
    return e


def _kv(s: str) -> dict:
    out = {}
    for item in filter(None, (s or "").split(",")):
        if "=" not in item:
            raise SystemExit(f"ipvariants: {item!r} is not NAME=VALUE")
        k, x = item.split("=", 1)
        try:
            out[k.strip()] = float(x) if "." in x else int(x)
        except ValueError:
            out[k.strip()] = x.strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m flow.ipvariants",
        description="Validate the IP library's implementation variants, or rank one entry's variants for a plan. "
                    "Example: python3 -m flow.ipvariants fir --params TAPS=32,FOLD=8 --budget dsp=0 --objective fabric")
    ap.add_argument("block", nargs="?", help="library entry to rank (omit to validate every entry with variants)")
    ap.add_argument("--params", default="", help="parameter point, e.g. TAPS=32,FOLD=8 (other parameters keep defaults)")
    ap.add_argument("--part", default=None, help=f"device part whose measurements to use (default {DEFAULT_PART})")
    ap.add_argument("--clock-ns", type=float, default=None,
                    help="target clock period in ns; a variant fits only if its Fmax estimate, measured at this point, reaches it")
    ap.add_argument("--budget", default="", help="what the plan has left for this block, e.g. dsp=0,bram_tiles=2 "
                                                  f"(keys: {', '.join(RESOURCE_KEYS)})")
    ap.add_argument("--need-ii", type=int, default=None, help="largest acceptable initiation interval in clocks")
    ap.add_argument("--objective", default="area", choices=["area", "fabric", "throughput", "fmax"],
                    help="how to order the fitting variants (default area)")
    ap.add_argument("--search", nargs="*", default=None, metavar="WORD",
                    help="list entries whose names or summaries contain every word")
    a = ap.parse_args(argv)
    try:
        if a.search is not None:
            print(json.dumps(search(" ".join(a.search)), indent=1))
            return 0
        if a.block:
            print(json.dumps(choose(a.block, _kv(a.params), a.part, _kv(a.budget), a.clock_ns, a.need_ii, a.objective),
                             indent=1))
            return 0
    except ValueError as ex:
        print(f"ipvariants: {ex}", file=sys.stderr)
        return 2
    errs = [x for b in entries_with_variants() for x in validate(b)]
    for x in errs:
        print(x)
    print(f"{len(entries_with_variants())} entries with variants, {len(errs)} problems")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
