"""Behavioural model of the loop-timing frequency tracker (brief 96F): a paper study, nothing here is RTL and nothing ran on a board.

The idea under study: the transmit clock of the GTH is steered to the frequency of the clock recovered from the partner, so that both
are equal by construction and no rate matching is needed. The steering is the QPLL's fractional-N divider (UG576 v1.7.1 section "Dynamic
Frac-N for UltraScale+ FPGAs", pages 56 to 58), written through SDM0DATA with an SDM0TOGGLE strobe.

What is modelled (every figure is an input in ``Params``; the ones marked ASSUMED are not from a document):

* the plant: the phase ``phi`` (ns) of the transmit parallel clock relative to the shared user clock is the integral of the frequency
  difference, ``dphi/dt = 1000 * (p - u)`` ns/s with ``p`` the partner's offset and ``u`` the transmit offset (both ppm);
* the actuator: ``u`` is the fractional part of the QPLL feedback divider, ``N.SDMDATA / 2**24`` (UG576 Equations 2-5, 2-6, Table 2-13: SDMWIDTH 24),
  so one least-significant bit is ``2**-24 / N`` of the VCO, 0.9 ppb for N = 66; it is applied ``latency_ticks`` updates after it is written;
* the window: with a fixed 156.25 MHz reference N is exactly 66.0 at the nominal 10.3125 Gb/s, so the fraction can only move the VCO one way
  from the nominal (``N = 66`` with a positive fraction, or ``N = 65`` with a fraction just below 1 for the other way). The model has two
  windows (``fixed_ref``) or one centred window (``centred_ref``, a reference that sits mid-range, as the article the brief cites uses);
* the observable: the fabric sees the phase only as a count of whole clock cycles (a cycle counter difference between the two domains),
  so the phase detector has one clock (6.2061 ns) of quantisation plus an ASSUMED jitter;
* the controller: acquire (estimate ``p`` from the phase slope over ``acq_ms``), set ``u``, close a proportional-plus-integral loop
  (``kp``, ``ki`` from a natural frequency and damping), clamp to the window, hold the SDM value constant between updates.

What is not modelled: the GT's own phase-alignment circuit (its behaviour under a continuous frequency difference is not in UG576),
the QPLL's own bandwidth and jitter, the CDR, and any dependence of the recovered clock on our transmitter (except the loopback scenario,
where the recovered clock is a delayed copy of ours).
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field, replace

import numpy as np

T_CLK_NS = 1e9 / 161.1328125e6              # core clock period, 6.2061 ns
SDM_BITS = 24                                # UG576 Table 2-13 / Equation 2-6: SDMWIDTH 16, 20 or 24
N_FBDIV = 66                                 # 10.3125 GHz VCO / 156.25 MHz reference
LSB_PPM = 1e6 * 2.0 ** -SDM_BITS / N_FBDIV   # 0.00090 ppm per SDMDATA step
DYN_LIMIT_PPM = 200.0                        # UG576 p.58: more than 200 ppm from the VCO frequency at the last QPLL reset needs a QPLL reset
HALF_RANGE_NS = 2.0                          # delay-alignment tap: full range +-4 ns, half range +-2 ns (UG576 p.138, RXPHDLY_CFG p.259)
FULL_RANGE_NS = 4.0


@dataclass(frozen=True)
class Params:
    tick_us: float = 100.0            # ASSUMED: controller update period (10 kHz); the SDM handshake needs only about 1 us (UG576 Table 2-16)
    latency_ticks: int = 2            # ASSUMED: ticks from measurement to the new fraction taking effect
    jitter_ns: float = 0.3            # ASSUMED: rms jitter added to the phase measurement; not measured
    fn_hz: float = 100.0              # loop natural frequency
    zeta: float = 1.0                 # damping
    acq_ms: float = 5.0               # acquisition: slope of the phase over this time sets the first u
    window: str = "fixed_ref"         # "fixed_ref" (two one-sided windows) or "centred_ref" (one window around 0)
    window_span_ppm: float = 200.0    # reachable span of one window; at most DYN_LIMIT_PPM
    deadband_ns: float = 0.0          # loopback guard: errors smaller than this are ignored
    leak_per_s: float = 0.0           # loopback guard: the integral leaks toward the acquisition value at this rate
    seed: int = 1
    hop_outage_ms: float = 20.0       # ASSUMED: QPLL reset, relock and TX realignment when the window is changed
    pd_res_ns: float = T_CLK_NS       # phase detector resolution: one core clock; a quarter clock if four clock phases are sampled (ASSUMED feasible)
    acq: str = "counter"              # "counter": the existing RXV27/28 window (2**24 core clocks, 0.1 ppm); "slope": phase slope over acq_ms
    guard_ppm: float = 0.0            # holdover guard: u may move at most this far from the acquired value (0 = off)
    txpi_bias_ppm: float = 61.04      # fixed_ref_txpi: the TX phase interpolator's first coarse step (UG576 Table 3-33 formula, measured in 96C)


def window_bounds(win: int, p: Params) -> tuple[float, float]:
    """The reachable u (ppm) of window ``win``: 0 = centred / upper (N = 66, fraction >= 0), 1 = lower (N = 65, fraction < 1)."""
    span = min(p.window_span_ppm, DYN_LIMIT_PPM)
    if p.window == "centred_ref":
        return -span, span
    if p.window == "fixed_ref_txpi":      # two overlapping windows, N = 66 with a fraction >= 0 in both, moved by a static TXPI ppm code
        b = -p.txpi_bias_ppm * (1 + win)
        return b, b + span
    return (0.0, span) if win == 0 else (-span, 0.0)


def gains(p: Params) -> tuple[float, float]:
    """kp (ppm/ns) and ki (ppm/(ns s)) for dphi/dt = 1000 (p - u) with u = kp phi + ki integral(phi): wn^2 = 1000 ki, 2 zeta wn = 1000 kp."""
    wn = 2 * math.pi * p.fn_hz
    return 2 * p.zeta * wn / 1000.0, wn * wn / 1000.0


def quantise_u(u: float) -> float:
    return round(u / LSB_PPM) * LSB_PPM


def simulate(partner, seconds: float, p: Params, loopback: bool = False, closed_at_zero: bool = False, kicks=()) -> dict:
    """Run the tracker. ``partner(t)`` gives the partner's offset in ppm at time t (s). With ``loopback`` the recovered clock is our own
    transmit clock (a delayed copy of ``u``), so ``partner`` is ignored. Returns the metrics and a decimated trace."""
    rng = np.random.default_rng(p.seed)
    dt = p.tick_us * 1e-6
    n = int(round(seconds / dt))
    kp, ki = gains(p)
    phi = float(rng.uniform(0, T_CLK_NS))          # true phase, ns; starts anywhere inside one clock
    u_applied = 0.0
    pipe = [0.0] * max(p.latency_ticks, 1)
    win = 0
    # --- acquisition: phase slope over acq_ms, measured through the quantiser ---
    acq_s = (2 ** 24) * T_CLK_NS * 1e-9 if p.acq == "counter" else p.acq_ms * 1e-3
    n_acq = max(int(round(acq_s / dt)), 2)
    ph0 = None
    t = 0.0
    psum = 0.0
    for k in range(n_acq):
        pt = 0.0 if loopback else partner(t)
        psum += pt
        phi += 1000.0 * (pt - u_applied) * dt
        t += dt
        if k == 0:
            ph0 = round(phi / T_CLK_NS) * T_CLK_NS
    ph1 = round(phi / T_CLK_NS) * T_CLK_NS
    if p.acq == "counter":
        est = round((psum / n_acq) / 0.1) * 0.1          # RXV27 resolution: 1 count in 2**24
    else:
        est = (ph1 - ph0) / (1000.0 * (n_acq - 1) * dt)       # ppm
    if p.window == "fixed_ref" and not closed_at_zero:
        win = 0 if est >= 0 else 1
    if p.window == "fixed_ref_txpi":
        win = 0 if est >= -30.0 else 1
    lo, hi = window_bounds(win, p)
    u_cmd = quantise_u(min(max(est, lo), hi)) if not closed_at_zero else 0.0
    acq_value = u_cmd
    u_applied = u_cmd
    pipe = [u_cmd] * len(pipe)
    phi_ref = round(phi / T_CLK_NS) * T_CLK_NS            # the phase seen at loop closure is the set point
    integ = u_cmd
    # --- closed loop ---
    trace_t, trace_phi, trace_u = [], [], []
    err_hist = []
    outage_until = -1.0
    hops = 0
    sat_ticks = 0
    guard_hits = 0
    phi_max = 0.0
    out_half = out_full = 0
    u_series = []
    phi_series = []
    lag = int(round(2e-6 / dt)) if loopback else 0         # ASSUMED 2 us link delay in loopback (a fraction of a tick)
    u_hist = [u_applied] * (lag + 2)
    for k in range(n):
        t = n_acq * dt + k * dt
        pt = (u_hist[-1 - lag] if loopback else partner(t))
        # plant
        phi += 1000.0 * (pt - u_applied) * dt
        for kt, kn in kicks:
            if abs(t - kt) < dt / 2:
                phi += kn
        # measure
        meas = round((phi + rng.normal(0.0, p.jitter_ns)) / p.pd_res_ns) * p.pd_res_ns
        e = meas - phi_ref
        if abs(e) < p.deadband_ns:
            e = 0.0
        # window logic (fixed reference only): the demanded u wants to leave the window at its closed end
        lo, hi = window_bounds(win, p)
        integ += ki * e * dt - p.leak_per_s * (integ - acq_value) * dt
        u_dem = integ + kp * e
        if p.window == "fixed_ref" and t > outage_until:
            other = 1 - win
            # hop when the demand has been beyond the closed end of the window by more than 0.5 ppm: the sign of the partner changed
            if (win == 0 and u_dem < -0.5) or (win == 1 and u_dem > 0.5):
                win = other
                hops += 1
                outage_until = t + p.hop_outage_ms * 1e-3
                lo, hi = window_bounds(win, p)
        if p.window == "fixed_ref_txpi":                   # a TXPI code change is a ppm step that the same write cancels in the fraction: no outage
            if win == 0 and u_dem < -p.txpi_bias_ppm + 10.0:
                win = 1
                hops += 1
            elif win == 1 and u_dem > -2 * p.txpi_bias_ppm + 110.0:
                win = 0
                hops += 1
            lo, hi = window_bounds(win, p)
        if p.guard_ppm > 0.0:
            lo, hi = max(lo, acq_value - p.guard_ppm), min(hi, acq_value + p.guard_ppm)
            if u_dem < lo or u_dem > hi:
                guard_hits += 1
        if u_dem < lo or u_dem > hi:
            sat_ticks += 1
        u_cmd = min(max(u_dem, lo), hi)
        integ = min(max(integ, lo), hi)                    # anti-windup
        u_cmd = quantise_u(u_cmd)
        pipe.append(u_cmd)
        u_applied = pipe.pop(0)
        u_hist.append(u_applied)
        u_hist.pop(0)
        if t > outage_until:                               # during a hop the link is down: not counted as a phase error
            phi_max = max(phi_max, abs(phi - phi_ref))
            out_half += abs(phi - phi_ref) > HALF_RANGE_NS
            out_full += abs(phi - phi_ref) > FULL_RANGE_NS
        phi_series.append(phi - phi_ref)
        u_series.append(u_applied)
        if k % max(n // 400, 1) == 0:
            trace_t.append(round(t, 5))
            trace_phi.append(round(phi - phi_ref, 3))
            trace_u.append(round(u_applied, 4))
    ps = np.array(phi_series)
    us = np.array(u_series)
    tail = slice(len(ps) // 2, None)
    return {
        "acq_estimate_ppm": round(est, 3),
        "acq_window": win if p.window == "fixed_ref" else None,
        "max_abs_phase_ns": round(float(np.max(np.abs(ps))), 3),
        "max_abs_phase_ns_excl_hop_outage": round(phi_max, 3),
        "rms_phase_ns_second_half": round(float(np.sqrt(np.mean(ps[tail] ** 2))), 3),
        "mean_phase_ns_second_half": round(float(np.mean(ps[tail])), 3),
        "ticks_beyond_half_range_2ns": int(out_half),
        "ticks_beyond_full_range_4ns": int(out_full),
        "u_final_ppm": round(float(us[-1]), 4),
        "u_min_ppm": round(float(us.min()), 4),
        "u_max_ppm": round(float(us.max()), 4),
        "u_rms_noise_ppm_second_half": round(float(np.std(us[tail])), 4),
        "saturated_fraction": round(sat_ticks / n, 4),
        "window_hops": hops,
        "guard_hit_ticks": guard_hits,
        "trace": {"t_s": trace_t, "phase_ns": trace_phi, "u_ppm": trace_u},
    }


def counter_window_controller(partner, seconds: float, window_clocks: int = 2 ** 24, p: Params = Params()) -> dict:
    """The only frequency measurement the design has today: RXV27/RXV28, the receive clock's cycles in a window of 2**24 core clocks
    (0.1 ppm resolution, 104 ms). A controller built on it can correct only once a window. The phase runs open loop in between.
    Returns the peak |phase| for the given partner trajectory (the loop is a deadbeat: u <- the last measured offset)."""
    win_s = window_clocks * T_CLK_NS * 1e-9
    steps = int(seconds / 1e-5)
    phi = 0.0
    u = 0.0
    peak = 0.0
    t_next = win_s
    acc_p = 0.0
    n_in = 0
    for k in range(steps):
        t = k * 1e-5
        pt = partner(t)
        phi += 1000.0 * (pt - u) * 1e-5
        acc_p += pt
        n_in += 1
        peak = max(peak, abs(phi))
        if t >= t_next:
            u = quantise_u(round((acc_p / n_in) / 0.1) * 0.1)       # the counter's 0.1 ppm resolution
            acc_p, n_in = 0.0, 0
            t_next += win_s
    return {"window_ms": round(win_s * 1e3, 1), "peak_abs_phase_ns": round(peak, 1)}


def closed_loop(fn_hz: float, zeta: float) -> dict:
    """Phase transfer of the PI loop (partner phase to transmit phase): H = (2 zeta wn s + wn^2) / (s^2 + 2 zeta wn s + wn^2). Jitter of the
    partner's recovered clock above the -3 dB frequency is not passed to the transmitter; a G.8262 EEC passes 1 to 10 Hz (Option 1)."""
    wn = 2 * math.pi * fn_hz

    def mag(f: float) -> float:
        s_ = 1j * 2 * math.pi * f
        return abs((2 * zeta * wn * s_ + wn * wn) / (s_ * s_ + 2 * zeta * wn * s_ + wn * wn))

    fs = np.logspace(-1, 4, 4000)
    m = np.array([mag(f) for f in fs])
    f3 = float(fs[np.argmax(m < 10 ** (-3 / 20)) ]) if (m < 10 ** (-3 / 20)).any() else float("nan")
    return {"f_minus3dB_hz": round(f3, 1), "peaking_db": round(float(20 * np.log10(m.max())), 2),
            "gain_db_at_10hz": round(float(20 * np.log10(mag(10.0))), 1), "gain_db_at_100hz": round(float(20 * np.log10(mag(100.0))), 1),
            "gain_db_at_1khz": round(float(20 * np.log10(mag(1000.0))), 1)}


