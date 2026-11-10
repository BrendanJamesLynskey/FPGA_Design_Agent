"""Block Memory Generator 8.4 adapter (brief 19, adapter 3): a Python-generated table (sine or window) -> `.coe` -> a
single-port ROM -> read back every word in xsim and compare. The table design is the external tool; the IP just holds it."""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from .adapter import IpAdapter
from .harness import to_unsigned, to_signed


def make_table(spec):
    n, w = spec["points"], spec["width"]
    full = 2 ** (w - 1) - 1
    k = np.arange(n)
    if spec["kind"] == "sine":
        t = np.sin(2 * np.pi * k / n)
    elif spec["kind"] == "hann":
        t = 0.5 - 0.5 * np.cos(2 * np.pi * k / n)  # periodic Hann, 0..1
    else:
        raise ValueError(spec["kind"])
    return np.rint(t * full).astype(np.int64)


def table_sqnr_db(table, ideal_kind, n, width):
    """SNR of the quantised table against the ideal curve, dB (the error a lookup of this table cannot beat)."""
    k = np.arange(n)
    full = 2 ** (width - 1) - 1
    ideal = np.sin(2 * np.pi * k / n) if ideal_kind == "sine" else 0.5 - 0.5 * np.cos(2 * np.pi * k / n)
    err = table - ideal * full
    return 10 * math.log10(np.mean((ideal * full) ** 2) / np.mean(err ** 2))


class BmgAdapter(IpAdapter):
    name = "bmg"
    create_args = "-name blk_mem_gen -vendor xilinx.com -library ip -version 8.4"
    clock_port = "clka"
    sim_kind = "mem"

    def design(self, spec):
        t = make_table(spec)
        sq = table_sqnr_db(t, spec["kind"], spec["points"], spec["width"])
        ideal = 6.02 * spec["width"] + 1.76 if spec["kind"] == "sine" else None
        n, w = spec["points"], spec["width"]
        return {"table": t,
                "summary": {"kind": spec["kind"], "points": n, "width": w, "bits": n * w,
                            "table_sqnr_db": sq, "ideal_full_scale_sine_sqnr_db": ideal,
                            "min": int(t.min()), "max": int(t.max())}}

    def design_artifacts(self, spec, d, outdir):
        outdir = Path(outdir)
        w = spec["width"]
        coe = outdir / "table.coe"
        digits = (w + 3) // 4
        body = ",\n".join(f"{to_unsigned(int(v), w):0{digits}x}" for v in d["table"])
        coe.write_text(f"memory_initialization_radix=16;\nmemory_initialization_vector=\n{body};\n")
        curve = outdir / "table.csv"
        with open(curve, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["index", "value"])
            for i, v in enumerate(d["table"]):
                wr.writerow([i, int(v)])
        return {"coe": coe, "table": curve}

    def props(self, spec, d, art):
        reg = bool(spec.get("register_output", True))
        return ["CONFIG.Memory_Type", "Single_Port_ROM", "CONFIG.Write_Width_A", str(spec["width"]),
                "CONFIG.Write_Depth_A", str(spec["points"]), "CONFIG.Enable_A", "Always_Enabled",
                "CONFIG.Register_PortA_Output_of_Memory_Primitives", "true" if reg else "false",
                "CONFIG.Load_Init_File", "true", "CONFIG.Coe_File", str(Path(art["coe"]).resolve())]

    def predicted(self, spec, d):
        n, w = spec["points"], spec["width"]
        ramb18 = math.ceil(n / 1024) * math.ceil(w / 18)  # 1K x 18 aspect of a RAMB18
        return {"read_latency_cycles": 2 if spec.get("register_output", True) else 1, "ramb18_equivalents": ramb18,
                "bram_tiles": ramb18 / 2}

    def readback_keys(self):
        return ["CONFIG.Memory_Type", "CONFIG.Write_Width_A", "CONFIG.Read_Width_A", "CONFIG.Write_Depth_A",
                "CONFIG.READ_LATENCY_A", "CONFIG.Primitive", "CONFIG.Algorithm", "CONFIG.Load_Init_File",
                "CONFIG.Register_PortA_Output_of_Memory_Primitives", "MODEL.C_MEM_TYPE", "MODEL.C_READ_LATENCY_A",
                "MODEL.C_READ_WIDTH_A", "MODEL.C_READ_DEPTH_A", "MODEL.C_ADDRA_WIDTH"]

    def dut_inst_mem(self, module, ports):
        return f"    {module} dut (.clka(clka), .addra(addra), .douta(douta));"

    def addresses(self, spec, d):
        """Every address in order, twice (back-to-back repeats included), then a seeded permutation, then the ends."""
        n = spec["points"]
        rng = np.random.default_rng(spec.get("seed", 19))
        seq = list(range(n)) + list(range(n)) + [int(v) for v in rng.permutation(n)] + [0, 0, n - 1, n - 1, 0, n - 1]
        return seq

    def check_mem(self, spec, d, addr_rows, data_rows, data_w):
        """D[r + L] must equal table[A[r]] for every row: find L, then compare every word."""
        table = [to_unsigned(int(v), data_w) for v in d["table"]]
        res = {"match": False, "latency_cycles": None, "n_words": len(addr_rows)}
        for L in range(0, 6):
            bad = 0
            n = 0
            for r in range(1, len(addr_rows) - L - 1):
                n += 1
                if data_rows[r + L] != table[addr_rows[r]]:
                    bad += 1
            if bad == 0 and n > 0:
                res.update({"match": True, "latency_cycles": L, "n_words": n, "n_mismatch": 0})
                break
            res["n_mismatch_at_L%d" % L] = bad
        res["full_table_read"] = True
        return res
