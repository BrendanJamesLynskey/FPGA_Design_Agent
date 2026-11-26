#!/usr/bin/env python3
"""Brief 177 part 1: one table of (early-stage features, routed outcome) from the builds we already have.

    python3 tools/qor/build_dataset.py [--out results/177_qor/dataset.csv]

No Vivado runs. Sources (paths are the local worktrees of the briefs named; every row says which):
  arith   brief 160 out-of-context runs: record JSON (routed) + the post-synthesis utilization_synth.rpt of the same point
  sweep   brief 166 clock-sweep rounds, only where the round's own utilization_synth.rpt exists
  gates   flow/gates.py gates.json files: committed ones in this repo, plus the final build of each agent run (82P2..82P7)

Post-synthesis timing (WNS, TNS) exists only in the gates rows; the arith records were made without a post-synthesis
timing report, so arith rows carry the target clock instead (clock_ns) and no synth WNS. Empty cell = not recorded.
"""
from __future__ import annotations
import argparse, csv, glob, hashlib, json, re, subprocess
from pathlib import Path

WT = Path("/home/brendan/Claude_sandbox/_worktrees")
REPO = Path(__file__).resolve().parents[2]

COLS = ["source", "group", "row_id", "vivado", "part", "clock_ns",
        "syn_wns", "syn_tns", "syn_whs", "syn_fail_frac", "syn_qor",
        "lut", "ff", "dsp", "bram", "lutram", "srl", "carry", "lut_avail", "lut_frac", "ff_frac", "dsp_frac", "bram_frac",
        "n_endpoints", "n_checktiming", "syn_meth_warn",
        "pl_wns", "pl_whs", "rt_qor",
        "rt_wns", "rt_whs", "rt_levels", "met", "gap_ns"]


def _row(txt, label):
    m = re.search(rf"^\|\s*{re.escape(label)}\*?\s*\|\s*([\d.]+)\s*\|[^|]*\|[^|]*\|\s*([\d.]+)", txt, re.M)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def parse_synth_util(p: Path) -> dict:
    t = p.read_text()
    lut, lav = _row(t, "Slice LUTs") if _row(t, "Slice LUTs")[0] is not None else _row(t, "CLB LUTs")
    ff, fav = _row(t, "Slice Registers") if _row(t, "Slice Registers")[0] is not None else _row(t, "CLB Registers")
    dsp, dav = _row(t, "DSPs")
    bram, bav = _row(t, "Block RAM Tile")
    srl, _ = _row(t, "LUT as Shift Register")
    lram, _ = _row(t, "LUT as Distributed RAM")
    carry = sum(int(m.group(2)) for m in re.finditer(r"^\|\s*(CARRY[48])\s*\|\s*(\d+)\s*\|", t, re.M))
    return dict(lut=lut, ff=ff, dsp=dsp, bram=bram, srl=srl, lutram=lram, carry=carry,
                lut_avail=lav, lut_frac=lut / lav if lut is not None and lav else None,
                ff_frac=ff / fav if ff is not None and fav else None,
                dsp_frac=dsp / dav if dsp is not None and dav else None,
                bram_frac=bram / bav if bram is not None and bav else None)


def met(wns, whs):
    return None if wns is None else int(wns >= 0 and (whs is None or whs >= 0))


def arith_rows():
    base = WT / "160-arith-vivado"
    recs = WT / "160-arith-vivado" / "arith"
    out = []
    for f in sorted(recs.glob("*/verif/results/vivado_ooc_*.json")):
        d = json.loads(f.read_text())
        for p in d["points"]:
            if p.get("status") != "ok" or p.get("wns_ns") is None:
                continue
            pid = "_".join(f"{k}{v}" for k, v in sorted(p["generics"].items()))
            rp = base / "build/arith_ooc" / d["function"] / d["variant"] / d["part_key"] / pid / "utilization_synth.rpt"
            if not rp.exists():
                continue
            r = dict(source="arith", group=d["function"], row_id=f"{d['function']}/{d['variant']}/{d['part_key']}/{pid}",
                     vivado="2026.1", part=d["part"], clock_ns=d["clock_ns"], rt_wns=p["wns_ns"], rt_whs=p["whs_ns"],
                     rt_levels=p.get("logic_levels"))
            r.update(parse_synth_util(rp))
            r["met"] = met(p["wns_ns"], p["whs_ns"]); r["gap_ns"] = round(-p["wns_ns"], 3)
            out.append(r)
    return out


