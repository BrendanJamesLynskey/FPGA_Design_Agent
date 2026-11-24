#!/usr/bin/env python3
"""What an FPGA output does to a line and a receiver (brief 155): driver from AMD's IBIS data, line, load, in the time domain.

    python3 flow/offchip_model.py --family artix7 --std LVCMOS33 --drive 8 --slew SLOW --z0 50 --length-in 6 --rs 22

The driver is AMD's own IBIS output model, kept as the pull-up and pull-down V-I curves sampled at 21 voltages for each
corner (typ, min, max), the die capacitance and the 20-80 % edge time (``flow/offchip_data/driver_models.json``, derived
by ``tools/ibis_extract.py``; the IBIS files themselves are not committed). The line is lossless (characteristic
impedance ``z0``, delay from length and ``er_eff``); the load is a capacitance with optional resistors (to ground, to
VCCO, to VTT = VCCO/2) and an AC branch; an optional series resistor sits at the source.

How it computes (the method of characteristics, i.e. the bounce diagram with a non-linear source and a lumped load):

    V1(t) = H1(t) + Z0*I1(t)      H1(t) = V2(t-T) + Z0*I2(t-T)        I1, I2 = current INTO the line at each end
    V2(t) = H2(t) + Z0*I2(t)      H2(t) = V1(t-T) + Z0*I1(t-T)

At the far end the load is linear (backward-Euler capacitors) so V2 is closed form. At the source the current is the root
of one monotone, piecewise-linear equation (the driver curve, the pad capacitance and the series resistor), solved by a
safeguarded Newton step. The switching current is ``Ku(t)*pullup(VCC-V) + Kd(t)*pulldown(V)`` with Ku and Kd a smooth-step
pair; the ramp time is calibrated once per model and corner so the driver into IBIS's own 50 ohm fixture reproduces
IBIS's 20-80 % time (the committed file holds no waveform).

What this does NOT model (so a user does not assume it does):

* package parasitics (the IBIS package L and C) and the receiver's own clamp diodes: overshoot is reported unclamped, which is
  the conservative reading against the absolute-maximum table;
* loss and dispersion in the line (lossless: right for a few inches of FR-4 at these edge rates, optimistic for long ones);
* crosstalk and simultaneous switching noise (see ``SLEW`` in docs/offchip_io.md: SSN is reasoned, not simulated here);
* the series resistor is ideal (no parasitic C or L) and sits at the pad.

``bounce`` and ``electrically_short`` follow the owner's Signal Integrity models (``Matrix_Articles/si_models/tline.py``,
brief 155 copies the formulas so the flow does not depend on that folder; the test cross-checks them against it when it is
present).
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent / "offchip_data" / "driver_models.json"
C0 = 299792458.0
INCH = 0.0254
CORNERS = ("typ", "min", "max")          # IBIS column order; min is the WEAK corner, max the STRONG one
CORNER_NAME = {"typ": "typical", "min": "weak (IBIS min: slow, low VCCO, hot)", "max": "strong (IBIS max: fast, high VCCO, cold)"}


# --- driver data -----------------------------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def library() -> dict[str, Any]:
    return json.loads(DATA.read_text())


def model_key(family: str, std: str, drive: int, slew: str, bank: str = "") -> str | None:
    """The library key for a family ('artix7', 'zynq', 'zynquplus'), standard, DRIVE (mA) and slew ('SLOW'/'MEDIUM'/'FAST').

    7-series HR banks use the artix7 file (``LVCMOS33_S_8_HR``); Zynq-7000 HP banks the zynq file; UltraScale+ the
    zynquplus file with ``HP_`` or ``HD_`` in front (bank 'HP' or 'HD'; LVCMOS33 only exists in HD banks)."""
    letter = {"SLOW": "S", "MEDIUM": "M", "FAST": "F"}[slew.upper()]
    lib = library()["models"]
    if family == "zynquplus":
        for pre in ([bank + "_"] if bank else ["HP_", "HD_"]):
            k = f"zynquplus:{pre}{std}_{letter}_{drive}"
            if k in lib:
                return k
        return None
    if family == "zynq" and bank == "HP":
        k = f"zynq:{std}_{letter}_{drive}_HP"
        return k if k in lib else None
    k = f"artix7:{std}_{letter}_{drive}_HR"
    return k if k in lib else None


class Curve:
    """Piecewise-linear I(V), clamped (flat) outside its table; ``eval`` gives the value and the slope."""

    def __init__(self, pts: list[list[float]], col: int):
        self.x = [p[0] for p in pts]
        self.y = [p[col] for p in pts]

    def eval(self, v: float) -> tuple[float, float]:
        x, y = self.x, self.y
        if v <= x[0]:
            return y[0], 0.0
        if v >= x[-1]:
            return y[-1], 0.0
        i = bisect.bisect_right(x, v) - 1
        s = (y[i + 1] - y[i]) / (x[i + 1] - x[i])
        return y[i] + s * (v - x[i]), s


@dataclass
class Driver:
    """One output model at one corner."""
    name: str
    corner: str
    vcc: float
    pu: Curve
    pd: Curve
    c_comp: float
    t2080_r: float
    t2080_f: float
    vinl: float
    vinh: float
    r_load_ibis: float = 50.0
    _ramp: dict = field(default_factory=dict)

    def idev(self, vp: float, ku: float, kd: float) -> tuple[float, float]:
        """Current INTO the device at pad voltage vp and its slope (IBIS sign: sourcing current is negative)."""
        ipu, spu = self.pu.eval(self.vcc - vp)
        ipd, spd = self.pd.eval(vp)
        return ku * ipu + kd * ipd, -ku * spu + kd * spd

    def ramp(self, edge: str) -> float:
        if edge not in self._ramp:
            self._ramp[edge] = _calibrate_ramp(self, edge)
        return self._ramp[edge]


class LinearDriver(Driver):
    """An ideal driver of constant output resistance (used to check the solver against the bounce diagram)."""

    def __init__(self, vcc: float, r_out: float, t_ramp: float = 1e-12, vinl: float = 0.8, vinh: float = 2.0):
        self.name, self.corner, self.vcc, self.c_comp = f"linear {r_out:g} ohm", "typ", vcc, 0.0
        self.vinl, self.vinh, self.t2080_r, self.t2080_f, self._ramp = vinl, vinh, 0.6 * t_ramp, 0.6 * t_ramp, {"r": t_ramp, "f": t_ramp}
        self.r_out = r_out

    def idev(self, vp: float, ku: float, kd: float) -> tuple[float, float]:
        g = 1.0 / self.r_out
        return ku * (-(self.vcc - vp) * g) + kd * (vp * g), g * (ku + kd)


def get_driver(key: str, corner: str = "typ") -> Driver:
    m = library()["models"][key]
    c = CORNERS.index(corner)
    return Driver(name=key.split(":", 1)[1], corner=corner, vcc=m["vcc"][c], pu=Curve(m["pullup"], c + 1),
                  pd=Curve(m["pulldown"], c + 1), c_comp=m["c_comp_f"][c], t2080_r=m["t2080_s"]["r"][c],
                  t2080_f=m["t2080_s"]["f"][c], vinl=m["vinl"], vinh=m["vinh"], r_load_ibis=m["t2080_s"].get("r_load", 50.0))


def source_for(key: str) -> dict[str, str]:
    """Where a driver's numbers come from (file, rev, date, model), for every table that quotes them."""
    lib = library()
    fam = key.split(":", 1)[0]
    s = lib["_source"][fam]
    return {"file": s["file"], "ibis_ver": s["IBIS ver"], "file_rev": s["File Rev"], "date": s["Date"], "model": key.split(":", 1)[1]}


