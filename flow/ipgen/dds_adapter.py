"""DDS Compiler 6.0 adapter (brief 19, adapter 4): SFDR and frequency resolution -> phase width, output width, phase increment
-> DDS Compiler (Hardware_Parameters, fixed PINC) -> xsim. The phase output is checked bit for bit against a Python phase
accumulator; the sine and cosine are checked against the ideal curve (error in LSB) and their SFDR is measured by FFT.
No bit-accurate model of the sine/cosine LUT is used (the core's C model was not built into the flow)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .adapter import IpAdapter
from .harness import tdata_bits, to_signed


def design_dds(spec):
    """The sizing rules of PG141, as an external tool: phase width from the resolution, output width from the SFDR, the
    phase increment for the wanted frequency (and the frequency actually produced)."""
    fclk = spec["clock_hz"]
    P = math.ceil(math.log2(fclk / spec["freq_resolution_hz"]))
    W = math.ceil((spec["sfdr_db"] + spec.get("sfdr_margin_db", 3.0)) / 6.02)  # 6.02 dB per bit; measured to fall just short
    pinc = round(spec["f_out_hz"] / fclk * 2 ** P)
    f_actual = pinc * fclk / 2 ** P
    return {"phase_width": P, "output_width": W, "pinc": int(pinc), "f_out_actual_hz": f_actual,
            "f_out_error_hz": f_actual - spec["f_out_hz"], "resolution_hz": fclk / 2 ** P,
            "summary": {"phase_width": P, "output_width": W, "pinc": int(pinc), "f_out_actual_hz": f_actual,
                        "f_out_error_hz": f_actual - spec["f_out_hz"], "resolution_hz": fclk / 2 ** P,
                        "sfdr_rule_db": 6.02 * W, "sfdr_margin_db": spec.get("sfdr_margin_db", 3.0)}}


class DdsAdapter(IpAdapter):
    name = "dds"
    create_args = "-name dds_compiler -vendor xilinx.com -library ip -version 6.0"

    def design(self, spec):
        return design_dds(spec)

    def props(self, spec, d, art):
        return ["CONFIG.PartsPresent", "Phase_Generator_and_SIN_COS_LUT", "CONFIG.Parameter_Entry", "Hardware_Parameters",
                "CONFIG.DDS_Clock_Rate", f"{spec['clock_hz'] / 1e6:g}", "CONFIG.Phase_Width", str(d["phase_width"]),
                "CONFIG.Output_Width", str(d["output_width"]), "CONFIG.Phase_Increment", "Fixed",
                "CONFIG.PINC1", format(d["pinc"], f"0{d['phase_width']}b"),
                "CONFIG.Output_Selection", "Sine_and_Cosine", "CONFIG.Has_Phase_Out", "true",
                "CONFIG.Noise_Shaping", spec.get("noise_shaping", "None")]

    def predicted(self, spec, d):
        return {"phase_width": d["phase_width"], "output_width": d["output_width"], "pinc": d["pinc"]}

    def readback_keys(self):
        return ["CONFIG.Phase_Width", "CONFIG.Output_Width", "CONFIG.PINC1", "CONFIG.Latency", "CONFIG.Noise_Shaping",
                "CONFIG.Memory_Type", "MODEL.C_LATENCY", "MODEL.C_PHASE_ANGLE_WIDTH", "MODEL.C_OUTPUT_WIDTH", "MODEL.C_NOISE_SHAPING",
                "MODEL.C_MEM_TYPE", "MODEL.C_PHASE_INCREMENT_VALUE"]

    #: this adapter reads two output channels, so the testbench sees them concatenated: {phase, data}
    out_port = "m_axis_data_tdata"
    source_only = True

    def dut_inst(self, module, ports):
        pw = ports["phase_tdata_bits"]
        dw = ports["data_tdata_bits"]
        return (f"    wire [{pw - 1}:0] ph_tdata;\n    wire [{dw - 1}:0] da_tdata;\n    wire da_tvalid, ph_tvalid;\n"
                f"    {module} dut (.aclk(aclk), .m_axis_data_tvalid(da_tvalid), .m_axis_data_tdata(da_tdata),\n"
                f"        .m_axis_phase_tvalid(ph_tvalid), .m_axis_phase_tdata(ph_tdata));\n"
                f"    assign out_tdata = {{ph_tdata, da_tdata}};\n    assign out_tvalid = da_tvalid;\n"
                f"    assign in_tready = 1'b1;\n    assign out_tlast = 1'b0;")

    def parse_ports(self, vhd):
        """tdata widths of the two output channels, from the generated VHDL wrapper."""
        import re
        w = lambda n: int(re.search(rf"{n}\s*:\s*OUT\s+STD_LOGIC_VECTOR\((\d+) DOWNTO 0\)", vhd, re.I).group(1)) + 1
        return {"phase_tdata_bits": w("m_axis_phase_tdata"), "data_tdata_bits": w("m_axis_data_tdata")}

    def stimulus(self, spec, d):
        return np.zeros(1, dtype=np.int64), 8  # a source has no input: one dummy beat so the testbench starts its drain

    def drain_cycles(self, spec):
        return spec.get("n_samples", 16384) + 64  # the testbench records until this many cycles after the dummy beat

    schedules = (("continuous", 0),)

    def check(self, spec, d, samples, resp, out_w):
        from . import chain  # the FFT measurements (needs scipy)
        P, W = d["phase_width"], d["output_width"]
        half = tdata_bits(W)           # sine and cosine each occupy a byte-padded half of the data word
        dbits = 2 * half
        raw = [int(v) & ((1 << out_w) - 1) for v in resp["data"]]
        phase = np.array([(v >> dbits) & ((1 << P) - 1) for v in raw], dtype=np.int64)
        cos = np.array([to_signed(v & ((1 << half) - 1), half) for v in raw], dtype=np.int64)         # PG141: cosine low,
        sin = np.array([to_signed((v >> half) & ((1 << half) - 1), half) for v in raw], dtype=np.int64)  # sine high
        n = spec.get("n_samples", 16384)  # the record the tone is coherent with; later words are the drain
        phase, sin, cos = phase[:n], sin[:n], cos[:n]
        pinc = d["pinc"]
        res = {"n_samples": n, "match": False}
        # the phase output is a plain accumulator: phase[k] = ((k0 + k) * PINC) mod 2^P; find the start k0
        k0 = next((c for c in range(4096) if (c * pinc) % (1 << P) == int(phase[0])), None)
        exp = np.array([((k0 + i) * pinc) % (1 << P) for i in range(n)], dtype=np.int64) if k0 is not None else None
        res["phase_exact"] = bool(k0 is not None and np.array_equal(exp, phase))
        res["phase_start_index"] = k0
        # sine and cosine against the ideal curve of the core's own phase
        amp = 2 ** (W - 1) - 1
        th = 2 * np.pi * phase.astype(float) / 2 ** P
        res["max_abs_err_sin_lsb"] = float(np.max(np.abs(sin - np.rint(amp * np.sin(th)))))
        res["max_abs_err_cos_lsb"] = float(np.max(np.abs(cos - np.rint(amp * np.cos(th)))))
        res["max_abs_out"] = int(max(np.max(np.abs(sin)), np.max(np.abs(cos))))
        fclk = spec["clock_hz"]
        m = chain.tone_metrics(sin.astype(float) / 2 ** (W - 1), fclk, [d["f_out_actual_hz"]],
                               band=(fclk / 2 ** 14, fclk / 2 - fclk / 2 ** 14))
        for key in ("sfdr_db", "sinad_db", "thd_db", "tone_dbfs"):
            res[key] = m[key]
        res["sfdr_spec_db"] = spec["sfdr_db"]
        res["f_out_hz_from_phase_step"] = int((phase[1] - phase[0]) % (1 << P)) * fclk / 2 ** P
        res["first_output_cycle"] = resp["cycles"][0] if resp["cycles"] else None
        res["match"] = bool(res["phase_exact"] and res["sfdr_db"] >= spec["sfdr_db"])
        return res
