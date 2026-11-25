#!/usr/bin/env python3
"""Brief 162: cross-check of brief 155's solver with ngspice (BSD-3-Clause, built user-local; version printed in the output).

    python3 tools/offchip_ngspice.py [--ngspice ~/.local/opt/ngspice-47/bin/ngspice] [--out results/162_kr260_si/ngspice_check.csv]

No free IBIS-to-SPICE route was used (none is installed, and an IBIS [Pullup]/[Pulldown] table is only the DC part of a model). Instead the same IBIS V-I tables
and the same calibrated switching ramp as ``flow/offchip_model.py`` become an ngspice behavioural current source on the pad (B element with ``pwl()``), a
lossless T element for the line, a series resistor and a capacitor. The two simulators therefore share the driver data and differ in the method
(155: method of characteristics with its own Newton solve; ngspice: modified nodal analysis with the T element). Agreement says the solver
is right; it says nothing about IBIS or about the board.
"""
from __future__ import annotations

import argparse
import csv
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow"))
import offchip_model as M        # noqa: E402


def _pwl(xs, ys):
    pts = [(-50.0, ys[0])] + list(zip(xs, ys)) + [(50.0, ys[-1])]
    return "pwl({v}," + ",".join(f"{x:.6g},{y:.9g}" for x, y in pts) + ")"


def netlist(drv: M.Driver, line: M.Line, c_pf: float, rs: float, edge: str, dt: float, t_stop: float, t0: float, out: Path) -> str:
    tr = drv.ramp(edge)
    pu, pd = _pwl(drv.pu.x, drv.pu.y), _pwl(drv.pd.x, drv.pd.y)
    s = f"((time-{t0:.6g})/{tr:.6g})"
    ramp = f"((time<{t0:.6g})?0:((time>{t0 + tr:.6g})?1:{s}*{s}*(3-2*{s})))"
    ku = ramp if edge == "r" else f"(1-{ramp})"
    kd = f"(1-{ramp})" if edge == "r" else ramp
    ku_ = f"{0 if edge == 'r' else 1}" ; kd_ = f"{1 if edge == 'r' else 0}"
    # initial (rest) state: ku, kd constants before t0
    return f"""* brief 162 cross-check of the brief 155 solver ({drv.name}, corner {drv.corner}, edge {edge})
.options reltol=1e-4 abstol=1e-12 vntol=1e-7 method=gear
Bku ku 0 V={ku}
Bkd kd 0 V={kd}
Bdev pad 0 I = V(ku)*{pu.replace('{v}', f'({drv.vcc}-V(pad))')} + V(kd)*{pd.replace('{v}', 'V(pad)')}
Ccomp pad 0 {drv.c_comp:.6g}
Rs pad a {max(rs, 1e-3):.6g}
T1 a 0 b 0 Z0={line.z0:.6g} TD={line.delay_s:.6g}
Cl b 0 {c_pf * 1e-12:.6g}
.tran {dt:.6g} {t_stop:.6g} 0 {dt:.6g}
.control
run
set wr_vecnames
wrdata {out} v(b)
.endc
.end
"""


def run_case(ngspice: str, key: str, corner: str, edge: str, length_in: float, c_pf: float, rs: float, z0: float = 50.0) -> dict:
    drv = M.get_driver(key, corner)
    line = M.Line(z0=z0, length_in=length_in)
    ref = M.simulate(drv, line, M.Load(c_pf=c_pf), rs=rs, edge=edge)
    T = line.delay_s
    dt_t = min(20e-12, drv.ramp(edge) / 16)      # the same time step as flow/offchip_model.simulate (T divided into whole steps)
    dt = max(T, 1e-12) / max(1, math.ceil(max(T, 1e-12) / dt_t))
    t0 = 10 * max(T, 1e-12)
    t0 = round(t0 / dt) * dt
    t_stop = t0 + drv.ramp(edge) + 24.0 * T + 8e-9
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "w.txt"
        net = Path(d) / "c.cir"
        net.write_text(netlist(drv, line, c_pf, rs, edge, dt, t_stop, t0, out))
        r = subprocess.run([ngspice, "-b", str(net)], capture_output=True, text=True, timeout=300)
        if not out.exists():
            raise RuntimeError(r.stdout[-800:] + r.stderr[-800:])
        rows = [ln.split() for ln in out.read_text().splitlines()[1:] if ln.strip()]
    t = [float(x[0]) - t0 for x in rows]
    v = [float(x[1]) for x in rows]
    m = M.metrics(drv, edge, t, v, T, drv.ramp(edge), drv.vcc, 0.05, dt)
    # waveform difference on 155's own time grid (linear interpolation of the ngspice samples)
    import bisect
    def interp(tq):
        j = bisect.bisect_left(t, tq)
        if j <= 0:
            return v[0]
        if j >= len(t):
            return v[-1]
        return v[j - 1] + (v[j] - v[j - 1]) * (tq - t[j - 1]) / (t[j] - t[j - 1])
    diffs = [interp(tq) - vq for tq, vq in zip(ref.t, ref.v_rx) if tq >= 0]
    max_abs = max(abs(x) for x in diffs)
    rms = math.sqrt(sum(x * x for x in diffs) / len(diffs))
    a = ref.metrics
    f = lambda x: None if x is None else round(x, 4)
    return {"model": key.split(":", 1)[1], "corner": corner, "edge": edge, "length_in": length_in, "c_pf": c_pf, "series_ohm": rs,
            "peak_v_155": f(a["peak_v"]), "peak_v_ngspice": f(m["peak_v"]), "trough_v_155": f(a["trough_v"]), "trough_v_ngspice": f(m["trough_v"]),
            "rise2080_ns_155": f(a["rise_2080_ns"]), "rise2080_ns_ngspice": f(m["rise_2080_ns"]),
            "waveform_max_abs_diff_v": f(max_abs), "waveform_rms_diff_v": f(rms),
            "settle_ns_155": f(a["settle_ns"]), "settle_ns_ngspice": f(m["settle_ns"]),
            "dpeak_v": f(m["peak_v"] - a["peak_v"]), "dtrough_v": f(m["trough_v"] - a["trough_v"])}


CASES = [("artix7:LVCMOS33_F_8_HR", 6, 0), ("artix7:LVCMOS33_F_8_HR", 6, 33), ("artix7:LVCMOS33_F_12_HR", 10, 22), ("artix7:LVCMOS33_S_16_HR", 3, 0),
         ("artix7:LVCMOS25_F_8_HR", 6, 22), ("artix7:LVCMOS25_F_12_HR", 10, 0)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngspice", default=str(Path.home() / ".local/opt/ngspice-47/bin/ngspice"))
    ap.add_argument("--out", default=str(ROOT / "results/162_kr260_si/ngspice_check.csv"))
    ap.add_argument("--keys", nargs="*")
    a = ap.parse_args()
    lib = M.library()["models"]
    cases = list(CASES)
    # add a UltraScale+ HP LVCMOS18 case if the model name exists
    for k in lib:
        if k.endswith("LVCMOS18_F_12_HP") or k.endswith("LVCMOS18_S_12_HP"):
            cases += [(k, 6, 22), (k, 10, 0)]
            break
    rows = []
    for key, ln, rs in cases:
        if key not in lib:
            continue
        for corner in M.CORNERS:
            for edge in ("r", "f"):
                rows.append(run_case(a.ngspice, key, corner, edge, ln, 5.0, rs))
        print(key, ln, rs, flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