# --- the steady-state view: effective output resistance ----------------------------------------------------------------------

def _solve_monotone(f, lo: float, hi: float, n: int = 60) -> float:
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def r_launch(drv: Driver, z_load: float) -> dict[str, float]:
    """Effective output resistance of each half of the driver, as the wave it launches into ``z_load`` sees it.

    Rising edge: the pull-up drives ``z_load`` from rest at 0 V. Its launched voltage V solves ``-pullup(VCC-V) = V/z_load`` and the
    effective (chord) resistance is ``(VCC-V)/I``. Falling edge: the pull-down drives a line at VCC; V solves
    ``pulldown(V) = (VCC-V)/z_load``, resistance ``V/I``. The chord, not the slope: a LVCMOS output is a current-limited
    source, so its resistance depends on how far down the curve the load pulls it (it is NOT one number per DRIVE).
    ``r_small_*`` is the slope resistance at the same point (what a small ripple sees); ``r_rail_*`` is the chord resistance 0.1 V from the rail
    the half is pulling to, where the output is in its linear region: the pull-down of a DRIVE 8 output is about 40 ohm while it launches and
    about 15 ohm near ground, which is why the later reflections are damped less than the launch resistance suggests."""
    vcc = drv.vcc
    fu = lambda v: -drv.pu.eval(vcc - v)[0] - v / z_load      # >0 when the pull-up supplies more than the load takes
    vu = _solve_monotone(lambda v: -fu(v), 0.0, vcc)
    iu = vu / z_load
    fd = lambda v: drv.pd.eval(v)[0] - (vcc - v) / z_load
    vd = _solve_monotone(fd, 0.0, vcc)
    idn = (vcc - vd) / z_load
    su = abs(drv.pu.eval(vcc - vu)[1]) or 1e-9
    sd = abs(drv.pd.eval(vd)[1]) or 1e-9
    return {"r_pu": (vcc - vu) / iu if iu > 0 else float("inf"), "v_launch_rise": vu,
            "r_pd": vd / idn if idn > 0 else float("inf"), "v_launch_fall": vd,
            "r_small_pu": 1.0 / su, "r_small_pd": 1.0 / sd,
            # near the rail (0.1 V from VCC for the pull-up, 0.1 V from ground for the pull-down) the output is in its linear region: this is the
            # resistance the driver presents to the later reflections, much lower than the launch resistance for a current-limited output
            "r_rail_pu": 0.1 / max(abs(drv.pu.eval(0.1)[0]), 1e-9), "r_rail_pd": 0.1 / max(abs(drv.pd.eval(0.1)[0]), 1e-9),
            "i_sat_pu": max(-y for y in drv.pu.y),
            "i_sat_pd": max(drv.pd.y)}


