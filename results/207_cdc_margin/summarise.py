#!/usr/bin/env python3
"""Brief 207: build results.md (and results.json) from raw/ (the Vivado and Quartus records). Every number in the method doc,
the KB skill and the report comes from here.

    python3 results/207_cdc_margin/summarise.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from flow import cdc_margin as CM          # noqa: E402
from flow import cdc_structure as CS       # noqa: E402

RAW = HERE / "raw"
CROSS = ["lvl", "tgl", "wptr", "rptr", "ram", "hsreq", "hsack", "hsdat", "cfgt", "cfgd"]
SLOW = "6_slow_1100mv_85c"        # Cyclone V worst slow corner; MAX 10 corner names are found at run time


def kv(line: str) -> dict[str, str]:
    out = {}
    for f in line.split("|"):
        if "=" in f:
            k, v = f.split("=", 1)
            out[k] = v
    return out


def vivado_variant(d: Path) -> dict:
    m = (d / "metrics.txt").read_text(errors="replace") if (d / "metrics.txt").exists() else ""
    r: dict = {"cross": {}, "fill": {}, "inter": {}, "bounds": {}, "upair": None}
    for ln in m.splitlines():
        p = ln.split("|")
        if p[0] == "CROSS" and len(p) > 2:
            r["cross"][p[1]] = kv(ln)
        elif p[0] == "FILL":
            r["fill"][p[1]] = kv(ln)
        elif p[0] == "INTER":
            r["inter"][p[1]] = kv(ln).get("wns", "none")
        elif p[0] == "BOUND":
            r["bounds"][p[1]] = kv(ln)
        elif p[0] in ("UPAIR", "UPAIR_MEASURED"):
            r["upair"] = float(p[1])
    bs = CM.parse_bus_skew((d / "bus_skew.rpt").read_text(errors="replace")) if (d / "bus_skew.rpt").exists() else []
    # per crossing: the routed skew (actual) from the post-route assertion, and the slack of the constraint used in routing
    r["skew"] = {}
    # bus_skew.rpt: the post-route measurement assertions (1000 ns, the same -from/-to as the routing constraint, which they replace,
    # last one wins; routing was already done); bus_skew_constraint.rpt: the constraints routing saw (D, DU, M), before the assertions
    def cname(c):
        txt = c["command"] + " " + c["from_to"]
        return next((n for n, pat in (("wptr", "wq1_b"), ("rptr", "rq1_a"), ("hsdat", "hs_data_b"), ("cfgd", "cfg_b")) if pat in txt), None)
    for c in bs:
        name = cname(c)
        if name is not None:
            e = r["skew"].setdefault(name, {"actual": c["actual"], "routed_slack": None, "routed_req": None})
            e["actual"] = max(e["actual"], c["actual"])
    bc = CM.parse_bus_skew((d / "bus_skew_constraint.rpt").read_text(errors="replace")) if (d / "bus_skew_constraint.rpt").exists() else []
    for c in bc:
        name = cname(c)
        if name is not None:
            e = r["skew"].setdefault(name, {"actual": c["actual"], "routed_slack": None, "routed_req": None})
            e["routed_slack"], e["routed_req"] = c["slack"], c["requirement"]
    mt = d / "mtbf.rpt"
    r["mtbf"] = CM.parse_mtbf(mt.read_text(errors="replace")) if mt.exists() else None
    meth = (d / "methodology.rpt").read_text(errors="replace") if (d / "methodology.rpt").exists() else ""
    r["timing44_45"] = len(CM.methodology_rules(meth, ("TIMING-44", "TIMING-45")))
    cdc = (d / "cdc.rpt").read_text(errors="replace") if (d / "cdc.rpt").exists() else ""
    r["cdc_rules"] = sorted({(x["rule"], x["severity"]) for x in CS.parse_cdc_rows(cdc)})
    if (d / "cdc_paths.rpt").exists():
        try:
            st = CS.evaluate(d / "cdc_paths.rpt", d / "cdc.rpt")
            r["structure"] = {"pass": st["pass"], "summary": st["summary"],
                              "unsafe": sorted({(u["rule"], CM._base(u["cell"])) for u in st["unsafe"]})}
        except ValueError as e:
            r["structure"] = {"error": str(e)}
    return r


def quartus_variant(d: Path) -> dict:
    m = (d / "metrics.txt").read_text(errors="replace") if (d / "metrics.txt").exists() else ""
    r: dict = {"corners": {}, "sdc_error": None}
    for ln in m.splitlines():
        p = ln.split("|")
        if p[0] == "SDC_ERROR":
            r["sdc_error"] = ln[10:200]
        if p[0] in ("CROSS", "FILL", "INTER") and len(p) > 3:
            c = r["corners"].setdefault(p[1], {"cross": {}, "fill": {}, "inter": {}})
            if p[0] == "CROSS":
                c["cross"][p[2]] = kv(ln)
            elif p[0] == "FILL":
                c["fill"][p[2]] = kv(ln)
            else:
                c["inter"][p[2]] = kv(ln).get("wns")
    for corner, c in r["corners"].items():
        f = d / f"max_skew_{corner}.rpt"
        if f.exists():
            t = f.read_text(errors="replace")
            mm = re.search(r"Found (\d+) paths \((\d+) violated\)\. Worst case slack is (-?[\d.]+)", t)
            c["max_skew"] = {"paths": int(mm.group(1)), "violated": int(mm.group(2)), "worst_slack": float(mm.group(3))} if mm else \
                {"paths": 0, "note": "no max-skew paths reported"}
            rows = {}
            for ln in t.splitlines():
                g = [x.strip() for x in ln.strip().strip(";").split(";")]
                if len(g) > 5 and g[0] == "set_max_skew":
                    name = next((n for n, pat in (("wptr", "wq1_b"), ("rptr", "rq1_a"), ("hsdat", "hs_data_b"), ("cfgd", "cfg_b")) if pat in g[5]), g[5])
                    rows[name] = {"slack": float(g[1]), "req": float(g[2]), "actual": float(g[3])}
            c["skew_rows"] = rows
        f = d / f"metastability_{corner}.rpt"
        if f.exists():
            t = f.read_text(errors="replace")
            g = {}
            for key, pat in (("worst_mtbf", r"Worst-Case MTBF of Design is ([^\n]+?)\.\n"), ("typ_mtbf", r"Typical MTBF of Design is ([^\n]+?)\.\n"),
                             ("chains", r"Number of Synchronizer Chains Found: (\d+)"), ("shortest", r"Shortest Synchronizer Chain: (\d+)"),
                             ("settle", r"Worst Case Available Settling Time: (-?[\d.]+) ns"), ("x100ps_worst", r"worst-case conditions, an increase of 100ps[^\n]*factor of ([\d.]+)")):
                mm = re.search(pat, t)
                g[key] = mm.group(1) if mm else None
            g["sources"] = sorted(set(re.findall(r"^; (\S+)\s+; (\S+)\s+; [^;]+; [^;]+; (?:Yes|No)", t, re.M)))
            c["meta"] = g
    return r


def corner_pick(r: dict) -> str | None:
    cs = list(r["corners"])
    slow = [c for c in cs if "slow" in c.lower() and "85" in c]
    return slow[0] if slow else (cs[0] if cs else None)


def fmt(x, nd=3):
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "-" if x in (None, "") else str(x)


def main() -> int:
    res: dict = {"vivado": {}, "quartus": {}, "xpm": {}}
    for d in sorted(RAW.glob("vv_*")):
        if d.is_dir():
            res["vivado"][d.name] = {v.name: vivado_variant(v) for v in sorted(d.iterdir()) if v.is_dir()}
    for d in sorted(RAW.glob("q_*")):
        if d.is_dir():
            res["quartus"][d.name] = {v.name: quartus_variant(v) for v in sorted(d.iterdir()) if v.is_dir() and v.name != "proj"}
    for d in sorted(RAW.glob("xpm_*")):
        if (d / "metrics.txt").exists():
            res["xpm"][d.name] = {"metrics": (d / "metrics.txt").read_text().splitlines(),
                                  "exceptions": CM.parse_exceptions_dpo((d / "exceptions.rpt").read_text(errors="replace")) if (d / "exceptions.rpt").exists() else [],
                                  "bus_skew": CM.parse_bus_skew((d / "bus_skew.rpt").read_text(errors="replace")) if (d / "bus_skew.rpt").exists() else []}
    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=str) + "\n")

    L = ["# Brief 207 results (generated by summarise.py from raw/; do not edit by hand)", ""]
    # ---- Vivado
    for job, vs in res["vivado"].items():
        L += [f"## Vivado {job}", ""]
        L += ["Latency = worst routed datapath delay to the first stage (ns); skew = routed bus skew from report_bus_skew (ns, the post-route "
              "assertion, so the same measure in every variant); 'slack' = the bus-skew constraint used during routing (D, DU, M only).", ""]
        L += ["| variant | " + " | ".join(f"{c} lat" for c in ("lvl", "wptr", "hsdat", "cfgd", "ram")) +
              " | wptr skew | hsdat skew | cfgd skew | rptr skew | min routed skew slack | filler WNS a | filler WNS b | inter WNS a->b | TIMING-44/45 | U_pair | MTBF overall |", "|" + "---|" * 18]
        for v, r in vs.items():
            cr = r["cross"]
            sk = r["skew"]
            rs = [e["routed_slack"] for e in sk.values() if e["routed_slack"] is not None]
            L.append(f"| {v} | " + " | ".join(fmt(cr.get(c, {}).get("dmax")) for c in ("lvl", "wptr", "hsdat", "cfgd", "ram")) +
                     f" | {fmt(sk.get('wptr', {}).get('actual'))} | {fmt(sk.get('hsdat', {}).get('actual'))} | {fmt(sk.get('cfgd', {}).get('actual'))} | "
                     f"{fmt(sk.get('rptr', {}).get('actual'))} | {fmt(min(rs)) if rs else '-'} | {fmt(r['fill'].get('a', {}).get('wns'))} | "
                     f"{fmt(r['fill'].get('b', {}).get('wns'))} | {fmt(r['inter'].get('a->b'))} | {r['timing44_45']} | {fmt(r['upair'])} | "
                     f"{(r['mtbf'] or {}).get('overall_text', '-') or '-'} |")
        L.append("")
        L += ["Per-crossing worst-path detail (slack, requirement and clock uncertainty from report_timing):", "",
              "| variant | crossing | npaths | ignored | latency | spread | slack | requirement | clock uncertainty |", "|---|---|---|---|---|---|---|---|---|"]
        for v, r in vs.items():
            for c in CROSS:
                x = r["cross"].get(c)
                if x:
                    L.append(f"| {v} | {c} | {x.get('npaths')} | {x.get('ignored')} | {fmt(x.get('dmax'))} | {fmt(x.get('spread'))} | "
                             f"{x.get('slack')} | {x.get('req', '-')} | {x.get('unc', '-')} |")
        L.append("")
        L += ["Checks on each variant: report_cdc rule IDs (severity); cdc_structure verdict; MTBF chains (UltraScale+).", "",
              "| variant | report_cdc rules | cdc_structure | MTBF chains | lowest chain MTBF |", "|---|---|---|---|---|"]
        for v, r in vs.items():
            st = r.get("structure", {})
            stt = ("pass" if st.get("pass") else "FAIL " + ", ".join(f"{a}:{b}" for a, b in st.get("unsafe", []))) if "pass" in st else st.get("error", "-")
            mt = r["mtbf"]
            low = min((c["mtbf_years"] for c in mt["chains"] if c["mtbf_years"] is not None), default=None) if mt else None
            L.append(f"| {v} | {', '.join(f'{a} ({b})' for a, b in r['cdc_rules'])} | {stt} | {len(mt['chains']) if mt else '-'} | "
                     f"{('%.3g years' % low) if low is not None else '-'} |")
        L.append("")
    # ---- Quartus
    for job, vs in res["quartus"].items():
        L += [f"## Quartus {job}", ""]
        L += ["Analysis variants on one fit (the fit used the variant in the directory name). Slow 85 C corner unless named. Settling time "
              "and design MTBF from report_metastability.", ""]
        L += ["| analysis | corner | lvl lat | wptr lat | wptr spread | hsdat lat | cfgd lat | wptr slack | max-skew paths | max-skew worst slack | "
              "wptr skew (actual/req) | hsdat skew | filler WNS a | filler WNS b | inter a->b | chains | shortest | settling (ns) | worst MTBF | SDC error |",
              "|" + "---|" * 20]
        for v, r in vs.items():
            cn = corner_pick(r)
            if cn is None:
                L.append(f"| {v} | - | " + " | ".join(["-"] * 17) + f" | {r['sdc_error'] or '-'} |")
                continue
            c = r["corners"][cn]
            x = c["cross"]
            ms = c.get("max_skew", {})
            sr = c.get("skew_rows", {})
            g = c.get("meta", {})
            L.append(f"| {v} | {cn} | {fmt(x.get('lvl', {}).get('dmax'))} | {fmt(x.get('wptr', {}).get('dmax'))} | {fmt(x.get('wptr', {}).get('spread'))} | "
                     f"{fmt(x.get('hsdat', {}).get('dmax'))} | {fmt(x.get('cfgd', {}).get('dmax'))} | {x.get('wptr', {}).get('slack', '-')} | "
                     f"{ms.get('paths', '-')} | {fmt(ms.get('worst_slack'))} | "
                     f"{fmt(sr.get('wptr', {}).get('actual'))}/{fmt(sr.get('wptr', {}).get('req'))} | {fmt(sr.get('hsdat', {}).get('actual'))} | "
                     f"{fmt(c['fill'].get('clk_a', {}).get('wns'))} | {fmt(c['fill'].get('clk_b', {}).get('wns'))} | {c['inter'].get('clk_a->clk_b')} | "
                     f"{g.get('chains', '-')} | {g.get('shortest', '-')} | {g.get('settle', '-')} | {g.get('worst_mtbf', '-')} | {r['sdc_error'] or '-'} |")
        L.append("")
        for v, r in vs.items():
            cn = corner_pick(r)
            if cn and r["corners"][cn].get("meta"):
                srcs = r["corners"][cn]["meta"]["sources"]
                L.append(f"- {v}: synchroniser chains found by report_metastability ({len(srcs)}): {', '.join(f'{a}->{b}' for a, b in srcs)}")
        L.append("")
    # ---- XPM
    for job, x in res["xpm"].items():
        L += [f"## XPM handshake / Gray: what flow/xpm_cdc.tcl applies ({job})", ""]
        L += [f"- {ln}" for ln in x["metrics"] if not ln.startswith("#")]
        L += [f"- exception: position {e['position']}, max_dpo {e['value']}: `{e['text'][:160]}`" for e in x["exceptions"]]
        L += [f"- bus skew: requirement {c['requirement']}, actual {c['actual']}, slack {c['slack']}: `{(c['command'] or c['from_to'])[:160]}`" for c in x["bus_skew"]]
        if not x["bus_skew"]:
            L.append("- bus skew: none")
        L.append("")
    (HERE / "results.md").write_text("\n".join(L) + "\n")
    # headline numbers for site/data/expertise.yaml (get: paths), each copied from the records above
    h: dict = {}
    try:
        V, Q = res["vivado"], res["quartus"]
        for fam in ("a7", "k26"):
            g = V.get(f"vv_{fam}_good", {})
            if g:
                h[fam] = {"upair_ns": g["N"]["upair"], "filler_whs_a_D": float(g["D_Default"]["fill"]["a"]["whs"]),
                          "filler_whs_a_U": float(g["U"]["fill"]["a"]["whs"]),
                          "lvl_slack_D": float(g["D_Default"]["cross"]["lvl"]["slack"]), "lvl_slack_DU": float(g["DU"]["cross"]["lvl"]["slack"])}
                if g["D_Default"].get("mtbf"):
                    h[fam]["mtbf_D_years"] = g["D_Default"]["mtbf"]["overall_years"]
                    h[fam]["mtbf_DU_years"] = g["DU"]["mtbf"]["overall_years"]
        for fam, cn in (("cv", "6_slow_1100mv_85c"), ("m10", "7_slow_1200mv_85c")):
            f = Q.get(f"q_{fam}_good_D_s1", {})
            if f:
                h[fam] = {"maxskew_paths_D": f["D"]["corners"][cn]["max_skew"]["paths"], "maxskew_paths_DD": f["DD"]["corners"][cn]["max_skew"]["paths"],
                          "settle_D_ns": float(f["D"]["corners"][cn]["meta"]["settle"]), "settle_DU_ns": float(f["DU"]["corners"][cn]["meta"]["settle"]),
                          "filler_wns_b_D": float(f["D"]["corners"][cn]["fill"]["clk_b"]["wns"]), "filler_wns_b_DU": float(f["DU"]["corners"][cn]["fill"]["clk_b"]["wns"]),
                          "worst_mtbf_D": f["D"]["corners"][cn]["meta"]["worst_mtbf"], "worst_mtbf_DU": f["DU"]["corners"][cn]["meta"]["worst_mtbf"]}
        for job, x in res["xpm"].items():
            ex = [e["value"] for e in x["exceptions"]]
            h[job] = {"flow_max_dpo_ns": sorted(set(ex)), "bus_skew_constraints": len(x["bus_skew"])}
    except (KeyError, TypeError, ValueError) as e:
        h["error"] = f"{type(e).__name__}: {e}"
    (HERE / "headline.json").write_text(json.dumps(h, indent=1, sort_keys=True) + "\n")
    print(f"results.md: {len(res['vivado'])} Vivado jobs, {len(res['quartus'])} Quartus fits, {len(res['xpm'])} XPM runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
