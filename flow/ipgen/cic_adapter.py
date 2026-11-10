"""CIC Compiler 4.0 adapter (brief 19, adapter 2): spec -> stages/rate -> CIC Compiler -> bit-exact check."""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from . import cic_design
from .adapter import IpAdapter
from .harness import compare


class CicAdapter(IpAdapter):
    name = "cic"
    create_args = "-name cic_compiler -vendor xilinx.com -library ip -version 4.0"

    def design(self, spec):
        return cic_design.design(spec)

    def design_artifacts(self, spec, d, outdir):
        outdir = Path(outdir)
        fs, R, M, N = spec["fs_in_hz"], d["rate"], d["diff_delay"], d["stages"]
        f = np.linspace(0, fs / 2, 2001)
        curve = outdir / "response.csv"
        with open(curve, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["freq_hz", "gain_db"])
            for a, b in zip(f, cic_design.cic_db(f, fs, R, M, N)):
                w.writerow([f"{a:.1f}", f"{b:.3f}"])
        return {"response": curve}

    def props(self, spec, d, art):
        return [
            "CONFIG.Filter_Type", "Decimation",
            "CONFIG.Number_Of_Stages", str(d["stages"]),
            "CONFIG.Differential_Delay", str(d["diff_delay"]),
            "CONFIG.Sample_Rate_Changes", "Fixed",
            "CONFIG.Fixed_Or_Initial_Rate", str(d["rate"]),
            "CONFIG.Input_Sample_Frequency", f"{spec['fs_in_hz'] / 1e6:g}",
            "CONFIG.Clock_Frequency", f"{spec['clock_hz'] / 1e6:g}",
            "CONFIG.Input_Data_Width", str(d["input_width"]),
            "CONFIG.Quantization", "Full_Precision",
            "CONFIG.Use_Xtreme_DSP_Slice", "true" if spec.get("use_dsp", False) else "false",
            "CONFIG.Number_Of_Channels", "1",
        ]

    def predicted(self, spec, d):
        return {"output_width_full_precision": d["full_precision_width"], "gain": d["gain"],
                "gain_db": d["gain_db"], "bit_growth": d["full_precision_width"] - d["input_width"],
                "droop_at_passband_edge_db": d["droop_at_passband_edge_db"],
                "alias_rejection_db": d["alias_rejection_db"]}

    def readback_keys(self):
        return ["CONFIG.Output_Data_Width", "CONFIG.Number_Of_Stages", "CONFIG.Differential_Delay",
                "CONFIG.Fixed_Or_Initial_Rate", "CONFIG.Input_Data_Width", "CONFIG.Use_Xtreme_DSP_Slice",
                "MODEL.C_OUTPUT_WIDTH", "MODEL.C_NUM_STAGES", "MODEL.C_RATE", "MODEL.C_USE_DSP",
                "MODEL.C_INPUT_WIDTH", "MODEL.C_HAS_ROUNDING"]

    def dut_inst(self, module, ports):
        return (f"    {module} dut (\n        .aclk(aclk),\n        .s_axis_data_tvalid(in_tvalid), "
                f".s_axis_data_tready(in_tready), .s_axis_data_tdata(in_tdata),\n"
                f"        .m_axis_data_tvalid(out_tvalid), .m_axis_data_tdata(out_tdata)\n    );\n"
                f"    assign out_tlast = 1'b0;")

    def stimulus(self, spec, d):
        """A seeded +-1 stream (a PDM-like bit stream: a 1 kHz tone density-modulated, plus randomness) so every
        integrator sees both signs, with a long run of +1 and of -1 at the end for worst-case growth."""
        rng = np.random.default_rng(spec.get("seed", 19))
        n = spec.get("n_samples", 20000)
        t = np.arange(n) / spec["fs_in_hz"]
        p = 0.5 + 0.4 * np.sin(2 * np.pi * 1000 * t)
        x = np.where(rng.random(n) < p, 1, -1).astype(np.int64)
        k = 3 * d["rate"] * d["stages"]
        x[n - 2 * k: n - k] = 1
        x[n - k:] = -1
        return x, d["input_width"]

    def check(self, spec, d, samples, resp, out_w):
        R = d["rate"]
        y_full = cic_design.golden(samples, R, d["diff_delay"], d["stages"])
        got = resp["data"]
        best = None
        for ph in range(R):
            r = compare(got, y_full[ph::R], phases=(0,))
            r["decimation_phase"] = ph
            if r["match"]:
                best = r
                break
            if best is None or r["n_mismatch"] < best["n_mismatch"]:
                best = r
        best["n_input"] = int(len(samples))
        best["n_expected_outputs_floor"] = int(len(samples) // R)
        cyc = resp["cycles"]
        best["first_input_cycle"] = resp["meta"].get("first_in")
        best["first_output_cycle"] = cyc[0] if cyc else None
        best["latency_cycles_first_in_to_first_out"] = (cyc[0] - resp["meta"]["first_in"]) if cyc and resp["meta"].get("first_in", -1) >= 0 else None
        best["max_abs_output"] = int(max(abs(v) for v in got)) if got else None
        best["max_abs_golden"] = int(np.max(np.abs(y_full)))
        return best
