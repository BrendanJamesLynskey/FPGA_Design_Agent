#!/usr/bin/env python3
"""Fit the per-family delay model (brief 62A) from the calibration build's reports (flow/delay_calib/calib.tcl).

    python3 flow/delay_calib/fit.py <calib out dir> [--extra timing_worst_setup.rpt ...] [--yaml out.yaml]

Each measured path gives its **stage time** = requirement - slack: the share of the clock period the stage uses,
clock-to-out, logic, route, setup, skew and uncertainty included. The model stores, per operator, the logic-and-route
part (stage time less the bare register-to-register overhead), and that overhead, so a planned stage is
``overhead + sum(segments)``. Adders, comparators and LUT multiplies get a straight-line fit over their widths.
Writes the YAML the knowledge bank keeps (``family_matrix/delay_model/7series.yaml``).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow.digest.timing import parse_paths  # noqa: E402


def stage(p: dict) -> float:
    return round(p["requirement_ns"] - p["slack_ns"], 3)


def worst(paths: list[dict], dest: str | None = None, src: str | None = None) -> dict | None:
    sel = [p for p in paths if (dest is None or re.search(dest, p["destination"] or ""))
           and (src is None or re.search(src, p["source"] or ""))]
    return min(sel, key=lambda p: p["slack_ns"]) if sel else None


def linfit(xs: list[float], ys: list[float]) -> dict:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return {"a": round(my - b * mx, 4), "b": round(b, 5), "points": [[x, y] for x, y in zip(xs, ys)]}


def fit(d: Path) -> tuple[dict, list[dict]]:
    rd = lambda n: parse_paths((d / n).read_text()) if (d / n).is_file() else []      # noqa: E731
    rows: list[dict] = []

    def take(name: str, p: dict | None, what: str) -> float | None:
        if not p:
            rows.append({"name": name, "what": what, "measured": None})
            return None
        s = stage(p)
        rows.append({"name": name, "what": what, "stage_ns": s, "data_path_ns": p["data_path_ns"], "slack_ns": p["slack_ns"],
                     "levels": p["levels_by_type"], "source": p["source"], "destination": p["destination"]})
        return s

    # the bare register-to-register overhead: the shortest FF->FF path in the shift register feeding the blocks is
    # not reported, so it is clock-to-out + setup + uncertainty read from any reported FF->FF path's rows
    any_ff = next((p for f in sorted(d.glob("path_u_*.rpt")) for p in rd(f.name) if p["cells"] and p["cells"][0]["type"].startswith("FD")
                   and (p["destination"] or "").endswith("/D")), None)
    clk_q = any_ff["cells"][0]["incr_ns"] if any_ff else 0.456
    txt = next((f.read_text() for f in sorted(d.glob("path_u_*.rpt"))), "")
    m = re.search(r"\(Setup_fdre_C_D\)\s+(-?[0-9.]+)", txt)
    setup = -float(m.group(1)) if m else -0.062           # the row adds to the required time: setup = -incr
    m2 = re.search(r"clock uncertainty\s+(-?[0-9.]+)", txt)
    unc = -float(m2.group(1)) if m2 else 0.035
    over = round(clk_q + setup + unc, 3)

    adds = [(w, take(f"add{w}", worst(rd(f"path_u_add{w}.rpt"), rf"u_add{w}/s_reg"), f"{w}-bit add, FF to FF")) for w in (16, 32, 64)]
    cmp32 = take("cmp32", worst(rd("path_u_cmp32.rpt"), r"u_cmp32/lt_reg"), "32-bit a < b, FF to FF")
    tab = take("table4x9", worst(rd("path_u_tab.rpt"), r"u_tab/c_reg"), "4-bit index to 9-bit constant table")
    mux = take("mux16x16", worst(rd("path_u_mux16.rpt"), r"u_mux16/y_reg"), "16:1 mux of 16 bits")
    lm = [(w, take(f"mul{w}_lut", worst(rd(f"path_u_mul{w}_lut.rpt"), rf"u_mul{w}_lut/p_reg"), f"{w} x {w} signed multiply in LUTs"))
          for w in (9, 18)]
    dsp0 = take("mul9_dsp_noreg", worst(rd("path_u_mul9_dsp0.rpt"), r"u_mul9_dsp0/pr_reg"), "9 x 9 in a DSP48E1, no internal register, FF to FF")
    din = take("dsp_operand_in", worst(rd("path_u_mul18_dsp3.rpt") + rd("path_u_mul18_dsp2.rpt"), r"(p|mr)_reg/[AB]\["),
               "fabric FF to a DSP48E1 A/B input register")
    internal = rd("path_dsp_internal.rpt")
    frm = rd("path_from_dsp.rpt")
    mult = take("dsp_areg_to_mreg", worst(internal, None, None) if internal else None, "inside the DSP48E1: AREG/BREG to MREG (or to PREG)")
    dout = take("dsp_preg_out", worst([p for p in frm if (p["destination"] or "").endswith("/D")]), "DSP48E1 PREG to a fabric FF")
    bram = rd("path_from_bram.rpt")
    b0 = take("bram_out_noreg", worst(bram, None, r"u_bram0/"), "block RAM read, no output register, to a fabric FF")
    b1 = take("bram_out_reg", worst(bram, None, r"u_bram1/"), "block RAM read with the output register, to a fabric FF")

    seg = lambda s: round(max(0.0, s - over), 3) if s is not None else None    # noqa: E731
    model = {
        "schema": "fpga-design-agent/delay-model/v1",
        "uncertainty_ns": unc,
        "ff": {"clk_to_q_ns": clk_q, "setup_ns": setup, "overhead_ns": over},
        "lut_level_ns": None,
        "table_ns": seg(tab), "mux16_ns": seg(mux),
        "fit": {"add_by_bits": linfit([w for w, s in adds if s], [seg(s) for w, s in adds if s]),
                "compare_by_bits": {"a": round(seg(cmp32) - 0.0, 4) if cmp32 else None, "b": 0.0,
                                    "points": [[32, seg(cmp32)]]},
                "lut_mul_by_width": linfit([w for w, s in lm if s], [seg(s) for w, s in lm if s])},
        "dsp48": {"comb_ns": seg(dsp0), "in_route_ns": seg(din), "mult_ns": seg(mult), "out_route_ns": seg(dout)},
        "bram": {"clk_to_out_ns": seg(b0), "clk_to_out_reg_ns": seg(b1)},
    }
    return model, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("calib", type=Path)
    ap.add_argument("--yaml", type=Path)
    a = ap.parse_args(argv)
    m, rows = fit(a.calib)
    out = {"model": m, "measurements": rows}
    text = yaml.safe_dump(out, sort_keys=False)
    if a.yaml:
        a.yaml.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
