#!/usr/bin/env python3
"""Turn the Vivado out-of-context records of the arithmetic library into measured surfaces (brief 160).

    python3 -m arith.tools.gen_surface [--check]

Reads arith/<fn>/verif/results/vivado_ooc_<variant>_<part>.json (written by run_vivado_ooc.py) and writes, per function,
arith/<fn>/verif/results/vivado_surface.json (every point: measured values, the wrapper's register bits, latency, the pre-stated expectation
and its verdict, the Pareto marks) and results/160_arith_vivado/{surface.json,README.md} (all functions: fronts, expectations, planning-estimate check).

Method:
  * Fmax = 1000 / (clock_ns - WNS), routed, one run at the build file's clock. Where WNS is positive the tool stopped optimising at an easy
    clock, so Fmax is a LOWER bound ("lower_bound": true).
  * Area vector for dominance = (LUT, DSP, BRAM tiles); FFs are reported but are not an axis (they are mostly the pipeline registers a variant
    is chosen for). Two fronts per group of points that solve the same problem (same function, part, and shape parameters; the knob parameters
    and the variants differ): area against Fmax, area against latency in clocks. A point is on a front when no other point of its group is
    at least as good on every axis and better on one.
  * Expectation: the spec's pre-stated primitive use as a number or range, where it gives one; met when the measured value is inside the range
    widened by 25 % (and 2 cells), else missed, with both numbers shown. Wrapper FFs (the registers on every wrapper port) are removed from
    the FF expectation.
  * Planning-estimate check: for every numeric expectation, predicted against measured, Spearman rank correlation and relative error.
    The HW_Design_Space_Agent cost model (brief 137) is a CORDIC-structure model (ArchConfig of four CORDIC families) and cannot be called on these functions.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from arith.tools import arith_common as ac  # noqa: E402

OUT = ROOT / "results" / "160_arith_vivado"
SHAPE = {"adder": ["WIDTH"], "multiplier": ["WA", "WB", "SIGNED"], "mac": ["WA", "WB", "LANES", "ACCW", "SIGNED"], "divider": ["W"], "isqrt": ["W"],
         "fxp_round": ["W_IN", "S", "W_OUT", "MODE", "SAT"], "lzc_norm": ["W"]}
FN_ORDER = ["adder", "multiplier", "mac", "divider", "fxp_round", "isqrt", "lzc_norm"]


def ceil(a, b):
    return -(-a // b)


# ---- wrapper registers ---------------------------------------------------------------------------------------------
def wrapper_bits(fn: str, build_file: str, top: str, gen: dict) -> int | None:
    cands = list((ROOT / "arith" / fn).glob(f"*/{top}.sv"))
    if not cands:
        return None
    n = 0
    for line in cands[0].read_text().splitlines():
        m = re.match(r"^\s*(input|output)\s+logic\s*(\[([^\]]+):0\])?\s*(\w+)", line)
        if not m or m.group(4) == "clk":
            continue
        if not m.group(2):
            n += 1
            continue
        e = m.group(3).replace("$clog2", "_clog2")
        try:
            n += eval(e, {"_clog2": lambda x: max(1, (int(x) - 1).bit_length())}, dict(gen)) + 1
        except Exception:      # noqa: BLE001
            return None
    return n


# ---- latency -------------------------------------------------------------------------------------------------------
def latency(fn: str, variant: str, gen: dict) -> int | None:
    try:
        if fn in ("adder", "multiplier", "mac"):
            return ac.latency_of(ac.load_spec(fn), variant, gen)
        import importlib
        m = importlib.import_module(f"arith.{fn}.model")
        v = gen["VARIANT"]
        if fn == "fxp_round":
            return m.latency(v)
        return m.latency(v, gen["W"], gen.get("PIPE", 1))
    except Exception:       # noqa: BLE001
        return None


# ---- expectations --------------------------------------------------------------------------------------------------
def cells(a7: bool, bits: int) -> int:
    return ceil(bits, 4 if a7 else 8)


def expect(fn: str, variant: str, g: dict, a7: bool, r: dict, wrap: int | None, given: dict | None) -> list[dict]:
    """The numeric parts of the spec's pre-stated primitive use for this point: [{what, lo, hi, measured, verdict, text}]."""
    out = []

    def add(what, lo, hi, meas, text):
        ok = meas is not None and (lo * 0.75 - 2) <= meas <= (hi * 1.25 + 2)
        out.append({"what": what, "expected_lo": lo, "expected_hi": hi, "measured": meas, "verdict": "met" if ok else "missed", "text": text})

    carry, lut, ff, dsp = r["carry"], r["lut"], r["ff"], r["dsp"]
    cff = None if wrap is None else max(ff - wrap, 0)       # FFs not in the wrapper's own port registers
    if given:                                                # 139b: expected_primitives dict
        c = given.get("carry4")
        if c is not None:
            add("carry cells", c if a7 else ceil(c, 2), c if a7 else ceil(c, 2), carry, "carry4 (a7) / about half as many CARRY8 (k26)")
        add("DSP", given.get("dsp48", 0), given.get("dsp48", 0), dsp, "dsp48")
        add("BRAM tiles", given.get("bram", 0), given.get("bram", 0), r["bram_tiles"], "bram")
        if given.get("ff") is not None:
            add("FF beyond the wrapper", given["ff"], given["ff"], cff, "ff (the build files' number excludes the wrapper's port registers)")
        return out
    if fn == "adder":
        w = g["WIDTH"]
        if variant == "ripple":
            add("carry cells", cells(a7, w), cells(a7, w), carry, "ceil(WIDTH/4 or 8) in one chain")
            add("LUT", w, w, lut, "about WIDTH")
            add("FF beyond the wrapper", 0, 0, cff, "0 FF")
        elif variant == "carry_select":
            b = g["BLOCK"]; nb = ceil(w, b)
            add("carry cells", (1 + 2 * (nb - 1)) * cells(a7, b), (1 + 2 * (nb - 1)) * cells(a7, b), carry, "(1 + 2*(NB-1)) chains of ceil(BLOCK/4 or 8)")
            add("LUT", 2 * w - b + nb - 1, 2 * w - b + nb - 1, lut, "about 2*WIDTH - BLOCK + NB - 1")
            add("FF beyond the wrapper", 0, 0, cff, "0 FF")
        else:
            s = g["STAGES"]
            add("FF beyond the wrapper", w * (s - 1) * 2 + s, w * (s - 1) * 2 + s, cff, "about 2*WIDTH*(STAGES-1) + STAGES")
            add("carry cells", s * cells(a7, ceil(w, s)), s * cells(a7, ceil(w, s)), carry, "STAGES chains of about WIDTH/STAGES bits")
        add("DSP", 0, 0, dsp, "0 DSP")
    elif fn == "multiplier":
        wa, wb, sg = g["WA"], g["WB"], g["SIGNED"]
        if variant == "dsp":
            ma, mb = (25, 18) if a7 else (27, 18)
            n = 1 if (wa <= ma - (0 if sg else 1) and wb <= mb - (0 if sg else 1)) else ceil(wa + 1, ma) * ceil(wb + 1, mb)
            add("DSP", n, n, dsp, f"tiling of a {ma}x{mb} DSP")
        else:
            add("DSP", 0, 0, dsp, "0 DSP")
            if variant == "lut_array":
                add("LUT", wa * wb // 2, wa * wb, lut, "about WA*WB/2 to WA*WB")
            else:
                npp = ceil(wb + 1 - sg, 2)
                add("LUT", npp * wa, npp * (wa + 2), lut, "about one LUT per partial-product bit, NP*(WA..WA+2)")
    elif fn == "mac":
        lanes, wa, wb, accw = g["LANES"], g["WA"], g["WB"], g["ACCW"]
        if variant in ("dsp", "dsp_cascade"):
            add("DSP", lanes, lanes if variant == "dsp" else lanes + 1, dsp, "LANES DSP slices")
        else:
            add("DSP", 0, 0, dsp, "0 DSP")
            add("LUT", lanes * wa * wb // 2, lanes * wa * wb, lut, "about LANES*WA*WB")
    return out


# ---- pareto --------------------------------------------------------------------------------------------------------
def dominated(a: tuple, b: tuple) -> bool:
    """True when b dominates a (tuples of values to minimise)."""
    return all(x <= y for x, y in zip(b, a)) and any(x < y for x, y in zip(b, a))


def mark_fronts(rows: list[dict]) -> None:
    groups: dict = {}
    for r in rows:
        if r["status"] == "ok":
            groups.setdefault((r["part_key"], tuple(sorted(r["shape"].items()))), []).append(r)
    for rs in groups.values():
        for r in rs:
            r["group_size"] = len(rs)
        for key, third in (("front_fmax", lambda r: -r["fmax_mhz"]), ("front_latency", lambda r: r["latency_clocks"])):
            cand = [r for r in rs if r["fmax_mhz"] is not None and r["latency_clocks"] is not None]
            vec = lambda r: (r["lut"], r["dsp"], r["bram_tiles"], third(r))
            for r in rs:
                r[key] = (len(cand) >= 2 and r in cand and not any(dominated(vec(r), vec(o)) for o in cand if o is not r))


def spearman(a: list[float], b: list[float]) -> float | None:
    def ranks(x):
        s = sorted(range(len(x)), key=lambda i: x[i]); rk = [0.0] * len(x); i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and x[s[j + 1]] == x[s[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[s[k]] = (i + j) / 2 + 1
            i = j + 1
        return rk
    if len(a) < 3 or len(set(a)) < 2 or len(set(b)) < 2:
        return None
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return round(num / den, 3) if den else None


# ---- build ---------------------------------------------------------------------------------------------------------
def load() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for fn in FN_ORDER:
        rows = []
        for f in sorted((ROOT / "arith" / fn / "verif" / "results").glob("vivado_ooc_*.json")):
            d = json.loads(f.read_text())
            a7 = d["part_key"] == "a7"
            for p in d["points"]:
                g = p["generics"]
                shape = {k: g[k] for k in SHAPE[fn] if k in g}
                r = {"function": fn, "variant": d["variant"], "part_key": d["part_key"], "part": d["part"], "generics": g, "shape": shape,
                     "clock_ns": d["clock_ns"], "tool": d["tool"], "date": d["date"], "status": p["status"], "record": f.name}
                if p["status"] == "ok":
                    r.update({k: p[k] for k in ("lut", "ff", "carry", "carry4", "carry8", "dsp", "bram_tiles", "srl", "wns_ns", "whs_ns", "logic_levels", "runtime_s")})
                    r["power_total_w"] = p["power_w"]["total"]
                    r["fmax_mhz"] = p["fmax_mhz"]
                    r["lower_bound"] = bool(p["wns_ns"] is not None and p["wns_ns"] > 0)
                    r["latency_clocks"] = latency(fn, d["variant"], g)
                    wrap = wrapper_bits(fn, d["build_file"], d["top"], g)
                    r["wrapper_register_bits"] = wrap
                    ex = expect(fn, d["variant"], g, a7, r, wrap, p.get("expected"))
                    r["expectations"] = ex
                    r["expectation"] = ("none stated" if not ex else "met" if all(e["verdict"] == "met" for e in ex) else "missed")
                else:
                    r["error"] = p["status"]
                rows.append(r)
        mark_fronts(rows)
        out[fn] = rows
    return out


def planning_check(data: dict) -> list[dict]:
    res = []
    for fn, rows in data.items():
        for part in ("a7", "k26"):
            for what, key in (("LUT", "lut"), ("carry cells", "carry"), ("FF beyond the wrapper", "ff")):
                pr, me, errs = [], [], []
                for r in rows:
                    if r["part_key"] != part or r["status"] != "ok":
                        continue
                    for e in r["expectations"]:
                        if e["what"] == what and e["measured"] is not None:
                            mid = (e["expected_lo"] + e["expected_hi"]) / 2
                            pr.append(mid); me.append(e["measured"])
                            if me[-1] > 0:
                                errs.append(abs(mid - me[-1]) / me[-1])
                if len(pr) >= 3:
                    res.append({"function": fn, "part": part, "quantity": what, "n": len(pr), "spearman": spearman(pr, me),
                                "median_abs_rel_error": round(sorted(errs)[len(errs) // 2], 3) if errs else None,
                                "max_abs_rel_error": round(max(errs), 3) if errs else None})
    return res


def pt_name(r: dict) -> str:
    return r["variant"] + " " + ", ".join(f"{k}={v}" for k, v in r["generics"].items() if k != "VARIANT")


def readme(data: dict, pc: list[dict]) -> str:
    all_rows = [r for rows in data.values() for r in rows]
    ok = [r for r in all_rows if r["status"] == "ok"]
    tool = sorted({r["tool"] for r in ok})
    L = ["# results/160_arith_vivado: measured out-of-context Vivado results for the arithmetic library (brief 160)", "",
         "Generated by `python -m arith.tools.gen_surface` from the records `arith/<function>/verif/results/vivado_ooc_<variant>_<part>.json`, which `python -m arith.tools.run_vivado_ooc` wrote. "
         "Do not edit. Method and definitions are in the docstring of [arith/tools/gen_surface.py](../../arith/tools/gen_surface.py); the reading of the results is in the brief's report.", "",
         f"Tool: {', '.join(tool)}. Points run: {len(all_rows)}; with a routed result: {len(ok)}; failed or not run: {len(all_rows) - len(ok)}. Two parts: xc7a100tcsg324-1 (`a7`) and xck26-sfvc784-2LV-c (`k26`).", "",
         "## Points and expectations", "",
         "| Function | Part | Points | Fmax is a lower bound (WNS > 0) | Expectation met | Expectation missed | No numeric expectation |", "|---|---|---|---|---|---|---|"]
    for fn, rows in data.items():
        for part in ("a7", "k26"):
            rs = [r for r in rows if r["part_key"] == part and r["status"] == "ok"]
            if rs:
                L.append(f"| {fn} | {part} | {len(rs)} | {sum(r['lower_bound'] for r in rs)} | {sum(r['expectation'] == 'met' for r in rs)} | {sum(r['expectation'] == 'missed' for r in rs)} | {sum(r['expectation'] == 'none stated' for r in rs)} |")
    L += ["", "## Pre-stated expectations that were missed", "", "A point is missed when any numeric expectation fails (inside the stated range widened by 25 % and 2 cells counts as met).", "",
          "| Function | Part | Point | Quantity | Expected | Measured |", "|---|---|---|---|---|---|"]
    for r in ok:
        for e in r["expectations"]:
            if e["verdict"] == "missed":
                lo, hi = e["expected_lo"], e["expected_hi"]
                L.append(f"| {r['function']} | {r['part_key']} | {pt_name(r)} | {e['what']} | {lo if lo == hi else f'{lo} to {hi}'} | {e['measured']} |")
    L += ["", "## Fronts", "", "Per function, part and problem shape: the points of the group that no other point of the group beats on every axis. Area = (LUT, DSP, BRAM tiles).", ""]
    for fn, rows in data.items():
        groups: dict = {}
        for r in rows:
            if r["status"] == "ok" and r.get("group_size", 0) >= 2:
                groups.setdefault((r["part_key"], tuple(sorted(r["shape"].items()))), []).append(r)
        if not groups:
            continue
        L += [f"### {fn}", "", "| Part | Shape | Points in group | Area against Fmax front | Area against latency front |", "|---|---|---|---|---|"]
        for (part, shape), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
            ff = "; ".join(pt_name(r) for r in rs if r.get("front_fmax")) or "none"
            fl = "; ".join(pt_name(r) for r in rs if r.get("front_latency")) or "none"
            L.append(f"| {part} | {', '.join(f'{k}={v}' for k, v in shape)} | {len(rs)} | {ff} | {fl} |")
        L.append("")
    L += ["## Planning estimates against measurement", "",
          "The cost model of brief 137 (HW_Design_Space_Agent `FpgaCostModel`) is a model of four CORDIC families and takes an `ArchConfig` of that family: it cannot be called on these functions. "
          "The only predictions that exist for them are the spec's own expected primitive use (written before the runs). Predicted (middle of the stated range) against measured, per function and part; "
          "Spearman is the rank correlation, errors are |predicted - measured| / measured.", "",
          "| Function | Part | Quantity | n | Spearman | Median error | Max error |", "|---|---|---|---|---|---|---|"]
    L += [f"| {c['function']} | {c['part']} | {c['quantity']} | {c['n']} | {c['spearman']} | {c['median_abs_rel_error']} | {c['max_abs_rel_error']} |" for c in pc]
    L.append("")
    return "\n".join(L)


def ooc_point_count(fn: str) -> int:
    """Points of every build.yaml of a function, counting each part (139a: one file, two parts; 139b: one file per part)."""
    n = 0
    for f in (ROOT / "arith" / fn / "build").glob("**/build.yaml"):
        y = yaml.safe_load(f.read_text())
        n += len(y["points"]) * (len(y["ooc"]["parts"]) if "ooc" in y else 1)
    return n


def ooc_requirement(fn: str, pre: str) -> tuple[dict, dict]:
    """The performance requirement and its timing item for a function's testplan (brief 160): every prepared point has a routed Vivado result."""
    base, n = f"arith/{fn}", ooc_point_count(fn)
    req = {"id": f"{pre}-P-OOC", "kind": "performance", "title": "Every prepared point places and routes out of context on Artix-7 and K26",
           "text": f"Each point of the build files of {fn} (build/<variant>/build.yaml; {n} in all, both parts) goes through Vivado 2026.1 out-of-context synthesis, placement and routing and leaves a recorded result "
                   "(utilisation, WNS, WHS, Fmax, logic levels, vectorless power) in verif/results/vivado_ooc_<variant>_<part>.json. The measured values and each point's pre-stated expectation are in the Measured table of spec.md and in verif/results/vivado_surface.json; "
                   "this requirement states only that the measurement exists for every point, because no Fmax or area bound has been agreed.",
           "source": f"{base}/spec.md", "spec_status": "draft",
           "performance": {"quantity": "prepared points with a routed out-of-context Vivado result", "unit": "points", "op": "ge", "bound": n,
                           "condition": "Vivado 2026.1 out-of-context, one thread, the clocks of the build files, brief 160"}}
    item = {"id": f"V-{pre}-OOC", "requirements": [req["id"]], "method": "timing", "title": "The routed Vivado results of every prepared point (the records of the last run)",
            "evidence": {"file": f"{base}/verif/results/vivado_surface.json", "reader": "json", "field": "summary.routed_points"},
            "checks": sorted(str(x.relative_to(ROOT)) for x in (ROOT / base / "build").glob("**/build.yaml"))}
    return req, item


def measured_section(fn: str) -> list[str]:
    """Markdown lines for spec.md: the measured table of one function (empty when there are no records)."""
    f = ROOT / "arith" / fn / "verif" / "results" / "vivado_surface.json"
    if not f.exists():
        return []
    rows = json.loads(f.read_text())["points"]
    if not rows:
        return []
    L = ["", "## Measured (Vivado out-of-context, brief 160)", "",
         f"{rows[0]['tool']}, out-of-context synthesis, placement and routing on one thread, one run per point, at the clock shown. LUT, FF and carry cells are as reported "
         "after routing for the wrapper (which registers every port, so the FF column includes the wrapper's register bits); WNS at the target clock gives "
         "Fmax = 1000 / (clock - WNS), a lower bound (marked `>=`) when WNS is positive; latency is the spec's, in clocks, without the wrapper's two. "
         "`F` marks a point on the area-against-Fmax front of its group, `L` on the area-against-latency front (see [../../results/160_arith_vivado/README.md](../../results/160_arith_vivado/README.md)). "
         "Records: [verif/results/](verif/results/), the pre-stated expectation and its verdict per point: [verif/results/vivado_surface.json](verif/results/vivado_surface.json).", "",
         "| Variant | Part | Point | Clock ns | LUT | FF | SRL | Carry | DSP | BRAM | WNS ns | Fmax MHz | Logic levels | Latency | Fronts | Expectation |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        pt = ", ".join(f"{k}={v}" for k, v in r["generics"].items() if k != "VARIANT")
        if r["status"] != "ok":
            L.append(f"| {r['variant']} | {r['part_key']} | {pt} | {r['clock_ns']} | {r['status']} | | | | | | | | | | | |")
            continue
        fr = ("F" if r.get("front_fmax") else "") + ("L" if r.get("front_latency") else "")
        L.append(f"| {r['variant']} | {r['part_key']} | {pt} | {r['clock_ns']} | {r['lut']} | {r['ff']} | {r['srl']} | {r['carry']} | {r['dsp']} | {r['bram_tiles']} | {r['wns_ns']} | "
                 f"{'>=' if r['lower_bound'] else ''}{r['fmax_mhz']} | {r['logic_levels']} | {r['latency_clocks']} | {fr} | {r['expectation']} |")
    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    data = load()
    pc = planning_check(data)
    bad = 0
    for fn, rows in data.items():
        if not rows:
            continue
        p = ROOT / "arith" / fn / "verif" / "results" / "vivado_surface.json"
        txt = json.dumps({"schema": "fda-arith/vivado_surface/1", "function": fn, "summary": {"points": len(rows), "routed_points": sum(r["status"] == "ok" for r in rows), "expectation_met": sum(r.get("expectation") == "met" for r in rows if r["status"] == "ok"), "expectation_missed": sum(r.get("expectation") == "missed" for r in rows if r["status"] == "ok")}, "points": rows}, indent=1) + "\n"
        if a.check:
            bad |= (not p.exists() or p.read_text() != txt)
        else:
            p.write_text(txt)
    OUT.mkdir(parents=True, exist_ok=True)
    txt = json.dumps({"schema": "fda-arith/vivado_surface_all/1", "planning_check": pc,
                      "counts": {fn: {"points": len(r), "ok": sum(x["status"] == "ok" for x in r)} for fn, r in data.items()}}, indent=1) + "\n"
    if a.check:
        bad |= (not (OUT / "surface.json").exists() or (OUT / "surface.json").read_text() != txt)
    else:
        (OUT / "surface.json").write_text(txt)
    rd = readme(data, pc)
    if a.check:
        bad |= (not (OUT / "README.md").exists() or (OUT / "README.md").read_text() != rd)
    else:
        (OUT / "README.md").write_text(rd)
    print("surface:", "FAIL (out of date)" if bad else ("ok" if a.check else "written"))
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
