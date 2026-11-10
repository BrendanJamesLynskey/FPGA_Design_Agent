"""FIR Compiler 7.2 adapter (brief 19, adapter 1): spec -> scipy design -> .coe -> FIR Compiler -> bit-exact check."""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from . import fir_design
from .adapter import IpAdapter
from .harness import compare


def fir_golden_full(x, coef):
    """Full-precision FIR in exact integer arithmetic: y[n] = sum_k c[k] x[n-k], zero state before the first sample.
    int64 holds it exactly (|x| < 2^31, sum|c| < 2^32)."""
    return np.convolve(np.asarray(x, dtype=np.int64), np.asarray(coef, dtype=np.int64))[: len(x)]


def full_precision_width(data_width, coef):
    """Signed bits needed for the worst-case output of an integer FIR (what the core's Full_Precision output is)."""
    peak = (1 << (data_width - 1)) * int(np.sum(np.abs(coef)))
    return int(peak).bit_length() + 1


def test_signal(spec, design, n=4096, seed=19):
    """Seeded 16-bit-style stimulus: a pass-band tone, a stop-band tone, noise, then full-scale extremes (a square
    wave at the extreme codes and a step), so the core's accumulator sees worst-case growth."""
    rng = np.random.default_rng(seed)
    w = spec["data_width"]
    fs = spec["fs_in_hz"]
    amp = (1 << (w - 1)) - 1
    t = np.arange(n) / fs
    f1 = 0.5 * spec["pass_edge_hz"]
    f2 = 0.5 * (spec["stop_edge_hz"] + fs / 2)
    x = 0.4 * amp * np.sin(2 * np.pi * f1 * t) + 0.3 * amp * np.sin(2 * np.pi * f2 * t) + 0.02 * amp * rng.standard_normal(n)
    x = np.rint(x).astype(np.int64)
    # worst-case tail: alternating extremes in the sign pattern of the largest coefficients, then a step
    k = min(n // 8, 600)
    x[n - 2 * k: n - k] = np.where(np.arange(k) % 2 == 0, amp, -(1 << (w - 1)))
    x[n - k:] = -(1 << (w - 1))
    return np.clip(x, -(1 << (w - 1)), amp)


class FirAdapter(IpAdapter):
    name = "fir"
    create_args = "-name fir_compiler -vendor xilinx.com -library ip -version 7.2"

    def design(self, spec):
        d = fir_design.design(spec)
        coef = d["coef"]
        d["summary"] = {k: d[k] for k in ("method", "taps", "float_metrics", "requested_coef_width", "coef_width",
                                         "quantised_metrics", "attenuation_lost_db", "width_search", "symmetric",
                                         "dc_gain_int", "candidates")}
        d["summary"]["spec_attenuation_db"] = spec["atten_db"]
        d["summary"]["spec_ripple_db"] = spec["ripple_db"]
        d["summary"]["coef_abs_sum"] = int(np.sum(np.abs(coef)))
        return d

    def design_artifacts(self, spec, d, outdir):
        outdir = Path(outdir)
        coe = outdir / "fir.coe"
        coe.write_text(fir_design.coe_text(d["coef"]))
        fs = spec["fs_in_hz"]
        fw, g_float = fir_design.response_curve(d["h_float"], fs, 1024)
        _, g_q = fir_design.response_curve(d["coef"], fs, 1024)
        curve = outdir / "response.csv"
        with open(curve, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["freq_hz", "float_db", "quantised_db"])
            for a, b, c in zip(fw, g_float, g_q):
                w.writerow([f"{a:.1f}", f"{b:.4f}", f"{c:.4f}"])
        return {"coe": coe, "response": curve}

    def props(self, spec, d, art):
        m = spec["decimation"]
        out = [
            "CONFIG.Filter_Type", "Decimation" if m > 1 else "Single_Rate",
            "CONFIG.Rate_Change_Type", "Integer",
            "CONFIG.Decimation_Rate", str(m),
            "CONFIG.Number_Channels", str(spec.get("channels", 1)),
            "CONFIG.RateSpecification", "Frequency_Specification",
            "CONFIG.Clock_Frequency", f"{spec['clock_hz'] / 1e6:g}",
            "CONFIG.Sample_Frequency", f"{spec['fs_in_hz'] / 1e6:g}",
            "CONFIG.CoefficientSource", "COE_File",
            "CONFIG.Coefficient_File", str(Path(art["coe"]).resolve()),
            "CONFIG.Quantization", "Integer_Coefficients",
            "CONFIG.Coefficient_Sign", "Signed",
            "CONFIG.Coefficient_Width", str(d["coef_width"]),
            "CONFIG.Coefficient_Structure", "Symmetric" if d["symmetric"] else "Non_Symmetric",
            "CONFIG.Data_Sign", "Signed",
            "CONFIG.Data_Width", str(spec["data_width"]),
            "CONFIG.Output_Rounding_Mode", "Full_Precision",
            "CONFIG.M_DATA_Has_TREADY", "true" if spec.get("back_pressure", True) else "false",
            "CONFIG.S_DATA_Has_FIFO", "true",
        ]
        if spec.get("optimization_goal"):
            out += ["CONFIG.Optimization_Goal", spec["optimization_goal"]]
        return out

    def predicted(self, spec, d):
        coef = d["coef"]
        return {
            "output_width_full_precision": full_precision_width(spec["data_width"], coef),
            "taps": int(len(coef)),
            "unique_multipliers_if_symmetric": int((len(coef) + 1) // 2) if d["symmetric"] else int(len(coef)),
            "dc_gain": int(np.sum(coef)),
            "hardware_oversampling": int(spec["clock_hz"] // spec["fs_in_hz"]),
            # one multiply-accumulate per DSP slice; the filter has clock/fs_out cycles to compute each output
            "multiply_accumulates": math.ceil(((len(coef) + 1) // 2 if d["symmetric"] else len(coef))
                                              / (spec["clock_hz"] / (spec["fs_in_hz"] / spec["decimation"]))),
        }

    def readback_keys(self):
        return ["CONFIG.Output_Width", "CONFIG.Coefficient_Structure", "CONFIG.Coefficient_Width",
                "CONFIG.Decimation_Rate", "CONFIG.Filter_Type", "CONFIG.Output_Rounding_Mode",
                "CONFIG.HardwareOversamplingRate", "CONFIG.Clock_Frequency", "CONFIG.Sample_Frequency",
                "MODEL.C_LATENCY", "MODEL.C_NUM_MADDS", "MODEL.C_OVERSAMPLING_RATE", "MODEL.C_NUM_TAPS",
                "MODEL.C_OUTPUT_WIDTH", "MODEL.C_SYMMETRY", "MODEL.C_DECIM_RATE", "MODEL.C_COL_MODE",
                "MODEL.C_COEF_MEMTYPE", "MODEL.C_DATA_MEMTYPE", "MODEL.C_OPTIMIZATION"]

    def dut_inst(self, module, ports):
        tready = ".m_axis_data_tready(out_tready)," if ports.get("m_tready") else ""
        return (f"    {module} dut (\n        .aclk(aclk),\n        .s_axis_data_tvalid(in_tvalid), "
                f".s_axis_data_tready(in_tready), .s_axis_data_tdata(in_tdata),\n        {tready}\n"
                f"        .m_axis_data_tvalid(out_tvalid), .m_axis_data_tdata(out_tdata)\n    );\n"
                f"    assign out_tlast = 1'b0;")

    def stimulus(self, spec, d):
        return test_signal(spec, d, n=spec.get("n_samples", 4096)), spec["data_width"]

    def check(self, spec, d, samples, resp, out_w):
        m = spec["decimation"]
        y_full = fir_golden_full(samples, d["coef"])
        got = resp["data"]
        best = None
        for ph in range(m):
            exp = y_full[ph::m]
            r = compare(got, exp, phases=(0,))
            r["decimation_phase"] = ph
            if r["match"]:
                best = r
                break
            if best is None or r["n_mismatch"] < best["n_mismatch"]:
                best = r
        best["n_input"] = int(len(samples))
        best["n_expected_outputs_floor"] = int(len(samples) // m)
        best["first_input_cycle"] = resp["meta"].get("first_in")
        cyc = resp["cycles"]
        best["first_output_cycle"] = cyc[0] if cyc else None
        best["latency_cycles_first_in_to_first_out"] = (cyc[0] - resp["meta"]["first_in"]) if cyc and resp["meta"].get("first_in", -1) >= 0 else None
        return best