def _strip(r: dict) -> dict:
    r = dict(r)
    r.pop("trace", None)
    return r


def run_all() -> dict:
    base = Params()
    out: dict = {"assumptions": {
        "tick_us": base.tick_us, "latency_ticks": base.latency_ticks, "jitter_ns_rms": base.jitter_ns, "fn_hz": base.fn_hz,
        "zeta": base.zeta, "acq": base.acq, "sdm_lsb_ppm": round(LSB_PPM, 6), "t_clk_ns": round(T_CLK_NS, 4),
        "hop_outage_ms": base.hop_outage_ms, "dynamic_update_limit_ppm": DYN_LIMIT_PPM,
        "txpi_bias_ppm": base.txpi_bias_ppm,
        "alignment_half_range_ns": HALF_RANGE_NS, "alignment_full_range_ns": FULL_RANGE_NS,
        "note": "tick, latency, jitter and hop outage are ASSUMED; the SDM width, the 200 ppm limit and the alignment ranges are from UG576 v1.7.1",
    }}
    kinds = ("fixed_ref", "fixed_ref_txpi", "centred_ref")
    # A. static offsets, three reference arrangements, FLL (counter) acquisition then PI
    static = {}
    for kind in kinds:
        rows = {}
        for ppm in (-100.0, -50.0, -1.0, 0.0, 1.0, 50.0, 100.0):
            rows[f"{ppm:+.0f}"] = _strip(simulate(lambda t, ppm=ppm: ppm, 2.0, replace(base, window=kind)))
        static[kind] = rows
    out["A_static_offsets"] = static
    # A2. one window only (no hop): a partner below the nominal cannot be reached
    out["A2_start_in_the_upper_window_partner_at_minus_50"] = _strip(
        simulate(lambda t: -50.0, 2.0, replace(base, window="fixed_ref"), closed_at_zero=True))
    # B. slow drifts across zero
    drift = {}
    for rate in (0.01, 0.1, 1.0):
        secs = min(4.0 / rate if rate < 1.0 else 10.0, 60.0)
        rows = {}
        for kind in kinds:
            rows[kind] = _strip(simulate(lambda t, rate=rate: -2.0 + rate * t, secs, replace(base, window=kind, seed=2)))
        drift[f"{rate} ppm/s"] = rows
    out["B_drift_across_zero"] = drift
    # C. a step in the partner's offset (stress; a real oscillator does not do this), by loop bandwidth
    step = {}
    for fn in (10.0, 30.0, 100.0, 300.0):
        step[f"fn {fn:g} Hz"] = _strip(simulate(lambda t: 10.0 + (30.0 if t > 1.0 else 0.0), 2.0,
                                                replace(base, window="centred_ref", fn_hz=fn, seed=3)))
    out["C_step_30ppm"] = step
    # D. loopback: the recovered clock is our own transmit clock; a 6 ns phase kick at t = 1 s (a realignment or a bit slip) has no
    # frequency cause, and nothing in the loop can remove it: the integral runs away unless it is guarded
    loop = {}
    kick = ((1.0, 6.0),)
    loop["no_guard"] = _strip(simulate(lambda t: 0.0, 5.0, replace(base, window="centred_ref", seed=4), loopback=True, kicks=kick))
    loop["deadband_and_leak"] = _strip(simulate(lambda t: 0.0, 5.0, replace(base, window="centred_ref", seed=4, deadband_ns=T_CLK_NS * 0.75,
                                                                           leak_per_s=2.0), loopback=True, kicks=kick))
    loop["holdover_guard_5ppm"] = _strip(simulate(lambda t: 0.0, 5.0, replace(base, window="centred_ref", seed=4, guard_ppm=5.0),
                                                  loopback=True, kicks=kick))
    out["D_loopback_same_oscillator_with_a_6ns_phase_kick"] = loop
    # E. the existing frequency counter used as the whole controller
    out["E_frequency_counter_only_controller"] = {
        "step_1ppm_at_0.5s": counter_window_controller(lambda t: 1.0 if t > 0.5 else 0.0, 2.0),
        "ramp_0.1ppm_per_s": counter_window_controller(lambda t: 0.1 * t, 3.0),
        "static_50ppm_from_start": counter_window_controller(lambda t: 50.0, 2.0)}
    # F. bandwidth trade-off: static offset, real-oscillator drift 0.1 ppm/s, a 5 ppm step; one-clock and quarter-clock phase detector
    bw = {}
    for res_name, res in (("pd_one_clock", T_CLK_NS), ("pd_quarter_clock", T_CLK_NS / 4)):
        rows = {}
        for fn in (3.0, 10.0, 30.0, 100.0, 300.0):
            q = replace(base, window="centred_ref", fn_hz=fn, seed=5, pd_res_ns=res)
            st = _strip(simulate(lambda t: 20.0, 3.0, q))
            dr = _strip(simulate(lambda t: 0.1 * t, 10.0, replace(q, seed=6)))
            sp = _strip(simulate(lambda t: 5.0 + (5.0 if t > 1.0 else 0.0), 2.0, q))
            rows[f"fn {fn:g} Hz"] = {
                "static_rms_phase_ns": st["rms_phase_ns_second_half"], "static_u_noise_ppm": st["u_rms_noise_ppm_second_half"],
                "drift_0.1ppm_per_s_max_phase_ns": dr["max_abs_phase_ns"], "step_5ppm_max_phase_ns": sp["max_abs_phase_ns"],
                "closed_loop": closed_loop(fn, base.zeta)}
        bw[res_name] = rows
    out["F_bandwidth_trade_off"] = bw
    return out


if __name__ == "__main__":
    res = run_all()
    path = sys.argv[1] if len(sys.argv) > 1 else "loop_timing_model.json"
    with open(path, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    print("wrote", path)
