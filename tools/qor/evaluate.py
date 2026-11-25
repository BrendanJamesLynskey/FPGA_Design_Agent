#!/usr/bin/env python3
"""Brief 177 parts 2 and 3: how well do early-stage numbers predict the routed outcome?

    python3 tools/qor/evaluate.py [--dataset results/177_qor/dataset.csv] [--out results/177_qor/evaluation.json]

A. arith rows (brief 160 + 166, out of context, post-synthesis utilization + target clock): met = routed setup and
   hold slack >= 0. Leave-one-function-out cross-validation (no point of a function is in its own training set).
B. gates rows: post-synthesis WNS, post-place WNS and AMD's report_qor_assessment score against the routed outcome.
All numbers go to the JSON; evaluation.md is written from it by hand-free formatting below.
"""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
import numpy as np
from model import LogReg, Stumps, auc, brier, reliability, go_stats

REPO = Path(__file__).resolve().parents[2]
F_ARITH = ["log_lut", "log_ff", "log_srl", "log_carry", "dsp", "bram", "freq_mhz", "is_k26"]
F_CLOCK = ["freq_mhz", "is_k26"]


def num(x):
    return float(x) if x not in ("", None) else float("nan")


def arith_matrix(rows):
    X = []
    for r in rows:
        X.append([math.log1p(num(r["lut"])), math.log1p(num(r["ff"])), math.log1p(num(r["srl"]) if r["srl"] != "" else 0),
                  math.log1p(num(r["carry"])), num(r["dsp"]), num(r["bram"]), 1000.0 / num(r["clock_ns"]),
                  1.0 if r["part"].startswith("xck26") else 0.0])
    return np.array(X)


def loo_group(X, y, g, make):
    p = np.zeros(len(y))
    for grp in sorted(set(g)):
        te = np.array([x == grp for x in g])
        p[te] = make().fit(X[~te], y[~te]).predict_proba(X[te])
    return p


def summarise(y, p, ts=(0.5, 0.7, 0.8)):
    return dict(auc=auc(y, p), brier=brier(y, p), reliability=reliability(y, p), go=[go_stats(y, p, t) for t in ts])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(REPO / "results/177_qor/dataset.csv"))
    ap.add_argument("--out", default=str(REPO / "results/177_qor/evaluation.json"))
    a = ap.parse_args(argv)
    R = list(csv.DictReader(open(a.dataset)))
    res = {}
    A = [r for r in R if r["source"] == "arith"]
    X = arith_matrix(A); y = np.array([int(r["met"]) for r in A]); g = [r["group"] for r in A]
    ci = [F_ARITH.index(c) for c in F_CLOCK]
    res["arith"] = dict(n=len(A), met=int(y.sum()), functions=sorted(set(g)),
                        prior=dict(auc=0.5, brier=brier(y, np.full(len(y), y.mean()))))
    res["arith"]["clock_part_only"] = summarise(y, loo_group(X[:, ci], y, g, lambda: LogReg(1.0)))
    res["arith"]["logreg_all"] = summarise(y, loo_group(X, y, g, lambda: LogReg(1.0)))
    res["arith"]["stumps_all"] = summarise(y, loo_group(X, y, g, lambda: Stumps()))
    res["arith"]["per_function_auc_logreg"] = {}
    p = loo_group(X, y, g, lambda: LogReg(1.0))
    for grp in sorted(set(g)):
        m = np.array([x == grp for x in g]); res["arith"]["per_function_auc_logreg"][grp] = dict(n=int(m.sum()), met=int(y[m].sum()), auc=auc(y[m], p[m]))
    # sweep rows: every one was run above the measured limit on purpose, so all fail; how many does the arith model hold back?
    S = [r for r in R if r["source"] == "sweep"]
    if S:
        mdl = LogReg(1.0).fit(X, y); ps = mdl.predict_proba(arith_matrix(S))
        res["sweep_check"] = dict(n=len(S), met=int(sum(int(r["met"]) for r in S)), mean_p_pass=float(ps.mean()), n_p_ge_0_5=int((ps >= 0.5).sum()))
    # B. gates rows
    G = [r for r in R if r["source"] == "gates"]
    yb = np.array([int(r["met"]) for r in G])
    B = dict(n=len(G), met=int(yb.sum()), fails=int((yb == 0).sum()))
    sw = [(num(r["syn_wns"]), num(r["rt_wns"])) for r in G if r["syn_wns"] != "" and r["rt_wns"] != ""]
    d = np.array([b - s for s, b in sw]) if sw else np.array([])
    if len(d):
        B["synth_to_route_wns"] = dict(n=len(d), mean_shift_ns=float(d.mean()), min_shift_ns=float(d.min()), max_shift_ns=float(d.max()),
                                       rows_synth_ge0_route_lt0=int(sum(1 for s, b in sw if s >= 0 and b < 0)),
                                       rows_synth_lt0=int(sum(1 for s, b in sw if s < 0)))
    pw = [(num(r["pl_wns"]), num(r["rt_wns"])) for r in G if r["pl_wns"] != "" and r["rt_wns"] != ""]
    if pw:
        B["place_to_route_wns"] = dict(n=len(pw), rows_place_ge0_route_lt0=int(sum(1 for s, b in pw if s >= 0 and b < 0)),
                                       rows_place_lt0=int(sum(1 for s, b in pw if s < 0)),
                                       rows_place_lt0_route_ge0=int(sum(1 for s, b in pw if s < 0 and b >= 0)))
    q = [(int(r["syn_qor"]), int(r["met"])) for r in G if r["syn_qor"] != ""]
    qr = [(int(r["rt_qor"]), int(r["met"])) for r in G if r["rt_qor"] != ""]
    def tab(pairs):
        t = {}
        for s, m in pairs:
            t.setdefault(str(s), [0, 0]); t[str(s)][m] += 1
        return {k: dict(routed_fail=v[0], routed_met=v[1]) for k, v in sorted(t.items())}
    B["amd_synth_score_vs_routed"] = dict(n=len(q), vivado="2025.2 (report_qor_assessment is refused on 2026.1 with the Basic licence: Implflow 47-29)", table=tab(q))
    B["amd_route_score_vs_routed"] = dict(n=len(qr), table=tab(qr))
    res["gates"] = B
    Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: (v if k != "arith" else {kk: (vv if not isinstance(vv, dict) or "auc" not in vv else (vv["auc"], vv["brier"])) for kk, vv in v.items() if kk != "per_function_auc_logreg"}) for k, v in res.items()}, indent=1)[:3500])


if __name__ == "__main__":
    main()
