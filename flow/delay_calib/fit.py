#!/usr/bin/env python3
"""Fit the per-family delay model from the calibration build's reports (flow/delay_calib/calib.tcl).

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


def clk_to_out(text: str, prim: str) -> tuple[float, float] | None:
    """(clock-to-out of the primitive's first output row, the route of the net after it) on the report's worst path."""
    blk = text.split("Slack", 2)[1] if "Slack" in text else ""
    m = re.search(rf"\(Prop_{prim}_CLK\w*_\w+(?:\[\d+\])?\)\s*\n?\s*(-?[0-9.]+)\s+[0-9.]+\s+[rf]?\s*\S+\s*\n\s+net \(fo=\d+[^)]*\)\s+([0-9.]+)", blk)
    return (float(m.group(1)), float(m.group(2))) if m else None


def min_period(text: str, prim: str) -> float | None:
    v = [float(m.group(1)) for m in re.finditer(rf"Min Period\s+n/a\s+{prim}/CLK\w*\s+n/a\s+([0-9.]+)", text)]
    return max(v) if v else None


def fit(d: Path, d2: Path | None = None) -> tuple[dict, list[dict]]:
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
    d2 = d2 or d
    ts = (d2 / "timing_summary.rpt").read_text() if (d2 / "timing_summary.rpt").is_file() else ""
    dsp_mp, bram_mp = min_period(ts, "DSP48E1"), min_period(ts, "RAMB18E1") or min_period(ts, "RAMB36E1")
    # report_timing does not report the register-to-register stages inside a DSP48E1: a fully pipelined slice is limited
    # by its minimum period (the pulse-width check), which is what an internal stage may use
    rows.append({"name": "dsp_min_period", "what": "DSP48E1 minimum period, fully pipelined (pulse-width check)", "stage_ns": dsp_mp})
    rows.append({"name": "bram_min_period", "what": "RAMB18E1 minimum period (pulse-width check)", "stage_ns": bram_mp})
    p_out = clk_to_out((d2 / "path_from_dsp.rpt").read_text(), "dsp48e1") if (d2 / "path_from_dsp.rpt").is_file() else None
    r_out = clk_to_out((d2 / "path_from_bram.rpt").read_text(), "ramb18e1") if (d2 / "path_from_bram.rpt").is_file() else None
    rows.append({"name": "dsp_preg_clk_to_p", "what": "DSP48E1 PREG clock to P, and the route of the net after it", "pair_ns": p_out})
    rows.append({"name": "bram_doreg_clk_to_do", "what": "RAMB18E1 with output register: clock to DO, and the route after it",
                 "pair_ns": r_out})
    mult = dsp_mp
    dout = None
    b0 = None
    b1 = None

    seg = lambda s: round(max(0.0, s - over), 3) if s is not None else None    # noqa: E731
    model = {
        "schema": "fpga-design-agent/delay-model/v1",
        "uncertainty_ns": unc,
        "ff": {"clk_to_q_ns": clk_q, "setup_ns": setup, "overhead_ns": over},
        "lut_level_ns": round(seg(mux) / 3, 3) if mux else None,      # mux16: LUT6 + MUXF7 + MUXF8, three levels
        "table_ns": seg(tab), "mux16_ns": seg(mux),
        "fit": {"add_by_bits": linfit([w for w, s in adds if s], [seg(s) for w, s in adds if s]),
                "compare_by_bits": {"a": round(seg(cmp32) - 0.0, 4) if cmp32 else None, "b": 0.0,
                                    "points": [[32, seg(cmp32)]]},
                "lut_mul_by_width": linfit([w for w, s in lm if s], [seg(s) for w, s in lm if s])},
        "dsp48": {"comb_ns": seg(dsp0), "in_route_ns": seg(din), "mult_ns": seg(mult), "madd_ns": seg(mult),
                  "out_route_ns": round(sum(p_out), 3) if p_out else None, "min_period_ns": dsp_mp},
        "bram": {"clk_to_out_reg_ns": round(sum(r_out), 3) if r_out else None, "clk_to_out_ns": None, "min_period_ns": bram_mp},
    }
    return model, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("calib", type=Path)
    ap.add_argument("calib2", type=Path, nargs="?", help="the second run (DSP/BRAM output paths, pulse-width checks)")
    ap.add_argument("--yaml", type=Path)
    a = ap.parse_args(argv)
    m, rows = fit(a.calib, a.calib2)
    out = {"model": m, "measurements": rows}
    text = yaml.safe_dump(out, sort_keys=False)
    if a.yaml:
        a.yaml.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
