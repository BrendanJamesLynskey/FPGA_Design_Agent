"""MMCM / PLL parameter search for Artix-7 -1 (brief 18, section 2b), the rule of the KB skill ``artix7-mmcm-pll-configuration``.

    python3 flow/mmcm_search.py 100 74.25                 # F_in then wanted outputs in MHz
    python3 flow/mmcm_search.py --pll 100 200 50
    python3 flow/mmcm_search.py --compare results/project_parity/clkwiz/clkwiz.jsonl

Search: for every D and M with the PFD and VCO in range, give each output its best divider O; rank by total frequency
error, then highest legal VCO, then smallest D (UG472 ch. 3, DS181 Tables 37 and 38; speed grade -1).
``--compare`` reads the Clocking Wizard's own answers (flow/clkwiz_probe.tcl) and prints both side by side.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

LIMITS = {
    "MMCM": dict(pfd=(10.0, 450.0), vco=(600.0, 1200.0), m=(2.0, 64.0), mstep=0.125, d=(1, 106), fout=(4.69, 800.0)),
    "PLL": dict(pfd=(19.0, 450.0), vco=(800.0, 1600.0), m=(2.0, 64.0), mstep=1.0, d=(1, 56), fout=(6.25, 800.0)),
}


def best_divider(vco: float, f: float, prim: str, first: bool) -> tuple[float, float] | None:
    """Best legal O for output ``f`` at ``vco`` (CLKOUT0 of an MMCM may be fractional in 1/8 steps from 2.0)."""
    cands = []
    base = vco / f
    if prim == "MMCM" and first:
        steps = [round(base * 8) / 8 + k / 8 for k in (-1, 0, 1)]
        cands = [o for o in steps if 2.0 <= o <= 128.0]
    else:
        cands = [float(o) for o in (int(base), int(base) + 1) if 1 <= o <= 128]
    if not cands:
        return None
    o = min(cands, key=lambda o: abs(vco / o - f))
    return o, vco / o


def search(fin: float, outs: list[float], prim: str = "MMCM") -> dict | None:
    lim = LIMITS[prim]
    best = None
    for d in range(lim["d"][0], lim["d"][1] + 1):
        pfd = fin / d
        if not lim["pfd"][0] <= pfd <= lim["pfd"][1]:
            continue
        n = int((lim["m"][1] - lim["m"][0]) / lim["mstep"]) + 1
        for i in range(n):
            m = lim["m"][0] + i * lim["mstep"]
            vco = pfd * m
            if not lim["vco"][0] <= vco <= lim["vco"][1]:
                continue
            divs = []
            for k, f in enumerate(outs):
                r = best_divider(vco, f, prim, k == 0)
                if r is None or not lim["fout"][0] <= r[1] <= lim["fout"][1]:
                    divs = None
                    break
                divs.append(r)
            if divs is None:
                continue
            err = sum(abs(a - f) for (_, a), f in zip(divs, outs))
            key = (round(err, 6), -vco, d)
            if best is None or key < best[0]:
                best = (key, dict(prim=prim, d=d, m=m, vco=vco, o=[o for o, _ in divs], f=[a for _, a in divs], err=err))
    return best[1] if best else None


def _num(row: dict, key: str, default=None):
    try:
        return float(row[key])
    except (KeyError, ValueError):
        return default


def wizard_row(row: dict) -> dict:
    """Reduce one jsonl row to the numbers the wizard chose (M, D, O per output, achieved F, jitter, phase error)."""
    prim = row["CONFIG.PRIMITIVE"] if "CONFIG.PRIMITIVE" in row else row["primitive"]
    n = len(row["req"].split(","))
    # the wizard keeps the chosen values in the MMCM_* properties whichever primitive is generated (measured)
    m = _num(row, "CONFIG.MMCM_CLKFBOUT_MULT_F")
    d = _num(row, "CONFIG.MMCM_DIVCLK_DIVIDE")
    o = [_num(row, "CONFIG.MMCM_CLKOUT0_DIVIDE_F")] + [_num(row, f"CONFIG.MMCM_CLKOUT{i}_DIVIDE") for i in range(1, n)]
    fin = float(row["fin"])
    vco = fin / d * m
    return dict(prim=prim, d=d, m=m, vco=vco, o=o, f=[vco / x for x in o],
                jitter=[_num(row, f"CONFIG.CLKOUT{i}_JITTER") for i in range(1, n + 1)],
                phase_error=[_num(row, f"CONFIG.CLKOUT{i}_PHASE_ERROR") for i in range(1, n + 1)])


def compare(path: str) -> list[dict]:
    rows = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("seterr"):
            rows.append(dict(name=r["name"], req=r["req"], wizard="rejected: " + re.sub(r"\s+", " ", r["seterr"]), hand=None))
            continue
        outs = [float(x) for x in r["req"].split(",")]
        w = wizard_row(r)
        h = search(float(r["fin"]), outs, "PLL" if r["primitive"] == "PLL" else "MMCM")
        rows.append(dict(name=r["name"], req=r["req"], wizard=w, hand=h))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pll", action="store_true")
    ap.add_argument("--compare")
    ap.add_argument("nums", nargs="*", type=float)
    a = ap.parse_args(argv)
    if a.compare:
        for r in compare(a.compare):
            print(json.dumps(r, indent=None))
        return 0
    if len(a.nums) < 2:
        ap.error("need F_in and at least one output")
    r = search(a.nums[0], a.nums[1:], "PLL" if a.pll else "MMCM")
    if r is None:
        print("no legal setting", file=sys.stderr)
        return 1
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
