#!/usr/bin/env python3
"""Implementation variants of the ip_lib entries (brief 63A): the `variants:` schema, its validation, and the read API
the architecture stage (brief 62A) uses to choose a variant. The data contract is docs/ip_variants.md.

    python3 -m flow.ipvariants                       # validate every entry that declares variants (exit 1 on errors)
    python3 -m flow.ipvariants fir                   # one entry: variants, predictions and measured costs as JSON
    python3 -m flow.ipvariants fir --params TAPS=32,FOLD=8 --clock-ns 5 --budget dsp=4,bram_tiles=2
    python3 -m flow.ipvariants --search filter       # library search by name, summary and variant text

Read API (no Vivado, no simulator; plain Python and PyYAML):

    entries_with_variants() -> list[str]
    search(text) -> list[dict]                                  # library search, first step of the architecture stage
    variants(block) -> dict[str, dict]                          # the ip.yaml `variants:` block, as written
    predict(block, variant, params) -> dict                     # latency, ii and `uses` evaluated at a parameter point
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
COST_KEYS = ("lut", "ff", "lutram", "srl", "bram_tiles", "ramb36", "ramb18", "dsp")
RESOURCE_KEYS = ("lut", "ff", "lutram", "bram_tiles", "dsp")       # what `uses` and a budget may name
VARIANT_KEYS = {"summary", "uses", "latency", "ii", "when", "params", "rtl", "fmax_hint", "notes"}
ROW_KEYS = {"variant", "params", "status", *COST_KEYS, "wns_ns", "fmax_mhz", "power_w", "latency", "ii"}


# ---- expressions ---------------------------------------------------------------------------------------------------
_FUNCS = {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max,
          "clog2": lambda n: max(0, math.ceil(math.log2(n))) if n > 0 else 0, "log2": math.log2}
_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call, ast.Add, ast.Sub,
          ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.IfExp, ast.Compare, ast.Eq,
          ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def evaluate(expr, params: dict):
    """An integer-valued expression over the entry's parameters: + - * / // % **, ceil, floor, min, max, clog2, log2,
    comparisons and `a if c else b`. A number is returned unchanged. Anything else is refused (no eval of code)."""
    if isinstance(expr, (int, float)):
        return expr
    tree = ast.parse(str(expr), mode="eval")
    for n in ast.walk(tree):
        if not isinstance(n, _NODES):
            raise ValueError(f"expression {expr!r}: {type(n).__name__} not allowed")
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in _FUNCS):
            raise ValueError(f"expression {expr!r}: only {sorted(_FUNCS)} may be called")
        if isinstance(n, ast.Name) and n.id not in _FUNCS and n.id not in params:
            raise ValueError(f"expression {expr!r}: unknown name {n.id}")
    v = eval(compile(tree, "<ip.yaml>", "eval"), {"__builtins__": {}}, {**_FUNCS, **params})   # noqa: S307 (checked above)
    return int(v) if isinstance(v, float) and v.is_integer() else v


# ---- reading entries ------------------------------------------------------------------------------------------------
def _yaml(block: str) -> dict:
    return yaml.safe_load((IP / block / "ip.yaml").read_text())


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


def predict(block: str, variant: str, params: dict | None = None) -> dict:
    """Latency, initiation interval and predicted resource use of one variant at a parameter point, from ip.yaml."""
    v = variants(block)[variant]
    p = {k: x for k, x in point(block, params, variant).items() if isinstance(x, (int, float))}
    out = {"variant": variant, "params": point(block, params, variant)}
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
    """One row per variant at a parameter point: the ip.yaml prediction and the nearest measured characterisation row.
    `measured.exact` is True only when the row was measured at this very point; otherwise it is the nearest point and
    the planner should treat the numbers as an estimate (and `predicted` still holds the exact latency and II).
    With clock_ns, `meets_clock` says whether the measured Fmax reaches that clock."""
    rows = measured(block, part)
    out = []
    for name in variants(block):
        pr = predict(block, name, params)
        mine = [r for r in rows if r["variant"] == name and r.get("status", "ok") == "ok"]
        want = {k: v for k, v in pr["params"].items() if k != variant_param(block)}
        best = min(mine, key=lambda r: _distance(r["params"], want), default=None)
        row = {"variant": name, "summary": variants(block)[name].get("summary", ""),
               "when": variants(block)[name].get("when", ""), "predicted": pr, "measured": None}
        if best:
            m = {k: best.get(k) for k in (*COST_KEYS, "wns_ns", "fmax_mhz", "power_w", "latency", "ii", "params")}
            m["exact"] = _distance(best["params"], want) == 0
            m["part"], m["clock_ns"], m["tool"] = best["part"], best["clock_ns"], best["tool"]
            row["measured"] = m
            if clock_ns and best.get("fmax_mhz"):
                row["meets_clock"] = best["fmax_mhz"] >= 1000.0 / clock_ns
        out.append(row)
    return out


def choose(block: str, params: dict | None = None, part: str | None = None, budget: dict | None = None,
           clock_ns: float | None = None, need_ii: int | None = None, objective: str = "area") -> list[dict]:
    """Rank the variants for a plan. Each row gets `fits` and `reasons` (why it fails: over a budget, misses the
    clock, too slow a rate). Fitting rows come first, ordered by the objective:
      area        fewest DSP, then block RAM tiles, then LUTs (hard resources first: brief 62's rule is to use a free
                  hard resource before fabric, so pass a budget that leaves out what is already spoken for)
      fabric      fewest LUTs, then FFs (save general logic; spend DSP and block RAM)
      throughput  lowest II, then highest Fmax
      fmax        highest measured Fmax
    The caller decides; this only orders what the data says."""
    rows = variant_costs(block, params, part, clock_ns)
    for r in rows:
        why = []
        m, pr = r["measured"] or {}, r["predicted"]
        for k, cap in (budget or {}).items():
            have = m.get(k) if m.get(k) is not None else pr["uses"].get(k)
            if have is not None and have > cap:
                why.append(f"{k} {have} > budget {cap}")
        if clock_ns and r.get("meets_clock") is False:
            why.append(f"measured Fmax {m.get('fmax_mhz')} MHz < {round(1000.0 / clock_ns, 1)} MHz")
        if need_ii is not None and pr.get("ii") is not None and pr["ii"] > need_ii:
            why.append(f"II {pr['ii']} > needed {need_ii}")
        if not m:
            why.append("not characterised on this part")
        r["fits"], r["reasons"] = not why, why
    g = lambda r, k: (r["measured"] or {}).get(k) or 0
    keys = {
        "area": lambda r: (g(r, "dsp"), g(r, "bram_tiles"), g(r, "lut")),
        "fabric": lambda r: (g(r, "lut"), g(r, "ff")),
        "throughput": lambda r: (r["predicted"].get("ii", 1e9), -g(r, "fmax_mhz")),
        "fmax": lambda r: (-g(r, "fmax_mhz"),),
    }
    if objective not in keys:
        raise ValueError(f"objective must be one of {sorted(keys)}")
    return sorted(rows, key=lambda r: (not r["fits"], keys[objective](r)))


def search(text: str) -> list[dict]:
    """Library search: entries whose name, summary, or variant summaries contain every word of `text`."""
    words = [w.lower() for w in re.findall(r"\w+", text)]
    out = []
    for b in entries():
        y = _yaml(b)
        hay = " ".join([b, y.get("summary", ""), *(f"{k} {v.get('summary', '')}" for k, v in (y.get("variants") or {}).items())]).lower()
        if all(w in hay for w in words):
            out.append({"block": b, "version": y.get("version"), "summary": y.get("summary"),
                        "variants": list((y.get("variants") or {}).keys())})
    return out


# ---- validation -----------------------------------------------------------------------------------------------------
def validate(block: str) -> list[str]:
    """Check an entry's variants block against the schema (docs/ip_variants.md) and its characterisation file."""
    y = _yaml(block)
    v = y.get("variants")
    if not v:
        return []
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
        for pt in [{}] + list(y.get("sweep_tested") or []) + list((y.get("characterisation") or {}).get("points") or []):
            try:
                predict(block, name, {k: x for k, x in pt.items() if k != vp})
            except Exception as ex:      # noqa: BLE001 (report every bad expression)
                e.append(f"{block}/{name}: at {pt or 'defaults'}: {ex}")
                break
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
    else:
        d = json.loads(f.read_text())
        if d.get("schema") != SCHEMA:
            e.append(f"{f.relative_to(ROOT)}: schema {d.get('schema')} != {SCHEMA}")
        for r in d.get("results", []):
            if set(r) - ROW_KEYS:
                e.append(f"{f.relative_to(ROOT)}: row keys {sorted(set(r) - ROW_KEYS)} not in the schema")
            if r.get("variant") not in v:
                e.append(f"{f.relative_to(ROOT)}: row for unknown variant {r.get('variant')}")
            elif r.get("status") == "ok":
                pr = predict(block, r["variant"], r["params"])
                for k in ("latency", "ii"):
                    if r.get(k) is not None and pr.get(k) != r[k]:
                        e.append(f"{f.relative_to(ROOT)}: {r['variant']} {k} {r[k]} != ip.yaml {pr.get(k)}")
        got = {(r["variant"], json.dumps(r["params"], sort_keys=True)) for r in d.get("results", [])}
        for name in v:
            for pt in ch.get("points", []):
                if (name, json.dumps({k: x for k, x in point(block, pt, None).items() if k != vp}, sort_keys=True)) not in got:
                    e.append(f"{f.relative_to(ROOT)}: no row for {name} at {pt}")
    return e


def _kv(s: str) -> dict:
    out = {}
    for item in filter(None, (s or "").split(",")):
        k, x = item.split("=", 1)
        try:
            out[k.strip()] = float(x) if "." in x else int(x)
        except ValueError:
            out[k.strip()] = x.strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("block", nargs="?")
    ap.add_argument("--params", default="")
    ap.add_argument("--part", default=None)
    ap.add_argument("--clock-ns", type=float, default=None)
    ap.add_argument("--budget", default="")
    ap.add_argument("--need-ii", type=int, default=None)
    ap.add_argument("--objective", default="area")
    ap.add_argument("--search", default=None)
    a = ap.parse_args(argv)
    if a.search is not None:
        print(json.dumps(search(a.search), indent=1))
        return 0
    if a.block:
        print(json.dumps(choose(a.block, _kv(a.params), a.part, _kv(a.budget), a.clock_ns, a.need_ii, a.objective), indent=1))
        return 0
    errs = [x for b in entries_with_variants() for x in validate(b)]
    for x in errs:
        print(x)
    print(f"{len(entries_with_variants())} entries with variants, {len(errs)} problems")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
