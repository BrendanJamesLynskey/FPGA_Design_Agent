"""Signal-chain overview (brief 19, section 7): a YAML chain of external converters and IP stages, two sets of numbers
per node (predicted from a noise budget; measured by running the bit-exact integer chain on test tones), the resources
from each IP's out-of-context run, and an SVG block diagram drawn from the committed result files.

    python3 -m flow.ipgen.chain <chain.yaml> <outdir>

numpy and scipy only. The integer stage models are the ones each adapter checked against its IP in xsim
(`sim.json` of the stage's results directory, `bit_exact` below); the chain itself is not simulated in xsim.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy import signal

from . import cic_design, fir_design
from .fir_adapter import fir_golden_full

# ------------------------------------------------------------------ the converter model (a PDM microphone)


def ntf_butterworth(order=3, hinf=1.5):
    """A noise transfer function with all zeros at DC and Butterworth poles, b0 = a0 = 1, its peak gain set to `hinf`
    (Lee's rule of thumb: about 1.5 keeps a 1-bit modulator stable). Returns (b, a)."""
    lo, hi = 1e-4, 0.45
    for _ in range(60):
        wc = 0.5 * (lo + hi)
        b, a = signal.butter(order, wc, btype="highpass")
        b = b / b[0]
        a = a / a[0]
        _, h = signal.freqz(b, a, worN=4096)
        if np.max(np.abs(h)) > hinf:
            hi = wc
        else:
            lo = wc
    return b, a


def pdm_modulate(u, b, a, return_error=False):
    """1-bit modulator in error-feedback form: y = u + NTF * e, e = y - w, y = +-1."""
    n = len(u)
    order = len(a) - 1
    y = np.empty(n)
    err = np.empty(n)
    e_hist = [0.0] * order
    s_hist = [0.0] * order
    ba = [b[k] - a[k] for k in range(1, order + 1)]
    ak = list(a[1:])
    for i in range(n):
        s = 0.0
        for k in range(order):
            s += ba[k] * e_hist[k] - ak[k] * s_hist[k]
        w = u[i] + s
        yi = 1.0 if w >= 0 else -1.0
        e = yi - w
        e_hist = [e] + e_hist[:-1]
        s_hist = [s] + s_hist[:-1]
        y[i] = yi
        err[i] = e
    if return_error:
        return y, err
    return y


# ------------------------------------------------------------------ measurements


def _bh(n):
    return signal.windows.blackmanharris(n, sym=False)


def spectrum(x, fs):
    """Windowed power spectrum (one-sided, scaled so a coherent tone of amplitude A has A^2/2 in its main lobe)."""
    n = len(x)
    w = _bh(n)
    X = np.fft.rfft(np.asarray(x, dtype=float) * w)
    # scaled so that the bins of a coherent tone of amplitude A sum to A^2/2 and white noise sums to its variance
    p = 2.0 * (np.abs(X) ** 2) / (n * np.sum(w ** 2))
    f = np.fft.rfftfreq(n, 1 / fs)
    return f, p


def tone_metrics(x, fs, tones_hz, band=(20.0, 20000.0), full_scale=1.0, lobe=5, n_harm=9):
    """SNR, SINAD, THD, SFDR, IMD3 and ENOB of a record with one or two coherent tones. Signal power = the main-lobe bins
    of every tone; noise and distortion = everything else in the band. THD is of the first tone's harmonics; SFDR is the
    first tone against the largest spur (the other tone excluded); IMD3 is 2f1-f2 and 2f2-f1 against the first tone.
    ENOB is full-scale referenced (IEEE 1241): (SINAD - 1.76 + 20 log10(FS / A)) / 6.02, A the amplitude of a single sine
    with the signal's total power."""
    f, p = spectrum(x, fs)
    df = f[1] - f[0]
    inband = (f >= band[0]) & (f <= band[1])

    def lobe_bins(f0):
        k = int(round(f0 / df))
        return np.arange(max(k - lobe, 0), min(k + lobe + 1, len(f)))

    sig_bins = lobe_bins(tones_hz[0])
    mask = inband.copy()
    all_sig = np.zeros_like(mask)
    for f_t in tones_hz:  # every tone is signal: SINAD of a two-tone record is (both tones) / (everything else)
        all_sig[lobe_bins(f_t)] = True
    sig = p[sig_bins].sum() if len(tones_hz) == 1 else p[all_sig].sum()
    sig1 = p[sig_bins].sum()
    mask[all_sig] = False
    harm = np.zeros_like(mask)
    harm_power = 0.0
    for h in range(2, n_harm + 1):
        fh = h * tones_hz[0]
        fh = fh % fs
        if fh > fs / 2:
            fh = fs - fh
        if band[0] <= fh <= band[1]:
            b = lobe_bins(fh)
            b = b[mask[b] & ~harm[b]]
            harm[b] = True
            harm_power += p[b].sum()
    noise_and_dist = p[mask].sum()
    pure_noise = noise_and_dist - harm_power
    # the spur search excludes the main lobe plus the pass band's few lowest bins
    spur_mask = mask.copy()
    spur_mask[f < band[0]] = False
    # largest single spur: the biggest 'lobe' of consecutive bins (sum of lobe width) outside the signal lobe
    smooth = np.convolve(np.where(spur_mask, p, 0.0), np.ones(2 * lobe + 1), mode="same")
    spur = float(np.max(smooth))
    a_db = 10 * math.log10(sig1 / (full_scale ** 2 / 2))  # level of the first tone, dBFS (sine, peak = FS)
    sinad = 10 * math.log10(sig / noise_and_dist)
    a_tot_db = 10 * math.log10(sig / (full_scale ** 2 / 2))
    imd3 = None
    if len(tones_hz) == 2:
        f1, f2 = tones_hz
        pw = 0.0
        for fi in (2 * f1 - f2, 2 * f2 - f1):
            if band[0] <= fi <= band[1]:
                bb = lobe_bins(fi)
                pw += p[bb].sum()
        imd3 = 10 * math.log10(max(pw, 1e-300) / sig1)
    out = {
        "tone_dbfs": a_db,
        "signal_total_dbfs": a_tot_db,
        "imd3_dbc": imd3,
        "sinad_db": sinad,
        "snr_db": 10 * math.log10(sig / max(pure_noise, 1e-300)),
        "thd_db": (10 * math.log10(harm_power / sig1)) if harm_power > 0 else None,
        "sfdr_db": 10 * math.log10(sig1 / spur),
        "enob_bits": (sinad - 1.76 - a_tot_db) / 6.02,
        "noise_floor_dbfs_inband": 10 * math.log10(max(pure_noise, 1e-300) / (full_scale ** 2 / 2)),
    }
    return out


# ------------------------------------------------------------------ predicted: the noise budget


def _fold_noise(f_grid, psd, fn, band):
    """Integrate a one-sided PSD (power/Hz) over a grid, folding each frequency down to a sampling rate `fn`; return the
    power that lands in `band`."""
    fold = np.abs(((f_grid + fn / 2) % fn) - fn / 2)
    sel = (fold >= band[0]) & (fold <= band[1])
    df = f_grid[1] - f_grid[0]
    return float(np.sum(psd[sel]) * df)


def characterise_modulator(chain, b_ntf, a_ntf, n=1 << 19):
    """The converter model's own shaped noise density: run the modulator on the reference tone with no mic noise and take
    the Welch PSD of y - u (= NTF * e exactly). This stands in for a data sheet's noise-density plot, which the real
    microphone's data sheet does not have. Returns (frequency grid, one-sided power/Hz)."""
    fs0 = chain["stages"][0]["rate_hz"]
    f0 = chain["cases"]["reference"]["tones_hz"][0]
    amp = 10 ** (chain["cases"]["reference"]["levels_dbfs"][0] / 20)
    u = amp * np.sin(2 * np.pi * f0 * np.arange(n) / fs0)
    y = pdm_modulate(u, b_ntf, a_ntf)
    q = (y - u)[4096:]
    f, pxx = signal.welch(q, fs=fs0, window="blackmanharris", nperseg=65536, noverlap=32768, detrend="constant")
    return f, pxx


def predicted(chain, cic, fir_coef, b_ntf, a_ntf):
    """Noise budget at each node (PDM, CIC output, FIR output): signal level after the droop at the tone, the mic's
    own noise (datasheet SNR at the datasheet level), the modulator's shaped quantisation noise (the converter model's
    measured noise density from `characterise_modulator`) and the aliasing of both through the CIC and the FIR.
    The data sheet gives only the total SNR, so the split between mic noise and quantisation noise is the model's."""
    mic = chain["stages"][0]
    fs0 = mic["rate_hz"]
    band = tuple(chain["band_hz"])
    f0 = chain["cases"]["reference"]["tones_hz"][0]
    a_dbfs = chain["cases"]["reference"]["levels_dbfs"][0]
    sig_amp = 10 ** (a_dbfs / 20)
    mic_noise_power = (sig_amp ** 2 / 2) / 10 ** (mic["snr_db"] / 10)  # in-band (20 Hz..20 kHz) white-noise power
    sigma_mic2 = mic_noise_power * (fs0 / 2) / (band[1] - band[0])    # so that white PSD x band = mic_noise_power
    f = np.linspace(1.0, fs0 / 2, 600000)
    psd_mic = np.full_like(f, sigma_mic2 / (fs0 / 2))                 # one-sided power/Hz
    fq, pq = characterise_modulator(chain, b_ntf, a_ntf)
    psd_q = np.interp(f, fq, pq)
    R1 = chain["stages"][1]["rate"]
    cic_h = cic_design.cic_mag(f, fs0, R1, cic["diff_delay"], cic["stages"])
    fs1 = fs0 / R1
    fir_h = np.abs(signal.freqz(fir_coef / np.sum(fir_coef), worN=np.mod(f, fs1), fs=fs1)[1])
    nodes = {}
    for name, H, fn in (("pdm", np.ones_like(f), fs0), ("cic", cic_h, fs1), ("fir", cic_h * fir_h, fs1 / chain["stages"][2]["decimation"])):
        n_mic = _fold_noise(f, psd_mic * H ** 2, fn, band)
        n_q = _fold_noise(f, psd_q * H ** 2, fn, band)
        h0 = float(np.interp(f0, f, H)) if name != "pdm" else 1.0
        if name == "pdm":
            h0 = 1.0
        else:
            h0 = float(cic_design.cic_mag(f0, fs0, R1, cic["diff_delay"], cic["stages"]))
            if name == "fir":
                h0 *= float(np.abs(signal.freqz(fir_coef / np.sum(fir_coef), worN=[f0], fs=fs1)[1][0]))
        sig_p = (sig_amp * h0) ** 2 / 2
        sinad = 10 * math.log10(sig_p / (n_mic * 1.0 + n_q)) if (n_mic + n_q) > 0 else None
        a_node = 20 * math.log10(sig_amp * h0)
        nodes[name] = {"signal_dbfs": a_node, "mic_noise_dbfs": 10 * math.log10(n_mic / 0.5),
                       "modulator_noise_dbfs": 10 * math.log10(n_q / 0.5),
                       "sinad_db": sinad, "enob_bits": (sinad - 1.76 - a_node) / 6.02}
    return nodes


# ------------------------------------------------------------------ the chain run


def load_json(p):
    return json.loads(Path(p).read_text())


def stage_ip_results(root: Path, rel: str) -> dict:
    d = Path(root) / rel
    out = {"dir": rel}
    for k in ("design", "readback", "sim", "ooc"):
        f = d / f"{k}.json"
        out[k] = load_json(f) if f.exists() else None
    return out


def fir_decim_phase(sim):
    return {s: r.get("decimation_phase") for s, r in (sim or {}).get("sim", {}).items()}


def run_cases(chain, cic, fir, outdir, root):
    mic = chain["stages"][0]
    fs0 = mic["rate_hz"]
    R1 = chain["stages"][1]["rate"]
    R2 = chain["stages"][2]["decimation"]
    n_fft = chain["fft_points_out"]
    settle = chain.get("settle_out_samples", 2048)
    n_out = n_fft + settle
    n_pdm = n_out * R1 * R2
    b, a = ntf_butterworth(chain["modulator"]["order"], chain["modulator"]["hinf"])
    fs2 = fs0 / (R1 * R2)
    cic_gain = cic["gain"]
    coef = fir["coef"]
    fir_dc = int(np.sum(coef))
    fs_node = {"pdm": fs0, "cic": fs0 / R1, "fir": fs2}
    t = np.arange(n_pdm) / fs0
    rng = np.random.default_rng(chain.get("seed", 19))
    sig_amp_ref = 10 ** (chain["cases"]["reference"]["levels_dbfs"][0] / 20)
    mic_noise_power = (sig_amp_ref ** 2 / 2) / 10 ** (mic["snr_db"] / 10)
    sigma = math.sqrt(mic_noise_power * (fs0 / 2) / (chain["band_hz"][1] - chain["band_hz"][0]))
    noise = sigma * rng.standard_normal(n_pdm)
    results = {}
    for cname, case in chain["cases"].items():
        u = noise.copy()
        for f_t, lvl in zip(case["tones_hz"], case["levels_dbfs"]):
            u += 10 ** (lvl / 20) * np.sin(2 * np.pi * f_t * t)
        y = pdm_modulate(u, b, a)
        x_int = y.astype(np.int64)  # +-1, exactly what the core's 2-bit signed input carries
        cic_full = cic_design.golden(x_int, R1, cic["diff_delay"], cic["stages"])
        cic_out = cic_full[chain["stages"][1].get("phase", 0)::R1]
        fir_full = fir_golden_full(cic_out, coef)
        fir_out = fir_full[chain["stages"][2].get("phase", 0)::R2]
        cic_f = cic_out.astype(float) / cic_gain
        fir_f = fir_out.astype(float) / (cic_gain * fir_dc)
        nodes = {}
        for name, rec, fs in (("pdm", y, fs0), ("cic", cic_f, fs0 / R1), ("fir", fir_f, fs2)):
            skip = settle * (R1 * R2 if name == "pdm" else R2 if name == "cic" else 1)
            rec = rec[skip: skip + n_fft * (R1 * R2 if name == "pdm" else R2 if name == "cic" else 1)]
            nodes[name] = tone_metrics(rec, fs, case["tones_hz"], tuple(chain["band_hz"]))
            nodes[name]["rate_hz"] = fs
            nodes[name]["n_points"] = len(rec)
        nodes["fir"]["max_abs_int"] = int(np.max(np.abs(fir_out)))
        nodes["cic"]["max_abs_int"] = int(np.max(np.abs(cic_out)))
        results[cname] = nodes
        if cname == "reference":
            # keep the output spectrum of the reference case for the record (decimated to 400 log-spaced points)
            rec = fir_f[settle: settle + n_fft]
            ff, pp = spectrum(rec, fs2)
            idx = np.unique(np.round(np.geomspace(1, len(ff) - 1, 400)).astype(int))
            with open(Path(outdir) / "output_spectrum.csv", "w") as fh:
                fh.write("freq_hz,power_dbfs\n")
                for i in idx:
                    fh.write(f"{ff[i]:.2f},{10 * math.log10(max(pp[i], 1e-30) / 0.5):.2f}\n")
    return results


def chain_frequency_response(cic, coef, fs0, R1, band_hz, R2):
    """Passband ripple and worst alias rejection of CIC x FIR, from the exact integer impulse responses."""
    fs1 = fs0 / R1
    fs2 = fs1 / R2
    fp = band_hz[1]
    f = np.linspace(20.0, fp, 4000)
    h_cic = cic_design.cic_mag(f, fs0, R1, cic["diff_delay"], cic["stages"])
    h_fir = np.abs(signal.freqz(coef / np.sum(coef), worN=np.mod(f, fs1), fs=fs1)[1])
    tot_db = 20 * np.log10(h_cic * h_fir)
    ripple = float(np.max(np.abs(tot_db - tot_db[0])))
    # alias rejection: the worst gain over the bands that fold onto 0..fp at the 48 kHz output
    worst = -300.0
    k = 1
    while k * fs2 - fp < fs0 / 2:
        fb = np.linspace(k * fs2 - fp, min(k * fs2 + fp, fs0 / 2 - 1), 600)
        hb = cic_design.cic_mag(fb, fs0, R1, cic["diff_delay"], cic["stages"]) * np.abs(
            signal.freqz(coef / np.sum(coef), worN=np.mod(fb, fs1), fs=fs1)[1])
        worst = max(worst, float(np.max(20 * np.log10(np.maximum(hb, 1e-30)))))
        k += 1
    return {"passband_ripple_db": ripple, "worst_alias_gain_db": worst, "alias_rejection_db": -worst,
            "droop_at_20khz_db": float(tot_db[-1] - tot_db[0])}


# ------------------------------------------------------------------ assembling the record and the picture


def read_coe(path):
    txt = Path(path).read_text()
    body = txt.split("coefdata", 1)[1].split("=", 1)[1].replace(";", "")
    return np.array([int(v) for v in body.replace("\n", " ").split(",") if v.strip()], dtype=np.int64)


def block_lines_ip(res, extra):
    o = res["ooc"] or {}
    sim = (res["sim"] or {}).get("sim", {}).get("continuous", {})
    ok = bool(sim.get("match")) and bool((res["sim"] or {}).get("sim", {}).get("random", {}).get("match"))
    lines = list(extra)
    lines.append("-")
    if o:
        lines.append(f"{o.get('luts')} LUT  {o.get('registers')} FF  {o.get('dsp')} DSP  {o.get('bram_tiles')} BRAM")
        lines.append(f"Fmax est. {o.get('fmax_est_mhz')} MHz (synth, OOC)")
    else:
        lines.append("OOC synthesis: not run")
    lines.append(f"latency {sim.get('latency_cycles_first_in_to_first_out')} clocks (xsim)")
    lines.append("xsim vs Python: " + (f"{sim.get('n_got')} of {sim.get('n_got')} outputs identical" if ok else "NOT matched"))
    return lines


def main(argv=None):
    from . import chain_svg
    argv = sys.argv[1:] if argv is None else argv
    chain_yaml, outdir = Path(argv[0]), Path(argv[1])
    root = Path(argv[2]) if len(argv) > 2 else Path.cwd()
    chain = yaml.safe_load(chain_yaml.read_text())
    outdir.mkdir(parents=True, exist_ok=True)
    mic, scic, sfir = chain["stages"][:3]
    cic_res = stage_ip_results(root, scic["results"])
    fir_res = stage_ip_results(root, sfir["results"])
    cic_spec = yaml.safe_load((root / scic["results"] / "spec.yaml").read_text())
    fir_spec = yaml.safe_load((root / sfir["results"] / "spec.yaml").read_text())
    cic = cic_design.design(cic_spec)
    coef = read_coe(root / sfir["results"] / "fir.coe")
    fir = {"coef": coef}
    # the decimation phase the IP chose, from its xsim run, is used by the chain model
    scic["phase"] = (cic_res["sim"]["sim"]["continuous"].get("decimation_phase") or 0)
    sfir["phase"] = (fir_res["sim"]["sim"]["continuous"].get("decimation_phase") or 0)
    b, a = ntf_butterworth(chain["modulator"]["order"], chain["modulator"]["hinf"])
    meas = run_cases(chain, cic, fir, outdir, root)
    pred = predicted(chain, cic, coef, b, a)
    resp = chain_frequency_response(cic, coef, mic["rate_hz"], scic["rate"], chain["band_hz"], sfir["decimation"])
    fs0 = mic["rate_hz"]
    nodes_meta = {"pdm": {"rate_hz": fs0, "width": "1 bit"},
                  "cic": {"rate_hz": fs0 / scic["rate"], "width": f"{cic['full_precision_width']} bit"},
                  "fir": {"rate_hz": fs0 / scic["rate"] / sfir["decimation"],
                          "width": f"{int((fir_res['readback'] or {}).get('selected', {}).get('CONFIG.Output_Width') or 0)} bit"}}
    result = {"chain": chain["name"], "band_hz": chain["band_hz"], "nodes": nodes_meta,
              "predicted": pred,
              "measured": meas, "response": resp, "stage_results": {
                  "cic": {"ooc": cic_res["ooc"], "readback": (cic_res["readback"] or {}).get("selected"),
                          "sim_match": {k: v.get("match") for k, v in (cic_res["sim"] or {}).get("sim", {}).items()}},
                  "fir": {"ooc": fir_res["ooc"], "readback": (fir_res["readback"] or {}).get("selected"),
                          "design": fir_res["design"]["design"] if fir_res["design"] else None,
                          "sim_match": {k: v.get("match") for k, v in (fir_res["sim"] or {}).get("sim", {}).items()}}}}
    (outdir / "chain_results.json").write_text(json.dumps(result, indent=2, default=float) + "\n")

    # ---- the picture
    ref = meas["reference"]
    pr = pred
    def link(node, lines0):
        m = ref[node]
        r = nodes_meta[node]["rate_hz"]
        rate = f"{r / 1e6:g} MS/s" if r >= 1e6 else f"{r / 1e3:g} kS/s"
        return {"lines": [lines0, f"{rate}  {nodes_meta[node]['width']}",
                          f"SINAD {m['sinad_db']:.1f} dB  ENOB {m['enob_bits']:.2f} b",
                          f"(predicted {pr[node]['sinad_db']:.1f} dB)"]}
    f_out = (fir_res["readback"] or {}).get("selected", {})
    blocks = [
        {"title": "Microphone", "sub": f"{mic['part']} (data sheet)", "external": True,
         "lines": ["PDM, 1 bit, clock " + f"{fs0 / 1e6:g} MHz", f"SNR {mic['snr_db']} dB(A) at 94 dB SPL",
                   f"sensitivity {mic['sensitivity_dbfs']} dBFS", f"THD <= {mic['thd_max_pct']} % at 94 dB SPL",
                   f"AOP {mic['aop_db_spl']} dB SPL", "-", "model: 4th-order 1-bit", "modulator + white noise at", "the data-sheet SNR"]},
        {"title": "CIC decimator", "sub": "CIC Compiler 4.0",
         "lines": block_lines_ip(cic_res, [f"N={cic['stages']}  R={scic['rate']}  M={cic['diff_delay']}",
                                           f"in {cic['input_width']} b, out {cic['full_precision_width']} b (full)",
                                           f"gain {cic['gain']} ({cic['gain_db']:.1f} dB)",
                                           f"droop {cic['droop_at_passband_edge_db']:.2f} dB at 20 kHz"])},
        {"title": "Compensating FIR", "sub": "FIR Compiler 7.2",
         "lines": block_lines_ip(fir_res, [f"{fir_res['design']['design']['taps']} taps, 16-bit coefficients" if fir_res["design"] else "",
                                           f"decimate by {sfir['decimation']}, symmetric",
                                           f"FIR x CIC ripple {resp['passband_ripple_db']:.3f} dB",
                                           f"alias rejection {resp['alias_rejection_db']:.1f} dB",
                                           f"out {f_out.get('CONFIG.Output_Width')} b (full precision)"])},
        {"title": "Audio stream", "sub": "to the rest of the design",
         "lines": [f"{nodes_meta['fir']['rate_hz'] / 1e3:g} kS/s", f"{nodes_meta['fir']['width']} two's complement",
                   f"band {chain['band_hz'][0]:g} Hz - {chain['band_hz'][1] / 1e3:g} kHz", "-",
                   f"reference tone {chain['cases']['reference']['tones_hz'][0]:.1f} Hz", f"at {chain['cases']['reference']['levels_dbfs'][0]} dBFS",
                   f"output SINAD {ref['fir']['sinad_db']:.1f} dB",
                   f"SFDR (loud tone) {meas['loud']['fir']['sfdr_db']:.1f} dB", f"THD (loud tone) {meas['loud']['fir']['thd_db']:.1f} dB"]},
    ]
    links = [link("pdm", "1-bit stream"), link("cic", "CIC output"), link("fir", "FIR output")]
    strip = {"axis": (50, 70), "reference": (mic["snr_db"], f"data-sheet SNR {mic['snr_db']} dB"),
             "title": "Where the chain loses quality", "sub": "SINAD of the reference tone in 20 Hz - 20 kHz (filled: measured on the integer chain; outline: noise-budget prediction)",
             "rows": [{"label": "microphone stream (2.4 MS/s)", "measured": ref["pdm"]["sinad_db"], "predicted": pr["pdm"]["sinad_db"], "enob": ref["pdm"]["enob_bits"]},
                      {"label": "CIC output (96 kS/s)", "measured": ref["cic"]["sinad_db"], "predicted": pr["cic"]["sinad_db"], "enob": ref["cic"]["enob_bits"]},
                      {"label": "FIR output (48 kS/s)", "measured": ref["fir"]["sinad_db"], "predicted": pr["fir"]["sinad_db"], "enob": ref["fir"]["enob_bits"]}]}
    foot = (f"Reference tone {chain['cases']['reference']['tones_hz'][0]:.1f} Hz at {chain['cases']['reference']['levels_dbfs'][0]} dBFS (94 dB SPL). ENOB is full-scale referenced: (SINAD - 1.76 - tone level in dBFS) / 6.02.",
            "Numbers: results/19_ipgen/chain/chain_results.json, results/19_ipgen/cic, results/19_ipgen/chain_fir (synthesis for xc7a100t, out of context).")
    (outdir / "chain.svg").write_text(chain_svg.render(chain["title"], blocks, links, strip, foot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