# --- time domain ---------------------------------------------------------------------------------------------------------

def _smooth(x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return x * x * (3 - 2 * x)


def _calibrate_ramp(drv: Driver, edge: str) -> float:
    """The switching ramp time so that the driver into IBIS's 50 ohm fixture (to ground) takes the IBIS 20-80 % time."""
    target = drv.t2080_r if edge == "r" else drv.t2080_f
    lo, hi = target * 0.2, target * 8.0
    for _ in range(26):
        mid = 0.5 * (lo + hi)
        t = _fixture_2080(drv, edge, mid)
        if t > target:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def _fixture_wave(drv: Driver, edge: str, t_ramp: float, dt: float, n: int, r_fix: float):
    # start at the settled state: rising from 0 V; falling from the settled high level
    vp = 0.0
    if edge == "f":
        vp = _dc_pad(drv, 1.0, 0.0, r_fix)
    vprev, out = vp, []
    for i in range(n):
        s = _smooth(i * dt / t_ramp)
        ku, kd = (s, 1 - s) if edge == "r" else (1 - s, s)
        vn = vprev
        for _ in range(40):                         # solve  -idev(v) = v/r + c (v - vprev)/dt
            idv, sl = drv.idev(vn, ku, kd)
            f = -idv - vn / r_fix - drv.c_comp * (vn - vprev) / dt
            df = -sl - 1 / r_fix - drv.c_comp / dt
            step = f / df
            vn -= step
            if abs(step) < 1e-9:
                break
        out.append(vn)
        vprev = vn
    return out


def _dc_pad(drv: Driver, ku: float, kd: float, r_load: float) -> float:
    return _solve_monotone(lambda v: drv.idev(v, ku, kd)[0] + v / r_load, -0.5, drv.vcc + 0.5)


def _fixture_2080(drv: Driver, edge: str, t_ramp: float) -> float:
    dt = max(t_ramp / 200, 1e-12)
    n = int(max(8 * t_ramp, 4e-9) / dt)
    w = _fixture_wave(drv, edge, t_ramp, dt, n, drv.r_load_ibis)
    lo_v, hi_v = (min(w), w[-1]) if edge == "r" else (w[-1], max(w))
    a, b = lo_v + 0.2 * (hi_v - lo_v), lo_v + 0.8 * (hi_v - lo_v)
    if edge == "f":
        a, b = b, a

    def when(level: float) -> float | None:
        for i in range(1, len(w)):
            if (edge == "r" and w[i - 1] < level <= w[i]) or (edge == "f" and w[i - 1] > level >= w[i]):
                return (i - 1 + (level - w[i - 1]) / (w[i] - w[i - 1])) * dt       # linear interpolation inside the step
        return None

    ta, tb = when(a), when(b)
    return (tb - ta) if ta is not None and tb is not None else 0.0


@dataclass
class Line:
    z0: float = 50.0
    length_in: float = 6.0
    er_eff: float = 3.2          # microstrip on FR-4 ~3.1-3.3 (about 150 ps/in); stripline ~4 (about 170 ps/in)

    @property
    def delay_s(self) -> float:
        return self.length_in * INCH * math.sqrt(self.er_eff) / C0


@dataclass
class Load:
    c_pf: float = 3.0            # receiver pin and trace stub capacitance at the far end
    r_gnd: float | None = None   # parallel termination to ground
    r_vcc: float | None = None   # to VCCO (a Thevenin termination has r_vcc = r_gnd = 2*Z0)
    r_vtt: float | None = None   # to VTT = VCCO/2 (the SSTL/HSTL "parallel to VTT")
    ac_r: float | None = None    # AC termination: R in series with ac_c to ground
    ac_c_pf: float = 100.0


@dataclass
class Result:
    edge: str
    t: list[float]
    v_rx: list[float]
    v_pad: list[float]
    t0: float
    metrics: dict[str, Any]


def simulate(drv: Driver, line: Line, load: Load, rs: float = 0.0, edge: str = "r", dt_target: float = 20e-12,
             vcco: float | None = None, band: float = 0.05, pre_t: int = 10, run_t: float = 24.0) -> Result:
    """One edge (``'r'`` rising, ``'f'`` falling) from the driver pad through ``rs`` and the line to the load.

    Returns the far-end (receiver) waveform and its metrics (see :func:`metrics`)."""
    vcco = drv.vcc if vcco is None else vcco
    z0, T = line.z0, max(line.delay_s, 1e-12)
    t_ramp = drv.ramp(edge)
    dt_target = min(dt_target, t_ramp / 16)
    n = max(1, math.ceil(T / dt_target))
    dt = T / n
    vtt = 0.5 * vcco
    g_gnd = 1 / load.r_gnd if load.r_gnd else 0.0
    g_vcc = 1 / load.r_vcc if load.r_vcc else 0.0
    g_vtt = 1 / load.r_vtt if load.r_vtt else 0.0
    cl = load.c_pf * 1e-12
    acr = load.ac_r
    acc = load.ac_c_pf * 1e-12
    g_ac = 1 / (acr + dt / acc) if acr else 0.0
    cc = drv.c_comp
    zs = z0 + rs

    n_pre = pre_t * n
    n_run = n_pre + int((t_ramp + run_t * T + (8e-9 if run_t > 8 else 0.0)) / dt)
    # initial (rest) state: all voltages at the logic level the pad rests at
    v_init = 0.0 if edge == "r" else vcco
    ku0, kd0 = (0.0, 1.0) if edge == "r" else (1.0, 0.0)
    v1h = [v_init] * (n + 1)          # V1 history ring (V at end 1), index t-T
    i1h = [0.0] * (n + 1)
    v2h = [v_init] * (n + 1)
    i2h = [0.0] * (n + 1)
    vpp = v_init
    v2p = v_init
    vc_ac = v_init
    t_out, v_rx, v_pad = [], [], []
    t0 = n_pre * dt
    i1 = 0.0
    for k in range(n_run):
        t = k * dt
        s = _smooth((t - t0) / t_ramp)
        ku, kd = (ku0, kd0) if t < t0 else ((s, 1 - s) if edge == "r" else (1 - s, s))
        slot = k % (n + 1)
        old = (k - n) % (n + 1) if k >= n else None
        h1 = (v2h[old] + z0 * i2h[old]) if old is not None else v_init + 0.0
        h2 = (v1h[old] + z0 * i1h[old]) if old is not None else v_init + 0.0
        # far end: linear load, V2 closed form
        gl = cl / dt + g_gnd + g_vcc + g_vtt + g_ac
        jl = (cl / dt) * v2p + g_vcc * vcco + g_vtt * vtt + (g_ac * vc_ac if acr else 0.0)
        v2 = (h2 + z0 * jl) / (1 + z0 * gl)
        i_load = gl * v2 - jl
        i2 = -i_load
        if acr:
            vc_ac += dt / acc * ((v2 - vc_ac) * g_ac)
        # source end: I1 into the line;  F(I1) = I1 + idev(Vp) + cc (Vp - Vpp)/dt = 0,  Vp = H1 + zs I1
        lo, hi = -0.3, 0.3
        x = i1
        for _ in range(60):
            vp = h1 + zs * x
            idv, sl = drv.idev(vp, ku, kd)
            f = x + idv + cc * (vp - vpp) / dt
            if f > 0:
                hi = min(hi, x)
            else:
                lo = max(lo, x)
            df = 1 + zs * (sl + cc / dt)
            xn = x - f / df
            if not (lo < xn < hi):
                xn = 0.5 * (lo + hi)
            if abs(xn - x) < 1e-12:
                x = xn
                break
            x = xn
        i1 = x
        vp = h1 + zs * i1
        v1 = vp - rs * i1
        vpp = vp
        v2p = v2
        v1h[slot], i1h[slot], v2h[slot], i2h[slot] = v1, i1, v2, i2
        if k >= n_pre - 2 * n:
            t_out.append(t - t0)
            v_rx.append(v2)
            v_pad.append(vp)
    return Result(edge, t_out, v_rx, v_pad, 0.0, metrics(drv, edge, t_out, v_rx, T, t_ramp, vcco, band, dt))


def _cross(t: list[float], v: list[float], level: float, rising: bool, start: int = 0) -> int | None:
    for i in range(max(start, 1), len(v)):
        if (rising and v[i - 1] < level <= v[i]) or ((not rising) and v[i - 1] > level >= v[i]):
            return i
    return None


def metrics(drv: Driver, edge: str, t: list[float], v: list[float], T: float, t_ramp: float, vcco: float,
            band: float, dt: float) -> dict[str, Any]:
    """Receiver-side figures for one edge. t is time from the start of the driver's switching (>= 0 from index where t = 0)."""
    i0 = next(i for i, x in enumerate(t) if x >= 0)
    tt, vv = t[i0:], v[i0:]
    rising = edge == "r"
    vf = vv[-1]
    v0 = v[i0 - 1] if i0 else vv[0]
    swing = vf - v0
    out: dict[str, Any] = {"edge": edge, "v_final": vf, "v_start": v0, "swing": abs(swing)}
    peak, trough = max(vv), min(vv)
    out["peak_v"], out["trough_v"] = peak, trough
    out["over_vcco_v"] = peak - vcco                  # above the rail: the absolute-maximum question
    out["under_gnd_v"] = -trough                      # below ground
    out["overshoot_v"] = (peak - max(vf, v0)) if rising else (min(vf, v0) - trough)    # past the settled level in the edge direction
    # threshold crossings
    first = _cross(tt, vv, drv.vinh if rising else drv.vinl, rising)
    out["t_cross_ns"] = None if first is None else tt[first] * 1e9
    if first is None:
        out["ringback_margin_v"] = None
    else:
        tail = vv[first:]
        # ringback: after first reaching the threshold, how far back toward the other level does it come (margin vs the threshold)
        out["ringback_margin_v"] = (min(tail) - drv.vinh) if rising else (drv.vinl - max(tail))
    # first incident wave: sample just before the source reflection of the far-end reflection returns (t0 + 3T)
    t_edge = (drv.t2080_r if rising else drv.t2080_f) / 0.6      # 0-100 % equivalent of the IBIS 20-80 % time
    out["t_edge_ns"] = t_edge * 1e9
    if t_edge <= 2 * T:
        idx = min(len(tt) - 1, int(round((3 * T - 2 * dt) / dt)))
        vfi = vv[idx]
        out["v_first_incident"] = vfi
        out["first_incident_margin_v"] = (vfi - drv.vinh) if rising else (drv.vinl - vfi)
        out["lumped"] = False
    else:
        out["v_first_incident"] = None
        out["first_incident_margin_v"] = None         # a line shorter than half the edge: it is a lumped load, not waves
        out["lumped"] = True
        # slow or short: the receiver follows the edge (no staircase); the margin that matters is the settled level
    # settling inside +-band*VCCO of the final value
    tol = band * vcco
    last_out = None
    for i in range(len(vv) - 1, -1, -1):
        if abs(vv[i] - vf) > tol:
            last_out = i
            break
    out["settle_ns"] = 0.0 if last_out is None else (tt[min(last_out + 1, len(tt) - 1)]) * 1e9
    out["settled"] = last_out is None or last_out < 0.8 * len(vv)
    # 20-80 % rise of the settled swing at the receiver
    if abs(swing) > 0.05:
        a = v0 + 0.2 * swing
        b = v0 + 0.8 * swing
        ia, ib = _cross(tt, vv, a, rising), _cross(tt, vv, b, rising)
        out["rise_2080_ns"] = None if ia is None or ib is None else (tt[ib] - tt[ia]) * 1e9
    else:
        out["rise_2080_ns"] = None
    out["reaches_threshold"] = first is not None
    # time spent beyond the recommended-operating range VCCO+0.2 V / GND-0.2 V (DS181 Table 2 note; Tables 4, 6, 7 give the allowed share of a UI)
    out["t_over_roc_ns"] = sum(dt for x in vv if x > vcco + 0.2) * 1e9
    out["t_under_roc_ns"] = sum(dt for x in vv if x < -0.2) * 1e9
    # peak-to-peak ringing after the first arrival of the final level
    ia = _cross(tt, vv, v0 + 0.9 * swing, rising) if abs(swing) > 0.05 else None
    out["ring_pp_v"] = None if ia is None else max(vv[ia:]) - min(vv[ia:])
    return out


def first_incident(drv: Driver, line: Line, load: Load, rs: float, edge: str, vcco: float | None = None) -> dict[str, float]:
    """The receiver's first-incident level, whatever the real line length: the same driver, series resistor and load on a line made
    long enough that no source reflection returns before the switching ramp is over, read just before the round trip ends (3T).

    This is the level a staircase would dwell at (a weak driver with R_out + Rs above Z0 launches less than half the swing, so an
    open receiver waits for its own reflection to come back). Whether the real line shows it is a separate question: it does when the
    edge is shorter than the round trip (``metrics['lumped']`` is False)."""
    t_ramp = drv.ramp(edge)
    t_aux = max(line.delay_s, 0.5 * (t_ramp + 3e-9))
    aux = Line(line.z0, 1.0, line.er_eff)
    aux.length_in = t_aux * C0 / math.sqrt(line.er_eff) / INCH
    res = simulate(drv, aux, load, rs, edge, vcco=vcco, pre_t=4, run_t=3.4)
    t, v = res.t, res.v_rx
    i0 = next(i for i, x in enumerate(t) if x >= 0)
    dt = t[i0 + 1] - t[i0]
    idx = min(len(v) - i0 - 1, int(round((3 * t_aux - 2 * dt) / dt)))
    vfi = v[i0 + idx]
    return {"v_first_incident": vfi, "margin_v": (vfi - drv.vinh) if edge == "r" else (drv.vinl - vfi)}


def both_edges(drv: Driver, line: Line, load: Load, rs: float = 0.0, **kw: Any) -> dict[str, Result]:
    return {e: simulate(drv, line, load, rs, e, **kw) for e in ("r", "f")}


# --- the lattice (bounce) diagram, for linear drivers --------------------------------------------------------------------------

def bounce(zs: float, z0: float, zl: float, n: int = 12) -> dict[str, Any]:
    """The reflection series on a mismatched line, term by term (the owner's ``tline.bounce``; copied with attribution).

    A source of impedance ``zs`` drives a line ``z0`` ending in ``zl``. The launched step is divided by the source divider
    and each arrival at an end is multiplied by that end's reflection coefficient. Voltages are per unit of the source
    step; ``steps[k]`` is the load voltage after the k-th round trip (arrival at odd multiples of the one-way delay)."""
    gl = (zl - z0) / (zl + z0) if math.isfinite(zl) else 1.0
    gs = (zs - z0) / (zs + z0)
    a0 = z0 / (z0 + zs)
    steps, v, amp = [], 0.0, a0
    for k in range(n):
        v += amp
        amp *= gl
        v += amp
        steps.append({"t_units": 2 * k + 1, "v_load": v})
        amp *= gs
    return {"gamma_load": gl, "gamma_source": gs, "v_final": (1.0 if not math.isfinite(zl) else zl / (zl + zs)), "steps": steps}


def electrically_short(tr_s: float, length_m: float, v0: float) -> dict[str, Any]:
    """The owner's ``tline.electrically_short``: how many rise times fit in the round trip; critical length = v*tr/12 (round trip
    under a sixth of the rise time, the usual lumped rule)."""
    tpd = length_m / v0
    return {"one_way_delay_s": tpd, "round_trip_s": 2 * tpd, "ratio_round_trip_to_tr": 2 * tpd / tr_s,
            "lumped_by_sixth_rule": bool(2 * tpd < tr_s / 6.0), "critical_length_m": v0 * tr_s / 12.0}


def critical_length_in(t_rise_s: float, er_eff: float = 3.2) -> float:
    return electrically_short(t_rise_s, 1.0, C0 / math.sqrt(er_eff))["critical_length_m"] / INCH


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--family", default="artix7")
    ap.add_argument("--std", default="LVCMOS33")
    ap.add_argument("--drive", type=int, default=8)
    ap.add_argument("--slew", default="SLOW")
    ap.add_argument("--bank", default="")
    ap.add_argument("--z0", type=float, default=50.0)
    ap.add_argument("--length-in", type=float, default=6.0)
    ap.add_argument("--c-pf", type=float, default=3.0)
    ap.add_argument("--rs", type=float, default=0.0)
    ap.add_argument("--r-gnd", type=float, default=None)
    a = ap.parse_args(argv)
    key = model_key(a.family, a.std, a.drive, a.slew, a.bank)
    if key is None:
        raise SystemExit("no IBIS model for that combination")
    print("source:", source_for(key))
    for corner in CORNERS:
        d = get_driver(key, corner)
        rl = r_launch(d, a.z0 + a.rs)
        res = both_edges(d, Line(a.z0, a.length_in), Load(a.c_pf, a.r_gnd), a.rs)
        print(f"{corner}: R_pu {rl['r_pu']:.1f} R_pd {rl['r_pd']:.1f} ohm (chord at Z0+Rs); " +
              "; ".join(f"{e}: over_vcco {r.metrics['over_vcco_v']:+.2f} V, under_gnd {r.metrics['under_gnd_v']:+.2f} V, "
                        f"first-incident margin {r.metrics['first_incident_margin_v']}, settle {r.metrics['settle_ns']:.1f} ns"
                        for e, r in res.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def r_mid(drv: Driver, frac: float = 0.5) -> dict[str, float]:
    """Slope resistance of the pull-up and pull-down at the pad voltage ``frac*VCC`` (the mid-rail point an SSTL/HSTL
    output works around, where DCI sets the impedance): the number an impedance-controlled output is specified by."""
    v = frac * drv.vcc
    su = abs(drv.pu.eval(drv.vcc - v)[1]) or 1e-9
    sd = abs(drv.pd.eval(v)[1]) or 1e-9
    return {"r_pu": 1.0 / su, "r_pd": 1.0 / sd}
