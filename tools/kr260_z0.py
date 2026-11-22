#!/usr/bin/env python3
"""Brief 162: Z0 and delay of the KR260 carrier's 50 ohm single-ended routing, from the board's own fab notes.

    python3 tools/kr260_z0.py [--out results/162_kr260_si/z0.json]

Inputs (all from AMD's KR260 carrier Allegro board file, xtp756, as text inside it; the file itself is not committed):
cross-section chart (TOP 1.9 mil copper, L2 0.6 mil, prepreg P001 1080 3.21 mil, core 2113 4.0 mil, prepreg 2116 4.77 mil, ...), and the fab drawing
table 2: 50 ohm single-ended = 5.2 mil on TOP and 4 mil on layers 3, 5 and 12 (tolerance +/-10 %). The laminate is EM-828G (its Dk is not in the file).

Method: the laminate Dk is the one value the file lacks, so it is *calibrated*: the Dk for which the microstrip of the fab table (5.2 mil over the 3.21 mil
prepreg) is exactly 50 ohm. Z0 is then computed two ways, an analytic formula (Hammerstad-Jensen microstrip, with a thickness correction) and the owner's
two-dimensional field solver (Matrix_Articles/si_models/fdm2d.py), and the two are compared. The stripline height b that gives 50 ohm at 4 mil is then checked
against the dielectric heights in the chart. No Dk is quoted from a data sheet: the delay is a consequence of the fab table's own 50 ohm.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIL = 0.0254                      # mm
sys.path.insert(0, "/home/brendan/Claude_sandbox/Matrix_Articles")
from si_models.fdm2d import CrossSection, rlgc, single_z0, cohn_stripline, hammerstad_microstrip   # noqa: E402

C0 = 299792458.0


def ms_analytic(w, h, t, er):
    """Hammerstad-Jensen microstrip with the standard thickness correction (all in mil)."""
    u = w / h
    du = (t / math.pi) * math.log(1 + 4 * math.e / (t / h / (1 / math.tanh(math.sqrt(6.517 * u))) ** 2)) if t > 0 else 0.0
    we = w + du * (1 + 1 / math.cosh(math.sqrt(er - 1)))
    return hammerstad_microstrip(we, h, er)


def ms_fdm(w, h, t, er, cell=0.005):
    W = 12 * h * MIL
    cs = CrossSection(max(W, 1.2), 14 * h * MIL, cell)
    cs.dielectric(0, cs.nx * cell, 0, h * MIL, er)
    cs.ground_plane(0, cell)
    x0 = cs.nx * cell / 2
    cs.conductor(x0 - w * MIL / 2, x0 + w * MIL / 2, h * MIL, (h + t) * MIL, 1)
    C, L = rlgc(cs)
    z0 = single_z0(C, L)
    c_per_m = C[0, 0]
    v = 1 / math.sqrt(L[0, 0] * c_per_m)
    return z0, (C0 / v) ** 2          # z0, effective permittivity


def solve(f, lo, hi):
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results/162_kr260_si/z0.json"))
    a = ap.parse_args(argv)
    W_TOP, H_TOP, T_TOP = 5.2, 3.21, 1.9
    er = solve(lambda e: ms_analytic(W_TOP, H_TOP, T_TOP, e)[0] - 50.0, 2.0, 7.0)   # Z0 falls as er rises
    z_an, ee_an = ms_analytic(W_TOP, H_TOP, T_TOP, er)
    z_fd, ee_fd = ms_fdm(W_TOP, H_TOP, T_TOP, er)
    # second calibration with the field solver (it models the 1.9 mil copper): bisection on Dk
    er_fd = solve(lambda e: ms_fdm(W_TOP, H_TOP, T_TOP, e)[0] - 50.0, 2.5, 9.0)
    z_fd2, ee_fd2 = ms_fdm(W_TOP, H_TOP, T_TOP, er_fd)
    # stripline: 4 mil wide, 0.6 mil thick, 50 ohm; Cohn (zero thickness) on an effective width w + dw
    w_s, t_s = 4.0, 0.6
    dw = (t_s / math.pi) * (1 + math.log(4 * math.pi * w_s / t_s))      # thickness correction (Wheeler, wide-line form)
    def zs(b):
        return cohn_stripline((w_s + dw) * MIL, b * MIL, er)
    b50 = solve(lambda b: 50.0 - zs(b), 4.0, 40.0)                       # Z0 rises with b
    # the stripline height from the chart: the two dielectrics either side of a signal layer (an ASSUMED pairing: the chart's order is not recoverable from the
    # file's text), 4.0 + 4.77 mil of dielectric (+0.6 mil copper for the other bound): the Dk that gives 50 ohm at 4 mil wide
    chart_b = {}
    for b in (4.0 + 4.77, 4.0 + 4.77 + 0.6):
        e = solve(lambda x: cohn_stripline((w_s + dw) * MIL, b * MIL, x) - 50.0, 2.0, 8.0)   # Z0 falls as Dk rises
        chart_b[f"b_{b:.2f}_mil"] = {"dk": e, "delay_ps_per_in": 25.4e-3 / C0 * math.sqrt(e) * 1e12}
    res = {"stripline_from_chart_gaps": chart_b, "calibrated_laminate_dk": er,
           "microstrip_top": {"w_mil": W_TOP, "h_mil": H_TOP, "t_mil": T_TOP, "z0_analytic_ohm": z_an, "er_eff_analytic": ee_an,
                              "z0_fdm2d_ohm": z_fd, "er_eff_fdm2d": ee_fd, "delay_ps_per_in_fdm2d": 25.4e-3 / C0 * math.sqrt(ee_fd) * 1e12 * 1e3 / 1e3 * 1e3 / 1e3,
                              "agreement_pct": 100 * (z_fd - z_an) / z_an},
           "stripline_inner": {"w_mil": w_s, "t_mil": t_s, "b_mil_for_50_ohm": b50, "er_eff": er,
                               "delay_ps_per_in": 25.4e-3 / C0 * math.sqrt(er) * 1e12},
           "calibrated_with_fdm2d": {"laminate_dk": er_fd, "microstrip_z0_ohm": z_fd2, "er_eff_microstrip": ee_fd2,
                                     "microstrip_delay_ps_per_in": 25.4e-3 / C0 * math.sqrt(ee_fd2) * 1e12,
                                     "stripline_delay_ps_per_in": 25.4e-3 / C0 * math.sqrt(er_fd) * 1e12},
           "note": "the two solvers disagree by about 17 % at the same Dk (analytic 50 ohm, fdm2d 58.5 ohm; thin-conductor limit 63.7 vs 66.6 ohm), so the calibrated Dk is 3.2 or 4.9 depending on which is trusted; delays are given for both",
           "chart_dielectrics_mil": {"P001_1080": 3.21, "P002_2116": 4.77, "P003_2113": 3.72, "C001_2113": 4.0, "C002_1067": 2.5},
           "chart_total_thickness_mil": 64.02}
    res["microstrip_top"]["delay_ps_per_in"] = 25.4e-3 / C0 * math.sqrt(ee_fd) * 1e12
    del res["microstrip_top"]["delay_ps_per_in_fdm2d"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