def sweep_rows():
    base = WT / "166-arith-sweep"
    out = []
    for f in sorted((base / "arith").glob("*/verif/results/vivado_sweep_*.json")):
        d = json.loads(f.read_text())
        for p in d["points"]:
            pid = "_".join(f"{k}{v}" for k, v in sorted(p["generics"].items()))
            for rd in p["rounds"]:
                rp = base / "build/arith_sweep" / d["function"] / d["variant"] / d["part_key"] / pid / f"r{rd['round']}" / "utilization_synth.rpt"
                if rd.get("status") != "ok" or rd.get("wns_ns") is None or not rp.exists():
                    continue
                r = dict(source="sweep", group=d["function"], row_id=f"{d['function']}/{d['variant']}/{d['part_key']}/{pid}/r{rd['round']}",
                         vivado="2026.1", part=d["part"], clock_ns=rd["clock_ns"], rt_wns=rd["wns_ns"], rt_whs=rd["whs_ns"])
                r.update(parse_synth_util(rp))
                r["met"] = met(rd["wns_ns"], rd["whs_ns"]); r["gap_ns"] = round(-rd["wns_ns"], 3)
                out.append(r)
    return out


def _g(d, *ks):
    for k in ks:
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d


def gates_row(d: dict, source: str, rid: str):
    st = d.get("stages")
    if not st or not d.get("timing") or d["timing"].get("wns_ns") is None:
        return None
    t = d["timing"]; syn = _g(st, "post_synth", "timing") or {}; pl = _g(st, "post_place", "timing") or {}
    u = _g(st, "post_synth", "utilization") or d.get("utilization") or {}
    if not syn and not u:
        return None
    ct = _g(st, "post_synth", "check_timing") or {}
    q = lambda s: (_g(st, s, "qor_assessment") or {}).get("score")
    lav = u.get("lut_available")
    r = dict(source=source, group=d.get("top") or "", row_id=rid, vivado=d.get("vivado_version") or "",
             part=f"lut{int(lav)}" if lav else "",
             syn_wns=syn.get("wns_ns"), syn_tns=syn.get("tns_ns"), syn_whs=syn.get("whs_ns"),
             syn_fail_frac=(syn["tns_failing_endpoints"] / syn["tns_total_endpoints"]) if syn.get("tns_total_endpoints") else None,
             syn_qor=q("post_synth"), rt_qor=q("post_route"),
             lut=u.get("lut"), ff=u.get("ff"), dsp=u.get("dsp"), bram=u.get("bram_tile"), lutram=u.get("lutram"),
             srl=None, carry=(u.get("carry8") or 0) + (u.get("carry4") or 0) if ("carry8" in u or "carry4" in u) else None,
             lut_avail=lav, lut_frac=u["lut"] / lav if u.get("lut") is not None and lav else None,
             ff_frac=u["ff"] / u["ff_available"] if u.get("ff") is not None and u.get("ff_available") else None,
             dsp_frac=u["dsp"] / u["dsp_available"] if u.get("dsp") is not None and u.get("dsp_available") else None,
             bram_frac=u["bram_tile"] / u["bram_tile_available"] if u.get("bram_tile") is not None and u.get("bram_tile_available") else None,
             n_endpoints=syn.get("tns_total_endpoints"), n_checktiming=sum(v for v in ct.values() if isinstance(v, int)) if ct else None,
             syn_meth_warn=_g(st, "post_synth", "methodology", "warnings"),
             pl_wns=pl.get("wns_ns"), pl_whs=pl.get("whs_ns"), rt_wns=t["wns_ns"], rt_whs=t.get("whs_ns"))
    r["met"] = met(t["wns_ns"], t.get("whs_ns")); r["gap_ns"] = round(-t["wns_ns"], 3)
    return r


def gates_rows():
    out, seen = [], set()
    def add(d, source, rid):
        r = gates_row(d, source, rid)
        if r is None:
            return
        # the same build copied into several worktrees: key on the build's own digest and its numbers
        k = (d.get("sources_sha256") or d.get("build_stamp"), d.get("top"), d.get("variant"), r["rt_wns"], r["syn_wns"], r["pl_wns"])
        if k in seen:
            return
        seen.add(k); out.append(r)
    for f in subprocess.check_output(["git", "-C", str(REPO), "ls-files"], text=True).splitlines():
        if re.search(r"gates[^/]*\.json$", f) and f.startswith(("results/", "agent/tests/fixtures")):
            try:
                d = json.loads((REPO / f).read_text())
            except Exception:
                continue
            if isinstance(d, dict):
                grp = f.split("/")[1] if f.startswith("results/") else "fixture"
                add(d, "gates", f)
                if out and out[-1]["row_id"] == f:
                    out[-1]["group"] = (out[-1]["group"] or grp)
    for f in sorted(WT.glob("82p*-frozen/runs/*/*/build/base/gates.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        add(d, "agentrun", f"{f.parts[-6]}/{f.parts[-5]}/{f.parts[-4]}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(REPO / "results/177_qor/dataset.csv"))
    a = ap.parse_args(argv)
    rows = arith_rows() + sweep_rows() + gates_rows()
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS); w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in COLS})
    by = {}
    for r in rows:
        by.setdefault(r["source"], [0, 0])
        by[r["source"]][0] += 1; by[r["source"]][1] += r["met"] or 0
    print(len(rows), "rows", {k: f"{v[0]} rows, {v[1]} met" for k, v in by.items()})


if __name__ == "__main__":
    main()
